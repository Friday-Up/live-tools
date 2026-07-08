import unittest

from bigscreen_capture.capture_manifest import CAPTURE_STEPS


class CaptureManifestTest(unittest.TestCase):
    def test_manifest_contains_confirmed_15_steps(self):
        labels = [step.filename_label for step in CAPTURE_STEPS]

        self.assertEqual(len(CAPTURE_STEPS), 15)
        self.assertEqual(CAPTURE_STEPS[0].filename_label, "概览总览")
        self.assertIn("渠道流量饼状图_在线", labels)
        self.assertIn("渠道成交饼状图_成交", labels)
        self.assertIn("挂袋数据", labels)
        self.assertIn("订单Top10", labels)
        self.assertIn("GMVTop10", labels)


if __name__ == "__main__":
    unittest.main()
