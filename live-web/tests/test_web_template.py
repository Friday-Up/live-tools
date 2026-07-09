import tempfile
import unittest
from pathlib import Path

from app import create_app


class WebTemplateTest(unittest.TestCase):
    def test_index_contains_price_audit_and_promotion_binding_tabs(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("直播运营工具", html)
        self.assertIn("SKU 测价、绑定券码/促销ID、批量创建直播间、蓝屏自动截图统一入口", html)
        self.assertNotIn("直播 SKU 价格巡检工具", html)
        self.assertIn("SKU 测价", html)
        self.assertIn("绑定券码/促销ID", html)
        self.assertIn("批量创建直播间", html)
        self.assertIn("生成导入模板", html)
        self.assertIn("promotionColumnMapping", html)
        self.assertIn("promotionSkuColumn", html)
        self.assertIn("promotionCodeColumn", html)
        self.assertNotIn("promotionProductNameColumn", html)
        self.assertNotIn("promotionColumnPreview", html)
        self.assertNotIn("商品名称列", html)
        self.assertIn("/api/promotion-binding/preview", html)
        self.assertIn("/api/promotion-binding/generate", html)
        self.assertIn("upload-area", html)
        self.assertIn("progress-section", html)
        self.assertIn("log-container", html)


    def test_index_contains_room_creator_panel(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn('id="roomCreatorPanel"', html)
        self.assertIn("/api/room-creator/preview", html)
        self.assertIn("/api/room-creator/start", html)
        self.assertIn("/api/room-creator/download", html)

    def test_index_contains_bigscreen_capture_panel(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("蓝屏自动截图", html)
        self.assertIn('id="bigscreenCapturePanel"', html)
        self.assertIn('id="bigscreenUrlInput"', html)
        self.assertIn('id="bigscreenHourGrid"', html)
        self.assertIn('id="bigscreenShowBrowserInput"', html)
        self.assertIn("显示截图浏览器窗口", html)
        self.assertIn("截图时间点", html)
        self.assertIn('id="bigscreenSelectFutureWholeBtn"', html)
        self.assertIn('id="bigscreenSelectFutureHalfBtn"', html)
        self.assertIn("选择未来整点", html)
        self.assertIn("选择未来半点", html)
        self.assertIn("请选择至少一个时间点", html)
        self.assertIn("计划时间点", html)
        self.assertIn("等待/执行时间点", html)
        self.assertNotIn("请选择至少一个整点", html)
        self.assertIn("/api/bigscreen-capture/preview", html)
        self.assertIn("/api/bigscreen-capture/start", html)
        self.assertIn("/api/bigscreen-capture/capture-now", html)
        self.assertIn("/api/bigscreen-capture/status", html)
        self.assertIn("show_browser: document.getElementById('bigscreenShowBrowserInput').checked", html)
        self.assertIn("function setBigscreenTaskButtonsDisabled(disabled)", html)
        self.assertIn("bigscreenCaptureNowBtn.disabled = disabled || !bigscreenRoomIdInput.value", html)
        self.assertIn("let bigscreenActiveTaskId = '';", html)
        self.assertIn("let lastBigscreenStatus = null;", html)
        self.assertIn("function showBigscreenConnectionFailureResult()", html)
        self.assertIn("bigscreenDownloadUrl = `/api/bigscreen-capture/download/${bigscreenActiveTaskId}`;", html)
        self.assertIn("showBigscreenConnectionFailureResult();", html)
        self.assertIn(
            "bigscreenPreviewBtn.disabled = true;\n            setBigscreenTaskButtonsDisabled(true);\n            showMessage(bigscreenStatusMessage, '正在识别链接...', 'info');",
            html,
        )
        self.assertIn("showMessage(bigscreenStatusMessage, '已启动截图任务，可在下方查看实时日志', 'info')", html)
        self.assertIn("startBigscreenStatusPolling();", html)

    def test_price_audit_progress_uses_completed_count_for_concurrent_runs(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("const completed = Math.min(data.current || 0, data.total || 0);", html)
        self.assertIn("(completed / data.total) * 100", html)
        self.assertNotIn("data.current - 1", html)

    def test_bigscreen_future_time_selection_compares_minutes(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("function getLocalDateValue(date)", html)
        self.assertIn("date.getFullYear()", html)
        self.assertIn("String(date.getMonth() + 1).padStart(2, '0')", html)
        self.assertIn("function selectBigscreenFutureOptions(includeHalfHours)", html)
        self.assertIn("const shouldIncludeMinute = includeHalfHours || minute === 0;", html)
        self.assertIn("const currentMinutes = now.getHours() * 60 + now.getMinutes();", html)
        self.assertIn("const optionMinutes = hour * 60 + minute;", html)
        self.assertIn("input.checked = shouldIncludeMinute && (selectedDate > today || (selectedDate === today && optionMinutes > currentMinutes));", html)
        self.assertIn("addEventListener('click', () => selectBigscreenFutureOptions(false))", html)
        self.assertIn("addEventListener('click', () => selectBigscreenFutureOptions(true))", html)
        self.assertIn("bigscreenDateInput.addEventListener('change', () => selectBigscreenFutureOptions(false));", html)

    def test_price_audit_result_summary_shows_failed_count(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn('id="resultFailed"', html)
        self.assertIn("异常数量", html)
        self.assertIn("const failed = data.fail_count || 0;", html)
        self.assertIn("document.getElementById('resultFailed').textContent = failed;", html)

    def test_price_audit_can_request_visible_browser_mode(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn('id="showBrowserInput"', html)
        self.assertIn("显示测价浏览器窗口", html)
        self.assertIn("show_browser: document.getElementById('showBrowserInput').checked", html)

    def test_price_and_room_creator_warn_when_bigscreen_capture_is_running(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("const BIGSCREEN_RUNNING_HINT = '蓝屏截图任务正在运行，整点前后可能影响截图耗时';", html)
        self.assertIn("function showBigscreenRunningHint(targetMessage)", html)
        self.assertIn("fetch('/api/bigscreen-capture/status')", html)
        self.assertIn("showBigscreenRunningHint(statusMessage);", html)
        self.assertIn("showBigscreenRunningHint(roomCreatorStatusMessage);", html)

    def test_price_audit_provides_sku_input_mode(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn('id="inputTabs"', html)
        self.assertIn('data-mode="sku"', html)
        self.assertIn('id="skuInput"', html)
        self.assertIn("/api/start-from-skus", html)


if __name__ == "__main__":
    unittest.main()
