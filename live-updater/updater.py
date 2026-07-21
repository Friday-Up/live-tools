"""Standalone Windows updater for Live Tools.

The updater is copied to the system temporary directory before it is launched,
so it can safely replace every file in the application directory.
"""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
import webbrowser
from zipfile import ZipFile


PRESERVED_TOP_LEVEL = {"runtime", "logs"}
BOOTSTRAP_FILES = {"启动直播工具.bat", "Live-Tools-Updater.exe"}
PRESERVED_FILES = (
    Path("live-sku-price-audit/jd_auth.json"),
    Path("product-selection-agent/model-config.local.json"),
    Path("关闭服务.bat"),
)
HEALTH_URL = "http://127.0.0.1:8080/api/health"
BACKUP_COMPLETE_MARKER = ".backup-complete"
UPDATE_TRANSACTION_NAME = "update-transaction.json"
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
WAIT_FAILED = 0xFFFFFFFF
ERROR_INVALID_PARAMETER = 87


def is_preserved_item(name: str) -> bool:
    return name in PRESERVED_TOP_LEVEL or name in BOOTSTRAP_FILES


def validate_wait_result(result: int, error_code: int = 0) -> None:
    if result == WAIT_OBJECT_0:
        return
    if result == WAIT_TIMEOUT:
        raise TimeoutError("等待旧程序退出超时")
    if result == WAIT_FAILED:
        formatter = getattr(ctypes, "FormatError", None)
        message = formatter(error_code) if formatter else os.strerror(error_code)
        raise OSError(error_code, message)
    raise OSError(f"等待旧程序退出时返回未知状态: {result}")


def wait_for_process(pid: int, timeout_seconds: int = 120) -> None:
    if os.name != "nt":
        return
    synchronize = 0x00100000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        error_code = kernel32.GetLastError()
        if error_code == ERROR_INVALID_PARAMETER:
            return
        formatter = getattr(ctypes, "FormatError", None)
        message = formatter(error_code) if formatter else os.strerror(error_code)
        raise OSError(error_code, message)
    try:
        result = kernel32.WaitForSingleObject(handle, timeout_seconds * 1000)
        error_code = kernel32.GetLastError() if result == WAIT_FAILED else 0
        validate_wait_result(result, error_code)
    finally:
        kernel32.CloseHandle(handle)


def safe_extract(package: Path, staging_dir: Path) -> None:
    staging_root = staging_dir.resolve()
    with ZipFile(package) as archive:
        for member in archive.infolist():
            target = (staging_dir / member.filename).resolve()
            try:
                target.relative_to(staging_root)
            except ValueError as exc:
                raise ValueError(f"更新包包含非法路径: {member.filename}") from exc
        archive.extractall(staging_dir)


def find_payload_root(staging_dir: Path) -> Path:
    direct = staging_dir / "Live-Tools-Web.exe"
    nested = staging_dir / "Live-Tools-Web" / "Live-Tools-Web.exe"
    if direct.is_file():
        return staging_dir
    if nested.is_file():
        return nested.parent
    matches = list(staging_dir.glob("*/Live-Tools-Web.exe"))
    if len(matches) == 1:
        return matches[0].parent
    raise ValueError("更新包中未找到 Live-Tools-Web.exe")


def read_preserved_files(install_dir: Path) -> dict[Path, bytes]:
    result = {}
    for relative_path in PRESERVED_FILES:
        path = install_dir / relative_path
        if path.is_file():
            result[relative_path] = path.read_bytes()
    return result


def restore_preserved_files(install_dir: Path, files: dict[Path, bytes]) -> None:
    for relative_path, content in files.items():
        path = install_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def move_current_install_to_backup(install_dir: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=False)
    for item in install_dir.iterdir():
        if is_preserved_item(item.name):
            continue
        shutil.move(str(item), str(backup_dir / item.name))
    (backup_dir / BACKUP_COMPLETE_MARKER).write_text("complete", encoding="utf-8")


def install_payload(payload_dir: Path, install_dir: Path) -> None:
    for item in payload_dir.iterdir():
        if is_preserved_item(item.name):
            continue
        destination = install_dir / item.name
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        shutil.move(str(item), str(destination))

    # Keep the launcher and updater available throughout the transaction, then
    # replace each of them atomically after the application payload is ready.
    for name in BOOTSTRAP_FILES:
        source = payload_dir / name
        if not source.is_file():
            raise ValueError(f"更新包缺少启动文件: {name}")
        destination = install_dir / name
        temporary = install_dir / f".{name}.update-new"
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    if not (install_dir / "Live-Tools-Web.exe").is_file():
        raise ValueError("新版主程序文件不存在")


def clear_replaceable_items(install_dir: Path) -> None:
    for item in install_dir.iterdir():
        if is_preserved_item(item.name):
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def restore_backup(install_dir: Path, backup_dir: Path) -> None:
    marker = backup_dir / BACKUP_COMPLETE_MARKER
    backup_items = [item for item in backup_dir.iterdir() if item.name != BACKUP_COMPLETE_MARKER]
    backup_names = {item.name for item in backup_items}

    # Only remove new-only files when the old installation was backed up in full.
    # For a partial backup, untouched old files must remain in place.
    if marker.is_file():
        for item in install_dir.iterdir():
            if not is_preserved_item(item.name) and item.name not in backup_names:
                remove_path(item)

    for item in backup_items:
        destination = install_dir / item.name
        remove_path(destination)
        shutil.move(str(item), str(destination))
    marker.unlink(missing_ok=True)
    try:
        backup_dir.rmdir()
    except OSError:
        pass


def write_update_transaction(
    transaction_file: Path,
    backup_dir: Path,
    expected_version: str,
    owner_pid: int | None = None,
) -> None:
    transaction_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = transaction_file.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            {
                "backup_dir": str(backup_dir),
                "expected_version": expected_version,
                "owner_pid": owner_pid,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, transaction_file)


def recover_interrupted_update(
    install_dir: Path,
    transaction_file: Path,
    log,
) -> None:
    if not transaction_file.is_file():
        return
    data = json.loads(transaction_file.read_text(encoding="utf-8"))
    owner_pid = int(data.get("owner_pid") or 0)
    if owner_pid and owner_pid != os.getpid():
        log("检测到更新进程仍在运行，正在等待更新结束")
        wait_for_process(owner_pid, timeout_seconds=180)
        if not transaction_file.is_file():
            log("更新进程已正常完成")
            return
        data = json.loads(transaction_file.read_text(encoding="utf-8"))
    backup_dir = Path(str(data.get("backup_dir", ""))).resolve()
    install_parent = install_dir.resolve().parent
    if backup_dir.parent != install_parent or not backup_dir.name.startswith(
        ".Live-Tools-Web-backup-"
    ):
        raise ValueError("更新恢复记录中的备份路径无效")
    expected_version = str(data.get("expected_version") or "").strip()
    if (
        expected_version
        and (install_dir / "Live-Tools-Web.exe").is_file()
        and get_running_version(install_dir) == expected_version
    ):
        # The updater may have been terminated after the new application became
        # healthy but before it committed the transaction. In that case the new
        # executable is still running and cannot safely be replaced on Windows;
        # its matching health version is sufficient to finish the commit.
        log("检测到新版本已正常运行，正在完成更新清理")
        transaction_file.unlink(missing_ok=True)
        shutil.rmtree(backup_dir, ignore_errors=True)
        log("更新恢复完成")
        return
    if backup_dir.is_dir():
        log("检测到未完成更新，正在恢复旧版本")
        restore_backup(install_dir, backup_dir)
    transaction_file.unlink(missing_ok=True)
    log("未完成更新已恢复")


def get_running_version(expected_install_dir: Path | None = None) -> str | None:
    try:
        with urlopen(HEALTH_URL, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and payload.get("success") is True:
                if expected_install_dir is not None:
                    reported_dir = str(payload.get("install_dir") or "").strip()
                    if not reported_dir or os.path.normcase(
                        str(Path(reported_dir).resolve())
                    ) != os.path.normcase(str(expected_install_dir.resolve())):
                        return None
                version = str(payload.get("version") or "").strip()
                return version or None
    except Exception:
        pass
    return None


def launch_application(install_dir: Path) -> subprocess.Popen:
    executable = install_dir / "Live-Tools-Web.exe"
    logs_dir = install_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = (logs_dir / "web.log").open("ab")
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [str(executable)],
        cwd=str(install_dir),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        close_fds=True,
        creationflags=creation_flags,
    )


def wait_for_health(
    process: subprocess.Popen,
    timeout_seconds: int = 45,
    expected_version: str | None = None,
    expected_install_dir: Path | None = None,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urlopen(HEALTH_URL, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if (
                    response.status == 200
                    and payload.get("success") is True
                    and (expected_version is None or payload.get("version") == expected_version)
                    and (
                        expected_install_dir is None
                        or (
                            payload.get("install_dir")
                            and os.path.normcase(
                                str(Path(str(payload["install_dir"])).resolve())
                            )
                            == os.path.normcase(str(expected_install_dir.resolve()))
                        )
                    )
                ):
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def update(package: Path, install_dir: Path, pid: int, expected_version: str, log) -> None:
    wait_for_process(pid)
    staging_dir: Path | None = None
    backup_dir = install_dir.parent / (
        f".Live-Tools-Web-backup-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )
    preserved_files: dict[Path, bytes] = {}
    transaction_file = install_dir / "runtime" / UPDATE_TRANSACTION_NAME
    moved_to_backup = False
    new_process: subprocess.Popen | None = None
    try:
        staging_dir = Path(tempfile.mkdtemp(prefix="live-tools-update-"))
        preserved_files = read_preserved_files(install_dir)
        log("正在解压更新包")
        safe_extract(package, staging_dir)
        payload_dir = find_payload_root(staging_dir)
        write_update_transaction(
            transaction_file,
            backup_dir,
            expected_version,
            owner_pid=os.getpid(),
        )
        log("正在备份当前版本")
        moved_to_backup = True
        move_current_install_to_backup(install_dir, backup_dir)
        log("正在安装新版本")
        install_payload(payload_dir, install_dir)
        restore_preserved_files(install_dir, preserved_files)
        new_process = launch_application(install_dir)
        log("正在验证新版本启动状态")
        if not wait_for_health(
            new_process,
            expected_version=expected_version,
            expected_install_dir=install_dir,
        ):
            raise RuntimeError("新版本启动失败")
        log("更新完成")
        transaction_file.unlink(missing_ok=True)
        shutil.rmtree(backup_dir, ignore_errors=True)
        package.unlink(missing_ok=True)
        webbrowser.open("http://127.0.0.1:8080")
    except Exception:
        if new_process is not None:
            terminate_process(new_process)
        if moved_to_backup and backup_dir.exists():
            log("更新失败，正在恢复旧版本")
            restore_backup(install_dir, backup_dir)
            restore_preserved_files(install_dir, preserved_files)
        transaction_file.unlink(missing_ok=True)
        if (install_dir / "Live-Tools-Web.exe").is_file():
            old_process = launch_application(install_dir)
            if wait_for_health(old_process, timeout_seconds=30):
                webbrowser.open("http://127.0.0.1:8080")
        raise
    finally:
        if staging_dir is not None:
            shutil.rmtree(staging_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package")
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--version")
    parser.add_argument("--ready-file")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--transaction-file")
    args = parser.parse_args()

    log_path = Path(tempfile.gettempdir()) / "Live-Tools-Updater.log"
    with log_path.open("a", encoding="utf-8") as log_file:
        def log(message: str) -> None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_file.write(f"[{timestamp}] {message}\n")
            log_file.flush()

        try:
            if args.recover:
                if not args.transaction_file:
                    parser.error("--recover requires --transaction-file")
                recover_interrupted_update(
                    Path(args.install_dir).resolve(),
                    Path(args.transaction_file).resolve(),
                    log,
                )
                return 0
            if not all((args.package, args.pid, args.version, args.ready_file)):
                parser.error("normal update requires package, pid, version and ready-file")
            log(f"开始安装版本 {args.version}")
            ready_file = Path(args.ready_file)
            ready_file.parent.mkdir(parents=True, exist_ok=True)
            ready_file.write_text(str(os.getpid()), encoding="utf-8")
            update(
                Path(args.package),
                Path(args.install_dir).resolve(),
                args.pid,
                args.version,
                log,
            )
            return 0
        except Exception as exc:
            log(f"更新失败: {exc}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
