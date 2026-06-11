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
        访问京东首页，检查是否跳转到登录页
        """
        try:
            self.page.goto("https://www.jd.com", wait_until="domcontentloaded")
            time.sleep(2)

            # 如果 URL 包含 passport，说明需要登录
            if "passport.jd.com" in self.page.url:
                return False

            # 检查页面是否有登录相关的元素
            login_indicators = [
                ".login-form",
                ".login-tab",
                "text=请登录",
                "text=登录/注册"
            ]

            for indicator in login_indicators:
                try:
                    if self.page.locator(indicator).count() > 0:
                        return False
                except:
                    pass

            # 检查是否显示用户名（已登录标志）
            try:
                # 京东已登录后会显示用户名或退出按钮
                if self.page.locator("text=退出").count() > 0:
                    return True
                if self.page.locator(".nickname").count() > 0:
                    return True
            except:
                pass

            # 如果以上都没匹配到，默认认为未登录（保守策略）
            return False

        except Exception as e:
            print(f"⚠️ 检查登录状态出错: {e}")
            return False

    def close(self, force=False):
        """
        关闭浏览器
        """
        # 保存登录状态
        if self.context:
            try:
                self.context.storage_state(path=self.auth_file)
                print(f"✅ 登录状态已保存到 {self.auth_file}")
            except Exception as e:
                print(f"⚠️ 保存登录状态失败: {e}")

        if force:
            # 强制关闭浏览器
            if self.context:
                try:
                    self.context.close()
                except:
                    pass
            if self.browser:
                try:
                    self.browser.close()
                except:
                    pass
            if self.playwright:
                try:
                    self.playwright.stop()
                except:
                    pass
            print("✅ 浏览器已关闭")
        else:
            # 不关闭浏览器进程，保持运行以便下次复用
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
