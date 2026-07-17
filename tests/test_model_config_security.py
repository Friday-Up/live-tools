import json
from pathlib import Path
import subprocess
import unittest


LIVE_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = LIVE_ROOT / "product-selection-agent"


class ModelConfigSecurityTest(unittest.TestCase):
    def test_private_model_config_is_ignored_and_untracked(self):
        ignore_content = (AGENT_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("model-config.local.json", ignore_content.splitlines())

        tracked = subprocess.run(
            ["git", "ls-files", "--", "product-selection-agent/model-config.local.json"],
            cwd=LIVE_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(tracked.stdout.strip(), "")

    def test_example_config_contains_no_real_credential(self):
        example = json.loads((AGENT_ROOT / "model-config.example.json").read_text(encoding="utf-8"))
        self.assertEqual(example["SELECTION_AI_API_KEY"], "replace-with-your-api-key")
        self.assertEqual(example["SELECTION_AI_API_URL"], "https://your-gateway.example/v1/chat/completions")
        self.assertEqual(example["SELECTION_AI_MODEL"], "your-model")

    def test_packaging_workflows_reject_private_config(self):
        windows = (LIVE_ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
        macos = (LIVE_ROOT / ".github" / "workflows" / "build-macos.yml").read_text(encoding="utf-8")

        self.assertIn("Private model config must not be included in the Windows package", windows)
        self.assertIn("Private model config must not be included in the macOS package", macos)
        self.assertIn("model-config.example.json", windows)
        self.assertIn("model-config.example.json", macos)
        self.assertNotIn('Copy-Item -Path "product-selection-agent/model-config.local.json"', windows)
        self.assertNotIn('cp "product-selection-agent/model-config.local.json"', macos)
        self.assertNotIn("SELECTION_AI_API_KEY", windows)
        self.assertNotIn("SELECTION_AI_API_KEY", macos)


if __name__ == "__main__":
    unittest.main()
