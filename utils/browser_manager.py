"""
浏览器管理模块
负责启动浏览器、复用登录态、检测登录状态
"""

import os
import time
from playwright.sync_api import sync_playwright

AUTH_FILE = "jd_auth.json"


class BrowserManager:
    def __init__(self, auth_file=AUTH_FILE):
        self.auth_file = auth_file
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
        # 必须可视化运行，方便人工登录
        self.browser = self.playwright.chromium.launch(headless=False)

        if os.path.exists(self.auth_file):
            # 复用已有登录态
            self.context = self.browser.new_context(storage_state=self.auth_file)
            print("✅ 已加载登录状态，无需再次登录")
        else:
            # 首次运行，需要人工登录
            self.context = self.browser.new_context()
            print("⚠️ 首次运行，请登录京东...")
            self._manual_login()

        self.page = self.context.new_page()
        return self.page

    def check_login_status(self):
        """
        检查当前是否处于登录状态
        访问京东首页，通过多种方式判断登录状态
        """
        try:
            # 方法1：访问订单页面，看是否重定向到登录页
            self.page.goto("https://order.jd.com/center/list.action", wait_until="domcontentloaded", timeout=10000)
            time.sleep(2)

            current_url = self.page.url
            if "passport.jd.com" in current_url or "login" in current_url:
                print(f"   重定向到登录页: {current_url}")
                return False

            # 方法2：检查页面标题
            title = self.page.title()
            if "登录" in title:
                print(f"   页面标题包含'登录': {title}")
                return False

            # 方法3：检查是否有登录表单
            try:
                login_form = self.page.locator(".login-form, .login-tab, #loginname").count()
                if login_form > 0:
                    print(f"   发现登录表单")
                    return False
            except:
                pass

            # 方法4：如果能访问到订单页面内容，说明已登录
            try:
                order_elements = self.page.locator(".order-list, .order-item, .o-list").count()
                if order_elements > 0:
                    print(f"   发现订单页面元素，已登录")
                    return True
            except:
                pass

            # 方法5：检查页面内容是否包含个人信息
            try:
                content = self.page.content()
                if "我的订单" in content or "个人中心" in content:
                    print("   页面包含个人中心内容，已登录")
                    return True
            except:
                pass

            # 方法6：检查 cookie 中的登录凭证
            try:
                cookies = self.context.cookies()
                for cookie in cookies:
                    if cookie.get('name') in ['pin', 'unick', '_pst', 'wskey']:
                        print(f"   发现登录cookie: {cookie['name']}")
                        return True
            except:
                pass

            # 方法7：访问首页检查是否有用户昵称
            self.page.goto("https://www.jd.com", wait_until="domcontentloaded", timeout=10000)
            time.sleep(1)

            try:
                user_elements = self.page.locator(".nickname, .user-name, [class*='user-info']").count()
                if user_elements > 0:
                    print(f"   发现用户昵称元素，已登录")
                    return True
            except:
                pass

            # 方法8：检查是否有退出按钮
            try:
                logout_btn = self.page.locator("text=退出, a[href*='logout']").count()
                if logout_btn > 0:
                    print("   发现退出按钮，已登录")
                    return True
            except:
                pass

            print("   未检测到登录状态")
            return False

        except Exception as e:
            print(f"⚠️ 检查登录状态出错: {e}")
            return False

    def close(self, force=False):
        """
        关闭浏览器
        """
        if self._closed and not force:
            return

        self._closed = True

        # 保存登录状态
        if self.context:
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
