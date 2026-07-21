import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from update_manager import MANIFEST_CACHE_MAX_AGE_SECONDS, UpdateManager, parse_version


class FakeResponse:
    def __init__(self, content: bytes, *, status=200, headers=None):
        self._stream = io.BytesIO(content)
        self.status = status
        self.headers = headers or {}

    def read(self, size=-1):
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def wait_for_stage(manager, stages, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = manager.status()
        if state["stage"] in stages:
            return state
        time.sleep(0.01)
    raise AssertionError(f"更新状态未结束: {manager.status()}")


def wait_for_check(manager, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = manager.status()
        if not state["checking"]:
            return state
        time.sleep(0.01)
    raise AssertionError(f"更新检查未结束: {manager.status()}")


class UpdateManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = UpdateManager(
            "0.5.0",
            self.temp_dir,
            enabled=True,
            manifest_url="https://example.test/live-tools-update.json",
        )

    def test_semver_comparison_uses_numeric_parts(self):
        self.assertGreater(parse_version("v0.10.0"), parse_version("0.9.9"))

    def test_check_reports_new_release(self):
        manifest = {
            "version": "0.5.1",
            "asset_url": "https://example.test/Live-Tools-Windows.zip",
            "sha256": "a" * 64,
            "release_url": "https://example.test/releases/v0.5.1",
        }
        response = FakeResponse(json.dumps(manifest).encode("utf-8"))
        with patch("update_manager.urlopen", return_value=response):
            state = self.manager.start_check()
            self.assertIn(state["stage"], {"checking", "available"})
            state = wait_for_stage(self.manager, {"available", "error"})

        self.assertEqual(state["stage"], "available")
        self.assertEqual(state["latest_version"], "0.5.1")
        self.assertTrue(self.manager.manifest_cache_path.is_file())

    def test_cache_write_failure_does_not_hide_fetched_update(self):
        manifest = {
            "version": "0.5.1",
            "asset_url": "https://example.test/Live-Tools-Windows.zip",
            "sha256": "a" * 64,
        }
        response = FakeResponse(json.dumps(manifest).encode("utf-8"))

        with patch("update_manager.urlopen", return_value=response), patch.object(
            self.manager,
            "_save_cached_manifest",
            side_effect=PermissionError("locked"),
        ):
            self.manager.start_check()
            state = wait_for_check(self.manager)

        self.assertEqual(state["stage"], "available")
        self.assertEqual(state["latest_version"], "0.5.1")

    def test_check_retries_transient_manifest_failures(self):
        manifest = {
            "version": "0.5.1",
            "asset_url": "https://example.test/Live-Tools-Windows.zip",
            "sha256": "a" * 64,
        }
        response = FakeResponse(json.dumps(manifest).encode("utf-8"))
        with patch(
            "update_manager.urlopen",
            side_effect=[TimeoutError("slow"), TimeoutError("slow"), response],
        ) as mocked, patch("update_manager.time.sleep"):
            self.manager.start_check()
            state = wait_for_stage(self.manager, {"available", "error"})

        self.assertEqual(state["stage"], "available")
        self.assertEqual(mocked.call_count, 3)

    def test_failed_refresh_keeps_last_valid_manifest_available(self):
        self.manager._manifest = {
            "version": "0.5.1",
            "asset_url": "https://example.test/old.zip",
            "sha256": "a" * 64,
        }
        self.manager._update_state(
            stage="available",
            latest_version="0.5.1",
            release_url="https://example.test/old",
        )

        with patch("update_manager.urlopen", side_effect=TimeoutError("offline")), patch(
            "update_manager.time.sleep"
        ):
            checking_state = self.manager.start_check()
            self.assertEqual(checking_state["stage"], "available")
            state = wait_for_check(self.manager)

        self.assertEqual(state["stage"], "available")
        self.assertEqual(state["latest_version"], "0.5.1")
        self.assertEqual(state["release_url"], "https://example.test/old")
        self.assertIn("offline", state["check_error"])

    def test_cached_manifest_survives_manager_restart(self):
        manifest = {
            "version": "0.5.1",
            "asset_url": "https://example.test/Live-Tools-Windows.zip",
            "sha256": "a" * 64,
            "release_url": "https://example.test/releases/v0.5.1",
        }
        self.manager._save_cached_manifest(manifest)

        restarted = UpdateManager(
            "0.5.0",
            self.temp_dir,
            enabled=True,
            manifest_url="https://example.test/live-tools-update.json",
        )

        state = restarted.status()
        self.assertEqual(state["stage"], "available")
        self.assertEqual(state["latest_version"], "0.5.1")
        self.assertEqual(state["release_url"], manifest["release_url"])

    def test_cache_for_installed_version_is_discarded(self):
        manifest = {
            "version": "0.5.0",
            "asset_url": "https://example.test/Live-Tools-Windows.zip",
            "sha256": "a" * 64,
        }
        self.manager._save_cached_manifest(manifest)

        restarted = UpdateManager(
            "0.5.0",
            self.temp_dir,
            enabled=True,
            manifest_url="https://example.test/live-tools-update.json",
        )

        self.assertEqual(restarted.status()["stage"], "idle")
        self.assertFalse(restarted.manifest_cache_path.exists())

    def test_expired_manifest_cache_is_discarded(self):
        manifest = {
            "version": "0.5.1",
            "asset_url": "https://example.test/Live-Tools-Windows.zip",
            "sha256": "a" * 64,
        }
        with patch("update_manager.time.time", return_value=1000):
            self.manager._save_cached_manifest(manifest)

        with patch(
            "update_manager.time.time",
            return_value=1000 + MANIFEST_CACHE_MAX_AGE_SECONDS + 1,
        ):
            restarted = UpdateManager(
                "0.5.0",
                self.temp_dir,
                enabled=True,
                manifest_url="https://example.test/live-tools-update.json",
            )

        self.assertEqual(restarted.status()["stage"], "idle")
        self.assertFalse(restarted.manifest_cache_path.exists())

    def test_fresh_check_without_update_clears_cached_release(self):
        cached_manifest = {
            "version": "0.5.1",
            "asset_url": "https://example.test/Live-Tools-Windows.zip",
            "sha256": "a" * 64,
        }
        self.manager._save_cached_manifest(cached_manifest)
        restarted = UpdateManager(
            "0.5.0",
            self.temp_dir,
            enabled=True,
            manifest_url="https://example.test/live-tools-update.json",
        )
        current_manifest = {
            "version": "0.5.0",
            "asset_url": "https://example.test/Live-Tools-Windows.zip",
            "sha256": "b" * 64,
        }

        with patch(
            "update_manager.urlopen",
            return_value=FakeResponse(json.dumps(current_manifest).encode("utf-8")),
        ):
            restarted.start_check()
            state = wait_for_check(restarted)

        self.assertEqual(state["stage"], "up_to_date")
        self.assertIsNone(restarted._manifest)
        self.assertFalse(restarted.manifest_cache_path.exists())

    def test_download_waits_for_refresh_to_finish(self):
        self.manager._manifest = {
            "version": "0.5.1",
            "asset_url": "https://example.test/Live-Tools-Windows.zip",
            "sha256": "a" * 64,
        }
        self.manager._update_state(stage="available", latest_version="0.5.1")
        self.manager._checking = True

        with self.assertRaisesRegex(RuntimeError, "正在检查更新"):
            self.manager.start_download()

    def test_download_runs_in_background_and_verifies_sha256(self):
        content = b"test update package"
        self.manager._manifest = {
            "version": "0.5.1",
            "asset_url": "https://example.test/Live-Tools-Windows.zip",
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        self.manager._update_state(stage="available", latest_version="0.5.1")

        def write_package(_url, partial):
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_bytes(content)
            self.manager._update_progress(len(content), len(content))

        with patch.object(self.manager, "_download_once", side_effect=write_package):
            state = self.manager.start_download()
            self.assertEqual(state["stage"], "downloading")
            state = wait_for_stage(self.manager, {"ready", "error"})

        self.assertEqual(state["stage"], "ready")
        self.assertEqual(state["progress"], 100)

    def test_resumable_download_appends_partial_content(self):
        partial = self.temp_dir / "package.part"
        partial.write_bytes(b"first-")
        response = FakeResponse(
            b"second",
            status=206,
            headers={"Content-Range": "bytes 6-11/12", "Content-Length": "6"},
        )
        with patch("update_manager.urlopen", return_value=response) as mocked:
            self.manager._download_once("https://example.test/package.zip", partial)

        self.assertEqual(partial.read_bytes(), b"first-second")
        self.assertEqual(mocked.call_args.args[0].headers["Range"], "bytes=6-")

    def test_incomplete_response_is_kept_for_next_resume(self):
        partial = self.temp_dir / "package.part"
        response = FakeResponse(
            b"short",
            status=200,
            headers={"Content-Length": "10"},
        )
        with patch("update_manager.urlopen", return_value=response):
            with self.assertRaisesRegex(OSError, "传输不完整"):
                self.manager._download_once("https://example.test/package.zip", partial)

        self.assertEqual(partial.read_bytes(), b"short")

    def test_mismatched_resume_range_restarts_on_next_attempt(self):
        partial = self.temp_dir / "package.part"
        partial.write_bytes(b"first-")
        response = FakeResponse(
            b"wrong",
            status=206,
            headers={"Content-Range": "bytes 3-7/8", "Content-Length": "5"},
        )
        with patch("update_manager.urlopen", return_value=response):
            with self.assertRaisesRegex(OSError, "断点位置"):
                self.manager._download_once("https://example.test/package.zip", partial)

        self.assertFalse(partial.exists())

    def test_manifest_allows_trusted_internal_http_and_rejects_other_http(self):
        manifest = self.manager._validate_manifest(
            {
                "version": "0.5.1",
                "asset_url": "http://stock.seifallspark.com/temp/aiTools/Live-Tools-Windows-v0.5.1.zip",
                "sha256": "a" * 64,
            }
        )
        self.assertEqual(
            manifest["asset_url"],
            "http://stock.seifallspark.com/temp/aiTools/Live-Tools-Windows-v0.5.1.zip",
        )

        with self.assertRaisesRegex(ValueError, "指定的内部更新地址"):
            self.manager._validate_manifest(
                {"version": "0.5.1", "asset_url": "http://example.test/a.zip", "sha256": "a" * 64}
            )

    def test_check_rejects_untrusted_http_manifest_url(self):
        manager = UpdateManager(
            "0.5.0",
            self.temp_dir,
            enabled=True,
            manifest_url="http://example.test/live-tools-update.json",
        )

        manager.start_check()
        state = wait_for_check(manager)

        self.assertEqual(state["stage"], "error")
        self.assertIn("指定的内部更新地址", state["check_error"])

    def test_updater_ready_handshake_rejects_early_process_exit(self):
        class ExitedProcess:
            def poll(self):
                return 1

        with self.assertRaisesRegex(RuntimeError, "启动失败"):
            self.manager._wait_for_updater_ready(
                ExitedProcess(),
                self.temp_dir / "missing.ready",
            )

    def test_stale_temporary_updaters_are_cleaned(self):
        stale = self.temp_dir / "Live-Tools-Updater-old.exe"
        unrelated = self.temp_dir / "keep.exe"
        stale.write_bytes(b"old")
        unrelated.write_bytes(b"keep")

        self.manager._cleanup_stale_updater_copies(self.temp_dir)

        self.assertFalse(stale.exists())
        self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
