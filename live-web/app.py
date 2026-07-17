from __future__ import annotations

"""Unified local web entry for live operation tools."""

import os
from datetime import date, datetime
from pathlib import Path
import signal
import sys
import threading
import time
import uuid
from zipfile import ZIP_DEFLATED, ZipFile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from flask import Flask, jsonify, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from config import DEFAULT_HOST, DEFAULT_PORT
from usage_reporter import create_usage_reporter


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
ROOM_CREATOR_ROOT = LIVE_DIR / "live-room-creator"
BIGSCREEN_CAPTURE_ROOT = LIVE_DIR / "live-bigscreen-capture"
PRODUCT_SELECTION_ROOT = LIVE_DIR / "product-selection-agent"
if str(PROMOTION_BINDING_ROOT) not in sys.path:
    sys.path.insert(0, str(PROMOTION_BINDING_ROOT))
if str(PRICE_AUDIT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRICE_AUDIT_ROOT))
if str(ROOM_CREATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(ROOM_CREATOR_ROOT))
if str(BIGSCREEN_CAPTURE_ROOT) not in sys.path:
    sys.path.insert(0, str(BIGSCREEN_CAPTURE_ROOT))
if PRODUCT_SELECTION_ROOT.exists() and str(PRODUCT_SELECTION_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCT_SELECTION_ROOT))


# fmt: off
from room_creator import config as room_creator_config
from room_creator.excel_reader import ColumnMapping as RoomColumnMapping
from room_creator import BatchRunner, RoomCreatorBrowser, inspect_workbook
from promotion_binding.workbook_reader import ColumnMapping, inspect_business_workbook
from promotion_binding.service import generate_binding_files
from bigscreen_capture.schedule import PlannedSlot, build_hour_options, build_planned_slots
from bigscreen_capture.service import (
    capture_once as capture_bigscreen_once,
    write_capture_bundle as write_bigscreen_capture_bundle,
)
from bigscreen_capture.url_parser import BigscreenUrlError, parse_bigscreen_url
from product_selection_agent.runtime import RunContext as ProductSelectionRunContext
from product_selection_agent.runtime import SelectionCancelled
from product_selection_agent.service import execute_selection as execute_product_selection
# fmt: on
RUNTIME_RETENTION_DAYS = 2


def _load_price_audit_concurrent_workers() -> int:
    """从 live-sku-price-audit/config.py 读取并发数，保持统一配置入口。"""
    try:
        import importlib.util

        config_path = PRICE_AUDIT_ROOT / "config.py"
        spec = importlib.util.spec_from_file_location("price_audit_config", config_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return max(1, int(module.CONFIG.get("concurrent_workers", 5)))
    except Exception:
        return 5


PRICE_AUDIT_CONCURRENT_WORKERS = _load_price_audit_concurrent_workers()


def parse_sku_input(raw):
    """解析页面输入的 SKU 字符串，支持英文/中文逗号和分号、换行等分隔符。"""
    if not raw or not isinstance(raw, str):
        return []
    separators = (",", ";", "，", "；", "\n", "\r", "\t")
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


_DEFAULT_USAGE_REPORTER = object()


def create_app(
    base_dir: str | Path | None = None,
    usage_reporter=_DEFAULT_USAGE_REPORTER,
) -> Flask:
    base_dir_provided = base_dir is not None
    base_dir = (
        Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
    )
    runtime_dir = base_dir / "runtime"
    input_dir = runtime_dir / "input" / "promotion-binding"
    output_dir = runtime_dir / "output" / "promotion-binding"
    price_input_dir = runtime_dir / "input" / "price-audit"
    price_output_dir = runtime_dir / "output" / "price-audit"
    price_screenshot_dir = price_output_dir / "screenshots"
    room_input_dir = runtime_dir / "input" / "room-creator"
    room_output_dir = runtime_dir / "output" / "room-creator"
    bigscreen_output_dir = runtime_dir / "output" / "bigscreen-capture"
    product_selection_output_dir = runtime_dir / "output" / "product-selection"
    template_file = (
        PROMOTION_BINDING_ROOT / "assets" / "商品上传模版（2026切片版）.xlsx"
    )
    cleanup_roots = [runtime_dir, base_dir / "input", base_dir / "output"]

    _cleanup_old_runtime_files(cleanup_roots, retention_days=RUNTIME_RETENTION_DAYS)
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    price_input_dir.mkdir(parents=True, exist_ok=True)
    price_output_dir.mkdir(parents=True, exist_ok=True)
    room_input_dir.mkdir(parents=True, exist_ok=True)
    room_output_dir.mkdir(parents=True, exist_ok=True)
    bigscreen_output_dir.mkdir(parents=True, exist_ok=True)
    product_selection_output_dir.mkdir(parents=True, exist_ok=True)

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
    app.config["ROOM_INPUT_DIR"] = room_input_dir
    app.config["ROOM_OUTPUT_DIR"] = room_output_dir
    app.config["ROOM_CREATOR_RESULTS"] = {}
    app.config["ROOM_CREATOR_MAPPINGS"] = {}
    app.config["BIGSCREEN_OUTPUT_DIR"] = bigscreen_output_dir
    app.config["BIGSCREEN_RESULTS"] = {}
    app.config["BIGSCREEN_AUTH_FILE"] = PRICE_AUDIT_ROOT / "jd_auth.json"
    app.config["PRODUCT_SELECTION_OUTPUT_DIR"] = product_selection_output_dir
    app.config["PRODUCT_SELECTION_RESULTS"] = {}
    if usage_reporter is _DEFAULT_USAGE_REPORTER:
        usage_reporter = create_usage_reporter(enabled=not base_dir_provided)
    app.config["USAGE_REPORTER"] = usage_reporter

    status_lock = threading.Lock()
    price_status = _initial_price_status()
    login_event = threading.Event()
    stop_flag = threading.Event()
    browser_lock = threading.Lock()
    current_browser = {"browser": None}
    room_status_lock = threading.Lock()
    room_creator_status = _initial_room_creator_status()
    room_stop_flag = threading.Event()
    room_login_event = threading.Event()
    room_browser_lock = threading.Lock()
    current_room_browser = {"browser": None}
    bigscreen_status_lock = threading.Lock()
    bigscreen_status = _initial_bigscreen_status()
    bigscreen_stop_flag = threading.Event()
    bigscreen_login_event = threading.Event()
    product_selection_status_lock = threading.Lock()
    product_selection_status = _initial_product_selection_status()
    product_selection_stop_event = threading.Event()

    def close_current_browsers():
        with browser_lock:
            browsers = current_browser.get("browser")
            current_browser["browser"] = None

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

    def close_current_room_browser():
        with room_browser_lock:
            browser = current_room_browser.get("browser")
            current_room_browser["browser"] = None
        if browser:
            try:
                browser.close(force=True)
            except Exception:
                pass
        return 1 if browser else 0

    def report_usage(tool_code: str, action: str, **kwargs):
        reporter = app.config.get("USAGE_REPORTER")
        if reporter is None:
            return
        try:
            reporter.report_async(tool_code=tool_code, action=action, **kwargs)
        except Exception as exc:
            print(f"[{time.strftime('%H:%M:%S')}] 使用统计上报失败: {exc}")

    @app.route("/")
    def index():
        report_usage("live_web", "page_view", status="success")
        return render_template("index.html")

    @app.route("/api/health")
    def health():
        return jsonify({"success": True})

    @app.route("/api/product-selection/status")
    def product_selection_task_status():
        with product_selection_status_lock:
            return jsonify(_copy_product_selection_status(product_selection_status))

    @app.route("/api/product-selection/start", methods=["POST"])
    def start_product_selection():
        data = request.get_json(silent=True) or {}
        headless = bool(data.get("headless", True))
        allow_partial = bool(data.get("allow_partial", False))
        with product_selection_status_lock:
            if product_selection_status["running"]:
                return _json_error("选品任务正在运行，请等待完成或先停止", 409)

            _cleanup_runtime_for_app(app)
            task_id = uuid.uuid4().hex
            task_dir = app.config["PRODUCT_SELECTION_OUTPUT_DIR"] / task_id
            product_selection_stop_event.clear()
            product_selection_status.clear()
            product_selection_status.update(
                {
                    **_initial_product_selection_status(),
                    "running": True,
                    "stage": "running",
                    "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "task_id": task_id,
                }
            )

        report_usage(
            "product_selection",
            "task_start",
            task_id=task_id,
            status="started",
        )

        def append_product_selection_log(message: str):
            with product_selection_status_lock:
                product_selection_status["logs"].append(str(message))
                product_selection_status["logs"] = product_selection_status["logs"][-1000:]

        def run_product_selection_task():
            try:
                result = execute_product_selection(
                    output_dir=task_dir,
                    headless=headless,
                    allow_partial=allow_partial,
                    context=ProductSelectionRunContext(
                        log_callback=append_product_selection_log,
                        stop_event=product_selection_stop_event,
                    ),
                )
                summary = _product_selection_summary(result.payload)
                app.config["PRODUCT_SELECTION_RESULTS"][task_id] = {
                    "excel": Path(result.excel_path),
                }
                warning = not (
                    summary.get("fetch_complete") and summary.get("ai_complete")
                )
                with product_selection_status_lock:
                    product_selection_status.update(
                        {
                            "running": False,
                            "stopping": False,
                            "stage": "completed_with_warnings" if warning else "completed",
                            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                            "success": True,
                            "summary": summary,
                            "excel_download_url": f"/api/product-selection/download/{task_id}",
                        }
                    )
                report_usage(
                    "product_selection",
                    "task_finish",
                    task_id=task_id,
                    status="warning" if warning else "success",
                    extra=summary,
                )
            except SelectionCancelled as exc:
                with product_selection_status_lock:
                    product_selection_status.update(
                        {
                            "running": False,
                            "stopping": False,
                            "stage": "cancelled",
                            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                            "success": False,
                            "error": str(exc),
                        }
                    )
                report_usage(
                    "product_selection",
                    "task_finish",
                    task_id=task_id,
                    status="cancelled",
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                append_product_selection_log(f"[main] 选品任务失败: {error}")
                with product_selection_status_lock:
                    product_selection_status.update(
                        {
                            "running": False,
                            "stopping": False,
                            "stage": "failed",
                            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                            "success": False,
                            "error": error,
                        }
                    )
                report_usage(
                    "product_selection",
                    "task_finish",
                    task_id=task_id,
                    status="failed",
                    error_code=type(exc).__name__,
                )

        threading.Thread(
            target=run_product_selection_task,
            name=f"product-selection-{task_id[:8]}",
            daemon=True,
        ).start()
        return jsonify({"success": True, "task_id": task_id}), 202

    @app.route("/api/product-selection/stop", methods=["POST"])
    def stop_product_selection():
        with product_selection_status_lock:
            if not product_selection_status["running"]:
                return _json_error("当前没有正在运行的选品任务", 409)
            product_selection_stop_event.set()
            product_selection_status["stopping"] = True
            product_selection_status["stage"] = "stopping"
            product_selection_status["logs"].append("[main] 收到停止请求")
            payload = _copy_product_selection_status(product_selection_status)
        return jsonify(payload)

    @app.route("/api/product-selection/download/<task_id>")
    def download_product_selection(task_id: str):
        result = app.config["PRODUCT_SELECTION_RESULTS"].get(task_id)
        if not result:
            return _json_error("选品任务不存在或结果已清理", 404)
        path = Path(result.get("excel", ""))
        if not path.is_file():
            return _json_error("选品结果文件不存在或已清理", 404)
        report_usage(
            "product_selection",
            "download",
            task_id=task_id,
            status="success",
            extra={"kind": "excel"},
        )
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.route("/api/bigscreen-capture/preview", methods=["POST"])
    def preview_bigscreen_capture():
        _cleanup_runtime_for_app(app)
        data = request.get_json(silent=True) or {}
        try:
            parsed = parse_bigscreen_url(data.get("url", ""))
        except BigscreenUrlError as exc:
            return _json_error(str(exc))
        return jsonify(
            {
                "success": True,
                "room_id": parsed.room_id,
                "hour_options": build_hour_options(10, 24, interval_minutes=30),
            }
        )

    @app.route("/api/bigscreen-capture/capture-now", methods=["POST"])
    def capture_bigscreen_now():
        with bigscreen_status_lock:
            if bigscreen_status["running"]:
                return _json_error("已有蓝屏截图任务正在运行")

        _cleanup_runtime_for_app(app)
        data = request.get_json(silent=True) or {}
        try:
            parsed = parse_bigscreen_url(data.get("url", ""))
        except BigscreenUrlError as exc:
            return _json_error(str(exc))

        task_id = uuid.uuid4().hex
        show_browser = bool(data.get("show_browser", False))
        slot = PlannedSlot(label="立即截图", run_at=datetime.now(), status="pending")
        bigscreen_stop_flag.clear()
        bigscreen_login_event.clear()
        with bigscreen_status_lock:
            bigscreen_status.update(_initial_bigscreen_status())
            bigscreen_status["running"] = True
            bigscreen_status["total"] = 1
            bigscreen_status["task_id"] = task_id
            bigscreen_status["room_id"] = parsed.room_id
            bigscreen_status["planned_slots"] = [slot.label]
            bigscreen_status["current_slot"] = slot.label
        report_usage(
            "bigscreen_capture",
            "task_start",
            task_id=task_id,
            item_count=1,
            status="started",
            extra={
                "room_id": parsed.room_id,
                "mode": "capture_now",
                "planned_slots": [slot.label],
                "show_browser": show_browser,
            },
        )

        thread = threading.Thread(
            target=run_bigscreen_capture_task,
            args=(task_id, parsed.url, [slot], show_browser),
        )
        thread.daemon = False
        thread.start()
        return jsonify({"success": True, "task_id": task_id, "room_id": parsed.room_id})

    @app.route("/api/bigscreen-capture/download/<task_id>")
    def download_bigscreen_capture(task_id):
        zip_path = _resolve_bigscreen_result_zip(app, task_id)
        if not zip_path:
            return _json_error("结果文件不存在", status_code=404)
        result_metadata = app.config["BIGSCREEN_RESULTS"].get(task_id) or {}
        with bigscreen_status_lock:
            if result_metadata:
                room_id = result_metadata.get("room_id") or bigscreen_status.get("room_id")
                room_name = result_metadata.get("room_name", "")
            else:
                room_id = bigscreen_status.get("room_id")
                room_name = bigscreen_status.get("room_name", "")
        report_usage(
            "bigscreen_capture",
            "download",
            task_id=task_id,
            status="success",
            extra={
                "room_id": room_id,
                "room_name": room_name,
                "kind": "zip",
                "recovered": task_id not in app.config["BIGSCREEN_RESULTS"],
            },
        )
        return send_file(zip_path, as_attachment=True)

    @app.route("/api/bigscreen-capture/start", methods=["POST"])
    def start_bigscreen_capture():
        with bigscreen_status_lock:
            if bigscreen_status["running"]:
                return _json_error("已有蓝屏截图任务正在运行")

        _cleanup_runtime_for_app(app)
        data = request.get_json(silent=True) or {}
        try:
            parsed = parse_bigscreen_url(data.get("url", ""))
        except BigscreenUrlError as exc:
            return _json_error(str(exc))

        hour_slots = data.get("hour_slots") or []
        if not hour_slots:
            return _json_error("请选择至少一个时间点")

        capture_date_raw = data.get("capture_date") or date.today().isoformat()
        try:
            capture_date = date.fromisoformat(capture_date_raw)
            planned_slots = build_planned_slots(capture_date, list(hour_slots))
        except Exception:
            return _json_error("时间点配置无效")

        pending_slots = [slot for slot in planned_slots if slot.status == "pending"]
        if not pending_slots:
            return _json_error("选择的时间点都已过期")

        task_id = uuid.uuid4().hex
        show_browser = bool(data.get("show_browser", False))
        bigscreen_stop_flag.clear()
        bigscreen_login_event.clear()
        with bigscreen_status_lock:
            bigscreen_status.update(_initial_bigscreen_status())
            bigscreen_status["running"] = True
            bigscreen_status["total"] = len(pending_slots)
            bigscreen_status["task_id"] = task_id
            bigscreen_status["room_id"] = parsed.room_id
            bigscreen_status["planned_slots"] = [slot.label for slot in planned_slots]
            bigscreen_status["missed_slots"] = [
                slot.label for slot in planned_slots if slot.status == "missed"
            ]
        report_usage(
            "bigscreen_capture",
            "task_start",
            task_id=task_id,
            item_count=len(pending_slots),
            status="started",
            extra={
                "room_id": parsed.room_id,
                "mode": "scheduled",
                "planned_slots": [slot.label for slot in planned_slots],
                "pending_slots": [slot.label for slot in pending_slots],
                "missed_slots": [slot.label for slot in planned_slots if slot.status == "missed"],
                "show_browser": show_browser,
            },
        )

        thread = threading.Thread(
            target=run_bigscreen_capture_task,
            args=(task_id, parsed.url, pending_slots, show_browser),
        )
        thread.daemon = False
        thread.start()
        return jsonify({"success": True, "task_id": task_id})

    @app.route("/api/bigscreen-capture/status")
    def get_bigscreen_capture_status():
        with bigscreen_status_lock:
            return jsonify(dict(bigscreen_status))

    @app.route("/api/bigscreen-capture/continue", methods=["POST"])
    def continue_bigscreen_capture():
        bigscreen_login_event.set()
        add_bigscreen_log('用户点击"我已登录"，继续运行')
        return jsonify({"success": True})

    @app.route("/api/bigscreen-capture/stop", methods=["POST"])
    def stop_bigscreen_capture():
        add_bigscreen_log("收到停止请求")
        bigscreen_stop_flag.set()
        bigscreen_login_event.set()
        with bigscreen_status_lock:
            bigscreen_status["stopping"] = True
            bigscreen_status["need_login"] = False
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
        report_usage(
            "sku_price_audit",
            "upload",
            status="success",
            extra={"filename": filename},
        )

        return jsonify(
            {"success": True, "filename": filename, "path": str(upload_path)}
        )

    @app.route("/api/start", methods=["POST"])
    def start_price_audit():
        with status_lock:
            if price_status["running"]:
                return _json_error("已有任务正在运行")

        data = request.get_json(silent=True) or {}
        input_file = _resolve_price_input_file(
            data.get("file"), app.config["PRICE_INPUT_DIR"]
        )
        if not input_file:
            return _json_error("文件不存在或不在 input 目录，请先上传")

        try:
            threshold = float(data.get("threshold", 6.0))
        except (TypeError, ValueError):
            return _json_error("价格门槛必须是有效数字")

        if threshold < 0:
            return _json_error("价格门槛不能为负数")

        show_browser = bool(data.get("show_browser"))
        task_id = uuid.uuid4().hex
        app.config["PRICE_ACTIVE_TASK_ID"] = task_id

        try:
            concurrent_workers = int(
                data.get("concurrent_workers", PRICE_AUDIT_CONCURRENT_WORKERS)
            )
        except (TypeError, ValueError):
            concurrent_workers = PRICE_AUDIT_CONCURRENT_WORKERS
        concurrent_workers = max(1, min(10, concurrent_workers))

        stop_flag.clear()
        login_event.clear()
        report_usage(
            "sku_price_audit",
            "task_start",
            task_id=task_id,
            status="started",
            extra={
                "input_mode": "file",
                "threshold_price": threshold,
                "show_browser": show_browser,
                "concurrent_workers": concurrent_workers,
            },
        )
        thread = threading.Thread(
            target=run_price_audit_task,
            args=(input_file, threshold, show_browser, concurrent_workers),
            kwargs={"cleanup_input": True},
        )
        thread.daemon = False
        thread.start()
        return jsonify({"success": True, "task_id": task_id})

    @app.route("/api/start-from-skus", methods=["POST"])
    def start_price_audit_from_skus():
        with status_lock:
            if price_status["running"]:
                return _json_error("已有任务正在运行")

        data = request.get_json(silent=True) or {}
        skus_raw = data.get("skus", "")

        try:
            threshold = float(data.get("threshold", 6.0))
        except (TypeError, ValueError):
            return _json_error("价格门槛必须是有效数字")

        if threshold < 0:
            return _json_error("价格门槛不能为负数")

        sku_list = parse_sku_input(skus_raw)
        if not sku_list:
            return _json_error("请输入有效的 SKU")

        try:
            concurrent_workers = int(
                data.get("concurrent_workers", PRICE_AUDIT_CONCURRENT_WORKERS)
            )
        except (TypeError, ValueError):
            concurrent_workers = PRICE_AUDIT_CONCURRENT_WORKERS
        concurrent_workers = max(1, min(10, concurrent_workers))

        show_browser = bool(data.get("show_browser"))
        task_id = uuid.uuid4().hex
        app.config["PRICE_ACTIVE_TASK_ID"] = task_id

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        input_file = (
            app.config["PRICE_INPUT_DIR"]
            / f"页面输入SKU_{timestamp}_{uuid.uuid4().hex[:8]}.xlsx"
        )
        try:
            from utils.excel_handler import create_sku_input_file

            create_sku_input_file(sku_list, str(input_file))
        except Exception as e:
            return _json_error(f"生成输入文件失败: {e}")

        stop_flag.clear()
        login_event.clear()
        add_price_log(f"页面输入 SKU {len(sku_list)} 个，已生成临时输入文件")
        report_usage(
            "sku_price_audit",
            "task_start",
            task_id=task_id,
            item_count=len(sku_list),
            status="started",
            extra={
                "input_mode": "manual_skus",
                "threshold_price": threshold,
                "show_browser": show_browser,
                "concurrent_workers": concurrent_workers,
            },
        )

        thread = threading.Thread(
            target=run_price_audit_task,
            args=(input_file, threshold, show_browser, concurrent_workers),
            kwargs={"cleanup_input": True},
        )
        thread.daemon = False
        thread.start()
        return jsonify({"success": True, "count": len(sku_list), "task_id": task_id})

    @app.route("/api/status")
    def get_price_status():
        with status_lock:
            return jsonify(dict(price_status))

    @app.route("/api/download")
    def download_price_result():
        with status_lock:
            result_file = price_status.get("result_file")
            task_id = price_status.get("task_id")

        if not result_file or not Path(result_file).exists():
            return _json_error("结果文件不存在", status_code=404)

        report_usage(
            "sku_price_audit",
            "download",
            task_id=task_id,
            status="success",
            extra={"filename": Path(result_file).name},
        )
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
        closed_count = close_current_browsers()
        if closed_count:
            add_price_log(f"已关闭 {closed_count} 个测价浏览器，正在退出当前步骤")
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
        report_usage(
            "promotion_binding",
            "upload",
            task_id=task_id,
            status="success",
            extra={"filename": filename},
        )

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
        enable_selling_point = False

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
            enable_selling_point = bool(data.get("enable_selling_point"))
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

        started_monotonic = time.monotonic()
        report_usage(
            "promotion_binding",
            "task_start",
            task_id=task_id,
            status="started",
            extra={"enable_selling_point": enable_selling_point},
        )
        try:
            result = generate_binding_files(
                business_file=input_path,
                template_file=app.config["PROMOTION_TEMPLATE_FILE"],
                output_dir=app.config["PROMOTION_OUTPUT_DIR"] / task_id,
                column_mapping=column_mapping,
                enable_selling_point=enable_selling_point,
            )
        except Exception as exc:
            report_usage(
                "promotion_binding",
                "task_finish",
                task_id=task_id,
                fail_count=1,
                duration_ms=int((time.monotonic() - started_monotonic) * 1000),
                status="failed",
                extra={
                    "enable_selling_point": enable_selling_point,
                    "error": str(exc),
                },
            )
            return _json_error(str(exc), status_code=500)

        app.config["PROMOTION_RESULTS"][task_id] = {
            "template": result.output_template_path,
            "report": result.report_path,
        }

        messages = []
        if enable_selling_point and not result.selling_point_column_found:
            messages.append("未识别到短卖点列")

        fail_count = result.invalid_count + result.duplicate_count
        item_count = result.success_count + result.skipped_empty_count + fail_count
        report_usage(
            "promotion_binding",
            "task_finish",
            task_id=task_id,
            item_count=item_count,
            success_count=result.success_count,
            fail_count=fail_count,
            duration_ms=int((time.monotonic() - started_monotonic) * 1000),
            status="success" if fail_count == 0 else "partial_success",
            extra={
                "coupon_key_count": result.coupon_key_count,
                "promo_id_count": result.promo_id_count,
                "selling_point_count": result.selling_point_count,
                "skipped_empty_count": result.skipped_empty_count,
                "invalid_count": result.invalid_count,
                "duplicate_count": result.duplicate_count,
                "enable_selling_point": enable_selling_point,
                "messages": messages,
            },
        )
        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "messages": messages,
                "summary": {
                    "success_count": result.success_count,
                    "coupon_key_count": result.coupon_key_count,
                    "promo_id_count": result.promo_id_count,
                    "selling_point_count": result.selling_point_count,
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

        report_usage(
            "promotion_binding",
            "download",
            task_id=task_id,
            status="success",
            extra={"kind": kind, "filename": path.name},
        )
        return send_file(path, as_attachment=True)

    @app.route("/api/room-creator/preview", methods=["POST"])
    def preview_room_creator():
        _cleanup_runtime_for_app(app)
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return _json_error("未选择文件")

        if not uploaded.filename.lower().endswith(".xlsx"):
            return _json_error("仅支持 .xlsx 文件")

        task_id = uuid.uuid4().hex
        filename = _safe_xlsx_name(uploaded.filename, task_id)
        input_path = app.config["ROOM_INPUT_DIR"] / filename
        uploaded.save(input_path)
        report_usage(
            "room_creator",
            "upload",
            task_id=task_id,
            status="success",
            extra={"filename": filename},
        )

        try:
            mapping, headers = inspect_workbook(input_path)
        except Exception as exc:
            return _json_error(str(exc), status_code=500)

        with room_status_lock:
            app.config["ROOM_CREATOR_UPLOADS"] = app.config.get(
                "ROOM_CREATOR_UPLOADS", {}
            )
            app.config["ROOM_CREATOR_UPLOADS"][task_id] = input_path
            app.config["ROOM_CREATOR_MAPPINGS"] = app.config.get(
                "ROOM_CREATOR_MAPPINGS", {}
            )
            app.config["ROOM_CREATOR_MAPPINGS"][task_id] = mapping

        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "filename": filename,
                "path": str(input_path),
                "columns": headers,
                "mapping": {
                    "title_col": mapping.title_col,
                    "cover_col": mapping.cover_col,
                    "start_time_col": mapping.start_time_col,
                    "live_form_col": mapping.live_form_col,
                    "live_direction_col": mapping.live_direction_col,
                    "live_location_col": mapping.live_location_col,
                    "live_category_col": mapping.live_category_col,
                },
                "defaults": {
                    "cover": "使用默认封面",
                    "live_form": room_creator_config.DEFAULT_LIVE_FORM,
                    "live_direction": room_creator_config.DEFAULT_LIVE_DIRECTION,
                    "live_location": room_creator_config.DEFAULT_LIVE_LOCATION,
                    "live_category": room_creator_config.DEFAULT_LIVE_CATEGORY,
                },
            }
        )

    @app.route("/api/room-creator/start", methods=["POST"])
    def start_room_creator():
        with room_status_lock:
            if room_creator_status["running"]:
                return _json_error("已有任务正在运行")

        data = request.get_json(silent=True) or {}
        task_id = str(data.get("task_id") or "")
        input_path = app.config.get("ROOM_CREATOR_UPLOADS", {}).get(task_id)
        if not input_path or not Path(input_path).exists():
            return _json_error("文件不存在，请重新上传", status_code=404)

        raw_mapping = data.get("column_mapping") or {}
        stored_mapping = app.config.get("ROOM_CREATOR_MAPPINGS", {}).get(task_id)
        if stored_mapping and isinstance(stored_mapping, RoomColumnMapping):
            column_mapping = stored_mapping
        else:
            column_mapping = RoomColumnMapping(
                title_col=raw_mapping.get("title_col") or "直播标题",
                cover_col=raw_mapping.get("cover_col"),
                start_time_col=raw_mapping.get("start_time_col") or "开播时间",
                live_form_col=raw_mapping.get("live_form_col"),
                live_direction_col=raw_mapping.get("live_direction_col"),
                live_location_col=raw_mapping.get("live_location_col"),
                live_category_col=raw_mapping.get("live_category_col"),
            )

        room_stop_flag.clear()
        room_login_event.clear()
        show_browser = bool(data.get("show_browser", False))
        report_usage(
            "room_creator",
            "task_start",
            task_id=task_id,
            status="started",
            extra={"show_browser": show_browser},
        )
        thread = threading.Thread(
            target=run_room_creator_task,
            args=(Path(input_path), column_mapping, show_browser, task_id),
        )
        thread.daemon = False
        thread.start()
        return jsonify({"success": True})

    @app.route("/api/room-creator/status")
    def get_room_creator_status():
        with room_status_lock:
            return jsonify(dict(room_creator_status))

    @app.route("/api/room-creator/continue", methods=["POST"])
    def continue_room_creator():
        room_login_event.set()
        add_room_log('用户点击"我已登录"，继续运行')
        return jsonify({"success": True})

    @app.route("/api/room-creator/stop", methods=["POST"])
    def stop_room_creator():
        add_room_log("收到停止请求")
        room_stop_flag.set()
        room_login_event.set()
        with room_status_lock:
            room_creator_status["stopping"] = True
            room_creator_status["need_login"] = False
        close_current_room_browser()
        return jsonify({"success": True})

    @app.route("/api/room-creator/download")
    def download_room_creator_result():
        with room_status_lock:
            result_file = room_creator_status.get("result_file")
            task_id = room_creator_status.get("task_id")

        if not result_file or not Path(result_file).exists():
            return _json_error("结果文件不存在", status_code=404)

        report_usage(
            "room_creator",
            "download",
            task_id=task_id,
            status="success",
            extra={"filename": Path(result_file).name},
        )
        return send_file(result_file, as_attachment=True)

    def add_price_log(message: str):
        with status_lock:
            price_status["logs"].append(
                {"time": time.strftime("%H:%M:%S"), "message": message}
            )
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


    def run_price_audit_task(
        input_file: Path,
        threshold_price: float,
        show_browser: bool = False,
        concurrent_workers: int = PRICE_AUDIT_CONCURRENT_WORKERS,
        cleanup_input: bool = False,
    ):

        browser = None
        page = None
        task_id = app.config.get("PRICE_ACTIVE_TASK_ID", "")
        started_monotonic = time.monotonic()

        try:
            # 延迟导入，避免启动时加载失败
            from utils.browser_manager import BrowserManager
            from utils.jd_crawler import (
                capture_low_price_result_screenshots_with_page_factory,
                crawl_sku,
            )
            from utils.excel_handler import read_sku_list, write_results
            from utils.audit_runner import run_sku_batch_with_page_factory

            with status_lock:
                price_status["running"] = True
                price_status["stopping"] = False
                price_status["total"] = 0
                price_status["current"] = 0
                price_status["current_sku"] = ""
                price_status["success_count"] = 0
                price_status["fail_count"] = 0
                price_status["unqualified_count"] = 0
                price_status["logs"] = []
                price_status["result_file"] = None
                price_status["error"] = None
                price_status["need_login"] = False
                price_status["task_id"] = task_id

            add_price_log("🚀 开始批量测价")
            add_price_log(f"📁 输入文件: {os.path.basename(input_file)}")
            add_price_log(f"💰 价格门槛: ¥{threshold_price}")
            worker_headless = not show_browser
            add_price_log(f'🌐 浏览器模式: {"有头" if show_browser else "无头"}')

            # 1. 读取 SKU 列表
            add_price_log("📖 正在读取 Excel...")
            try:
                sku_data = read_sku_list(str(input_file), "商品SKU")
            except Exception as e:
                with status_lock:
                    price_status["error"] = str(e)
                add_price_log(f"❌ {e}")
                return

            with status_lock:
                price_status["total"] = len(sku_data)
            add_price_log(f"✅ 共读取 {len(sku_data)} 个 SKU")

            if len(sku_data) == 0:
                with status_lock:
                    price_status["error"] = "未找到 SKU，请检查表格格式"
                return

            # 2. 启动浏览器
            add_price_log("🌐 正在启动浏览器...")
            browser = BrowserManager(
                str(app.config["PRICE_AUTH_FILE"]), headless=worker_headless
            )

            with browser_lock:
                current_browser["browser"] = [browser]

            page = browser.start()

            # 3. 检查登录状态
            add_price_log("🔐 检查登录状态...")
            is_logged_in = browser.check_login_status()
            add_price_log(f'   登录状态检查结果: {"已登录" if is_logged_in else "未登录"}')
            if stop_flag.is_set():
                add_price_log("🛑 测价已停止")
                return

            if not is_logged_in:
                try:
                    browser.close(force=True)
                except Exception:
                    pass
                browser = BrowserManager(
                    str(app.config["PRICE_AUTH_FILE"]),
                    headless=False,
                    block_resources=False,
                )
                with browser_lock:
                    current_browser["browser"] = [browser]
                page = browser.start()
                if not wait_for_web_login(browser):
                    with status_lock:
                        price_status["error"] = "登录失败，请重新运行"
                    return
                try:
                    browser.close(force=True)
                except Exception:
                    pass
                add_price_log("✅ 登录成功后切回测价浏览器")
                browser = BrowserManager(
                    str(app.config["PRICE_AUTH_FILE"]), headless=worker_headless
                )
                with browser_lock:
                    current_browser["browser"] = [browser]
                page = browser.start()
                add_price_log("🔐 检查测价浏览器登录状态...")
                if not browser.check_login_status(recheck_seconds=10):
                    with status_lock:
                        price_status["error"] = "登录状态未能同步到测价浏览器，请重新运行"
                    add_price_log("❌ 登录状态未能同步到测价浏览器，请重新运行")
                    return
            add_price_log("✅ 登录状态正常")

            add_price_log(f"⚡ 启用快扫响应取价 + {concurrent_workers} 浏览器并发")

            # 4. 创建输出目录
            if os.path.exists(str(app.config["PRICE_SCREENSHOT_DIR"])):
                for file in os.listdir(str(app.config["PRICE_SCREENSHOT_DIR"])):
                    file_path = os.path.join(str(app.config["PRICE_SCREENSHOT_DIR"]), file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
            os.makedirs(str(app.config["PRICE_SCREENSHOT_DIR"]), exist_ok=True)

            # 5. 批量测价
            def on_item_start(i, total, row_index, sku):
                with status_lock:
                    price_status["current_sku"] = sku
                add_price_log(f"[{i}/{len(sku_data)}] 处理 SKU: {sku}")

            def crawl_one(worker_page, row_index, sku):
                return crawl_sku(
                    page=worker_page,
                    sku=sku,
                    screenshot_dir=str(app.config["PRICE_SCREENSHOT_DIR"]),
                    delay_min=1,
                    delay_max=3,
                    threshold_price=threshold_price,
                    should_stop=stop_flag.is_set,
                )

            def create_worker_page(worker_index, block_images=False):
                worker_browser = BrowserManager(
                    str(app.config["PRICE_AUTH_FILE"]),
                    headless=worker_headless,
                    block_images=block_images,
                )
                try:
                    worker_page = worker_browser.start()
                except Exception:
                    worker_browser.close(force=True)
                    raise
                with browser_lock:
                    browsers = current_browser.get("browser")
                    if isinstance(browsers, list):
                        browsers.append(worker_browser)

                def cleanup_worker():
                    try:
                        worker_browser.close(force=True)
                    finally:
                        with browser_lock:
                            browsers = current_browser.get("browser")
                            if isinstance(browsers, list) and worker_browser in browsers:
                                browsers.remove(worker_browser)

                def recover_worker_login():
                    login_browser = BrowserManager(
                        str(app.config["PRICE_AUTH_FILE"]),
                        headless=False,
                        block_resources=False,
                    )
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
                                if (
                                    isinstance(current_browser, list)
                                    and login_browser in current_browser
                                ):
                                    current_browser.remove(login_browser)

                return worker_page, cleanup_worker, recover_worker_login

            def on_result(result):
                if result["status"] == "success":
                    with status_lock:
                        price_status["current"] += 1
                        price_status["success_count"] += 1
                    if result["price"] is not None and result["price"] < threshold_price:
                        with status_lock:
                            price_status["unqualified_count"] += 1
                        add_price_log(f'  🚫 低于门槛价: ¥{result["price"]}')
                    else:
                        add_price_log(f'  ✅ 价格: ¥{result["price"]}')
                elif result["status"] == "partial":
                    with status_lock:
                        price_status["current"] += 1
                        price_status["fail_count"] += 1
                    add_price_log(f'  ⚠️ 需人工复核: {result["message"]}')
                else:
                    with status_lock:
                        price_status["current"] += 1
                        price_status["fail_count"] += 1
                    add_price_log(f'  ❌ 失败: {result["message"]}')
                diagnostics_log = _format_price_diagnostics(result.get("diagnostics"))
                if diagnostics_log:
                    add_price_log(f"  {diagnostics_log}")

            batch = run_sku_batch_with_page_factory(
                sku_data=sku_data,
                crawl_func=crawl_one,
                recover_login_func=wait_for_web_login,
                stop_event=stop_flag,
                page_factory=lambda worker_index: create_worker_page(
                    worker_index, block_images=True
                ),
                worker_count=concurrent_workers,
                on_item_start=on_item_start,
                on_result=on_result,
                on_login_required=lambda row_index, sku, result: add_price_log(
                    f"SKU {sku} 需要人工处理: {result.get('message', '登录态已失效')}"
                ),
            )
            results = batch.results

            # 6. 测价结束后集中为低价 SKU 补截图，再写入结果表。
            if (
                results
                and not batch.stopped
                and not batch.login_failed
                and not stop_flag.is_set()
            ):
                add_price_log(
                    f"📸 正在为低于门槛的商品并发补充截图（{concurrent_workers} 个窗口）..."
                )
                screenshot_summary = capture_low_price_result_screenshots_with_page_factory(
                    results=results,
                    screenshot_dir=str(app.config["PRICE_SCREENSHOT_DIR"]),
                    threshold_price=threshold_price,
                    page_factory=lambda worker_index: create_worker_page(
                        worker_index, block_images=False
                    ),
                    worker_count=concurrent_workers,
                    should_stop=stop_flag.is_set,
                )
                add_price_log(
                    f"📸 低价截图：应补 {screenshot_summary.total} 张，"
                    f"成功 {screenshot_summary.captured} 张，失败 {screenshot_summary.failed} 张"
                )
                if screenshot_summary.failed_skus:
                    failed_skus_text = ", ".join(screenshot_summary.failed_skus[:20])
                    if len(screenshot_summary.failed_skus) > 20:
                        failed_skus_text += "..."
                    add_price_log(f"⚠️ 低价截图失败 SKU: {failed_skus_text}")

            # 7. 写入结果
            if results:
                add_price_log("📝 正在写入结果...")
                output_path = write_results(
                    file_path=str(input_file),
                    results=results,
                    threshold_price=threshold_price,
                    output_dir=str(app.config["PRICE_OUTPUT_DIR"]),
                    sku_column="商品SKU",
                    price_column="价格",
                    image_column="图片",
                    remark_column="备注",
                )
                with status_lock:
                    price_status["result_file"] = output_path
                add_price_log(f"✅ 结果已保存: {os.path.basename(output_path)}")

            # 8. 检查是否因停止而结束
            if batch.stopped or stop_flag.is_set():
                add_price_log("🛑 测价已停止")
            elif batch.login_failed:
                with status_lock:
                    price_status["error"] = "登录失败，程序中断"
                add_price_log("❌ 登录失败，程序中断")
            else:
                add_price_log("🎉 测价完成！")

        except Exception as e:
            with status_lock:
                price_status["error"] = str(e)
            add_price_log(f"❌ 错误: {str(e)}")
            import traceback

            add_price_log(f"❌ 详细错误: {traceback.format_exc()}")
        finally:
            # 确保浏览器被关闭
            if browser:
                try:
                    add_price_log("🛑 正在关闭浏览器...")
                    browser.close(force=True)
                    add_price_log("✅ 浏览器已关闭")
                except Exception as e:
                    add_price_log(f"⚠️ 关闭浏览器出错: {e}")

            with browser_lock:
                current_browser["browser"] = None

            with status_lock:
                price_status["running"] = False
                price_status["stopping"] = False
                price_status["need_login"] = False
                snapshot = dict(price_status)

            price_fail_count = snapshot.get("fail_count", 0) or 0
            if stop_flag.is_set() or snapshot.get("stopped_count"):
                final_status = "stopped"
            elif snapshot.get("error"):
                final_status = "failed"
            elif price_fail_count > 0:
                final_status = "partial_success"
            else:
                final_status = "success"
            report_usage(
                "sku_price_audit",
                "task_finish",
                task_id=task_id,
                item_count=snapshot.get("total", 0) or 0,
                success_count=snapshot.get("success_count", 0) or 0,
                fail_count=price_fail_count,
                duration_ms=int((time.monotonic() - started_monotonic) * 1000),
                status=final_status,
                extra={
                    "unqualified_count": snapshot.get("unqualified_count", 0) or 0,
                    "threshold_price": threshold_price,
                    "show_browser": show_browser,
                    "concurrent_workers": concurrent_workers,
                    "error": snapshot.get("error"),
                },
            )

            if cleanup_input:
                try:
                    if input_file.exists():
                        _unlink_with_retries(input_file)
                        add_price_log(f"已清理临时输入文件: {input_file.name}")
                except Exception as exc:
                    add_price_log(f"清理临时输入文件失败: {exc}")

    def add_room_log(message: str):
        with room_status_lock:
            room_creator_status["logs"].append(
                {"time": time.strftime("%H:%M:%S"), "message": message}
            )
            if len(room_creator_status["logs"]) > 200:
                room_creator_status["logs"] = room_creator_status["logs"][-200:]
        print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def wait_for_room_login(browser):
        add_room_log("登录态已失效，请登录")
        with room_status_lock:
            room_creator_status["need_login"] = True
        room_login_event.clear()

        try:
            browser.open_login_page()
        except Exception as exc:
            add_room_log(f"打开登录页失败: {exc}")

        wait_count = 0
        while not room_login_event.is_set() and wait_count < 120:
            room_login_event.wait(timeout=5)
            wait_count += 1
            if wait_count % 6 == 0:
                add_room_log(f"仍在等待用户登录... ({wait_count * 5}秒)")
            if room_stop_flag.is_set():
                add_room_log("创建已停止")
                break

        with room_status_lock:
            room_creator_status["need_login"] = False

        if room_stop_flag.is_set():
            return False

        add_room_log("重新检查登录状态...")
        is_logged_in = browser.check_login_status()
        add_room_log(f"登录状态检查结果: {'已登录' if is_logged_in else '未登录'}")

        if not is_logged_in:
            add_room_log("登录失败")
            return False

        browser.save_auth_state()
        add_room_log("登录恢复，继续运行")
        return True

    def run_room_creator_task(
        input_file: Path,
        column_mapping: RoomColumnMapping,
        show_browser: bool = False,
        task_id: str = "",
    ):
        browser = None
        started_monotonic = time.monotonic()
        try:
            from room_creator.excel_reader import read_room_rows
            from room_creator.runner import BatchRunner
            from room_creator.validator import find_duplicates, validate_row
            from room_creator.models import RoomCreateResult
            from room_creator.report_writer import write_batch_report

            with room_status_lock:
                room_creator_status.clear()
                room_creator_status.update(_initial_room_creator_status())
                room_creator_status["running"] = True
                room_creator_status["task_id"] = task_id

            add_room_log("开始批量创建直播间")
            add_room_log(f"输入文件: {input_file.name}")

            rows = read_room_rows(input_file, column_mapping)
            duplicates = find_duplicates(rows)
            valid_rows = []
            skipped_rows = []
            for row in rows:
                errors = validate_row(row)
                if row.row_index in duplicates:
                    errors.append("与前面行的标题+开播时间重复")
                if errors:
                    error_text = "; ".join(errors)
                    skipped_rows.append((row, error_text))
                    add_room_log(f"第 {row.row_index} 行预校验失败: {error_text}")
                else:
                    valid_rows.append(row)

            total = len(valid_rows)
            with room_status_lock:
                room_creator_status["total"] = total
                room_creator_status["skipped"] = len(skipped_rows)
            add_room_log(f"可创建 {total} 个，预校验跳过 {len(skipped_rows)} 个")

            if total == 0:
                with room_status_lock:
                    room_creator_status["error"] = "没有可创建的直播间"
                return

            browser = RoomCreatorBrowser(
                auth_file=app.config["PRICE_AUTH_FILE"],
                headless=not show_browser,
                log_callback=add_room_log,
            )
            with room_browser_lock:
                current_room_browser["browser"] = browser

            page = browser.start()
            add_room_log("检查登录状态...")
            if not browser.ensure_login(interactive=False):
                add_room_log("需要登录")
                # headless 模式下用户看不到登录页，切换到可视化窗口
                if not show_browser:
                    add_room_log("当前为无头模式，切换为显示窗口以便登录")
                    try:
                        browser.close(force=True)
                    except Exception:
                        pass
                    browser = RoomCreatorBrowser(
                        auth_file=app.config["PRICE_AUTH_FILE"],
                        headless=False,
                        log_callback=add_room_log,
                    )
                    browser.start()
                    with room_browser_lock:
                        current_room_browser["browser"] = browser
                browser.open_login_page()
                if not wait_for_room_login(browser):
                    with room_status_lock:
                        room_creator_status["error"] = "登录失败，请重新运行"
                    return
                browser._page = browser.browser_manager.page
                browser._page.goto(
                    "https://jlive.jd.com/my/listNew?jlive=%2Fmy%2Flist",
                    wait_until="networkidle",
                    timeout=60000,
                )
                browser._page.wait_for_timeout(1500)

            def on_room_progress(
                current, total, created_count, failed_count, current_title
            ):
                with room_status_lock:
                    room_creator_status["current"] = current
                    room_creator_status["total"] = total
                    room_creator_status["created_count"] = created_count
                    room_creator_status["failed_count"] = failed_count
                    room_creator_status["current_title"] = current_title

            runner = BatchRunner(
                browser=browser,
                log_callback=add_room_log,
                stop_event=room_stop_flag,
                progress_callback=on_room_progress,
            )
            result = runner.run_batch(valid_rows)

            # 把预校验跳过的行加入结果
            for row, error in skipped_rows:
                result.results.append(
                    RoomCreateResult(
                        row_index=row.row_index,
                        title=row.title,
                        start_time=row.start_time,
                        live_form=row.live_form,
                        live_direction=row.live_direction,
                        live_location=row.live_location,
                        live_category=row.live_category,
                        success=False,
                        error=error,
                    )
                )
            result.skipped_count = len(skipped_rows)

            output_path = write_batch_report(result, app.config["ROOM_OUTPUT_DIR"])
            add_room_log(f"结果已保存: {Path(output_path).name}")

            with room_status_lock:
                room_creator_status["result_file"] = str(output_path)
                room_creator_status["current"] = (
                    result.created_count + result.failed_count
                )
                room_creator_status["created_count"] = result.created_count
                room_creator_status["failed_count"] = result.failed_count
                room_creator_status["skipped"] = result.skipped_count

            if result.stopped_by_limit:
                with room_status_lock:
                    room_creator_status["error"] = result.error
            elif room_stop_flag.is_set():
                add_room_log("创建已停止")
            else:
                add_room_log("创建完成")

        except Exception as exc:
            with room_status_lock:
                room_creator_status["error"] = str(exc)
            add_room_log(f"错误: {exc}")
        finally:
            if browser:
                try:
                    add_room_log("正在关闭浏览器...")
                    browser.close(force=True)
                    add_room_log("浏览器已关闭")
                except Exception as exc:
                    add_room_log(f"关闭浏览器出错: {exc}")

            with room_browser_lock:
                current_room_browser["browser"] = None
            with room_status_lock:
                room_creator_status["running"] = False
                room_creator_status["stopping"] = False
                room_creator_status["need_login"] = False
                app.config.get("ROOM_CREATOR_UPLOADS", {}).pop(task_id, None)
                app.config.get("ROOM_CREATOR_MAPPINGS", {}).pop(task_id, None)
                snapshot = dict(room_creator_status)

            room_failed = snapshot.get("failed_count", 0) or 0
            skipped = snapshot.get("skipped", 0) or 0
            if room_stop_flag.is_set():
                final_status = "stopped"
            elif snapshot.get("error"):
                final_status = "failed"
            elif room_failed > 0 or skipped > 0:
                final_status = "partial_success"
            else:
                final_status = "success"
            report_usage(
                "room_creator",
                "task_finish",
                task_id=task_id,
                item_count=(snapshot.get("created_count", 0) or 0) + room_failed + skipped,
                success_count=snapshot.get("created_count", 0) or 0,
                fail_count=room_failed + skipped,
                duration_ms=int((time.monotonic() - started_monotonic) * 1000),
                status=final_status,
                extra={
                    "failed_count": room_failed,
                    "skipped_count": skipped,
                    "show_browser": show_browser,
                    "error": snapshot.get("error"),
                },
            )

            # 清理本次上传的临时文件
            try:
                if input_file.exists():
                    input_file.unlink()
                    add_room_log(f"已清理上传文件: {input_file.name}")
            except Exception as exc:
                add_room_log(f"清理上传文件失败: {exc}")

    def add_bigscreen_log(message: str):
        with bigscreen_status_lock:
            bigscreen_status["logs"].append(
                {"time": time.strftime("%H:%M:%S"), "message": message}
            )
            if len(bigscreen_status["logs"]) > 200:
                bigscreen_status["logs"] = bigscreen_status["logs"][-200:]
        print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def mark_bigscreen_login_required(_browser):
        with bigscreen_status_lock:
            bigscreen_status["need_login"] = True
        add_bigscreen_log("蓝屏截图需要登录，请在弹出的浏览器窗口完成登录")

    def wait_for_bigscreen_login():
        add_bigscreen_log("等待用户完成蓝屏登录")
        while not bigscreen_stop_flag.is_set():
            if bigscreen_login_event.wait(1):
                bigscreen_login_event.clear()
                with bigscreen_status_lock:
                    bigscreen_status["need_login"] = False
                return not bigscreen_stop_flag.is_set()
        return False

    def run_bigscreen_capture_task(task_id: str, url: str, planned_slots, show_browser: bool = False):
        all_records = []
        bundle_room_id = ""
        bundle_room_name = ""
        bundle_started_at = planned_slots[0].run_at if planned_slots else datetime.now()
        started_monotonic = time.monotonic()

        def update_bigscreen_bundle(message: str):
            if not all_records:
                return
            bundle_dir = app.config["BIGSCREEN_OUTPUT_DIR"] / task_id
            _manifest_file, bundle_zip = write_bigscreen_capture_bundle(
                bundle_dir,
                bundle_room_id or parse_bigscreen_url(url).room_id,
                bundle_started_at,
                all_records,
            )
            app.config["BIGSCREEN_RESULTS"][task_id] = {
                "zip": bundle_zip,
                "room_id": bundle_room_id or parse_bigscreen_url(url).room_id,
                "room_name": bundle_room_name,
            }
            with bigscreen_status_lock:
                bigscreen_status["result_file"] = str(bundle_zip)
            add_bigscreen_log(message)

        try:
            add_bigscreen_log("开始蓝屏自动截图")
            for slot in planned_slots:
                if bigscreen_stop_flag.is_set():
                    add_bigscreen_log("蓝屏截图已停止")
                    break

                with bigscreen_status_lock:
                    bigscreen_status["current_slot"] = slot.label

                while not bigscreen_stop_flag.is_set():
                    wait_seconds = (slot.run_at - datetime.now()).total_seconds()
                    if wait_seconds <= 0:
                        break
                    time.sleep(min(30, max(0.2, wait_seconds)))

                if bigscreen_stop_flag.is_set():
                    add_bigscreen_log("蓝屏截图已停止")
                    break

                add_bigscreen_log(f"开始执行 {slot.label} 蓝屏截图")
                result = capture_bigscreen_once(
                    url=url,
                    output_dir=app.config["BIGSCREEN_OUTPUT_DIR"] / task_id / slot.label.replace(":", ""),
                    planned_slot=slot.label,
                    captured_at=slot.run_at,
                    auth_file=app.config["BIGSCREEN_AUTH_FILE"],
                    should_stop=bigscreen_stop_flag.is_set,
                    log_callback=add_bigscreen_log,
                    show_browser=show_browser,
                    on_login_required=mark_bigscreen_login_required,
                    wait_for_login=wait_for_bigscreen_login,
                )
                all_records.extend(result.records)
                bundle_room_id = result.room_id
                if result.room_name:
                    bundle_room_name = result.room_name
                with bigscreen_status_lock:
                    bigscreen_status["current"] += 1
                    bigscreen_status["success_count"] += result.success_count
                    bigscreen_status["fail_count"] += result.fail_count
                    bigscreen_status["stopped_count"] += result.stopped_count
                    bigscreen_status["room_name"] = bundle_room_name
                if result.stopped_count:
                    add_bigscreen_log(
                        f"{slot.label} 截图已停止，成功 {result.success_count} 项，失败 {result.fail_count} 项，停止 {result.stopped_count} 项"
                    )
                else:
                    add_bigscreen_log(
                        f"{slot.label} 截图完成，成功 {result.success_count} 项，失败 {result.fail_count} 项"
                    )
                try:
                    update_bigscreen_bundle("已更新蓝屏截图总 ZIP")
                except Exception as exc:
                    add_bigscreen_log(f"更新蓝屏截图总 ZIP 失败: {exc}")

            if all_records:
                update_bigscreen_bundle("已生成蓝屏截图总 ZIP")

            if not bigscreen_stop_flag.is_set():
                add_bigscreen_log("蓝屏自动截图完成")
        except Exception as exc:
            with bigscreen_status_lock:
                bigscreen_status["error"] = str(exc)
            add_bigscreen_log(f"蓝屏截图错误: {exc}")
        finally:
            with bigscreen_status_lock:
                bigscreen_status["running"] = False
                bigscreen_status["need_login"] = False
                bigscreen_status["stopping"] = False
                bigscreen_status["current_slot"] = ""
                snapshot = dict(bigscreen_status)

            success_count = snapshot.get("success_count", 0) or 0
            fail_count = snapshot.get("fail_count", 0) or 0
            stopped_count = snapshot.get("stopped_count", 0) or 0
            try:
                room_id = bundle_room_id or snapshot.get("room_id") or parse_bigscreen_url(url).room_id
            except Exception:
                room_id = snapshot.get("room_id")
            room_name = bundle_room_name or snapshot.get("room_name", "")
            if bigscreen_stop_flag.is_set() or stopped_count > 0:
                final_status = "stopped"
            elif snapshot.get("error"):
                final_status = "failed"
            elif fail_count > 0:
                final_status = "partial_success"
            else:
                final_status = "success"
            report_usage(
                "bigscreen_capture",
                "task_finish",
                task_id=task_id,
                item_count=success_count + fail_count + stopped_count,
                success_count=success_count,
                fail_count=fail_count,
                duration_ms=int((time.monotonic() - started_monotonic) * 1000),
                status=final_status,
                extra={
                    "room_id": room_id,
                    "room_name": room_name,
                    "planned_slots": [slot.label for slot in planned_slots],
                    "stopped_count": stopped_count,
                    "show_browser": show_browser,
                    "error": snapshot.get("error"),
                },
            )

    def shutdown_server():
        add_price_log("正在关闭服务...")
        stop_flag.set()
        login_event.set()
        close_current_browsers()

        add_room_log("正在关闭直播间创建浏览器...")
        room_stop_flag.set()
        room_login_event.set()
        close_current_room_browser()

        add_bigscreen_log("正在停止蓝屏自动截图...")
        bigscreen_stop_flag.set()
        bigscreen_login_event.set()
        os.kill(os.getpid(), signal.SIGTERM)

    return app


def _json_error(message: str, status_code: int = 400):
    return jsonify({"success": False, "error": message}), status_code


def _format_price_diagnostics(diagnostics) -> str:
    if not diagnostics:
        return ""

    source_counts = diagnostics.get("price_source_counts") or {}
    dom_count = source_counts.get("dom-fallback", 0) + source_counts.get("dom", 0)
    duration_seconds = (diagnostics.get("duration_ms") or 0) / 1000
    spec_count = diagnostics.get("spec_count") or 0
    return (
        f"诊断: 耗时 {duration_seconds:.1f}s，规格 {spec_count}，"
        f"取价 ware={source_counts.get('ware-business', 0)}/"
        f"dom={dom_count}/"
        f"selected={source_counts.get('selected-dom', 0)}"
    )


def _unlink_with_retries(path: Path, attempts: int = 5, delay_seconds: float = 0.2):
    last_error = None
    path = Path(path)
    for attempt in range(attempts):
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(delay_seconds)
    raise last_error


def _initial_price_status():
    return {
        "running": False,
        "total": 0,
        "current": 0,
        "current_sku": "",
        "success_count": 0,
        "fail_count": 0,
        "stopped_count": 0,
        "unqualified_count": 0,
        "logs": [],
        "result_file": None,
        "error": None,
        "need_login": False,
        "stopping": False,
        "task_id": "",
    }


def _initial_room_creator_status():
    return {
        "running": False,
        "total": 0,
        "current": 0,
        "current_title": "",
        "created_count": 0,
        "failed_count": 0,
        "skipped": 0,
        "logs": [],
        "result_file": None,
        "error": None,
        "need_login": False,
        "stopping": False,
        "task_id": "",
    }


def _initial_bigscreen_status():
    return {
        "running": False,
        "total": 0,
        "current": 0,
        "current_slot": "",
        "success_count": 0,
        "fail_count": 0,
        "stopped_count": 0,
        "logs": [],
        "result_file": None,
        "error": None,
        "need_login": False,
        "stopping": False,
        "task_id": "",
        "room_id": "",
        "room_name": "",
        "planned_slots": [],
        "missed_slots": [],
    }


def _initial_product_selection_status():
    return {
        "running": False,
        "stopping": False,
        "stage": "idle",
        "logs": [],
        "started_at": "",
        "finished_at": "",
        "task_id": "",
        "success": False,
        "error": "",
        "summary": {},
        "excel_download_url": "",
    }


def _copy_product_selection_status(status: dict) -> dict:
    payload = dict(status)
    payload["logs"] = list(status.get("logs", []))
    payload["summary"] = dict(status.get("summary", {}))
    return payload


def _product_selection_summary(payload: dict) -> dict:
    diagnostics = payload.get("diagnostics", {})
    selection = payload.get("selection", {})
    return {
        "source_count": len(diagnostics.get("sources", {})),
        "category_count": sum(len(categories) for categories in selection.values()),
        "selected_count": sum(
            len(products)
            for categories in selection.values()
            for products in categories.values()
        ),
        "items_count": int(payload.get("items_count") or 0),
        "recommendation_mode": payload.get("recommendation_mode", ""),
        "fetch_complete": bool(diagnostics.get("fetch_complete")),
        "ai_complete": bool(diagnostics.get("ai_complete")),
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
    app.config["ROOM_INPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["ROOM_OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["BIGSCREEN_OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["PRODUCT_SELECTION_OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)


def _resolve_bigscreen_result_zip(app: Flask, task_id: str):
    result = app.config["BIGSCREEN_RESULTS"].get(task_id)
    if result:
        zip_path = Path(result["zip"])
        if zip_path.is_file():
            return zip_path

    task_dir = _resolve_bigscreen_task_dir(app.config["BIGSCREEN_OUTPUT_DIR"], task_id)
    if not task_dir:
        return None

    official_zips = sorted(
        [
            path
            for path in task_dir.glob("蓝屏数据截图_*.zip")
            if path.is_file() and not path.name.startswith("蓝屏数据截图_已完成结果_")
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if official_zips:
        return official_zips[0]

    return _write_bigscreen_recovery_zip(task_dir, task_id)


def _resolve_bigscreen_task_dir(output_root: Path, task_id: str):
    output_root = Path(output_root).resolve()
    task_dir = (output_root / task_id).resolve()
    try:
        task_dir.relative_to(output_root)
    except ValueError:
        return None
    if not task_dir.is_dir():
        return None
    return task_dir


def _write_bigscreen_recovery_zip(task_dir: Path, task_id: str):
    recovery_zip = task_dir / f"蓝屏数据截图_已完成结果_{task_id}.zip"
    temp_zip = task_dir / f".{recovery_zip.name}.{uuid.uuid4().hex}.tmp"
    files = [
        path
        for path in sorted(task_dir.rglob("*"))
        if path.is_file()
        and path not in {recovery_zip, temp_zip}
        and not any(part.startswith(".") for part in path.relative_to(task_dir).parts)
    ]
    if not files:
        return None

    with ZipFile(temp_zip, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(task_dir).as_posix())
    temp_zip.replace(recovery_zip)
    return recovery_zip


def _cleanup_old_runtime_files(
    roots: list[Path], retention_days: int, now: float | None = None
):
    cutoff = (now if now is not None else time.time()) - retention_days * 24 * 60 * 60
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue

        for path in root.rglob("*"):
            try:
                if (
                    path.is_file() or path.is_symlink()
                ) and path.stat().st_mtime < cutoff:
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
        "selling_point_col": mapping.selling_point_col,
    }


def _parse_column_mapping(raw_mapping) -> ColumnMapping:
    sku_col = _parse_column_value(raw_mapping.get("sku_col"))
    code_col = _parse_column_value(raw_mapping.get("code_col"))
    product_name_col = _parse_column_value(raw_mapping.get("product_name_col"))
    selling_point_col = _parse_column_value(raw_mapping.get("selling_point_col"))
    if sku_col is None:
        raise ValueError("请选择 SKU 列")
    if code_col is None:
        raise ValueError("请选择券码/促销编码列")
    return ColumnMapping(
        sku_col=sku_col,
        code_col=code_col,
        product_name_col=product_name_col,
        selling_point_col=selling_point_col,
    )


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
