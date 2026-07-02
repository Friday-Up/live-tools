"""京东直播后台直播间创建浏览器自动化。"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional

# 复用 live-sku-price-audit 的浏览器管理（登录态、资源拦截等）
PRICE_AUDIT_ROOT = Path(__file__).resolve().parents[2] / "live-sku-price-audit"
if str(PRICE_AUDIT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRICE_AUDIT_ROOT))

from utils.browser_manager import BrowserManager  # type: ignore

from . import config
from .models import RoomCreateRow, RoomCreateResult


class RoomCreateError(Exception):
    """创建过程中可恢复的业务错误。"""


class DailyLimitReachedError(RoomCreateError):
    """当日创建场次已达上限。"""


class RoomCreatorBrowser:
    """封装直播间创建页面操作。"""

    def __init__(
        self,
        auth_file: str | Path | None = None,
        headless: bool = False,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.auth_file = Path(auth_file) if auth_file else PRICE_AUDIT_ROOT / "jd_auth.json"
        self.headless = headless
        self._log = log_callback or (lambda _: None)
        self.browser_manager: BrowserManager | None = None
        self._page = None

    def _log_msg(self, message: str):
        print(message)
        self._log(message)

    def start(self):
        """启动浏览器并进入直播列表页。"""
        self._log_msg("启动浏览器...")
        self.browser_manager = BrowserManager(str(self.auth_file), headless=self.headless, block_resources=False)
        self._page = self.browser_manager.start()
        self._page.goto(
            "https://jlive.jd.com/my/listNew?jlive=%2Fmy%2Flist",
            wait_until="networkidle",
            timeout=60000,
        )
        self._page.wait_for_timeout(1500)
        self._close_modals()
        self._log_msg(f"当前页面: {self._page.title()}")
        return self._page

    def _close_modals(self, press_escape: bool = True, click_mask: bool = True):
        """关闭可能遮挡操作的弹窗（无权限提示、引导等）。

        Args:
            press_escape: 是否允许按 Escape 兜底关闭弹窗。在抽屉打开后调用时应传 False，
                          避免 Escape 把抽屉也关了。
            click_mask: 是否允许点击遮罩层关闭弹窗。在抽屉打开后调用时应传 False，
                        避免把抽屉一起关掉。
        """
        for attempt in range(5):
            closed = False
            try:
                # 1) 关闭 jd-modal-wrap / ant-modal 类弹窗的关闭按钮
                close_selectors = [
                    '.jd-modal-wrap .jd-modal-close',
                    '.jd-modal-wrap .jd-modal-close-x',
                    '.jd-modal-wrap .ant-modal-close',
                    '.jd-modal-wrap .ant-modal-close-x',
                    '.ant-modal-close',
                    '.ant-modal-close-x',
                    '.jd-modal-close',
                    '.jd-modal-confirm-btns button',
                    '.ant-modal-confirm-btns button',
                ]
                for selector in close_selectors:
                    try:
                        for btn in self._page.locator(selector).all():
                            if btn.is_visible():
                                btn.click(force=True)
                                self._page.wait_for_timeout(500)
                                closed = True
                    except Exception:
                        pass

                # 2) 兜底：弹窗内常见按钮
                for text in ['知道了', '关闭', '同意', '确定', '好的', '暂不', '取消', '以后再说']:
                    try:
                        btn = self._page.locator(f'.jd-modal-wrap button:has-text("{text}")').first
                        if btn.is_visible():
                            btn.click(force=True)
                            self._page.wait_for_timeout(500)
                            closed = True
                    except Exception:
                        pass

                # 3) 点击遮罩层关闭
                if click_mask:
                    try:
                        mask = self._page.locator('.jd-modal-mask, .ant-modal-mask').first
                        if mask.is_visible():
                            mask.click(force=True)
                            self._page.wait_for_timeout(500)
                            closed = True
                    except Exception:
                        pass
            except Exception:
                pass

            if press_escape:
                self._page.keyboard.press('Escape')
                self._page.wait_for_timeout(300)

            if not closed:
                try:
                    wraps = self._page.locator('.jd-modal-wrap, .ant-modal-wrap').all()
                    if not any(w.is_visible() for w in wraps):
                        break
                except Exception:
                    break

    def ensure_login(self, interactive: bool = True) -> bool:
        """检查登录态，失效时引导登录。"""
        if self.browser_manager is None or self._page is None:
            raise RuntimeError("浏览器未启动")

        self._log_msg("检查登录状态...")
        # 在直播列表页本身判断登录态，避免跳转购物车页面。
        if self._check_login_on_live_page():
            self._log_msg("登录态有效")
            return True

        if not interactive:
            return False

        self._log_msg("登录态失效，请重新登录")
        return self._do_relogin()

    def _check_login_on_live_page(self) -> bool:
        """在当前直播列表页判断是否已经登录，不跳转其他页面。"""
        try:
            url = self._page.url or ""
            if "passport.jd.com" in url:
                return False

            title = self._page.title() or ""
            if "登录" in title and "京东直播" not in title:
                return False

            # 未登录时直播列表页通常会出现登录引导元素
            login_indicators = [
                'text=你好，请登录',
                'text=登录后将显示',
                'text=免费注册',
                '.login-form',
                '#loginname',
                '.qrcode-login',
            ]
            for selector in login_indicators:
                try:
                    if self._page.locator(selector).count() > 0:
                        # 某些元素可能在小模块里出现，需要进一步确认是登录表单/提示
                        if self._page.locator('.login-form, #loginname, .qrcode-login').count() > 0:
                            return False
                        # 文本提示直接判定为未登录
                        return False
                except Exception:
                    pass

            # 如果页面不是登录页，且没有登录提示，则判定为已登录
            return True
        except Exception as exc:
            self._log_msg(f"登录态判断异常: {exc}")
        return False

    def _do_relogin(self) -> bool:
        """登录态失效时，引导重新登录并回到直播列表页。"""
        try:
            self.browser_manager.close(force=True)
        except Exception:
            pass

        self.browser_manager = BrowserManager(str(self.auth_file), headless=False, block_resources=False)
        self._page = self.browser_manager.start()
        self.browser_manager.open_login_page()
        self.browser_manager.wait_for_login_interactive()

        if not self.browser_manager.check_login_status():
            return False

        self.browser_manager.save_auth_state()
        self._page.goto(
            "https://jlive.jd.com/my/listNew?jlive=%2Fmy%2Flist",
            wait_until="networkidle",
            timeout=60000,
        )
        self._page.wait_for_timeout(1500)
        return True

    def open_login_page(self):
        """打开京东登录页（供 Web 界面等非交互入口使用）。"""
        if self.browser_manager is None:
            raise RuntimeError("浏览器未启动")
        self.browser_manager.open_login_page()

    def check_login_status(self) -> bool:
        """基于当前页面判断登录态，不跳转购物车。"""
        if self._page is None:
            return False
        return self._check_login_on_live_page()

    def save_auth_state(self):
        """保存当前登录态到文件。"""
        if self.browser_manager is None:
            raise RuntimeError("浏览器未启动")
        self.browser_manager.save_auth_state()

    def open_create_drawer(self):
        """点击"创建直播"打开侧边栏。"""
        if self._page is None:
            raise RuntimeError("浏览器未启动")

        # 先关闭可能遮挡创建按钮的弹窗/提示（创建成功后可能出现）
        self._close_modals(press_escape=False, click_mask=True)
        self._page.wait_for_timeout(500)

        # 等待"创建直播"按钮可见（创建成功后页面可能需要一点时间恢复）
        create_btn = None
        deadline = time.time() + 10
        while time.time() < deadline:
            create_btn = self._page.locator(config.SELECTORS["create_button"]).first
            if create_btn.count() and create_btn.is_visible():
                break
            self._page.wait_for_timeout(500)
        else:
            raise RoomCreateError('未找到"创建直播"按钮')
        create_btn.click(force=True)
        # 等待侧边栏出现并渲染内部表单
        self._page.locator(config.SELECTORS["drawer"]).first.wait_for(state="visible", timeout=10000)
        # 轮询等待标题输入框真正渲染出来（避免 drawer 外壳已显示但内容还在加载）
        deadline = time.time() + 20
        while time.time() < deadline:
            title_input = self._page.locator(config.SELECTORS["title_input"]).first
            if title_input.count() and title_input.is_visible():
                break
            self._page.wait_for_timeout(500)
        else:
            raise RoomCreateError("创建侧边栏中的标题输入框未在 20 秒内渲染")
        self._page.wait_for_timeout(500)
        # 抽屉打开后不能按 Escape，否则会把抽屉一起关掉
        self._close_modals(press_escape=False, click_mask=False)
        self._log_msg("已打开创建侧边栏")

    def _fill_title(self, title: str):
        """填写直播标题（auto-complete 输入框）。"""
        input_locator = self._page.locator(config.SELECTORS["title_input"]).first
        input_locator.wait_for(state="visible", timeout=10000)
        input_locator.click(force=True)
        input_locator.fill("")
        input_locator.fill(title)
        self._page.wait_for_timeout(300)
        # 避免按 Enter 误选下拉联想项；fill 后让输入框失去焦点即可
        input_locator.press("Tab")
        self._page.wait_for_timeout(300)
        self._log_msg(f"填写标题: {title}")

    def _fill_publish_time(self, start_time):
        """填写开播时间。"""
        picker_input = self._page.locator(config.SELECTORS["publish_time_input"]).first
        picker_input.click()
        self._page.wait_for_selector(
            config.SELECTORS["picker_popup"], state="visible", timeout=5000
        )

        # 选择日期
        date_str = start_time.strftime("%Y-%m-%d")
        date_cell = None
        for _ in range(12):
            cell = self._page.locator(f'td[title="{date_str}"]').first
            if cell.count() > 0:
                date_cell = cell
                break
            # 尝试切换到下个月
            next_btn = self._page.locator(
                '.jd-picker-header-next-btn, .ant-picker-header-next-btn, '
                '.jd-picker-next-icon, .ant-picker-next-icon, '
                'button[class*="next"]'
            ).first
            if next_btn.count() == 0 or not next_btn.is_enabled():
                break
            # 下月按钮可能被时间面板挤到视口外，用 JS 点击避免 viewport 限制
            next_btn.evaluate("el => el.click()")
            self._page.wait_for_timeout(500)
        if date_cell is None or date_cell.count() == 0:
            raise RoomCreateError(f"日期选择器中未找到日期: {date_str}")
        # 日期 cell 可能被时间面板挤到视口外，用 JS 点击避免 viewport 限制
        date_cell.evaluate("el => el.click()")
        self._page.wait_for_timeout(300)

        # 选择时间（时/分/秒）
        time_values = [
            start_time.strftime("%H"),
            start_time.strftime("%M"),
            start_time.strftime("%S"),
        ]
        columns = self._page.locator('.jd-picker-time-panel-column').all()
        if len(columns) < 3:
            raise RoomCreateError("开播时间选择器未显示时/分/秒列")
        for idx, value in enumerate(time_values):
            selected_cell = None
            for li in columns[idx].locator('li').all():
                if li.inner_text().strip() == value:
                    selected_cell = li
                    break
            if selected_cell is None:
                raise RoomCreateError(f"时间选择器中未找到: {value}")
            selected_cell.evaluate("el => el.click()")
            self._page.wait_for_timeout(200)

        # 点击确定关闭选择器（按 Esc 会触发抽屉的离开未保存提示）
        ok_btn = self._page.locator(config.SELECTORS["picker_ok_button"]).first
        if ok_btn.count() and ok_btn.is_enabled():
            ok_btn.click(force=True)
        else:
            raise RoomCreateError("开播时间选择器确定按钮不可用")
        self._page.wait_for_timeout(500)
        self._page.locator(config.SELECTORS["picker_popup"]).wait_for(state="hidden", timeout=5000)

        display_text = start_time.strftime("%Y-%m-%d %H:%M:%S")
        self._log_msg(f"填写开播时间: {display_text}")

    def _select_option(self, select_selector: str, option_text: str):
        """从 jd-select 下拉框或级联选择器中选择指定文本。"""
        # 先关闭可能残留的上一个下拉弹窗（点击抽屉空白处，避免 Escape 关闭抽屉）
        try:
            self._page.locator(config.SELECTORS["drawer"]).first.click(force=True)
            self._page.wait_for_timeout(300)
        except Exception:
            pass

        # 点击 select 容器而不是 input，避免被 .jd-select-selection-item 遮挡
        container = self._page.locator(
            f'.jd-select:has({select_selector}), .ant-select:has({select_selector})'
        ).first
        if container.count():
            container.click(force=True)
        else:
            # 级联选择器容器
            container = self._page.locator(
                f'.jd-cascader:has({select_selector}), .ant-cascader:has({select_selector})'
            ).first
            if container.count():
                container.click(force=True)
            else:
                self._page.locator(select_selector).first.click(force=True)
        self._page.wait_for_timeout(800)

        # 优先用 title 精确匹配
        option = self._page.locator(
            f'{config.SELECTORS["select_dropdown"]} '
            f'{config.SELECTORS["select_option"]}[title="{option_text}"]'
        ).first

        # title 可能为空，再用文本匹配
        if option.count() == 0:
            option = self._page.locator(
                f'{config.SELECTORS["select_dropdown"]} '
                f'{config.SELECTORS["select_option"]}:has-text("{option_text}")'
            ).first

        if option.count() == 0:
            # 级联选择器选项
            option = self._page.locator(
                f'{config.SELECTORS["cascader_dropdown"]} '
                f'{config.SELECTORS["cascader_option"]}:has-text("{option_text}")'
            ).first

        if option.count() == 0:
            # 兜底：页面任意位置包含该文本的选项
            option = self._page.locator(
                f'.jd-select-item[title="{option_text}"], '
                f'.ant-select-item[title="{option_text}"], '
                f'.jd-select-item:has-text("{option_text}"), '
                f'.ant-select-item:has-text("{option_text}"), '
                f'.jd-cascader-menu-item:has-text("{option_text}"), '
                f'.ant-cascader-menu-item:has-text("{option_text}")'
            ).first

        if option.count() == 0:
            raise RoomCreateError(f"下拉框中未找到选项: {option_text}")

        option.evaluate("el => el.click()")
        self._page.wait_for_timeout(600)
        # 等待下拉弹窗消失，避免 Escape 触发离开未保存提示
        try:
            self._page.locator(config.SELECTORS["select_dropdown"]).wait_for(state="hidden", timeout=3000)
        except Exception:
            pass

    def _fill_select_field(self, select_selector: str, value: str, label: str):
        """填写单个下拉字段。"""
        if not value:
            return
        self._select_option(select_selector, value)
        self._log_msg(f"填写 {label}: {value}")

    def fill_form(self, row: RoomCreateRow):
        """依次填写创建表单。"""
        if self._page is None:
            raise RuntimeError("浏览器未启动")

        self._fill_title(row.title)
        self._fill_publish_time(row.start_time)
        self._fill_select_field(
            config.SELECTORS["live_form_select"], row.live_form, "直播形式"
        )
        self._fill_select_field(
            config.SELECTORS["screen_direction_select"], row.live_direction, "画面方向"
        )
        self._fill_select_field(
            config.SELECTORS["location_region_select"], row.live_location, "直播地点"
        )
        self._fill_select_field(
            config.SELECTORS["category_select"], row.live_category, "直播品类"
        )

    def submit_form(self) -> bool:
        """点击创建按钮并等待提交完成。"""
        if self._page is None:
            raise RuntimeError("浏览器未启动")

        submit_btn = self._page.locator(config.SELECTORS["submit_button"]).first
        if not submit_btn.is_visible():
            raise RoomCreateError('未找到"创建"按钮')

        if not submit_btn.is_enabled():
            raise RoomCreateError('"创建"按钮当前不可用，请检查必填项')

        submit_btn.click(force=True)
        self._log_msg("点击创建按钮，等待响应...")
        self._page.wait_for_timeout(3000)

        # 检测是否有错误提示弹窗
        error_text = None
        error_selectors = [
            '.ant-modal-confirm-error',
            '.jd-modal-confirm-error',
            '.ant-modal-confirm-content',
            '.jd-modal-confirm-content',
            '.jd-modal-wrap .jd-modal-content',
            '.ant-modal-wrap .ant-modal-content',
            '.jd-modal-body',
            '.ant-modal-body',
        ]
        for selector in error_selectors:
            loc = self._page.locator(selector).first
            try:
                if loc.count() and loc.is_visible():
                    error_text = loc.inner_text().strip()
                    if error_text:
                        break
            except Exception:
                continue

        if error_text:
            # 尝试关闭弹窗
            try:
                ok_btn = self._page.locator(
                    '.ant-modal-confirm-btns button, .jd-modal-confirm-btns button, '
                    '.jd-modal-wrap button:has-text("我知道了"), '
                    '.ant-modal-wrap button:has-text("我知道了")'
                ).first
                if ok_btn.count() and ok_btn.is_visible():
                    ok_btn.click()
                    self._page.wait_for_timeout(500)
            except Exception:
                pass
            # 日创建上限特殊处理：停止后续创建
            if (
                "创建场次上限" in error_text
                or "已达当日创建" in error_text
                or ("上限" in error_text and str(config.DAILY_CREATE_LIMIT) in error_text)
            ):
                raise DailyLimitReachedError(error_text)
            raise RoomCreateError(f"创建失败: {error_text}")

        # 创建成功的一个明显信号：抽屉关闭
        drawer = self._page.locator(config.SELECTORS["drawer"]).first
        try:
            drawer.wait_for(state="hidden", timeout=15000)
        except Exception:
            raise RoomCreateError("创建提交后抽屉未关闭，可能创建未成功")

        # 关闭可能出现的成功提示/弹窗，避免遮挡下一次"创建直播"按钮
        self._page.wait_for_timeout(800)
        self._close_modals(press_escape=False, click_mask=True)

        return True

    def close_drawer(self):
        """点击取消或按 Esc 关闭侧边栏，准备下一条。"""
        if self._page is None:
            return
        # 关闭可能遮挡的弹窗/提示；不按 Escape，避免误触发抽屉的未保存提示
        self._close_modals(press_escape=False, click_mask=True)
        try:
            cancel_btn = self._page.locator(config.SELECTORS["cancel_button"]).first
            if cancel_btn.is_visible():
                cancel_btn.click()
                self._page.wait_for_timeout(800)
                self._close_modals()
                return
        except Exception:
            pass
        # 避免按 Esc 触发未保存提示；优先点击抽屉关闭按钮
        try:
            close_btn = self._page.locator('.jd-drawer-close, .ant-drawer-close').first
            if close_btn.is_visible():
                close_btn.click(force=True)
                self._page.wait_for_timeout(800)
                self._close_modals()
                return
        except Exception:
            pass

    def create_room(self, row: RoomCreateRow) -> RoomCreateResult:
        """创建单个直播间。"""
        result = RoomCreateResult(
            row_index=row.row_index,
            title=row.title,
            start_time=row.start_time,
            live_form=row.live_form,
            live_direction=row.live_direction,
            live_location=row.live_location,
            live_category=row.live_category,
        )

        try:
            self.open_create_drawer()
            self.fill_form(row)
            self.submit_form()
            result.success = True
            self._log_msg(f"第 {row.row_index} 行创建成功: {row.title}")
        except DailyLimitReachedError as exc:
            result.error = str(exc)
            self._log_msg(f"第 {row.row_index} 行触发日创建上限: {exc}")
            raise
        except RoomCreateError as exc:
            result.error = str(exc)
            self._log_msg(f"第 {row.row_index} 行创建失败: {exc}")
        except Exception as exc:
            result.error = f"异常: {exc}"
            self._log_msg(f"第 {row.row_index} 行异常: {exc}")

        try:
            self.close_drawer()
        except Exception:
            pass

        return result

    def close(self, force: bool = True):
        """关闭浏览器。"""
        if self.browser_manager:
            try:
                self.browser_manager.close(force=force)
            except Exception:
                pass
            finally:
                self.browser_manager = None
                self._page = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close(force=True)
        return False
