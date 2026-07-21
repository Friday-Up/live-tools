import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


class UsageReportingConfigTest(unittest.TestCase):
    def test_usage_reporting_is_enabled_with_working_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = runpy.run_path(str(Path("config.py")))

        self.assertTrue(config["LIVE_USAGE_EVENT_ENABLED"])
        self.assertEqual(
            config["LIVE_USAGE_EVENT_ENDPOINT"],
            "http://114.67.72.156/AllSpark/api/live-tools/events",
        )
        self.assertEqual(
            config["LIVE_USAGE_EVENT_TOKEN"],
            "live-tools-analytics-2026",
        )
        self.assertEqual(config["LIVE_TOOLS_APP_VERSION"], "0.5.3")
        self.assertEqual(
            config["LIVE_TOOLS_UPDATE_MANIFEST_URL"],
            "https://github.com/Friday-Up/live-tools/releases/latest/download/live-tools-update.json",
        )

    def test_environment_can_override_usage_reporting_defaults(self):
        environment = {
            "LIVE_USAGE_EVENT_ENDPOINT": "https://order.example/api/live-tools/events",
            "LIVE_USAGE_EVENT_TOKEN": "override-token",
            "LIVE_USAGE_EVENT_ENABLED": "false",
            "LIVE_USAGE_EVENT_TIMEOUT_SECONDS": "4.5",
            "LIVE_TOOLS_UPDATE_MANIFEST_URL": "https://updates.example/live-tools.json",
        }
        with patch.dict(os.environ, environment, clear=True):
            config = runpy.run_path(str(Path("config.py")))

        self.assertFalse(config["LIVE_USAGE_EVENT_ENABLED"])
        self.assertEqual(
            config["LIVE_USAGE_EVENT_ENDPOINT"],
            "https://order.example/api/live-tools/events",
        )
        self.assertEqual(config["LIVE_USAGE_EVENT_TOKEN"], "override-token")
        self.assertEqual(config["LIVE_USAGE_EVENT_TIMEOUT_SECONDS"], 4.5)
        self.assertEqual(
            config["LIVE_TOOLS_UPDATE_MANIFEST_URL"],
            "https://updates.example/live-tools.json",
        )


if __name__ == "__main__":
    unittest.main()
