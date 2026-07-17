import os
from pathlib import Path
import stat
import unittest


LIVE_ROOT = Path(__file__).resolve().parents[1]


class MacOSPackagingTest(unittest.TestCase):
    def test_macos_launchers_are_executable_and_use_unified_app(self):
        start = LIVE_ROOT / "启动直播工具.command"
        stop = LIVE_ROOT / "关闭直播工具.command"

        for launcher in (start, stop):
            self.assertTrue(launcher.exists())
            if os.name != "nt":
                self.assertTrue(launcher.stat().st_mode & stat.S_IXUSR)

        start_content = start.read_text(encoding="utf-8")
        stop_content = stop.read_text(encoding="utf-8")
        self.assertIn('APP="$SCRIPT_DIR/Live-Tools-Web"', start_content)
        self.assertIn('PLAYWRIGHT_BROWSERS_PATH="$BROWSER_DIR"', start_content)
        self.assertIn("/api/health", start_content)
        self.assertIn('open "$URL"', start_content)
        self.assertIn("/api/shutdown", stop_content)

    def test_github_workflow_builds_intel_and_apple_silicon_packages(self):
        workflow = LIVE_ROOT / ".github" / "workflows" / "build-macos.yml"

        self.assertTrue(workflow.exists())
        content = workflow.read_text(encoding="utf-8")
        self.assertIn("Build Live Tools macOS", content)
        self.assertIn("macos-15-intel", content)
        self.assertIn("runner: macos-15", content)
        self.assertIn("Live-Tools-macOS-Intel.zip", content)
        self.assertIn("Live-Tools-macOS-Apple-Silicon.zip", content)
        self.assertIn('--contents-directory "."', content)
        self.assertIn("live-web/app.py", content)
        self.assertIn("启动直播工具.command", content)
        self.assertIn("关闭直播工具.command", content)
        self.assertIn("model-config.example.json", content)
        self.assertIn('browser_cache="$HOME/Library/Caches/ms-playwright"', content)
        self.assertIn('ditto "$browser_cache" "$dist_path/ms-playwright"', content)
        self.assertNotIn('PLAYWRIGHT_BROWSERS_PATH: "0"', content)
        self.assertIn("Private model config must not be included in the macOS package", content)
        self.assertIn("ditto -c -k --sequesterRsrc --keepParent", content)
        self.assertIn("actions/upload-artifact@v4", content)

    def test_github_workflow_signs_embedded_python_framework(self):
        workflow = LIVE_ROOT / ".github" / "workflows" / "build-macos.yml"

        content = workflow.read_text(encoding="utf-8")
        self.assertIn("Sign packaged macOS runtime", content)
        self.assertIn(
            'codesign --force --deep --sign - "$dist_path/Python.framework"',
            content,
        )
        self.assertIn(
            'codesign --verify --deep --strict --verbose=2 "$dist_path/Python.framework"',
            content,
        )

    def test_github_workflow_verifies_signatures_after_archive_round_trip(self):
        workflow = LIVE_ROOT / ".github" / "workflows" / "build-macos.yml"

        content = workflow.read_text(encoding="utf-8")
        self.assertIn("Verify archived macOS package", content)
        self.assertIn('ditto -x -k "dist/${{ matrix.archive }}" "$verify_dir"', content)
        self.assertIn(
            'codesign --verify --deep --strict --verbose=2 "$verify_app/Python.framework"',
            content,
        )
        self.assertIn(
            'codesign --verify --strict --verbose=2 "$verify_app/Live-Tools-Web"',
            content,
        )

    def test_readme_removes_quarantine_from_the_whole_macos_package(self):
        readme = (LIVE_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            'xattr -dr com.apple.quarantine "/完整路径/Live-Tools-Web"',
            readme,
        )


if __name__ == "__main__":
    unittest.main()
