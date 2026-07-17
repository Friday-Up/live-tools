# Playwright 无 Headless Shell 打包优化设计

## 目标

Windows 和 macOS 安装包不再携带独立的 Chromium Headless Shell，继续保留完整 Chrome for Testing，保证无头抓取、显示浏览器、人工登录和截图流程都可用。

## 方案比较

### 方案 A：完整 Chrome + 新版无头模式（采用）

- 安装命令使用 `playwright install chromium --no-shell`。
- 所有 Chromium 启动入口指定 `channel="chromium"`。
- 无头任务使用完整 Chrome 的新版无头模式；有头任务继续使用同一完整浏览器。
- 优点：删除重复的 Headless Shell，保留全部现有业务能力。
- 风险：新版无头模式与旧 Headless Shell 在渲染和资源占用上可能有细微差异，需要打包版回归。

### 方案 B：保留当前双浏览器结构

- 不改启动逻辑和安装命令。
- 优点：运行行为不变。
- 缺点：安装包继续携带完整 Chrome 和 Headless Shell，体积问题不解决。

### 方案 C：只保留 Headless Shell

- 安装时使用 `--only-shell`。
- 优点：纯无头包最小。
- 缺点：无法支持显示浏览器、人工登录和可视化排查，不符合直播运营工具需求，因此不采用。

## 改动边界

1. Windows、macOS GitHub Actions 的 Playwright 安装命令增加 `--no-shell`。
2. SKU 测价共享 BrowserManager 和选品独立抓取入口指定 `channel="chromium"`；直播间创建、蓝屏截图复用 BrowserManager，因此随之生效。
3. 保持 `headless` 页面开关、登录恢复、抓取规则、截图规则和业务输出不变。
4. 增加回归测试，约束打包流程不安装 Headless Shell，并约束真实启动参数使用 Chromium channel。

## 验证

- 单元测试覆盖安装命令和启动参数。
- 运行各业务模块整仓测试。
- GitHub Actions 构建 Windows、Intel macOS、Apple Silicon macOS 包。
- 构建过程执行现有打包程序健康检查；产物中确认不存在 `chromium_headless_shell` / `chrome-headless-shell` 目录。
- 对比新旧产物大小；业务侧重点试跑选品品类加载、抓品、SKU 无头测价、登录窗口和蓝屏截图。

