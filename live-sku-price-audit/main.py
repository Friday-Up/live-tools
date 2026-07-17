"""
主程序入口
支持命令行参数或交互式输入价格门槛
"""

import os
import sys
import argparse
import threading

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CONFIG
from utils.browser_manager import BrowserManager
from utils.jd_crawler import capture_low_price_result_screenshots_with_page_factory, crawl_sku
from utils.excel_handler import read_sku_list, write_results
from utils.audit_runner import run_sku_batch


SCREENSHOT_WORKERS = 3


def list_input_files():
    """
    列出 input 目录下的所有 xlsx 文件
    """
    input_dir = CONFIG['input_dir']
    if not os.path.exists(input_dir):
        return []

    files = [f for f in os.listdir(input_dir) if f.endswith('.xlsx')]
    return sorted(files)


def select_input_file():
    """
    交互式选择输入文件
    """
    files = list_input_files()

    if not files:
        print(f"❌ 目录 {CONFIG['input_dir']} 下没有找到 .xlsx 文件")
        return None

    if len(files) == 1:
        # 只有一个文件，直接使用
        selected = files[0]
        print(f"✅ 自动选择文件: {selected}")
        return os.path.join(CONFIG['input_dir'], selected)

    # 多个文件，让用户选择
    print("\n" + "="*60)
    print("📁 请选择要处理的表格文件")
    print("="*60)
    for i, file in enumerate(files, 1):
        print(f"  [{i}] {file}")
    print("-"*60)

    while True:
        try:
            user_input = input(f"请输入编号（1-{len(files)}）：").strip()
            index = int(user_input) - 1
            if 0 <= index < len(files):
                selected = files[index]
                print(f"✅ 已选择: {selected}")
                return os.path.join(CONFIG['input_dir'], selected)
            else:
                print(f"❌ 请输入 1-{len(files)} 之间的数字")
        except ValueError:
            print("❌ 请输入有效的数字")


def get_inputs():
    """
    获取价格门槛和输入文件
    优先级：命令行参数 > 交互式输入 > 配置文件默认值
    """
    # 1. 尝试从命令行参数获取
    parser = argparse.ArgumentParser(description='直播-点菜 SKU 巡检 - 测价工具')
    parser.add_argument(
        '-t', '--threshold',
        type=float,
        help='价格门槛（如：6.0）'
    )
    parser.add_argument(
        '-f', '--file',
        type=str,
        help='输入Excel文件路径（如：input/6月5日点菜.xlsx）'
    )
    args = parser.parse_args()

    # 获取输入文件
    if args.file:
        # 命令行指定了文件
        input_file = args.file
    else:
        # 交互式选择文件
        input_file = select_input_file()
        if not input_file:
            return None, None

    # 获取价格门槛
    if args.threshold is not None:
        threshold_price = args.threshold
    else:
        # 交互式输入门槛
        print("\n" + "="*60)
        print("💰 请设置本次测价的价格门槛")
        print("="*60)
        print(f"提示：低于门槛价的商品将被标记为\"不符合上菜\"")
        print(f"配置文件默认值：¥{CONFIG['threshold_price']}")
        print("-"*60)

        while True:
            try:
                user_input = input(f"请输入价格门槛（直接回车使用默认值 ¥{CONFIG['threshold_price']}）：").strip()
                if user_input == '':
                    threshold_price = CONFIG['threshold_price']
                    break
                threshold_price = float(user_input)
                if threshold_price < 0:
                    print("❌ 价格门槛不能为负数，请重新输入")
                    continue
                break
            except ValueError:
                print("❌ 请输入有效的数字（如：6.0）")

    return threshold_price, input_file


def main():
    print("="*60)
    print("🚀 直播-点菜 SKU 巡检 - 测价工具")
    print("="*60)

    # 获取价格门槛和输入文件
    threshold_price, input_file = get_inputs()

    # 检查是否获取成功
    if threshold_price is None or input_file is None:
        print("❌ 未获取到有效的输入，程序退出")
        return

    print(f"\n✅ 本次价格门槛：¥{threshold_price}")
    print(f"📁 输入文件：{input_file}")

    # 1. 检查输入文件
    if not os.path.exists(input_file):
        print(f"❌ 输入文件不存在: {input_file}")
        print("请确保输入文件存在，或使用 -f 参数指定文件路径")
        return

    # 2. 读取 SKU 列表
    print(f"\n📖 正在读取: {input_file}")
    try:
        sku_data = read_sku_list(input_file, CONFIG['sku_column'])
    except Exception as e:
        print(f"❌ {e}")
        return
    print(f"✅ 共读取 {len(sku_data)} 个 SKU")

    if len(sku_data) == 0:
        print("❌ 未找到 SKU，请检查表格格式")
        return

    # 3. 启动浏览器
    print("\n🌐 正在启动浏览器...")
    browser = BrowserManager(CONFIG['auth_file'], block_resources=False)
    page = browser.start()

    # 4. 检查登录状态
    print("\n🔐 检查登录状态...")
    if not browser.check_login_status():
        print("⚠️  登录态已失效，正在引导重新登录...")
        # 自动引导重新登录，无需手动删除文件
        login_success = browser.re_login()
        if not login_success:
            print("❌ 重新登录失败，程序退出")
            browser.close(force=True)
            return
    print("✅ 登录状态正常")

    # 5. 创建输出目录，并清空旧截图
    if os.path.exists(CONFIG['screenshot_dir']):
        # 清空截图目录下的旧文件
        for file in os.listdir(CONFIG['screenshot_dir']):
            file_path = os.path.join(CONFIG['screenshot_dir'], file)
            if os.path.isfile(file_path):
                os.remove(file_path)
        print(f"🧹 已清空旧截图目录: {CONFIG['screenshot_dir']}")
    os.makedirs(CONFIG['screenshot_dir'], exist_ok=True)

    # 6. 批量测价
    print(f"\n📦 开始批量测价（门槛价: ¥{threshold_price}）")
    print("-"*60)

    def crawl_one(row_index, sku):
        return crawl_sku(
            page=page,
            sku=sku,
            screenshot_dir=CONFIG['screenshot_dir'],
            delay_min=CONFIG['delay_min'],
            delay_max=CONFIG['delay_max'],
            threshold_price=threshold_price
        )

    def on_item_start(i, total, row_index, sku):
        print(f"\n[{i}/{total}] SKU: {sku}")

    def on_login_required(row_index, sku, result):
        print(f"\n❌ {result['message']}")

    def recover_login():
        browser.wait_for_login_interactive()
        print("\n🔐 重新检查登录状态...")
        if browser.check_login_status():
            browser.save_auth_state()
            print("✅ 登录状态已恢复，继续运行")
            return True
        print("❌ 登录状态仍未恢复")
        return False

    batch = run_sku_batch(
        sku_data=sku_data,
        crawl_func=crawl_one,
        recover_login_func=recover_login,
        stop_event=threading.Event(),
        on_item_start=on_item_start,
        on_login_required=on_login_required,
    )
    results = batch.results

    print("\n" + "="*60)

    # 7. 测价结束后集中为低价 SKU 补截图，再写入结果表。
    if results:
        if not batch.stopped and not batch.login_failed:
            print(f"\n📸 正在为低于门槛的商品并发补充截图（{SCREENSHOT_WORKERS} 个窗口）...")

            def create_screenshot_page(worker_index):
                worker_browser = BrowserManager(CONFIG['auth_file'], headless=True)
                try:
                    worker_page = worker_browser.start()
                except Exception:
                    worker_browser.close(force=True)
                    raise

                def cleanup_worker():
                    worker_browser.close(force=True)

                return worker_page, cleanup_worker

            screenshot_summary = capture_low_price_result_screenshots_with_page_factory(
                results=results,
                screenshot_dir=CONFIG['screenshot_dir'],
                threshold_price=threshold_price,
                page_factory=create_screenshot_page,
                worker_count=SCREENSHOT_WORKERS,
            )
            print(
                f"📸 低价截图：应补 {screenshot_summary.total} 张，"
                f"成功 {screenshot_summary.captured} 张，失败 {screenshot_summary.failed} 张"
            )
            if screenshot_summary.failed_skus:
                failed_skus_text = ", ".join(screenshot_summary.failed_skus[:20])
                if len(screenshot_summary.failed_skus) > 20:
                    failed_skus_text += "..."
                print(f"⚠️ 低价截图失败 SKU: {failed_skus_text}")

        print("\n📝 正在写入结果...")
        output_path = write_results(
            file_path=input_file,
            results=results,
            threshold_price=threshold_price,
            output_dir=CONFIG['output_dir'],
            sku_column=CONFIG['sku_column'],
            price_column=CONFIG['price_column'],
            image_column=CONFIG['image_column'],
            remark_column=CONFIG['remark_column']
        )

        # 统计
        success_count = sum(1 for r in results if r['status'] == 'success')
        fail_count = len(results) - success_count
        unqualified_count = sum(1 for r in results
                               if r['status'] == 'success'
                               and r['price'] is not None
                               and r['price'] < threshold_price)

        print("\n📊 统计结果:")
        print(f"  ✅ 成功: {success_count}")
        print(f"  ❌ 失败: {fail_count}")
        print(f"  🚫 不符合上菜: {unqualified_count}")
        print(f"  💰 价格门槛: ¥{threshold_price}")

    # 8. 保存登录态（不关闭浏览器，便于下次复用）
    browser.close(force=False)

    if batch.login_failed:
        print("\n⚠️ 检测到登录态失效，已中断运行")
        print("请重新运行程序，会自动引导重新登录")
    else:
        print("\n🎉 测价完成！浏览器保持运行，可直接再次执行程序")

    print("="*60)


if __name__ == "__main__":
    main()
