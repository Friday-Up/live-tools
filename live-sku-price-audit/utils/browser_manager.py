"""
浏览器管理模块
负责启动浏览器、复用登录态、检测登录状态
"""

import os
import re
import time
from playwright.sync_api import sync_playwright

AUTH_FILE = "jd_auth.json"
DEFAULT_PAGE_ZOOM = "75%"
DEFAULT_CONTEXT_OPTIONS = {
    "viewport": {"width": 1600, "height": 1100},
}

BLOCKED_RESOURCE_TYPES = {"font", "media"}
BLOCKED_URL_KEYWORDS = (
    "wl.jd.com",
    "gia.jd.com",
    "jrad.jd.com",
    "jzt.jd.com",
    "uranus.jd.com",
    "mercury.jd.com",
    "blackhole",
    "joya.js",
)

_BLOCKED_URL_PATTERN = re.compile("|".join(map(re.escape, BLOCKED_URL_KEYWORDS)))


def _chromium_launch_args(block_images=False):
    """
    浏览器级资源控制参数，避免把每个请求都送到 Python route handler 处理。
    图片在扫描 worker 中通过 blink settings 直接禁用，节省大量 IPC 往返。
    """
    args = []
    if block_images:
        args.append("--blink-settings=imagesEnabled=false")
    return args if args else None


def should_block_request(request, block_images=False):
    resource_type = getattr(request, "resource_type", "")
    url = getattr(request, "url", "")
    if block_images and resource_type == "image":
        return True
    if resource_type in BLOCKED_RESOURCE_TYPES:
        return True
    return any(keyword in url for keyword in BLOCKED_URL_KEYWORDS)


class BrowserManager:
    def __init__(self, auth_file=AUTH_FILE, headless=False, block_resources=True, block_images=False):
        self.auth_file = auth_file
        self.headless = headless
        self.block_resources = block_resources
        self.block_images = block_images
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._closed = False

    def start(self):
        """
        启动浏览器
        如果存在登录态文件则复用，否则需要人工登录
        """
        self.playwright = sync_playwright().start()
        # 登录窗口需要可视化；批量测价 worker 可用无头模式避免抢占桌面。
        launch_kwargs = {"headless": self.headless}
        args = _chromium_launch_args(self.block_images)
        if args:
            launch_kwargs["args"] = args
        self.browser = self.playwright.chromium.launch(**launch_kwargs)

        if os.path.exists(self.auth_file):
            # 复用已有登录态
            try:
                self.context = self.browser.new_context(
                    storage_state=self.auth_file,
                    **DEFAULT_CONTEXT_OPTIONS,
                )
                self.configure_page_display()
                if self.block_resources:
                    self.enable_fast_resource_blocking()
                print("✅ 已加载登录状态")
            except Exception as e:
                print(f"⚠️ 登录状态文件不可用，将重新登录: {e}")
                self.context = self.browser.new_context(**DEFAULT_CONTEXT_OPTIONS)
                self.configure_page_display()
                if self.block_resources:
                    self.enable_fast_resource_blocking()
        else:
            # 首次运行，需要人工登录
            self.context = self.browser.new_context(**DEFAULT_CONTEXT_OPTIONS)
            self.configure_page_display()
            if self.block_resources:
                self.enable_fast_resource_blocking()
            print("⚠️ 首次运行，请登录京东...")

        self.page = self.context.new_page()
        return self.page

    def new_page(self):
        """
        从当前浏览器上下文创建一个新页面。
        """
        if not self.context:
            raise RuntimeError("浏览器上下文未启动")
        return self.context.new_page()

    def configure_page_display(self):
        """
        商品规格较多时右侧购买栏容易挡住点击点；默认使用更大视口和 75% 页面缩放。
        """
        if not self.context:
            raise RuntimeError("浏览器上下文未启动")

        self.context.add_init_script(f"""
            (() => {{
                const applyZoom = () => {{
                    if (document.documentElement) {{
                        document.documentElement.style.zoom = '{DEFAULT_PAGE_ZOOM}';
                    }}
                }};
                applyZoom();
                document.addEventListener('DOMContentLoaded', applyZoom);
            }})();
        """)

    def enable_fast_resource_blocking(self):
        """
        拦截字体、视频和埋点请求；扫描 worker 可额外拦截图片，截图 worker 保留图片。

        为降低 Windows 上 Playwright route 拦截的 IPC 开销：
        1. 图片在浏览器级禁用（--blink-settings=imagesEnabled=false）。
        2. 字体/媒体按 URL 后缀/路径用精准正则 route 拦截，不再用 catch-all handler。
        3. 埋点/广告 URL 用精准正则 route 拦截，只有命中关键字的请求才进 Python。
        """
        if not self.context:
            raise RuntimeError("浏览器上下文未启动")

        # 字体/媒体按 URL 匹配，避免 catch-all handler 对每个请求都做 IPC。
        self.context.route(
            re.compile(r".*\.(woff2?|ttf|otf|eot)(\?.*)?$", re.IGNORECASE),
            lambda route: route.abort(),
        )
        self.context.route(
            re.compile(r".*\.(mp4|webm|ogg|mp3|wav|flv)(\?.*)?$", re.IGNORECASE),
            lambda route: route.abort(),
        )

        # 精准拦截埋点/广告域名，只有命中关键字的请求才会进入 Python handler。
        if BLOCKED_URL_KEYWORDS:
            self.context.route(_BLOCKED_URL_PATTERN, lambda route: route.abort())

    def check_login_status(self, recheck_seconds=20, recheck_interval=2):
        """
        检查当前是否处于登录状态
        访问需要登录的购物车页面验证登录态。
        首页 DOM 和历史 cookie 都可能误判，只把能正常进入购物车作为已登录依据。
        """
        try:
            self.page.goto("https://cart.jd.com/cart_index", wait_until="domcontentloaded", timeout=30000)
            deadline = time.time() + recheck_seconds

            while True:
                if not self._is_login_page():
                    print("   可访问购物车，已登录")
                    return True

                if time.time() >= deadline:
                    return False

                time.sleep(recheck_interval)

        except Exception as e:
            print(f"⚠️ 检查登录状态出错: {e}")
            return False

    def _is_login_page(self):
        current_url = self.page.url or ""
        if "passport.jd.com" in current_url:
            print(f"   重定向到登录页: {current_url}")
            return True

        try:
            title = self.page.title()
            if "登录" in title:
                print(f"   页面标题包含'登录': {title}")
                return True
        except Exception:
            pass

        try:
            login_form = self.page.locator(".login-form, .login-tab, #loginname, .qrcode-login").count()
            if login_form > 0:
                print("   发现登录表单")
                return True
        except Exception:
            pass

        cart_login_prompts = [
            "text=登录后将显示您之前加入的商品",
            "text=你好，请登录",
            "text=免费注册",
        ]
        for selector in cart_login_prompts:
            try:
                if self.page.locator(selector).count() > 0:
                    print(f"   发现未登录提示: {selector}")
                    return True
            except Exception:
                pass

        return False

    def close(self, force=False):
        """
        关闭浏览器
        """
        if self._closed and not force:
            return

        self._closed = True

        # 常规关闭时保存登录态；强制关闭要优先释放浏览器，避免被 storage_state 卡住。
        if self.context and not force:
            try:
                self.context.storage_state(path=self.auth_file)
                print(f"✅ 登录状态已保存到 {self.auth_file}")
            except Exception as e:
                print(f"⚠️ 保存登录状态失败: {e}")

        if force:
            # 强制关闭浏览器 - 使用非阻塞方式
            print("🛑 强制关闭浏览器...")

            # 先关闭 page
            if self.page:
                try:
                    self.page.close()
                except:
                    pass
                finally:
                    self.page = None

            # 再关闭 context
            if self.context:
                try:
                    self.context.close()
                except:
                    pass
                finally:
                    self.context = None

            # 关闭 browser（带超时）
            if self.browser:
                try:
                    self.browser.close()
                except:
                    pass
                finally:
                    self.browser = None

            # 停止 playwright
            if self.playwright:
                try:
                    self.playwright.stop()
                except:
                    pass
                finally:
                    self.playwright = None

            print("✅ 浏览器已关闭")
        else:
            # 不关闭浏览器进程，保持运行以便下次复用
            if self.page:
                try:
                    self.page.close()
                except:
                    pass
            if self.context:
                try:
                    self.context.close()
                except:
                    pass
            print("ℹ️ 浏览器保持运行，下次可直接复用")

    def _manual_login(self):
        """
        引导人工登录京东
        打开登录页后暂停，等待人工完成登录
        注意：此方法仅在命令行模式下使用，Web模式下由前端控制
        """
        self.page = self.context.new_page()
        self.page.goto("https://passport.jd.com/new/login.aspx")
        print("\n" + "="*50)
        print("⚠️  需要人工登录京东")
        print("="*50)
        print("请在新打开的浏览器窗口中完成登录")
        print("登录完成后，请在此终端按回车键继续...")
        print("="*50 + "\n")

        # 使用标准输入读取，等待用户确认
        try:
            input("按回车确认已登录...")
        except EOFError:
            # 如果在非交互环境（如自动化测试），等待固定时间
            print("非交互环境，等待 60 秒...")
            time.sleep(60)

        # 保存登录状态
        self.context.storage_state(path=self.auth_file)
        print(f"✅ 登录状态已保存到 {self.auth_file}")

    def open_login_page(self):
        if not self.page:
            self.page = self.context.new_page()
        self.page.goto("https://passport.jd.com/new/login.aspx", wait_until="domcontentloaded", timeout=30000)

    def save_auth_state(self):
        if self.context:
            self.context.storage_state(path=self.auth_file)
            print(f"✅ 登录状态已保存到 {self.auth_file}")

    def wait_for_login_interactive(self):
        self.open_login_page()
        print("\n" + "=" * 50)
        print("⚠️  需要人工登录京东")
        print("=" * 50)
        print("请在浏览器窗口中完成登录，登录完成后回到终端按回车继续。")
        print("=" * 50 + "\n")
        try:
            input("按回车确认已登录...")
        except EOFError:
            print("非交互环境，等待 60 秒...")
            time.sleep(60)

    def re_login(self):
        self.wait_for_login_interactive()
        if self.check_login_status():
            self.save_auth_state()
            return True
        return False
