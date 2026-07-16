# Product Selection Web Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将京东四来源选品作为后台任务接入直播运营统一 Web 页面，并清理正式运行不依赖的调研残留。

**Architecture:** 把现有平铺模块整理为 `product_selection_agent` Python 包，新增运行上下文和服务入口，CLI 与 `live-web` 共用服务。Web 通过后台线程执行服务、轮询内存状态并从受控运行时目录下载 JSON/Excel；Windows PyInstaller 显式包含该包。

**Tech Stack:** Python 3.9+、Flask、threading、Playwright、openpyxl、原生 HTML/JavaScript、unittest、PyInstaller。

---

### Task 1: 清理调研残留并建立正式包边界

**Files:**
- Delete: `product-selection-agent/scripts/`
- Delete: `product-selection-agent/output/.DS_Store`
- Create: `product-selection-agent/product_selection_agent/__init__.py`
- Move: `product-selection-agent/{config,fetcher,parser,recommender,selector}.py` 到正式包
- Modify: 包内模块使用相对导入
- Modify: `product-selection-agent/tests/test_core.py`

**Steps:**
1. 写一个导入测试，断言 `product_selection_agent` 的核心模块可加载。
2. 运行测试确认当前缺少正式包。
3. 建立包、迁移模块并改相对导入；删除 `flatten_selection()` 和 `selector.py` 调试主程序，保留仍有回归价值的 `select_top()`。
4. 删除探测脚本、大样本和系统缓存。
5. 运行选品测试确认迁移通过。

### Task 2: 增加可复用运行上下文和选品服务

**Files:**
- Create: `product-selection-agent/product_selection_agent/runtime.py`
- Create: `product-selection-agent/product_selection_agent/service.py`
- Modify: `product-selection-agent/product_selection_agent/fetcher.py`
- Modify: `product-selection-agent/product_selection_agent/recommender.py`
- Modify: `product-selection-agent/main.py`
- Test: `product-selection-agent/tests/test_service.py`

**Steps:**
1. 写失败测试覆盖日志回调、停止信号、输出 JSON/Excel 和精简 CLI 调用。
2. 实现 `RunContext.log()`、`RunContext.check_cancelled()` 与 `SelectionCancelled`。
3. 把抓取和推荐日志改为运行上下文输出，并在来源、Tab、类目任务边界检查停止信号。
4. 将原 `main.py` 的业务编排和报表写入迁到 `service.py`，提供 `run_selection()` 与 `execute_selection()`。
5. 将 `main.py` 收敛成参数解析、服务调用和简报输出。
6. 运行选品模块测试。

### Task 3: 增加 Web 后台任务 API

**Files:**
- Modify: `live-web/app.py`
- Test: `live-web/tests/test_product_selection_routes.py`

**Steps:**
1. 写失败路由测试：初始状态、启动、重复启动、日志更新、停止、成功结果、失败结果和安全下载。
2. 注册选品模块路径和服务导入，增加运行时输出目录。
3. 实现单任务状态、锁、停止事件和日志回调。
4. 实现 `/api/product-selection/start|status|stop|download/...`。
5. 将任务开始、结束和下载接入现有使用统计。
6. 运行 Web 路由测试。

### Task 4: 增加统一页面选品面板

**Files:**
- Modify: `live-web/templates/index.html`
- Test: `live-web/tests/test_web_template.py`

**Steps:**
1. 写失败模板测试，断言页签、配置控件、四个 API、日志与下载控件存在且 ID 唯一。
2. 新增“选品 Agent”页签和面板。
3. 实现开始、每秒轮询、停止、结果摘要、JSON/Excel 下载交互。
4. 对 `fetch_complete=false`、`ai_complete=false` 和任务失败分别展示警告或错误。
5. 运行模板测试并搜索重复 ID。

### Task 5: 更新依赖、Windows 打包和说明

**Files:**
- Modify: `live/.github/workflows/build-windows.yml`
- Modify: `live/tests/test_windows_packaging.py`
- Modify: `live/live-web/README.md`
- Modify: `live/README.md`
- Modify: `live/product-selection-agent/README.md`

**Steps:**
1. 写失败打包测试，要求安装选品依赖、加入包路径/隐式导入并校验发布目录。
2. 更新工作流测试、依赖安装、PyInstaller 参数和发布目录复制/校验。
3. 更新统一入口、目录、运行时与选品使用说明，并修正 `live-web` 文档中“7 天”与代码“2 天”的旧不一致。
4. 运行仓库级打包测试。

### Task 6: 全量验证与目录卫生

**Files:**
- Verify all modified files

**Steps:**
1. 在 `product-selection-agent` 运行 `python3 -m unittest discover -s tests -v`。
2. 在 `live-web` 运行 `python3 -m unittest discover -s tests -v`。
3. 在 `live` 根运行 `python3 -m unittest discover -s tests -v`。
4. 运行 `python3 -m compileall -q product-selection-agent live-web`。
5. 运行 `git diff --check`，确认未提交密钥、输出、日志和缓存。
6. 使用 Flask 测试客户端执行一次桩选品任务生命周期，验证状态和两个下载端点。
