from __future__ import annotations

"""Unified local web entry for live operation tools."""

import os
from pathlib import Path
import signal
import sys
import threading
import time
import uuid

from flask import Flask, jsonify, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from config import DEFAULT_HOST, DEFAULT_PORT


def resolve_live_dir(
    file_path: str | Path | None = None,
    executable_path: str | Path | None = None,
    frozen: bool | None = None,
) -> Path:
    is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if is_frozen:
        return Path(executable_path or sys.executable).parent
    return Path(file_path or __file__).resolve().parents[1]


def resolve_web_root(live_dir: str | Path, file_path: str | Path | None = None) -> Path:
    live_dir = Path(live_dir)
    packaged_web_root = live_dir / "live-web"
    if packaged_web_root.exists():
        return packaged_web_root
    return Path(file_path or __file__).resolve().parent


LIVE_DIR = resolve_live_dir()
LIVE_WEB_ROOT = resolve_web_root(LIVE_DIR)
PROMOTION_BINDING_ROOT = LIVE_DIR / "live-promotion-binding"
PRICE_AUDIT_ROOT = LIVE_DIR / "live-sku-price-audit"
if str(PROMOTION_BINDING_ROOT) not in sys.path:
    sys.path.insert(0, str(PROMOTION_BINDING_ROOT))
if str(PRICE_AUDIT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRICE_AUDIT_ROOT))

from promotion_binding.service import generate_binding_files
from promotion_binding.workbook_reader import ColumnMapping, inspect_business_workbook


RUNTIME_RETENTION_DAYS = 7


def create_app(base_dir: str | Path | None = None) -> Flask:
    base_dir = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
    runtime_dir = base_dir / "runtime"
    input_dir = runtime_dir / "input" / "promotion-binding"
    output_dir = runtime_dir / "output" / "promotion-binding"
    price_input_dir = runtime_dir / "input" / "price-audit"
    price_output_dir = runtime_dir / "output" / "price-audit"
    price_screenshot_dir = price_output_dir / "screenshots"
    template_file = PROMOTION_BINDING_ROOT / "assets" / "商品上传模版（2026切片版）.xlsx"
    cleanup_roots = [runtime_dir, base_dir / "input", base_dir / "output"]

    _cleanup_old_runtime_files(cleanup_roots, retention_days=RUNTIME_RETENTION_DAYS)
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    price_input_dir.mkdir(parents=True, exist_ok=True)
    price_output_dir.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__, template_folder=str(LIVE_WEB_ROOT / "templates"))
    app.config["PROMOTION_RESULTS"] = {}
    app.config["PROMOTION_UPLOADS"] = {}
    app.config["RUNTIME_DIR"] = runtime_dir
    app.config["RUNTIME_RETENTION_DAYS"] = RUNTIME_RETENTION_DAYS
    app.config["RUNTIME_CLEANUP_ROOTS"] = cleanup_roots
    app.config["PROMOTION_INPUT_DIR"] = input_dir
    app.config["PROMOTION_OUTPUT_DIR"] = output_dir
    app.config["PROMOTION_TEMPLATE_FILE"] = template_file
    app.config["PRICE_INPUT_DIR"] = price_input_dir
    app.config["PRICE_OUTPUT_DIR"] = price_output_dir
    app.config["PRICE_SCREENSHOT_DIR"] = price_screenshot_dir
    app.config["PRICE_AUTH_FILE"] = PRICE_AUDIT_ROOT / "jd_auth.json"

    status_lock = threading.Lock()
    price_status = _initial_price_status()
    login_event = threading.Event()
    stop_flag = threading.Event()
    browser_lock = threading.Lock()
    current_browser = {"browser": None}

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/health")
    def health():
        return jsonify({"success": True})

    @app.route("/api/upload", methods=["POST"])
    def upload_price_file():
        _cleanup_runtime_for_app(app)
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return _json_error("未选择文件")

        if not uploaded.filename.lower().endswith(".xlsx"):
            return _json_error("仅支持 .xlsx 格式")

        filename = _preserve_safe_filename(uploaded.filename)
        upload_path = app.config["PRICE_INPUT_DIR"] / filename
        uploaded.save(upload_path)

        return jsonify({"success": True, "filename": filename, "path": str(upload_path)})

    @app.route("/api/start", methods=["POST"])
    def start_price_audit():
        with status_lock:
            if price_status["running"]:
                return _json_error("已有任务正在运行")

        data = request.get_json(silent=True) or {}
        input_file = _resolve_price_input_file(data.get("file"), app.config["PRICE_INPUT_DIR"])
        if not input_file:
            return _json_error("文件不存在或不在 input 目录，请先上传")

        try:
            threshold = float(data.get("threshold", 6.0))
        except (TypeError, ValueError):
            return _json_error("价格门槛必须是有效数字")

        if threshold < 0:
            return _json_error("价格门槛不能为负数")

        stop_flag.clear()
        login_event.clear()
        thread = threading.Thread(target=run_price_audit_task, args=(input_file, threshold))
        thread.daemon = False
        thread.start()
        return jsonify({"success": True})

    @app.route("/api/status")
    def get_price_status():
        with status_lock:
            return jsonify(dict(price_status))

    @app.route("/api/download")
    def download_price_result():
        with status_lock:
            result_file = price_status.get("result_file")

        if not result_file or not Path(result_file).exists():
            return _json_error("结果文件不存在", status_code=404)

        return send_file(result_file, as_attachment=True)

    @app.route("/api/continue", methods=["POST"])
    def continue_price_audit():
        login_event.set()
        add_price_log('用户点击"我已登录"，继续运行')
        return jsonify({"success": True})

    @app.route("/api/stop", methods=["POST"])
    def stop_price_audit():
        add_price_log("收到停止请求")
        stop_flag.set()
        login_event.set()
        with status_lock:
            price_status["stopping"] = True
            price_status["need_login"] = False
        return jsonify({"success": True})

    @app.route("/api/shutdown", methods=["POST"])
    def shutdown():
        threading.Thread(target=shutdown_server, daemon=True).start()
        return jsonify({"success": True})

    @app.route("/api/promotion-binding/preview", methods=["POST"])
    def preview_promotion_binding():
        _cleanup_runtime_for_app(app)
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return _json_error("未选择文件")

        if not uploaded.filename.lower().endswith(".xlsx"):
            return _json_error("仅支持 .xlsx 文件")

        task_id = uuid.uuid4().hex
        filename = _safe_xlsx_name(uploaded.filename, task_id)
        input_path = app.config["PROMOTION_INPUT_DIR"] / filename
        uploaded.save(input_path)

        try:
            inspection = inspect_business_workbook(input_path)
        except Exception as exc:
            return _json_error(str(exc), status_code=500)

        app.config["PROMOTION_UPLOADS"][task_id] = input_path
        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "filename": filename,
                "path": str(input_path),
                **_inspection_payload(inspection),
            }
        )

    @app.route("/api/promotion-binding/generate", methods=["POST"])
    def generate_promotion_binding():
        _cleanup_runtime_for_app(app)
        column_mapping = None

        if request.is_json:
            data = request.get_json(silent=True) or {}
            task_id = str(data.get("task_id") or "")
            input_path = app.config["PROMOTION_UPLOADS"].get(task_id)
            if not input_path or not Path(input_path).exists():
                return _json_error("文件不存在，请重新上传", status_code=404)
            try:
                column_mapping = _parse_column_mapping(data.get("column_mapping") or {})
            except ValueError as exc:
                return _json_error(str(exc))
        else:
            uploaded = request.files.get("file")
            if uploaded is None or not uploaded.filename:
                return _json_error("未选择文件")

            if not uploaded.filename.lower().endswith(".xlsx"):
                return _json_error("仅支持 .xlsx 文件")

            task_id = uuid.uuid4().hex
            filename = _safe_xlsx_name(uploaded.filename, task_id)
            input_path = app.config["PROMOTION_INPUT_DIR"] / filename
            uploaded.save(input_path)

        try:
            result = generate_binding_files(
                business_file=input_path,
                template_file=app.config["PROMOTION_TEMPLATE_FILE"],
                output_dir=app.config["PROMOTION_OUTPUT_DIR"] / task_id,
                column_mapping=column_mapping,
            )
        except Exception as exc:
            return _json_error(str(exc), status_code=500)

        app.config["PROMOTION_RESULTS"][task_id] = {
            "template": result.output_template_path,
            "report": result.report_path,
        }

        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "summary": {
                    "success_count": result.success_count,
                    "coupon_key_count": result.coupon_key_count,
                    "promo_id_count": result.promo_id_count,
                    "skipped_empty_count": result.skipped_empty_count,
                    "invalid_count": result.invalid_count,
                    "duplicate_count": result.duplicate_count,
                },
                "template_download_url": url_for(
                    "download_promotion_binding_result",
                    task_id=task_id,
                    kind="template",
                ),
                "report_download_url": url_for(
                    "download_promotion_binding_result",
                    task_id=task_id,
                    kind="report",
                ),
            }
        )

    @app.route("/api/promotion-binding/download/<task_id>/<kind>")
    def download_promotion_binding_result(task_id, kind):
        result = app.config["PROMOTION_RESULTS"].get(task_id)
        if not result or kind not in result:
            return _json_error("结果文件不存在", status_code=404)

        path = Path(result[kind])
        if not path.exists():
            return _json_error("结果文件不存在", status_code=404)

        return send_file(path, as_attachment=True)

    def add_price_log(message: str):
        with status_lock:
            price_status["logs"].append({"time": time.strftime("%H:%M:%S"), "message": message})
            if len(price_status["logs"]) > 200:
                price_status["logs"] = price_status["logs"][-200:]
        print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def wait_for_web_login(browser):
        add_price_log("登录态已失效，请登录")
        with status_lock:
            price_status["need_login"] = True
        login_event.clear()

        try:
            browser.open_login_page()
        except Exception as exc:
            add_price_log(f"打开登录页失败: {exc}")

        wait_count = 0
        while not login_event.is_set() and wait_count < 120:
            login_event.wait(timeout=5)
            wait_count += 1
            if wait_count % 6 == 0:
                add_price_log(f"仍在等待用户登录... ({wait_count * 5}秒)")
            if stop_flag.is_set():
                add_price_log("测价已停止")
                break

        with status_lock:
            price_status["need_login"] = False

        if stop_flag.is_set():
            return False

        add_price_log("重新检查登录状态...")
        is_logged_in = browser.check_login_status()
        add_price_log(f"登录状态检查结果: {'已登录' if is_logged_in else '未登录'}")

        if not is_logged_in:
            add_price_log("登录失败")
            return False

        browser.save_auth_state()
        add_price_log("登录恢复，继续运行")
        return True

    def run_price_audit_task(input_file: Path, threshold_price: float):
        browser = None
        try:
            from utils.audit_runner import run_sku_batch
            from utils.browser_manager import BrowserManager
            from utils.excel_handler import read_sku_list, write_results
            from utils.jd_crawler import crawl_sku

            with status_lock:
                price_status.clear()
                price_status.update(_initial_price_status())
                price_status["running"] = True

            add_price_log("开始批量测价")
            add_price_log(f"输入文件: {input_file.name}")
            add_price_log(f"价格门槛: ¥{threshold_price}")

            try:
                sku_data = read_sku_list(str(input_file), "商品SKU")
            except Exception as exc:
                with status_lock:
                    price_status["error"] = str(exc)
                add_price_log(str(exc))
                return

            with status_lock:
                price_status["total"] = len(sku_data)
            add_price_log(f"共读取 {len(sku_data)} 个 SKU")

            if not sku_data:
                with status_lock:
                    price_status["error"] = "未找到 SKU，请检查表格格式"
                return

            app.config["PRICE_SCREENSHOT_DIR"].mkdir(parents=True, exist_ok=True)
            for file_path in app.config["PRICE_SCREENSHOT_DIR"].glob("*"):
                if file_path.is_file():
                    file_path.unlink()

            browser = BrowserManager(str(app.config["PRICE_AUTH_FILE"]))
            with browser_lock:
                current_browser["browser"] = browser
            page = browser.start()

            add_price_log("检查登录状态...")
            is_logged_in = browser.check_login_status()
            add_price_log(f"登录状态检查结果: {'已登录' if is_logged_in else '未登录'}")
            if not is_logged_in and not wait_for_web_login(browser):
                with status_lock:
                    price_status["error"] = "登录失败，请重新运行"
                return

            def on_item_start(i, total, row_index, sku):
                with status_lock:
                    price_status["current"] = i
                    price_status["current_sku"] = sku
                add_price_log(f"[{i}/{total}] 处理 SKU: {sku}")

            def crawl_one(row_index, sku):
                return crawl_sku(
                    page=page,
                    sku=sku,
                    screenshot_dir=str(app.config["PRICE_SCREENSHOT_DIR"]),
                    delay_min=1,
                    delay_max=3,
                    threshold_price=threshold_price,
                    should_stop=stop_flag.is_set,
                )

            def on_result(result):
                if result["status"] == "success":
                    with status_lock:
                        price_status["success_count"] += 1
                    if result["price"] is not None and result["price"] < threshold_price:
                        with status_lock:
                            price_status["unqualified_count"] += 1
                        add_price_log(f"低于门槛价: ¥{result['price']}")
                    else:
                        add_price_log(f"价格: ¥{result['price']}")
                else:
                    with status_lock:
                        price_status["fail_count"] += 1
                    add_price_log(f"失败: {result.get('message', '')}")

            batch = run_sku_batch(
                sku_data=sku_data,
                crawl_func=crawl_one,
                recover_login_func=lambda: wait_for_web_login(browser),
                stop_event=stop_flag,
                on_item_start=on_item_start,
                on_result=on_result,
                on_login_required=lambda row_index, sku, result: add_price_log(f"SKU {sku} 需要重新登录"),
            )

            if batch.results:
                add_price_log("正在写入结果...")
                output_path = write_results(
                    file_path=str(input_file),
                    results=batch.results,
                    threshold_price=threshold_price,
                    output_dir=str(app.config["PRICE_OUTPUT_DIR"]),
                    sku_column="商品SKU",
                    price_column="价格",
                    image_column="图片",
                    remark_column="备注",
                )
                with status_lock:
                    price_status["result_file"] = output_path
                add_price_log(f"结果已保存: {Path(output_path).name}")

            if batch.stopped or stop_flag.is_set():
                add_price_log("测价已停止")
            elif batch.login_failed:
                with status_lock:
                    price_status["error"] = "登录失败，程序中断"
                add_price_log("登录失败，程序中断")
            else:
                add_price_log("测价完成")

        except Exception as exc:
            with status_lock:
                price_status["error"] = str(exc)
            add_price_log(f"错误: {exc}")
        finally:
            if browser:
                try:
                    add_price_log("正在关闭浏览器...")
                    browser.close(force=True)
                    add_price_log("浏览器已关闭")
                except Exception as exc:
                    add_price_log(f"关闭浏览器出错: {exc}")

            with browser_lock:
                current_browser["browser"] = None
            with status_lock:
                price_status["running"] = False
                price_status["stopping"] = False
                price_status["need_login"] = False

    def shutdown_server():
        add_price_log("正在关闭服务...")
        stop_flag.set()
        login_event.set()
        with browser_lock:
            browser = current_browser.get("browser")
            if browser:
                try:
                    browser.close(force=True)
                except Exception:
                    pass
                current_browser["browser"] = None
        os.kill(os.getpid(), signal.SIGTERM)

    return app


def _json_error(message: str, status_code: int = 400):
    return jsonify({"success": False, "error": message}), status_code


def _initial_price_status():
    return {
        "running": False,
        "total": 0,
        "current": 0,
        "current_sku": "",
        "success_count": 0,
        "fail_count": 0,
        "unqualified_count": 0,
        "logs": [],
        "result_file": None,
        "error": None,
        "need_login": False,
        "stopping": False,
    }


def _cleanup_runtime_for_app(app: Flask):
    _cleanup_old_runtime_files(
        app.config["RUNTIME_CLEANUP_ROOTS"],
        retention_days=app.config["RUNTIME_RETENTION_DAYS"],
    )
    app.config["PROMOTION_INPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["PROMOTION_OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["PRICE_INPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["PRICE_OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)


def _cleanup_old_runtime_files(roots: list[Path], retention_days: int, now: float | None = None):
    cutoff = (now if now is not None else time.time()) - retention_days * 24 * 60 * 60
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue

        for path in root.rglob("*"):
            try:
                if (path.is_file() or path.is_symlink()) and path.stat().st_mtime < cutoff:
                    path.unlink()
            except FileNotFoundError:
                continue

        dirs = [path for path in root.rglob("*") if path.is_dir()]
        for path in sorted(dirs, key=lambda item: len(item.parts), reverse=True):
            try:
                path.rmdir()
            except OSError:
                pass


def _resolve_price_input_file(file_path, input_dir: Path):
    if not file_path:
        return None
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = input_dir / candidate
    candidate = candidate.resolve()
    input_dir = input_dir.resolve()
    try:
        candidate.relative_to(input_dir)
    except ValueError:
        return None
    if not candidate.is_file() or candidate.suffix.lower() != ".xlsx":
        return None
    return candidate


def _safe_xlsx_name(filename: str, task_id: str) -> str:
    safe = secure_filename(filename) or "upload.xlsx"
    if not safe.lower().endswith(".xlsx"):
        safe = f"{safe}.xlsx"
    return f"{task_id}_{safe}"


def _preserve_safe_filename(filename: str) -> str:
    name = (filename or "").replace("\\", "/").split("/")[-1].strip()
    if not name or name in {".", ".."}:
        return f"{uuid.uuid4().hex}.xlsx"
    if not name.lower().endswith(".xlsx"):
        name = f"{name}.xlsx"
    return name


def _inspection_payload(inspection):
    return {
        "columns": [
            {
                "index": column.index,
                "header": column.header,
                "sample_values": column.sample_values,
            }
            for column in inspection.columns
        ],
        "suggested_mapping": _mapping_payload(inspection.suggested_mapping),
    }


def _mapping_payload(mapping: ColumnMapping):
    return {
        "sku_col": mapping.sku_col,
        "code_col": mapping.code_col,
        "product_name_col": mapping.product_name_col,
    }


def _parse_column_mapping(raw_mapping) -> ColumnMapping:
    sku_col = _parse_column_value(raw_mapping.get("sku_col"))
    code_col = _parse_column_value(raw_mapping.get("code_col"))
    product_name_col = _parse_column_value(raw_mapping.get("product_name_col"))
    if sku_col is None:
        raise ValueError("请选择 SKU 列")
    if code_col is None:
        raise ValueError("请选择券码/促销编码列")
    return ColumnMapping(sku_col=sku_col, code_col=code_col, product_name_col=product_name_col)


def _parse_column_value(value):
    if value in (None, ""):
        return None
    try:
        column_index = int(value)
    except (TypeError, ValueError):
        raise ValueError("列选择不是有效数字")
    if column_index < 1:
        raise ValueError("列选择超出表格范围")
    return column_index


if __name__ == "__main__":
    app = create_app()
    print(f"直播本地工具已启动: http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    app.run(host=DEFAULT_HOST, port=DEFAULT_PORT, debug=False, threaded=True)
