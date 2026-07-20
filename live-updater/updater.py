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
PRESERVED_FILES = (
    Path("live-sku-price-audit/jd_auth.json"),
    Path("product-selection-agent/model-config.local.json"),
    Path("关闭服务.bat"),
)
HEALTH_URL = "http://127.0.0.1:8080/api/health"
BACKUP_COMPLETE_MARKER = ".backup-complete"


def wait_for_process(pid: int, timeout_seconds: int = 120) -> None:
    if os.name != "nt":
        return
    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return
    try:
        result = ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_seconds * 1000)
        if result == 0x00000102:
            raise TimeoutError("等待旧程序退出超时")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


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
        if item.name in PRESERVED_TOP_LEVEL:
            continue
        shutil.move(str(item), str(backup_dir / item.name))
    (backup_dir / BACKUP_COMPLETE_MARKER).write_text("complete", encoding="utf-8")


def install_payload(payload_dir: Path, install_dir: Path) -> None:
    for item in payload_dir.iterdir():
        if item.name in PRESERVED_TOP_LEVEL:
            continue
        destination = install_dir / item.name
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        shutil.move(str(item), str(destination))
    if not (install_dir / "Live-Tools-Web.exe").is_file():
        raise ValueError("新版主程序文件不存在")


def clear_replaceable_items(install_dir: Path) -> None:
    for item in install_dir.iterdir():
        if item.name in PRESERVED_TOP_LEVEL:
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
            if item.name not in PRESERVED_TOP_LEVEL and item.name not in backup_names:
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
                ):
                    return True
        except Exception:
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
    moved_to_backup = False
    new_process: subprocess.Popen | None = None
    try:
        staging_dir = Path(tempfile.mkdtemp(prefix="live-tools-update-"))
        preserved_files = read_preserved_files(install_dir)
        log("正在解压更新包")
        safe_extract(package, staging_dir)
        payload_dir = find_payload_root(staging_dir)
        log("正在备份当前版本")
        moved_to_backup = True
        move_current_install_to_backup(install_dir, backup_dir)
        log("正在安装新版本")
        install_payload(payload_dir, install_dir)
        restore_preserved_files(install_dir, preserved_files)
        new_process = launch_application(install_dir)
        log("正在验证新版本启动状态")
        if not wait_for_health(new_process, expected_version=expected_version):
            raise RuntimeError("新版本启动失败")
        log("更新完成")
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
    parser.add_argument("--package", required=True)
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--version", required=True)
    parser.add_argument("--ready-file", required=True)
    args = parser.parse_args()

    log_path = Path(tempfile.gettempdir()) / "Live-Tools-Updater.log"
    with log_path.open("a", encoding="utf-8") as log_file:
        def log(message: str) -> None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_file.write(f"[{timestamp}] {message}\n")
            log_file.flush()

        try:
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
