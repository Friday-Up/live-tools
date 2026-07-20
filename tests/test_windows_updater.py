import importlib.util
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
        (payload_dir / "product-selection-agent").mkdir(parents=True)
        (payload_dir / "product-selection-agent" / "package.py").write_text("new", encoding="utf-8")
        (payload_dir / "Live-Tools-Web.exe").write_text("new", encoding="utf-8")

        preserved = updater.read_preserved_files(install_dir)
        updater.move_current_install_to_backup(install_dir, backup_dir)
        updater.install_payload(payload_dir, install_dir)
        updater.restore_preserved_files(install_dir, preserved)

        self.assertEqual((install_dir / "Live-Tools-Web.exe").read_text(), "new")
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


if __name__ == "__main__":
    unittest.main()
