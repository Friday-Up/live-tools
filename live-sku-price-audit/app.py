"""
Web GUI 服务
提供上传 Excel、配置门槛价、实时查看进度、下载结果的功能
"""

import os
import sys
import time
import threading
import uuid
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 兼容 PyInstaller 打包后的路径
def get_base_dir():
    """获取程序根目录（兼容源码和打包模式）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的 EXE 运行
        # sys.executable 指向 _internal/SKU-Price-Audit-Web.exe
        exe_dir = os.path.dirname(sys.executable)
        # 如果 exe 在 _internal 目录中，向上回退一级
        if os.path.basename(exe_dir).lower() == '_internal':
            return os.path.dirname(exe_dir)
        return exe_dir
    else:
        # 源码运行
        return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()

# 添加项目根目录到 Python 路径
sys.path.insert(0, BASE_DIR)

# 导入配置
from config import CONFIG

# 创建 Flask 应用，指定模板目录
template_dir = os.path.join(BASE_DIR, 'templates')
static_dir = os.path.join(BASE_DIR, 'static')

print(f"📁 BASE_DIR: {BASE_DIR}")
print(f"📁 模板目录: {template_dir}")
print(f"📁 模板是否存在: {os.path.exists(template_dir)}")

# 如果模板目录不存在，尝试其他可能的路径
if not os.path.exists(template_dir):
    # 尝试 exe 所在目录
    alt_dir = os.path.dirname(sys.executable)
    alt_template_dir = os.path.join(alt_dir, 'templates')
    print(f"📁 尝试备用模板目录: {alt_template_dir}")
    if os.path.exists(alt_template_dir):
        template_dir = alt_template_dir
        print(f"✅ 使用备用模板目录")
    else:
        # 列出 BASE_DIR 下的所有文件，帮助调试
        if os.path.exists(BASE_DIR):
            print(f"📁 BASE_DIR 内容: {os.listdir(BASE_DIR)}")
        else:
            print(f"❌ BASE_DIR 不存在: {BASE_DIR}")
        print(f"❌ 错误: 找不到模板目录！")

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# 全局状态 - 使用锁保护
status_lock = threading.Lock()
audit_status = {
    'running': False,
    'total': 0,
    'current': 0,
    'current_sku': '',
    'success_count': 0,
    'fail_count': 0,
    'unqualified_count': 0,
    'logs': [],
    'result_file': None,
    'error': None,
    'need_login': False,
    'stopping': False
}

# 登录等待事件
login_event = threading.Event()

# 停止标志
stop_flag = threading.Event()

# 全局浏览器实例（用于强制关闭）
current_browser = None
browser_lock = threading.Lock()
CONCURRENT_WORKERS = max(1, int(CONFIG.get('concurrent_workers', 3)))


def json_error(message, status_code=400):
    return jsonify({'success': False, 'error': message}), status_code


def resolve_input_file(file_path):
    """只允许启动 input 目录下的文件，避免任意本地路径被 Web 请求触发读取。"""
    if not file_path:
        return None

    input_dir = Path(CONFIG['input_dir']).resolve()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = Path(BASE_DIR) / candidate
    candidate = candidate.resolve()

    try:
        candidate.relative_to(input_dir)
    except ValueError:
        return None

    if not candidate.is_file() or candidate.suffix.lower() != '.xlsx':
        return None

    return str(candidate)


def safe_upload_name(filename):
    name = (filename or '').replace('\\', '/').split('/')[-1].strip()
    if not name or name in {'.', '..'} or not name.lower().endswith('.xlsx'):
        return None
    return name


def parse_sku_input(raw):
    """解析页面输入的 SKU 字符串，支持英文/中文逗号和分号、换行等分隔符。"""
    if not raw or not isinstance(raw, str):
        return []
    separators = (',', ';', '，', '；', '\n', '\r', '\t')
    parts = [raw]
    for sep in separators:
        split_parts = []
        for part in parts:
            split_parts.extend(part.split(sep))
        parts = split_parts

    seen = set()
    result = []
    for sku in parts:
        normalized = sku.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def add_log(message):
    """添加日志（线程安全）"""
    with status_lock:
        audit_status['logs'].append({
            'time': time.strftime('%H:%M:%S'),
            'message': message
        })
        # 只保留最近 200 条
        if len(audit_status['logs']) > 200:
            audit_status['logs'] = audit_status['logs'][-200:]
    print(f"[{time.strftime('%H:%M:%S')}] {message}")


def _format_price_diagnostics(diagnostics):
    if not diagnostics:
        return ''

    source_counts = diagnostics.get('price_source_counts') or {}
    dom_count = source_counts.get('dom-fallback', 0) + source_counts.get('dom', 0)
    duration_seconds = (diagnostics.get('duration_ms') or 0) / 1000
    spec_count = diagnostics.get('spec_count') or 0
    return (
        f"诊断: 耗时 {duration_seconds:.1f}s，规格 {spec_count}，"
        f"取价 ware={source_counts.get('ware-business', 0)}/"
        f"dom={dom_count}/"
        f"selected={source_counts.get('selected-dom', 0)}"
    )


def close_current_browsers():
    """主动关闭当前测价浏览器，用于停止长时间页面等待。"""
    global current_browser

    with browser_lock:
        browsers = current_browser
        current_browser = None

    if not browsers:
        return 0

    if not isinstance(browsers, list):
        browsers = [browsers]

    closed_count = 0
    for browser in list(browsers):
        try:
            browser.close(force=True)
            closed_count += 1
        except Exception:
            pass
    return closed_count


def run_audit_task(input_file, threshold_price, show_browser=False, cleanup_input=False):
    """在后台线程运行测价任务"""
    global audit_status
    global current_browser

    browser = None
    page = None

    try:
        # 延迟导入，避免启动时加载失败
        from utils.browser_manager import BrowserManager
        from utils.jd_crawler import capture_low_price_result_screenshots_with_page_factory, crawl_sku
        from utils.excel_handler import read_sku_list, write_results
        from utils.audit_runner import run_sku_batch_with_page_factory

        with status_lock:
            audit_status['running'] = True
            audit_status['stopping'] = False
            audit_status['total'] = 0
            audit_status['current'] = 0
            audit_status['current_sku'] = ''
            audit_status['success_count'] = 0
            audit_status['fail_count'] = 0
            audit_status['unqualified_count'] = 0
            audit_status['logs'] = []
            audit_status['result_file'] = None
            audit_status['error'] = None
            audit_status['need_login'] = False

        add_log('🚀 开始批量测价')
        add_log(f'📁 输入文件: {os.path.basename(input_file)}')
        add_log(f'💰 价格门槛: ¥{threshold_price}')
        worker_headless = not show_browser
        add_log(f'🌐 浏览器模式: {"有头" if show_browser else "无头"}')

        # 1. 读取 SKU 列表
        add_log('📖 正在读取 Excel...')
        try:
            sku_data = read_sku_list(input_file, CONFIG['sku_column'])
        except Exception as e:
            with status_lock:
                audit_status['error'] = str(e)
            add_log(f'❌ {e}')
            return

        with status_lock:
            audit_status['total'] = len(sku_data)
        add_log(f'✅ 共读取 {len(sku_data)} 个 SKU')

        if len(sku_data) == 0:
            with status_lock:
                audit_status['error'] = '未找到 SKU，请检查表格格式'
            return

        # 2. 启动浏览器
        add_log('🌐 正在启动浏览器...')
        browser = BrowserManager(CONFIG['auth_file'], headless=worker_headless)

        with browser_lock:
            current_browser = [browser]

        page = browser.start()

        # 3. 检查登录状态
        add_log('🔐 检查登录状态...')
        is_logged_in = browser.check_login_status()
        add_log(f'   登录状态检查结果: {"已登录" if is_logged_in else "未登录"}')
        if stop_flag.is_set():
            add_log('🛑 测价已停止')
            return

        def wait_for_web_login(login_browser=None):
            login_browser = login_browser or browser
            add_log('⚠️ 登录态已失效，请登录')
            with status_lock:
                audit_status['need_login'] = True
            login_event.clear()

            # 等待前端通知继续
            add_log('⏳ 等待用户完成登录并点击"我已登录"...')
            # 循环等待，检查是否停止
            wait_count = 0
            try:
                login_browser.open_login_page()
            except Exception as e:
                add_log(f'⚠️ 打开登录页失败: {e}')

            while not login_event.is_set() and wait_count < 120:  # 最多等待10分钟
                login_event.wait(timeout=5)
                wait_count += 1
                if wait_count % 6 == 0:  # 每30秒输出一次日志
                    add_log(f'⏳ 仍在等待用户登录... ({wait_count * 5}秒)')
                if stop_flag.is_set():
                    add_log('🛑 测价已停止')
                    break

            with status_lock:
                audit_status['need_login'] = False

            if stop_flag.is_set():
                return False

            # 再次检查登录状态
            add_log('🔐 重新检查登录状态...')
            is_logged_in = login_browser.check_login_status()
            add_log(f'   登录状态检查结果: {"已登录" if is_logged_in else "未登录"}')

            if not is_logged_in:
                add_log('❌ 登录失败')
                return False

            try:
                login_browser.save_auth_state()
            except Exception as e:
                add_log(f'⚠️ 保存登录状态失败: {e}')

            add_log('✅ 登录恢复，继续运行')
            return True

        if not is_logged_in:
            try:
                browser.close(force=True)
            except Exception:
                pass
            browser = BrowserManager(CONFIG['auth_file'], headless=False, block_resources=False)
            with browser_lock:
                current_browser = [browser]
            page = browser.start()
            if not wait_for_web_login(browser):
                with status_lock:
                    audit_status['error'] = '登录失败，请重新运行'
                return
            try:
                browser.close(force=True)
            except Exception:
                pass
            add_log('✅ 登录成功后切回测价浏览器')
            browser = BrowserManager(CONFIG['auth_file'], headless=worker_headless)
            with browser_lock:
                current_browser = [browser]
            page = browser.start()
            add_log('🔐 检查测价浏览器登录状态...')
            if not browser.check_login_status(recheck_seconds=10):
                with status_lock:
                    audit_status['error'] = '登录状态未能同步到测价浏览器，请重新运行'
                add_log('❌ 登录状态未能同步到测价浏览器，请重新运行')
                return
        add_log('✅ 登录状态正常')

        add_log(f'⚡ 启用快扫响应取价 + {CONCURRENT_WORKERS} 浏览器并发')

        # 4. 创建输出目录
        if os.path.exists(CONFIG['screenshot_dir']):
            for file in os.listdir(CONFIG['screenshot_dir']):
                file_path = os.path.join(CONFIG['screenshot_dir'], file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        os.makedirs(CONFIG['screenshot_dir'], exist_ok=True)

        # 5. 批量测价
        def on_item_start(i, total, row_index, sku):
            with status_lock:
                audit_status['current_sku'] = sku
            add_log(f'[{i}/{len(sku_data)}] 处理 SKU: {sku}')

        def crawl_one(worker_page, row_index, sku):
            return crawl_sku(
                page=worker_page,
                sku=sku,
                screenshot_dir=CONFIG['screenshot_dir'],
                delay_min=CONFIG['delay_min'],
                delay_max=CONFIG['delay_max'],
                threshold_price=threshold_price,
                should_stop=stop_flag.is_set
            )

        def create_worker_page(worker_index, block_images=False):
            worker_browser = BrowserManager(CONFIG['auth_file'], headless=worker_headless, block_images=block_images)
            try:
                worker_page = worker_browser.start()
            except Exception:
                worker_browser.close(force=True)
                raise
            with browser_lock:
                if isinstance(current_browser, list):
                    current_browser.append(worker_browser)

            def cleanup_worker():
                try:
                    worker_browser.close(force=True)
                finally:
                    with browser_lock:
                        if isinstance(current_browser, list) and worker_browser in current_browser:
                            current_browser.remove(worker_browser)

            def recover_worker_login():
                login_browser = BrowserManager(CONFIG['auth_file'], headless=False, block_resources=False)
                try:
                    login_browser.start()
                except Exception:
                    login_browser.close(force=True)
                    raise
                with browser_lock:
                    if isinstance(current_browser, list):
                        current_browser.append(login_browser)
                try:
                    return wait_for_web_login(login_browser)
                finally:
                    try:
                        login_browser.close(force=True)
                    finally:
                        with browser_lock:
                            if isinstance(current_browser, list) and login_browser in current_browser:
                                current_browser.remove(login_browser)

            return worker_page, cleanup_worker, recover_worker_login

        def on_result(result):
            if result['status'] == 'success':
                with status_lock:
                    audit_status['current'] += 1
                    audit_status['success_count'] += 1
                if result['price'] is not None and result['price'] < threshold_price:
                    with status_lock:
                        audit_status['unqualified_count'] += 1
                    add_log(f'  🚫 低于门槛价: ¥{result["price"]}')
                else:
                    add_log(f'  ✅ 价格: ¥{result["price"]}')
            elif result['status'] == 'need_login':
                with status_lock:
                    audit_status['current'] += 1
                    audit_status['fail_count'] += 1
                add_log(f'  ❌ 需要登录: {result["message"]}')
            elif result['status'] == 'partial':
                with status_lock:
                    audit_status['current'] += 1
                    audit_status['fail_count'] += 1
                add_log(f'  ⚠️ 需人工复核: {result["message"]}')
            else:
                with status_lock:
                    audit_status['current'] += 1
                    audit_status['fail_count'] += 1
                add_log(f'  ❌ 失败: {result["message"]}')
            diagnostics_log = _format_price_diagnostics(result.get('diagnostics'))
            if diagnostics_log:
                add_log(f'  {diagnostics_log}')

        def on_login_required(row_index, sku, result):
            add_log(f'⚠️ SKU {sku} 需要人工处理: {result.get("message", "登录态已失效")}')

        batch = run_sku_batch_with_page_factory(
            sku_data=sku_data,
            crawl_func=crawl_one,
            recover_login_func=wait_for_web_login,
            stop_event=stop_flag,
            page_factory=lambda worker_index: create_worker_page(worker_index, block_images=True),
            worker_count=CONCURRENT_WORKERS,
            on_item_start=on_item_start,
            on_result=on_result,
            on_login_required=on_login_required,
        )
        results = batch.results

        # 6. 测价结束后集中为低价 SKU 补截图，再写入结果表。
        if results and not batch.stopped and not batch.login_failed and not stop_flag.is_set():
            add_log(f'📸 正在为低于门槛的商品并发补充截图（{CONCURRENT_WORKERS} 个窗口）...')
            screenshot_summary = capture_low_price_result_screenshots_with_page_factory(
                results=results,
                screenshot_dir=CONFIG['screenshot_dir'],
                threshold_price=threshold_price,
                page_factory=lambda worker_index: create_worker_page(worker_index, block_images=False),
                worker_count=CONCURRENT_WORKERS,
                should_stop=stop_flag.is_set,
            )
            add_log(
                f'📸 低价截图：应补 {screenshot_summary.total} 张，'
                f'成功 {screenshot_summary.captured} 张，失败 {screenshot_summary.failed} 张'
            )
            if screenshot_summary.failed_skus:
                failed_skus_text = ', '.join(screenshot_summary.failed_skus[:20])
                if len(screenshot_summary.failed_skus) > 20:
                    failed_skus_text += '...'
                add_log(f'⚠️ 低价截图失败 SKU: {failed_skus_text}')

        # 7. 写入结果
        if results:
            add_log('📝 正在写入结果...')
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
            with status_lock:
                audit_status['result_file'] = output_path
            add_log(f'✅ 结果已保存: {os.path.basename(output_path)}')

        # 8. 检查是否因停止而结束
        if batch.stopped or stop_flag.is_set():
            add_log('🛑 测价已停止')
        elif batch.login_failed:
            with status_lock:
                audit_status['error'] = '登录失败，程序中断'
            add_log('❌ 登录失败，程序中断')
        else:
            add_log('🎉 测价完成！')

    except Exception as e:
        with status_lock:
            audit_status['error'] = str(e)
        add_log(f'❌ 错误: {str(e)}')
        import traceback
        add_log(f'❌ 详细错误: {traceback.format_exc()}')
    finally:
        # 确保浏览器被关闭
        if browser:
            try:
                add_log('🛑 正在关闭浏览器...')
                browser.close(force=True)
                add_log('✅ 浏览器已关闭')
            except Exception as e:
                add_log(f'⚠️ 关闭浏览器出错: {e}')

        with browser_lock:
            current_browser = None

        with status_lock:
            audit_status['running'] = False
            audit_status['stopping'] = False
            audit_status['need_login'] = False

        if cleanup_input:
            try:
                if os.path.exists(input_file):
                    os.remove(input_file)
                    add_log(f'🧹 已清理临时输入文件: {os.path.basename(input_file)}')
            except Exception as e:
                add_log(f'⚠️ 清理临时输入文件失败: {e}')


@app.route('/')
def index():
    """首页"""
    try:
        return render_template('index.html')
    except Exception as e:
        return f"""
        <h1>错误：无法加载页面</h1>
        <p>错误信息: {str(e)}</p>
        <p>BASE_DIR: {BASE_DIR}</p>
        <p>模板目录: {template_dir}</p>
        <p>模板是否存在: {os.path.exists(template_dir)}</p>
        <p>目录内容: {os.listdir(BASE_DIR) if os.path.exists(BASE_DIR) else 'N/A'}</p>
        """, 500


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """上传 Excel 文件"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未选择文件'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'})

    safe_name = safe_upload_name(file.filename)
    if not safe_name:
        return jsonify({'success': False, 'error': '仅支持 .xlsx 格式'})

    # 保存到 input 目录
    os.makedirs(CONFIG['input_dir'], exist_ok=True)
    upload_path = os.path.join(CONFIG['input_dir'], safe_name)
    file.save(upload_path)

    return jsonify({
        'success': True,
        'filename': safe_name,
        'path': upload_path
    })


@app.route('/api/start', methods=['POST'])
def start_audit():
    """开始测价"""
    global audit_status

    with status_lock:
        if audit_status['running']:
            return jsonify({'success': False, 'error': '已有任务正在运行'})

    data = request.get_json(silent=True) or {}
    input_file = data.get('file')
    threshold = data.get('threshold', CONFIG['threshold_price'])
    show_browser = bool(data.get('show_browser'))

    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        return json_error('价格门槛必须是有效数字')

    if threshold < 0:
        return json_error('价格门槛不能为负数')

    input_file = resolve_input_file(input_file)
    if not input_file:
        return json_error('文件不存在或不在 input 目录，请先上传')

    stop_flag.clear()
    login_event.clear()

    # 启动后台线程
    thread = threading.Thread(
        target=run_audit_task,
        args=(input_file, threshold, show_browser)
    )
    thread.daemon = False  # 改为非守护线程，确保能正常完成
    thread.start()

    return jsonify({'success': True})


@app.route('/api/start-from-skus', methods=['POST'])
def start_audit_from_skus():
    """从页面输入的 SKU 字符串开始测价"""
    global audit_status

    with status_lock:
        if audit_status['running']:
            return jsonify({'success': False, 'error': '已有任务正在运行'})

    data = request.get_json(silent=True) or {}
    skus_raw = data.get('skus', '')
    threshold = data.get('threshold', CONFIG['threshold_price'])
    show_browser = bool(data.get('show_browser'))

    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        return json_error('价格门槛必须是有效数字')

    if threshold < 0:
        return json_error('价格门槛不能为负数')

    sku_list = parse_sku_input(skus_raw)
    if not sku_list:
        return json_error('请输入有效的 SKU')

    # 在 input 目录下生成临时输入文件
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    input_file = os.path.join(CONFIG['input_dir'], f'页面输入SKU_{timestamp}_{uuid.uuid4().hex[:8]}.xlsx')
    try:
        from utils.excel_handler import create_sku_input_file
        create_sku_input_file(sku_list, input_file)
    except Exception as e:
        return json_error(f'生成输入文件失败: {e}')

    stop_flag.clear()
    login_event.clear()

    add_log(f'📝 页面输入 SKU {len(sku_list)} 个，已生成临时输入文件')

    thread = threading.Thread(
        target=run_audit_task,
        args=(input_file, threshold, show_browser),
        kwargs={'cleanup_input': True}
    )
    thread.daemon = False
    thread.start()

    return jsonify({'success': True, 'count': len(sku_list)})


@app.route('/api/status')
def get_status():
    """获取任务状态"""
    with status_lock:
        return jsonify(audit_status)


@app.route('/api/download')
def download_result():
    """下载结果文件"""
    with status_lock:
        result_file = audit_status.get('result_file')

    if not result_file or not os.path.exists(result_file):
        return jsonify({'success': False, 'error': '结果文件不存在'})

    try:
        return send_file(result_file, as_attachment=True)
    except Exception as e:
        return jsonify({'success': False, 'error': f'下载失败: {str(e)}'})


@app.route('/api/continue', methods=['POST'])
def continue_audit():
    """用户登录完成后通知后端继续"""
    login_event.set()
    add_log('✅ 用户点击"我已登录"，继续运行')
    return jsonify({'success': True})


@app.route('/api/stop', methods=['POST'])
def stop_audit():
    """停止测价任务"""
    add_log('🛑 收到停止请求')
    stop_flag.set()
    login_event.set()  # 唤醒可能正在等待登录的线程

    with status_lock:
        audit_status['stopping'] = True
        audit_status['need_login'] = False
    add_log('🛑 已请求停止，正在等待当前步骤结束')
    closed_count = close_current_browsers()
    if closed_count:
        add_log(f'🛑 已关闭 {closed_count} 个测价浏览器，正在退出当前步骤')

    return jsonify({'success': True})


def shutdown_server():
    """关闭服务器和浏览器"""
    add_log('🛑 正在关闭服务...')

    # 停止测价
    stop_flag.set()
    login_event.set()

    # 关闭浏览器
    close_current_browsers()

    # 优雅退出
    import signal
    os.kill(os.getpid(), signal.SIGTERM)


@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    """接收关闭请求"""
    threading.Thread(target=shutdown_server, daemon=True).start()
    return jsonify({'success': True})


if __name__ == '__main__':
    # 延迟导入，避免启动时加载失败
    from utils.cleanup import auto_cleanup

    # 自动清理临时文件
    auto_cleanup()

    # 确保目录存在
    os.makedirs(CONFIG['input_dir'], exist_ok=True)
    os.makedirs(CONFIG['output_dir'], exist_ok=True)

    # 启动服务
    print('🚀 启动 Web 服务...')
    print('📱 请在浏览器中访问: http://localhost:8080')
    print('🛑 关闭方式：')
    print('   1. 在网页上点击"关闭服务"按钮')
    print('   2. 双击"关闭服务.bat"')
    print('   3. 在任务管理器中结束进程')

    # 使用多线程模式运行
    app.run(host='127.0.0.1', port=8080, debug=False, threaded=True)
