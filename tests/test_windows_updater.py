import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import shutil


LIVE_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "live_tools_updater",
    LIVE_ROOT / "live-updater" / "updater.py",
)
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class WindowsUpdaterTest(unittest.TestCase):
    def test_extract_rejects_zip_path_traversal(self):
        root = Path(tempfile.mkdtemp())
        package = root / "bad.zip"
        with ZipFile(package, "w") as archive:
            archive.writestr("../outside.txt", "bad")

        with self.assertRaisesRegex(ValueError, "非法路径"):
            updater.safe_extract(package, root / "staging")

    def test_replace_preserves_runtime_and_local_config(self):
        root = Path(tempfile.mkdtemp())
        install_dir = root / "Live-Tools-Web"
        payload_dir = root / "payload"
        backup_dir = root / "backup"
        (install_dir / "runtime").mkdir(parents=True)
        (install_dir / "runtime" / "business.xlsx").write_text("data", encoding="utf-8")
        (install_dir / "product-selection-agent").mkdir()
        (install_dir / "product-selection-agent" / "model-config.local.json").write_text(
            "local", encoding="utf-8"
        )
        (install_dir / "Live-Tools-Web.exe").write_text("old", encoding="utf-8")
        (install_dir / "Live-Tools-Updater.exe").write_text("old-updater", encoding="utf-8")
        (install_dir / "启动直播工具.bat").write_text("old-launcher", encoding="utf-8")
        (payload_dir / "product-selection-agent").mkdir(parents=True)
        (payload_dir / "product-selection-agent" / "package.py").write_text("new", encoding="utf-8")
        (payload_dir / "Live-Tools-Web.exe").write_text("new", encoding="utf-8")
        (payload_dir / "Live-Tools-Updater.exe").write_text("new-updater", encoding="utf-8")
        (payload_dir / "启动直播工具.bat").write_text("new-launcher", encoding="utf-8")

        preserved = updater.read_preserved_files(install_dir)
        updater.move_current_install_to_backup(install_dir, backup_dir)
        updater.install_payload(payload_dir, install_dir)
        updater.restore_preserved_files(install_dir, preserved)

        self.assertEqual((install_dir / "Live-Tools-Web.exe").read_text(), "new")
        self.assertEqual((install_dir / "Live-Tools-Updater.exe").read_text(), "new-updater")
        self.assertEqual((install_dir / "runtime" / "business.xlsx").read_text(), "data")
        self.assertEqual(
            (install_dir / "product-selection-agent" / "model-config.local.json").read_text(),
            "local",
        )

        updater.restore_backup(install_dir, backup_dir)
        self.assertEqual((install_dir / "Live-Tools-Web.exe").read_text(), "old")
        self.assertEqual((install_dir / "runtime" / "business.xlsx").read_text(), "data")

    def test_partial_backup_failure_restores_every_old_file(self):
        root = Path(tempfile.mkdtemp())
        install_dir = root / "Live-Tools-Web"
        backup_dir = root / "backup"
        install_dir.mkdir()
        for name in ("a.txt", "b.txt", "c.txt"):
            (install_dir / name).write_text(name, encoding="utf-8")

        real_move = shutil.move
        move_count = 0

        def fail_second_move(source, destination):
            nonlocal move_count
            move_count += 1
            if move_count == 2:
                raise PermissionError("simulated Windows file lock")
            return real_move(source, destination)

        with self.assertRaises(PermissionError):
            with patch.object(updater.shutil, "move", side_effect=fail_second_move):
                updater.move_current_install_to_backup(install_dir, backup_dir)

        updater.restore_backup(install_dir, backup_dir)
        self.assertEqual(
            sorted(path.name for path in install_dir.iterdir()),
            ["a.txt", "b.txt", "c.txt"],
        )

    def test_startup_recovery_restores_interrupted_transaction(self):
        root = Path(tempfile.mkdtemp())
        install_dir = root / "Live-Tools-Web"
        backup_dir = root / ".Live-Tools-Web-backup-test"
        transaction_file = install_dir / "runtime" / updater.UPDATE_TRANSACTION_NAME
        (install_dir / "runtime").mkdir(parents=True)
        (install_dir / "Live-Tools-Web.exe").write_text("old", encoding="utf-8")

        updater.write_update_transaction(transaction_file, backup_dir, "0.5.1")
        updater.move_current_install_to_backup(install_dir, backup_dir)
        (install_dir / "Live-Tools-Web.exe").write_text("partial-new", encoding="utf-8")

        updater.recover_interrupted_update(install_dir, transaction_file, lambda _message: None)

        self.assertEqual((install_dir / "Live-Tools-Web.exe").read_text(), "old")
        self.assertFalse(transaction_file.exists())
        self.assertFalse(backup_dir.exists())

    def test_wait_result_rejects_timeout_and_api_failure(self):
        with self.assertRaises(TimeoutError):
            updater.validate_wait_result(updater.WAIT_TIMEOUT)
        with self.assertRaises(OSError):
            updater.validate_wait_result(updater.WAIT_FAILED, 5)

    def test_health_wait_does_not_busy_loop_on_wrong_running_version(self):
        class Process:
            def __init__(self):
                self.poll_count = 0

            def poll(self):
                self.poll_count += 1
                return None if self.poll_count == 1 else 1

        class Response:
            status = 200

            def __init__(self):
                self.body = io.BytesIO(
                    json.dumps({"success": True, "version": "0.5.0"}).encode()
                )

            def read(self):
                return self.body.read()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with patch.object(updater, "urlopen", return_value=Response()), patch.object(
            updater.time, "sleep"
        ) as sleep:
            healthy = updater.wait_for_health(Process(), expected_version="0.5.1")

        self.assertFalse(healthy)
        sleep.assert_called_once_with(1)

    def test_recovery_waits_for_live_update_owner(self):
        root = Path(tempfile.mkdtemp())
        install_dir = root / "Live-Tools-Web"
        transaction_file = install_dir / "runtime" / updater.UPDATE_TRANSACTION_NAME
        updater.write_update_transaction(
            transaction_file,
            root / ".Live-Tools-Web-backup-test",
            "0.5.1",
            owner_pid=12345,
        )

        def finish_update(_pid, timeout_seconds):
            self.assertEqual(timeout_seconds, 180)
            transaction_file.unlink()

        with patch.object(updater, "wait_for_process", side_effect=finish_update) as mocked:
            updater.recover_interrupted_update(
                install_dir,
                transaction_file,
                lambda _message: None,
            )

        mocked.assert_called_once()

    def test_recovery_commits_when_expected_new_version_is_already_healthy(self):
        root = Path(tempfile.mkdtemp())
        install_dir = root / "Live-Tools-Web"
        backup_dir = root / ".Live-Tools-Web-backup-test"
        transaction_file = install_dir / "runtime" / updater.UPDATE_TRANSACTION_NAME
        (install_dir / "runtime").mkdir(parents=True)
        backup_dir.mkdir()
        (backup_dir / "Live-Tools-Web.exe").write_text("old", encoding="utf-8")
        (install_dir / "Live-Tools-Web.exe").write_text("new", encoding="utf-8")
        updater.write_update_transaction(transaction_file, backup_dir, "0.5.1")

        with patch.object(updater, "get_running_version", return_value="0.5.1"):
            updater.recover_interrupted_update(
                install_dir,
                transaction_file,
                lambda _message: None,
            )

        self.assertEqual((install_dir / "Live-Tools-Web.exe").read_text(), "new")
        self.assertFalse(transaction_file.exists())
        self.assertFalse(backup_dir.exists())


if __name__ == "__main__":
    unittest.main()
