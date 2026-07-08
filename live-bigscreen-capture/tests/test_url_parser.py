import unittest

from bigscreen_capture.url_parser import BigscreenUrlError, parse_bigscreen_url


class BigscreenUrlParserTest(unittest.TestCase):
    def test_parses_jlive_bigscreen_id(self):
        parsed = parse_bigscreen_url("https://jlive.jd.com/bigScreen?id=46794566")

        self.assertEqual(parsed.room_id, "46794566")
        self.assertEqual(parsed.url, "https://jlive.jd.com/bigScreen?id=46794566")

    def test_rejects_missing_id(self):
        with self.assertRaises(BigscreenUrlError):
            parse_bigscreen_url("https://jlive.jd.com/bigScreen")

    def test_rejects_wrong_host(self):
        with self.assertRaises(BigscreenUrlError):
            parse_bigscreen_url("https://example.com/bigScreen?id=46794566")


if __name__ == "__main__":
    unittest.main()
