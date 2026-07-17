import os
from pathlib import Path
import subprocess
import sys
import unittest


class ProductSelectionPackageTest(unittest.TestCase):
    def test_core_modules_are_available_from_product_selection_package(self):
        from product_selection_agent import config, fetcher, parser, recommender, selector

        self.assertEqual(config.TOP_N_PER_CATEGORY, 10)
        self.assertTrue(callable(fetcher.fetch_all))
        self.assertTrue(callable(parser.parse_all))
        self.assertTrue(callable(recommender.recommend))
        self.assertTrue(callable(selector.build_candidate_pool))

    def test_cli_is_a_thin_wrapper_around_service(self):
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

        self.assertIn("from product_selection_agent.service import", source)
        self.assertNotIn("def save_excel", source)
        self.assertNotIn("def _diagnostics", source)

    def test_packaged_defaults_use_allspark_proxy_without_jd_gateway_key(self):
        agent_root = Path(__file__).resolve().parents[1]
        config_source = (agent_root / "product_selection_agent" / "config.py").read_text(encoding="utf-8")
        self.assertNotIn("llm-gw.jd.local", config_source)

        env = dict(os.environ)
        env.update(
            {
                "SELECTION_AI_CONFIG_PATH": str(agent_root / "missing-model-config.json"),
                "LIVE_LLM_PROXY_URL": "http://proxy.test/AllSpark/api/live-tools/llm/chat/completions",
                "LIVE_LLM_PROXY_TOKEN": "restricted-client-token",
                "LIVE_LLM_PROXY_MODEL": "proxy-model",
            }
        )
        for name in ("SELECTION_AI_API_URL", "SELECTION_AI_API_KEY", "SELECTION_AI_MODEL"):
            env.pop(name, None)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from product_selection_agent import config; "
                    "print(config.AI_API_URL.endswith('/llm/chat/completions')); "
                    "print(config.AI_API_KEY == 'restricted-client-token'); "
                    "print(config.AI_MODEL == 'proxy-model'); "
                    "print(config.AI_TIMEOUT_SECONDS == 210)"
                ),
            ],
            cwd=agent_root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.stdout.splitlines(), ["True", "True", "True", "True"])


if __name__ == "__main__":
    unittest.main()
