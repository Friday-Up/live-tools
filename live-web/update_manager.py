"""Background update download support for the packaged Windows application."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid


DEFAULT_MANIFEST_URL = (
    "https://github.com/Friday-Up/live-tools/releases/latest/download/"
    "live-tools-update.json"
)
_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
MANIFEST_CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def parse_version(value: str) -> tuple[int, int, int]:
    match = _VERSION_PATTERN.fullmatch((value or "").strip())
    if not match:
        raise ValueError(f"无效版本号: {value}")
    return tuple(int(part) for part in match.groups())


class UpdateManager:
    """Owns update state and performs resumable downloads in worker threads."""

    def __init__(
        self,
        current_version: str,
        install_dir: str | Path,
        *,
        enabled: bool,
        manifest_url: str = DEFAULT_MANIFEST_URL,
        updater_name: str = "Live-Tools-Updater.exe",
        timeout_seconds: float = 15.0,
    ):
        self.current_version = current_version
        self.install_dir = Path(install_dir).resolve()
        self.enabled = bool(enabled)
        self.manifest_url = manifest_url
        self.updater_path = self.install_dir / updater_name
        self.timeout_seconds = timeout_seconds
        self.update_dir = self.install_dir / "runtime" / "update"
        self.manifest_cache_path = self.update_dir / "manifest-cache.json"
        self._lock = threading.Lock()
        self._checking = False
        self._manifest: dict | None = None
        self._package_path: Path | None = None
        self._state = {
            "supported": self.enabled,
            "stage": "idle" if self.enabled else "unsupported",
            "current_version": self.current_version,
            "latest_version": None,
            "release_url": None,
            "notes": "",
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "progress": 0,
            "error": None,
            "checking": False,
            "check_error": None,
            "last_checked_at": None,
        }
        if self.enabled:
            self._restore_cached_manifest()

    def status(self) -> dict:
        with self._lock:
            return dict(self._state)

    def _update_state(self, **values) -> None:
        with self._lock:
            self._state.update(values)

    def start_check(self) -> dict:
        if not self.enabled:
            return self.status()
        with self._lock:
            if self._checking or self._state["stage"] in {
                "downloading",
                "ready",
                "installing",
            }:
                return dict(self._state)
            self._checking = True
            values = {"checking": True, "check_error": None}
            if self._manifest is None:
                values.update(stage="checking", error=None)
            self._state.update(**values)
        threading.Thread(target=self._check_worker, daemon=True).start()
        return self.status()

    def _check_worker(self) -> None:
        try:
            manifest = None
            last_error: Exception | None = None
            for attempt in range(4):
                try:
                    request = Request(
                        self.manifest_url,
                        headers={"User-Agent": f"Live-Tools/{self.current_version}"},
                    )
                    with urlopen(request, timeout=self.timeout_seconds) as response:
                        manifest = json.loads(response.read().decode("utf-8"))
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 3:
                        time.sleep(min(2 ** attempt, 4))
            if last_error is not None or manifest is None:
                raise last_error or RuntimeError("未读取到更新清单")
            manifest = self._validate_manifest(manifest)
            latest_version = manifest["version"]
            common = {
                "latest_version": latest_version,
                "release_url": manifest.get("release_url"),
                "notes": manifest.get("notes", ""),
                "error": None,
            }
            update_available = parse_version(latest_version) > parse_version(
                self.current_version
            )
            if update_available:
                try:
                    self._save_cached_manifest(manifest)
                except OSError:
                    # A read-only or temporarily locked cache must not hide a
                    # valid update that was already fetched from the network.
                    pass
            else:
                self._discard_cached_manifest()
            with self._lock:
                self._checking = False
                if update_available:
                    self._manifest = manifest
                    self._state.update(
                        stage="available",
                        checking=False,
                        check_error=None,
                        last_checked_at=int(time.time()),
                        **common,
                    )
                else:
                    self._manifest = None
                    self._package_path = None
                    self._state.update(
                        stage="up_to_date",
                        checking=False,
                        check_error=None,
                        last_checked_at=int(time.time()),
                        **common,
                    )
        except Exception as exc:
            message = f"检查更新失败: {exc}"
            with self._lock:
                self._checking = False
                self._state.update(
                    checking=False,
                    check_error=message,
                    last_checked_at=int(time.time()),
                )
                if self._manifest is None:
                    self._state.update(stage="error", error=message)

    def _restore_cached_manifest(self) -> None:
        try:
            payload = json.loads(self.manifest_cache_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("更新缓存格式错误")
            cached_at = int(payload.get("cached_at") or 0)
            if (
                cached_at <= 0
                or time.time() - cached_at > MANIFEST_CACHE_MAX_AGE_SECONDS
            ):
                self._discard_cached_manifest()
                return
            manifest = self._validate_manifest(payload.get("manifest"))
            if parse_version(manifest["version"]) <= parse_version(self.current_version):
                self._discard_cached_manifest()
                return
            self._manifest = manifest
            self._state.update(
                stage="available",
                latest_version=manifest["version"],
                release_url=manifest.get("release_url"),
                notes=manifest.get("notes", ""),
                error=None,
                last_checked_at=cached_at,
            )
        except FileNotFoundError:
            return
        except Exception:
            self._discard_cached_manifest()

    def _save_cached_manifest(self, manifest: dict) -> None:
        self.update_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_cache_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                {"cached_at": int(time.time()), "manifest": manifest},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.manifest_cache_path)

    def _discard_cached_manifest(self) -> None:
        try:
            self.manifest_cache_path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _validate_manifest(manifest: object) -> dict:
        if not isinstance(manifest, dict):
            raise ValueError("更新清单格式错误")
        version = str(manifest.get("version", "")).strip().lstrip("v")
        parse_version(version)
        asset_url = str(manifest.get("asset_url", "")).strip()
        if not asset_url.startswith("https://"):
            raise ValueError("更新包地址必须使用 HTTPS")
        sha256 = str(manifest.get("sha256", "")).strip().lower()
        if not _SHA256_PATTERN.fullmatch(sha256):
            raise ValueError("更新包缺少有效的 SHA256")
        result = dict(manifest)
        result.update(version=version, asset_url=asset_url, sha256=sha256)
        return result

    def start_download(self) -> dict:
        if not self.enabled:
            raise RuntimeError("当前运行方式不支持自动更新")
        with self._lock:
            if self._checking:
                raise RuntimeError("正在检查更新，请稍候")
            if self._state["stage"] == "downloading":
                return dict(self._state)
            if self._state["stage"] == "ready":
                return dict(self._state)
            if not self._manifest or self._state["stage"] not in {"available", "error"}:
                raise RuntimeError("请先检查更新")
            self._state.update(stage="downloading", error=None)
        threading.Thread(target=self._download_worker, daemon=True).start()
        return self.status()

    def _download_worker(self) -> None:
        with self._lock:
            assert self._manifest is not None
            manifest = dict(self._manifest)
        version = manifest["version"]
        self.update_dir.mkdir(parents=True, exist_ok=True)
        target = self.update_dir / f"Live-Tools-Windows-{version}.zip"
        partial = target.with_suffix(".zip.part")
        try:
            if target.is_file() and self._sha256(target) == manifest["sha256"]:
                self._package_path = target
                size = target.stat().st_size
                self._update_state(
                    stage="ready",
                    downloaded_bytes=size,
                    total_bytes=size,
                    progress=100,
                    error=None,
                )
                return

            last_error: Exception | None = None
            for attempt in range(4):
                try:
                    self._download_once(manifest["asset_url"], partial)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 3:
                        time.sleep(min(2 ** attempt, 4))
            if last_error is not None:
                raise last_error

            if self._sha256(partial) != manifest["sha256"]:
                partial.unlink(missing_ok=True)
                raise ValueError("更新包校验失败，请重新下载")
            partial.replace(target)
            self._package_path = target
            size = target.stat().st_size
            self._update_state(
                stage="ready",
                downloaded_bytes=size,
                total_bytes=size,
                progress=100,
                error=None,
            )
        except Exception as exc:
            self._update_state(stage="error", error=f"下载更新失败: {exc}")

    def _download_once(self, url: str, partial: Path) -> None:
        existing_size = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": f"Live-Tools/{self.current_version}"}
        if existing_size:
            headers["Range"] = f"bytes={existing_size}-"
        request = Request(url, headers=headers)
        try:
            response = urlopen(request, timeout=self.timeout_seconds)
        except HTTPError as exc:
            if exc.code == 416 and partial.exists():
                return
            raise

        with response:
            resumed = response.status == 206 and existing_size > 0
            if resumed:
                range_start = self._content_range_start(
                    response.headers.get("Content-Range", "")
                )
                if range_start != existing_size:
                    partial.unlink(missing_ok=True)
                    raise OSError("服务器返回的断点位置不一致，将重新下载")
            if not resumed:
                existing_size = 0
            content_range = response.headers.get("Content-Range", "")
            total_size = self._content_range_total(content_range)
            if total_size is None:
                remaining = int(response.headers.get("Content-Length", "0") or 0)
                total_size = existing_size + remaining if remaining else 0
            mode = "ab" if resumed else "wb"
            downloaded = existing_size
            self._update_progress(downloaded, total_size)
            with partial.open(mode) as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    self._update_progress(downloaded, total_size)
            if total_size and downloaded != total_size:
                raise OSError(
                    f"更新包传输不完整: 已下载 {downloaded} 字节，应为 {total_size} 字节"
                )

    def _update_progress(self, downloaded: int, total: int) -> None:
        progress = int(downloaded * 100 / total) if total else 0
        self._update_state(
            downloaded_bytes=downloaded,
            total_bytes=total,
            progress=max(0, min(progress, 100)),
        )

    @staticmethod
    def _content_range_total(value: str) -> int | None:
        match = re.search(r"/(\d+)$", value or "")
        return int(match.group(1)) if match else None

    @staticmethod
    def _content_range_start(value: str) -> int | None:
        match = re.match(r"^bytes\s+(\d+)-\d+/", value or "", re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def launch_installer(self, pid: int) -> dict:
        if os.name != "nt" or not self.enabled:
            raise RuntimeError("自动安装仅支持 Windows 打包版本")
        with self._lock:
            if self._state["stage"] != "ready" or self._package_path is None:
                raise RuntimeError("更新包尚未下载完成")
            package_path = self._package_path
            version = self._state["latest_version"]
        if not self.updater_path.is_file():
            raise RuntimeError("更新器不存在，请重新下载完整安装包")

        temporary_dir = Path(tempfile.gettempdir())
        self._cleanup_stale_updater_copies(temporary_dir)
        launch_id = uuid.uuid4().hex
        temporary_updater = temporary_dir / f"Live-Tools-Updater-{launch_id}.exe"
        ready_file = temporary_dir / f"Live-Tools-Updater-{launch_id}.ready"
        shutil.copy2(self.updater_path, temporary_updater)
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        updater_process = subprocess.Popen(
            [
                str(temporary_updater),
                "--package",
                str(package_path),
                "--install-dir",
                str(self.install_dir),
                "--pid",
                str(pid),
                "--version",
                str(version),
                "--ready-file",
                str(ready_file),
            ],
            cwd=str(self.install_dir.parent),
            close_fds=True,
            creationflags=creation_flags,
        )
        try:
            self._wait_for_updater_ready(updater_process, ready_file)
        finally:
            ready_file.unlink(missing_ok=True)
        self._update_state(stage="installing", error=None)
        return self.status()

    @staticmethod
    def _wait_for_updater_ready(process, ready_file: Path, timeout_seconds: float = 20.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if ready_file.is_file():
                return
            if process.poll() is not None:
                raise RuntimeError("更新器启动失败，当前程序将继续运行")
            time.sleep(0.1)
        try:
            process.terminate()
        except Exception:
            pass
        raise RuntimeError("更新器启动超时，当前程序将继续运行")

    @staticmethod
    def _cleanup_stale_updater_copies(temporary_dir: Path) -> None:
        for path in temporary_dir.glob("Live-Tools-Updater-*.exe"):
            try:
                path.unlink()
            except OSError:
                pass
