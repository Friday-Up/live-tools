import json
import threading
import unittest
from datetime import datetime, timezone, timedelta
from urllib.error import URLError

from usage_reporter import LiveToolUsageReporter


class UsageReporterTest(unittest.TestCase):
    def test_async_events_are_sent_in_enqueue_order(self):
        actions = []
        completed = threading.Event()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{}'

        def fake_urlopen(request, timeout):
            action = json.loads(request.data.decode("utf-8"))["events"][0]["action"]
            actions.append(action)
            if len(actions) == 3:
                completed.set()
            return FakeResponse()

        reporter = LiveToolUsageReporter(
            endpoint="http://usage.example/events",
            token="token",
            urlopen=fake_urlopen,
        )
        reporter.report_async(tool_code="red_rain_creator", action="upload")
        reporter.report_async(tool_code="red_rain_creator", action="task_start")
        reporter.report_async(tool_code="red_rain_creator", action="task_finish")

        self.assertTrue(completed.wait(2))
        self.assertEqual(actions, ["upload", "task_start", "task_finish"])

    def test_build_event_matches_order_contract(self):
        fixed_now = datetime(2026, 7, 9, 20, 30, 0, tzinfo=timezone(timedelta(hours=8)))
        reporter = LiveToolUsageReporter(
            endpoint="http://order.example/AllSpark/api/live-tools/events",
            token="token",
            user_name="zhangyaolong.5",
            session_id="session-1",
            app_version="2026.07.09",
            id_factory=lambda: "event-1",
            now_func=lambda: fixed_now,
        )

        event = reporter.build_event(
            tool_code="bigscreen_capture",
            action="task_finish",
            task_id="task-1",
            item_count=15,
            success_count=14,
            fail_count=1,
            duration_ms=1234,
            status="partial_success",
            extra={"room_id": "46794566"},
        )

        self.assertEqual(event["event_id"], "event-1")
        self.assertEqual(event["event_time"], "2026-07-09T20:30:00+08:00")
        self.assertEqual(event["app_name"], "live-tools")
        self.assertEqual(event["app_version"], "2026.07.09")
        self.assertEqual(event["tool_code"], "bigscreen_capture")
        self.assertEqual(event["action"], "task_finish")
        self.assertEqual(event["user_name"], "zhangyaolong.5")
        self.assertEqual(event["session_id"], "session-1")
        self.assertEqual(event["task_id"], "task-1")
        self.assertEqual(event["item_count"], 15)
        self.assertEqual(event["success_count"], 14)
        self.assertEqual(event["fail_count"], 1)
        self.assertEqual(event["duration_ms"], 1234)
        self.assertEqual(event["status"], "partial_success")
        self.assertEqual(event["extra"], {"room_id": "46794566"})

    def test_send_event_posts_batch_with_bearer_token(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"code":0}'

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = request.data
            return FakeResponse()

        reporter = LiveToolUsageReporter(
            endpoint="http://usage.example/AllSpark/api/live-tools/events",
            token="test-token",
            user_name="zhangyaolong.5",
            session_id="session-1",
            id_factory=lambda: "event-1",
            urlopen=fake_urlopen,
        )

        sent = reporter.send_event(
            tool_code="promotion_binding",
            action="task_start",
            task_id="task-1",
            status="started",
        )

        self.assertTrue(sent)
        self.assertEqual(captured["url"], "http://usage.example/AllSpark/api/live-tools/events")
        self.assertEqual(captured["timeout"], 2.0)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(captured["headers"]["Content-type"], "application/json")
        payload = json.loads(captured["body"].decode("utf-8"))
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events"][0]["event_id"], "event-1")
        self.assertEqual(payload["events"][0]["status"], "started")

    def test_send_event_returns_false_when_remote_unavailable(self):
        reporter = LiveToolUsageReporter(
            endpoint="http://order.example/AllSpark/api/live-tools/events",
            token="token",
            user_name="zhangyaolong.5",
            urlopen=lambda request, timeout: (_ for _ in ()).throw(URLError("down")),
        )

        self.assertFalse(
            reporter.send_event(
                tool_code="sku_price_audit",
                action="task_start",
                status="started",
            )
        )


if __name__ == "__main__":
    unittest.main()
