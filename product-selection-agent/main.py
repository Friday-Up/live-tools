"""京东四来源选品 Agent 命令行入口。"""
from __future__ import annotations

import argparse

from product_selection_agent import config
from product_selection_agent.service import execute_selection


def main() -> None:
    parser = argparse.ArgumentParser(description="京东四来源选品 Agent")
    parser.add_argument("--headless", action="store_true", help="无头浏览器模式")
    parser.add_argument("--offline", metavar="JSON", help="使用原始抓取 JSON，跳过在线抓取")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="允许来源为空仍生成报表；默认任一来源为空就失败",
    )
    args = parser.parse_args()

    result = execute_selection(
        output_dir=config.OUTPUT_DIR,
        headless=args.headless,
        offline_path=args.offline,
        allow_partial=args.allow_partial,
    )

    print("\n===== 选品推荐简报 =====")
    for source_name, categories in result.payload["recommendation"].items():
        print(f"\n【{source_name}】")
        for category_name, data in categories.items():
            top_pick = data.get("top_pick")
            if top_pick:
                print(f"  {category_name}: {top_pick['copy']}")


if __name__ == "__main__":
    main()
