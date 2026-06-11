"""
Web GUI 服务
提供上传 Excel、配置门槛价、实时查看进度、下载结果的功能
"""

import os
import sys
import time
import threading
import json
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 兼容 PyInstaller 打包后的路径
if getattr(sys, 'frozen', False):
    # 打包后的运行环境
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 源码运行环境
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from config import CONFIG
from utils.browser_manager import BrowserManager
from utils.jd_crawler import crawl_sku
from utils.excel_handler import read_sku_list, write_results
from utils.cleanup import auto_cleanup

# 创建 Flask 应用，指定模板目录
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))

# 全局状态
audit_status = {
    'running': False,
    'total': 0,
    'current': 0,
    'current_sku': '',
    'unqualified_count': 0,
    'logs': [],
    'result_file': None,
    'error': None,
    'need_login': False
}

# 登录等待事件
login_event = threading.Event()

# 停止标志
stop_flag = threading.Event()

# 全局浏览器实例（用于强制关闭）
current_browser = None


def add_log(message):
    """添加日志"""
    audit_status['logs'].append({
        'time': time.strftime('%H:%M:%S'),
        'message': message
    })
    # 只保留最近 100 条
    if len(audit_status['logs']) > 100:
        audit_status['logs'] = audit_status['logs'][-100:]


def run_audit_task(input_file, threshold_price):
    """在后台线程运行测价任务"""
    global audit_status

    try:
        audit_status['running'] = True
        audit_status['total'] = 0
        audit_status['current'] = 0
        audit_status['current_sku'] = ''
        audit_status['unqualified_count'] = 0
        audit_status['logs'] = []
        audit_status['result_file'] = None
        audit_status['error'] = None

        add_log('🚀 开始批量测价')
        add_log(f'📁 输入文件: {os.path.basename(input_file)}')
        add_log(f'💰 价格门槛: ¥{threshold_price}')

        # 1. 读取 SKU 列表
        add_log('📖 正在读取 Excel...')
        sku_data = read_sku_list(input_file, CONFIG['sku_column'])
        audit_status['total'] = len(sku_data)
        add_log(f'✅ 共读取 {len(sku_data)} 个 SKU')

        if len(sku_data) == 0:
            audit_status['error'] = '未找到 SKU，请检查表格格式'
            return

        # 2. 启动浏览器
        add_log('🌐 正在启动浏览器...')
        global current_browser
        browser = BrowserManager(CONFIG['auth_file'])
        current_browser = browser
        page = browser.start()

        # 3. 检查登录状态
        add_log('🔐 检查登录状态...')
        if not browser.check_login_status():
            add_log('⚠️ 登录态已失效，请登录')
            audit_status['need_login'] = True
            login_event.clear()
            # 等待前端通知继续
            login_event.wait(timeout=300)  # 最多等待5分钟
            audit_status['need_login'] = False
            if not browser.check_login_status():
                audit_status['error'] = '登录失败，请重新运行'
                browser.close(force=True)
                return
        add_log('✅ 登录状态正常')

        # 4. 创建输出目录
        if os.path.exists(CONFIG['screenshot_dir']):
            for file in os.listdir(CONFIG['screenshot_dir']):
                file_path = os.path.join(CONFIG['screenshot_dir'], file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        os.makedirs(CONFIG['screenshot_dir'], exist_ok=True)

        # 5. 批量测价
        results = []
        stop_flag.clear()
        for i, (row_index, sku) in enumerate(sku_data, 1):
            # 检查是否停止
            if stop_flag.is_set():
                add_log('🛑 测价已停止')
                break

            audit_status['current'] = i
            audit_status['current_sku'] = sku
            add_log(f'[{i}/{len(sku_data)}] 处理 SKU: {sku}')

            result = crawl_sku(
                page=page,
                sku=sku,
                screenshot_dir=CONFIG['screenshot_dir'],
                delay_min=CONFIG['delay_min'],
                delay_max=CONFIG['delay_max'],
                threshold_price=threshold_price
            )
            result['row_index'] = row_index
            results.append(result)

            if result['status'] == 'success':
                if result['price'] is not None and result['price'] < threshold_price:
                    audit_status['unqualified_count'] += 1
                    add_log(f'  🚫 低于门槛价: ¥{result["price"]}')
                else:
                    add_log(f'  ✅ 价格: ¥{result["price"]}')
            elif result['status'] == 'need_login':
                add_log('⚠️ 登录态失效，等待登录...')
                audit_status['need_login'] = True
                login_event.clear()
                # 等待前端通知继续
                login_event.wait(timeout=300)  # 最多等待5分钟
                audit_status['need_login'] = False
                if browser.check_login_status():
                    add_log('✅ 登录恢复，继续运行')
                    # 重新处理当前 SKU
                    i -= 1
                    continue
                else:
                    audit_status['error'] = '登录失败，程序中断'
                    break
            else:
                add_log(f'  ❌ 失败: {result["message"]}')

        # 6. 写入结果
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
            audit_status['result_file'] = output_path
            add_log(f'✅ 结果已保存: {os.path.basename(output_path)}')

        # 7. 检查是否因停止而结束
        if stop_flag.is_set():
            add_log('🛑 浏览器已关闭')
            browser.close(force=True)  # 强制关闭浏览器
        else:
            # 正常完成，保存登录态
            browser.close(force=False)
            add_log('🎉 测价完成！')

        current_browser = None

    except Exception as e:
        audit_status['error'] = str(e)
        add_log(f'❌ 错误: {str(e)}')
    finally:
        audit_status['running'] = False


@app.route('/')
def index():
    """首页"""
    return render_template('index.html')


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """上传 Excel 文件"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未选择文件'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'})

    if not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'error': '仅支持 .xlsx 格式'})

    # 保存到 input 目录
    upload_path = os.path.join(CONFIG['input_dir'], file.filename)
    file.save(upload_path)

    return jsonify({
        'success': True,
        'filename': file.filename,
        'path': upload_path
    })


@app.route('/api/start', methods=['POST'])
def start_audit():
    """开始测价"""
    global audit_status

    if audit_status['running']:
        return jsonify({'success': False, 'error': '已有任务正在运行'})

    data = request.json
    input_file = data.get('file')
    threshold = data.get('threshold', CONFIG['threshold_price'])

    if not input_file or not os.path.exists(input_file):
        return jsonify({'success': False, 'error': '文件不存在，请先上传'})

    # 启动后台线程
    thread = threading.Thread(
        target=run_audit_task,
        args=(input_file, float(threshold))
    )
    thread.daemon = True
    thread.start()

    return jsonify({'success': True})


@app.route('/api/status')
def get_status():
    """获取任务状态"""
    return jsonify(audit_status)


@app.route('/api/download')
def download_result():
    """下载结果文件"""
    result_file = audit_status.get('result_file')
    if not result_file or not os.path.exists(result_file):
        return jsonify({'success': False, 'error': '结果文件不存在'})

    return send_file(result_file, as_attachment=True)


@app.route('/api/list_files')
def list_files():
    """列出 input 目录下的文件"""
    files = []
    if os.path.exists(CONFIG['input_dir']):
        for f in sorted(os.listdir(CONFIG['input_dir'])):
            if f.endswith('.xlsx'):
                files.append({
                    'name': f,
                    'path': os.path.join(CONFIG['input_dir'], f)
                })
    return jsonify({'files': files})


@app.route('/api/continue', methods=['POST'])
def continue_audit():
    """用户登录完成后通知后端继续"""
    login_event.set()
    return jsonify({'success': True})


@app.route('/api/stop', methods=['POST'])
def stop_audit():
    """停止测价任务"""
    stop_flag.set()
    # 强制关闭浏览器
    global current_browser
    if current_browser:
        try:
            current_browser.close(force=True)
            add_log('🛑 浏览器已强制关闭')
        except Exception as e:
            print(f"关闭浏览器出错: {e}")
    return jsonify({'success': True})


if __name__ == '__main__':
    # 自动清理临时文件
    auto_cleanup()

    # 确保目录存在
    os.makedirs(CONFIG['input_dir'], exist_ok=True)
    os.makedirs(CONFIG['output_dir'], exist_ok=True)

    # 启动服务
    print('🚀 启动 Web 服务...')
    print('📱 请在浏览器中访问: http://localhost:5000')

    # 自动打开浏览器
    import webbrowser
    import threading
    def open_browser():
        time.sleep(1.5)
        webbrowser.open('http://localhost:8080')
    threading.Thread(target=open_browser, daemon=True).start()

    app.run(host='0.0.0.0', port=8080, debug=False)
