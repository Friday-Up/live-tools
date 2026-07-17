import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


class RunContextTest(unittest.TestCase):
    def test_forwards_logs_and_raises_when_cancelled(self):
        from product_selection_agent.runtime import (
            RunContext,
            SelectionCancelled,
        )

        messages = []
        stop_event = threading.Event()
        context = RunContext(log_callback=messages.append, stop_event=stop_event)

        context.log("第一条日志")
        stop_event.set()

        self.assertEqual(messages, ["第一条日志"])
        with self.assertRaises(SelectionCancelled):
            context.check_cancelled()


class SelectionServiceTest(unittest.TestCase):
    def test_execute_selection_writes_excel_only(self):
        from product_selection_agent import service
        from product_selection_agent.runtime import RunContext

        payload = {
            "generated_at": "2026-07-16T19:00:00+08:00",
            "recommendation_mode": "llm_enhanced",
            "ai_complete": True,
            "candidate_pool": {},
            "selection": {},
            "recommendation": {},
            "diagnostics": {"fetch_complete": True, "ai_complete": True, "sources": {}},
        }
        messages = []
        output_dir = Path(tempfile.mkdtemp())

        with mock.patch.object(service, "run_selection", return_value=payload):
            result = service.execute_selection(
                output_dir=output_dir,
                context=RunContext(log_callback=messages.append),
            )

        self.assertTrue(result.excel_path.is_file())
        self.assertEqual(list(output_dir.glob("*.json")), [])
        self.assertEqual(result.payload, payload)
        self.assertFalse(any("JSON:" in message for message in messages))
        self.assertTrue(any("Excel" in message for message in messages))

    def test_fetcher_accepts_context_and_checks_cancel_before_start(self):
        from product_selection_agent import fetcher
        from product_selection_agent.runtime import RunContext, SelectionCancelled

        stop_event = threading.Event()
        stop_event.set()
        context = RunContext(stop_event=stop_event)

        with self.assertRaises(SelectionCancelled):
            fetcher.fetch_all(headless=True, context=context)

    def test_rule_recommendation_uses_context_logger(self):
        from product_selection_agent import recommender
        from product_selection_agent.runtime import RunContext

        messages = []
        candidate_pool = {
            "测试来源": {
                "测试类目": [
                    {
                        "sku_id": "1",
                        "name": "测试商品",
                        "display_price": 10,
                        "sales_num": 100,
                        "source_rank": 1,
                    }
                ]
            }
        }
        with mock.patch.object(recommender.config, "AI_API_URL", ""), mock.patch.object(
            recommender.config, "AI_API_KEY", ""
        ), mock.patch.object(recommender.config, "AI_MODEL", ""):
            recommender.recommend(
                candidate_pool,
                context=RunContext(log_callback=messages.append),
            )

        self.assertTrue(any("规则推荐" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
