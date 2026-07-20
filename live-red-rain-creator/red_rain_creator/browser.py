"""京东直播红包雨页面自动化。"""

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional, Tuple, Union

PRICE_AUDIT_ROOT = Path(__file__).resolve().parents[2] / "live-sku-price-audit"
if str(PRICE_AUDIT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRICE_AUDIT_ROOT))

from utils.browser_manager import BrowserManager  # type: ignore

from . import config
from .models import RedRainResult, RedRainRow


class RedRainCreateError(Exception):
    pass


class LoginRequiredError(RedRainCreateError):
    pass


class RedRainCreatorBrowser:
    SUBMISSION_GUARD_SECONDS = 7 * 24 * 60 * 60

    def __init__(
        self,
        auth_file=None,
        headless=False,
        log_callback: Optional[Callable[[str], None]] = None,
        guard_file=None,
    ):
        self.auth_file = Path(auth_file) if auth_file else PRICE_AUDIT_ROOT / "jd_auth.json"
        self.headless = headless
        self._log = log_callback or (lambda _: None)
        self.guard_file = (
            Path(guard_file)
            if guard_file
            else self.auth_file.parent.parent / "live-web" / "runtime" / "red-rain-submission-guard.json"
        )
        self.browser_manager = None
        self._page = None

    def _log_msg(self, message):
        self._log(message)

    def start(self):
        self.browser_manager = BrowserManager(str(self.auth_file), headless=self.headless, block_resources=False)
        self._page = self.browser_manager.start()
        self._page.goto(config.RED_RAIN_URL, wait_until="domcontentloaded", timeout=60000)
        self._page.wait_for_timeout(1200)
        return self._page

    def restart_for_login(self):
        self.close(force=True)
        self.headless = False
        return self.start()

    def ensure_login(self, interactive=True):
        if self._page is None:
            raise RuntimeError("浏览器未启动")
        if self._is_logged_in():
            return True
        if not interactive:
            return False
        self.browser_manager.open_login_page()
        self.browser_manager.wait_for_login_interactive()
        if not self.browser_manager.check_login_status():
            return False
        self.browser_manager.save_auth_state()
        self._page.goto(config.RED_RAIN_URL, wait_until="domcontentloaded", timeout=60000)
        self._page.wait_for_timeout(1200)
        return self._is_logged_in()

    def _is_logged_in(self):
        url = self._page.url or ""
        if "passport.jd.com" in url:
            return False
        if self._page.locator('.login-form, #loginname, .qrcode-login').count() > 0:
            return False
        return self._page.locator('button:has-text("创建红包雨")').count() > 0

    def open_login_page(self):
        self.browser_manager.open_login_page()

    def check_login_status(self):
        return self._is_logged_in() if self._page else False

    def is_login_required(self):
        if self._page is None:
            return True
        url = self._page.url or ""
        if "passport.jd.com" in url:
            return True
        try:
            return self._page.locator('.login-form, .login-tab, #loginname, .qrcode-login').count() > 0
        except Exception:
            return False

    def finish_interactive_login(self):
        """在登录页完成登录后校验京东会话，并回到红包雨页面。"""
        if not self.browser_manager or not self.browser_manager.check_login_status():
            return False
        self.browser_manager.save_auth_state()
        self._page.goto(config.RED_RAIN_URL, wait_until="domcontentloaded", timeout=60000)
        self._page.wait_for_timeout(1200)
        return self._is_logged_in()

    def save_auth_state(self):
        self.browser_manager.save_auth_state()

    def _dialog(self):
        dialogs = self._page.locator('.ant-modal-wrap:visible .ant-modal-content')
        if dialogs.count() != 1:
            raise RedRainCreateError("未找到唯一的创建红包雨弹窗")
        return dialogs.first

    @staticmethod
    def _normalize_table_text(value):
        return "".join(str(value or "").split()).lower()

    @classmethod
    def _header_index(cls, headers, aliases):
        normalized_aliases = {cls._normalize_table_text(alias) for alias in aliases}
        for index, header in enumerate(headers):
            value = cls._normalize_table_text(header)
            if value in normalized_aliases:
                return index
        return None

    def _fingerprint(self, row: RedRainRow):
        payload = "|".join(
            [
                row.activity_name.strip(),
                row.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                row.end_time.strftime("%Y-%m-%d %H:%M:%S"),
                row.issue_method,
                row.red_packet_id.strip(),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _read_guard(self):
        try:
            value = json.loads(self.guard_file.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _write_guard(self, value):
        self.guard_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.guard_file.with_suffix(self.guard_file.suffix + ".tmp")
        temp_file.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_file.replace(self.guard_file)

    def _guard_entry(self, row: RedRainRow):
        entries = self._read_guard()
        entry = entries.get(self._fingerprint(row))
        if not isinstance(entry, dict):
            return None
        try:
            age_seconds = time.time() - float(entry.get("recorded_at", 0))
        except (TypeError, ValueError):
            age_seconds = self.SUBMISSION_GUARD_SECONDS + 1
        if age_seconds > self.SUBMISSION_GUARD_SECONDS:
            entries.pop(self._fingerprint(row), None)
            self._write_guard(entries)
            return None
        return entry

    def _mark_guard(self, row: RedRainRow, state, activity_id=""):
        entries = self._read_guard()
        entries[self._fingerprint(row)] = {
            "state": state,
            "recorded_at": time.time(),
            "activity_id": str(activity_id or ""),
        }
        self._write_guard(entries)

    def _clear_guard(self, row: RedRainRow):
        entries = self._read_guard()
        if entries.pop(self._fingerprint(row), None) is not None:
            self._write_guard(entries)

    def _match_activity_cells(self, headers, cells, row: RedRainRow):
        if not cells:
            return False, ""
        name_index = self._header_index(headers, ["活动名称"])
        time_index = self._header_index(headers, ["活动时间"])
        packet_index = self._header_index(headers, ["红包ID", "红包 ID"])
        activity_id_index = self._header_index(headers, ["活动ID", "活动 ID"])
        row_text = self._normalize_table_text(" ".join(cells))
        expected_name = self._normalize_table_text(row.activity_name)
        expected_packet = self._normalize_table_text(row.red_packet_id)
        expected_start = self._normalize_table_text(row.start_time.strftime("%Y-%m-%d %H:%M:%S"))
        expected_end = self._normalize_table_text(row.end_time.strftime("%Y-%m-%d %H:%M:%S"))
        actual_name = self._normalize_table_text(cells[name_index]) if name_index is not None and name_index < len(cells) else ""
        actual_packet = self._normalize_table_text(cells[packet_index]) if packet_index is not None and packet_index < len(cells) else ""
        actual_time = self._normalize_table_text(cells[time_index]) if time_index is not None and time_index < len(cells) else row_text
        name_matches = actual_name == expected_name if actual_name else expected_name in row_text
        packet_matches = actual_packet == expected_packet if actual_packet else expected_packet in row_text
        if not (name_matches and packet_matches and expected_start in actual_time and expected_end in actual_time):
            return False, ""
        activity_id = (
            cells[activity_id_index].strip()
            if activity_id_index is not None and activity_id_index < len(cells)
            else ""
        )
        return True, activity_id

    def find_existing_activity(self, row: RedRainRow) -> Tuple[bool, str]:
        search = self._page.locator('input[placeholder="输入活动名称检索"]')
        if search.count() != 1:
            raise RedRainCreateError("未找到活动名称查询框")
        search.fill(row.activity_name)
        query = self._page.locator('button:has-text("查 询")')
        query.first.click()
        self._page.wait_for_timeout(800)
        headers = self._page.locator("thead th").all_inner_texts()
        for table_row in self._page.locator("tbody tr").all():
            cells = table_row.locator("td").all_inner_texts()
            matched, activity_id = self._match_activity_cells(headers, cells, row)
            if matched:
                return True, activity_id
        return False, ""

    def open_create_dialog(self):
        button = self._page.locator('button:has-text("创建红包雨")')
        if button.count() != 1:
            raise RedRainCreateError("未找到创建红包雨按钮")
        button.click()
        self._page.locator('.ant-modal-wrap:visible').wait_for(state="visible", timeout=10000)
        dialog = self._dialog()
        cmc = dialog.locator('button:has-text("CMC红包创建")')
        if cmc.count() != 1 or not cmc.is_enabled():
            raise RedRainCreateError("CMC红包创建当前不可用")
        cmc.click()
        next_button = dialog.locator('button:has-text("下一步")')
        if next_button.count() != 1:
            raise RedRainCreateError("未找到下一步按钮")
        next_button.click()
        dialog.locator("#activityName").wait_for(state="visible", timeout=10000)

    def _select_time(self, columns, value):
        option = columns.locator(f'li:has-text("{value}")')
        matches = [item for item in option.all() if item.inner_text().strip() == value]
        if len(matches) != 1:
            raise RedRainCreateError(f"时间选择器中未找到 {value}")
        matches[0].evaluate("el => el.click()")

    def _fill_activity_time(self, dialog, row):
        inputs = dialog.locator('.ant-picker-range input').all()
        if len(inputs) != 2:
            raise RedRainCreateError("活动时间控件结构异常")

        inputs[0].click()
        dropdown = self._page.locator('.ant-picker-dropdown:visible')
        dropdown.wait_for(state="visible", timeout=5000)
        start_cell = dropdown.locator(f'td[title="{row.start_time:%Y-%m-%d}"]:not(.ant-picker-cell-disabled)')
        if start_cell.count() == 0:
            raise RedRainCreateError(f"日期选择器中未找到开始日期: {row.start_time:%Y-%m-%d}")
        start_cell.first.click()
        columns = dropdown.locator('.ant-picker-time-panel-column').all()
        if len(columns) < 3:
            raise RedRainCreateError("开始时间选择器未显示时分秒")
        for column, value in zip(columns[-3:], [f"{row.start_time:%H}", f"{row.start_time:%M}", f"{row.start_time:%S}"]):
            self._select_time(column, value)

        inputs[1].click()
        dropdown = self._page.locator('.ant-picker-dropdown:visible')
        end_cell = dropdown.locator(f'td[title="{row.end_time:%Y-%m-%d}"]:not(.ant-picker-cell-disabled)')
        if end_cell.count() == 0:
            raise RedRainCreateError(f"日期选择器中未找到结束日期: {row.end_time:%Y-%m-%d}")
        end_cell.first.click()
        columns = dropdown.locator('.ant-picker-time-panel-column').all()
        if len(columns) < 3:
            raise RedRainCreateError("结束时间选择器未显示时分秒")
        for column, value in zip(columns[-3:], [f"{row.end_time:%H}", f"{row.end_time:%M}", f"{row.end_time:%S}"]):
            self._select_time(column, value)
        ok = dropdown.locator('button:has-text("确 定")')
        if ok.count() == 0 or not ok.first.is_enabled():
            raise RedRainCreateError("活动时间选择器确定按钮不可用")
        ok.first.click()

    def fill_form(self, row: RedRainRow):
        dialog = self._dialog()
        dialog.locator("#activityName").fill(row.activity_name)
        self._fill_activity_time(dialog, row)
        radio = dialog.locator(f'label:has-text("{row.issue_method}")')
        if radio.count() != 1:
            raise RedRainCreateError(f"未找到发放方式: {row.issue_method}")
        radio.click()
        dialog.locator("#redPacketId").fill(row.red_packet_id)
        if row.issue_method == config.ISSUE_METHOD_NORMAL:
            probability = dialog.locator('.ant-input-number-input')
            if probability.count() != 1:
                raise RedRainCreateError("普通发放未显示中奖概率")
            probability.fill(str(row.win_probability))

    def submit(self, row: RedRainRow):
        dialog = self._dialog()
        complete = dialog.locator('button:has-text("完 成")')
        if complete.count() != 1 or not complete.is_enabled():
            raise RedRainCreateError("完成按钮当前不可用")
        self._mark_guard(row, "submitting")
        complete.click()
        try:
            self._page.locator('.ant-modal-wrap:visible').wait_for(state="hidden", timeout=15000)
        except Exception:
            messages = []
            for locator in self._page.locator('.ant-message-error, .ant-form-item-explain-error, .ant-modal-confirm-content').all():
                if locator.is_visible() and locator.inner_text().strip():
                    messages.append(locator.inner_text().strip())
            if messages:
                self._clear_guard(row)
            raise RedRainCreateError("; ".join(messages) or "提交后弹窗未关闭，提交状态待确认")

    def close_dialog(self):
        try:
            close = self._page.locator('.ant-modal-wrap:visible .ant-modal-close')
            if close.count() and close.first.is_visible():
                close.first.click()
        except Exception:
            pass

    def create_activity(self, row: RedRainRow) -> RedRainResult:
        try:
            existed, activity_id = self.find_existing_activity(row)
            if existed:
                self._mark_guard(row, "confirmed", activity_id)
                return RedRainResult.from_row(row, status="已存在", activity_id=activity_id)
            guarded = self._guard_entry(row)
            if guarded:
                return RedRainResult.from_row(
                    row,
                    status="待确认",
                    activity_id=str(guarded.get("activity_id") or ""),
                    error="本机记录显示该活动近期已点击完成，为防止重复创建，本次未再次提交，请先在后台确认",
                )
            self.open_create_dialog()
            self.fill_form(row)
            self.submit(row)
            for _ in range(5):
                existed, activity_id = self.find_existing_activity(row)
                if existed:
                    self._mark_guard(row, "confirmed", activity_id)
                    return RedRainResult.from_row(row, status="成功", activity_id=activity_id)
                self._page.wait_for_timeout(1000)
            return RedRainResult.from_row(
                row,
                status="待确认",
                error="已点击完成，但多次刷新后仍未查询到活动；已启用本地提交保护，请勿重复提交",
            )
        except Exception as exc:
            self.close_dialog()
            if self.is_login_required():
                raise LoginRequiredError("京东登录态已失效") from exc
            return RedRainResult.from_row(row, status="失败", error=str(exc))

    def close(self, force=True):
        if self.browser_manager:
            self.browser_manager.close(force=force)
            self.browser_manager = None
            self._page = None
