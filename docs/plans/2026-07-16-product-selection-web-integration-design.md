# 选品 Agent 接入统一 Web 入口设计

## 目标

将 `product-selection-agent` 接入 `live-web`，让业务用户在统一页面启动京东四来源抓取和 AI 选品、查看实时日志与运行结果并下载 JSON/Excel，同时保留精简 CLI 供开发排错。

## 方案比较

### 方案 A：Web 直接启动选品 CLI 子进程

优点是改动少、模块隔离强。缺点是 Windows PyInstaller 单文件运行时没有可直接调用的独立 Python 解释器，打包发布难以稳定支持；状态和停止也只能通过解析进程输出实现。

### 方案 B：把选品代码复制到 `live-web`

短期接入快，但会形成两套抓取、模型配置和报表逻辑，后续修复无法保持一致，不符合统一入口的模块边界。

### 方案 C：选品模块提供可复用服务，Web 后台线程调用（采用）

选品核心继续留在独立目录，提供带日志回调、停止信号和输出目录参数的服务入口；CLI 与 Web 复用同一服务。`live-web` 只负责任务编排、状态、下载和界面。该方案既适合源码运行，也能通过 PyInstaller 隐式导入和数据打包支持 Windows 发布包。

## 模块结构

- `product-selection-agent/product_selection_agent/`：正式 Python 包，包含配置、抓取、解析、候选池、AI 推荐、报表和服务编排。
- `product-selection-agent/main.py`：只保留参数解析和调用服务的薄 CLI。
- `live-web/app.py`：注册选品后台任务 API，维护单任务状态并调用选品服务。
- `live-web/templates/index.html`：新增“选品 Agent”工具页签，展示运行选项、实时日志、结果摘要和下载按钮。

## 任务流程

1. 页面点击“开始抓取并推荐”。
2. `POST /api/product-selection/start` 校验当前没有选品任务运行，初始化状态并启动后台线程。
3. 后台线程调用选品服务；服务通过回调把原有控制台日志同步写入 Web 状态。
4. 页面每秒轮询 `GET /api/product-selection/status`，显示阶段、日志、来源数、类目数、抓取完整性和 AI 完整性。
5. 完成后由 `live-web/runtime/output/product-selection/<task_id>/` 保存 JSON 和 Excel。
6. 页面分别调用下载 API 获取结果；运行时文件遵循统一的 2 天清理策略。

## 停止与并发

- 同一时间只允许一个选品任务，重复启动返回明确错误。
- `POST /api/product-selection/stop` 设置停止信号。
- 抓取阶段在来源或类目边界检查停止信号；AI 推荐阶段在提交新类目任务前检查。无法安全打断的单次浏览器或模型调用完成后再退出。
- 选品任务与其他浏览器工具共用京东登录态文件，但各自创建浏览器实例；页面沿用现有互斥提示，避免用户同时启动多个高负载浏览器任务。

## 状态与错误

状态至少包含：`running`、`stopping`、`stage`、`logs`、`started_at`、`finished_at`、`task_id`、`success`、`error`、`summary`、`json_download_url`、`excel_download_url`。

- 抓取或模型异常写入实时日志和最终错误。
- `fetch_complete=false` 或 `ai_complete=false` 不隐藏结果；页面用警告状态展示，并允许下载审计。
- 下载 API 只允许访问当前任务记录中的两个结果文件，禁止任意路径读取。

## 清理范围

删除仅用于早期接口调研的 `scripts/` 及其中 HTML/JSON 大样本；删除未被正式代码和测试调用的 `flatten_selection()`。保留当前仍覆盖排序回退行为的 `select_top()`，避免在 Web 接入中顺带扩大业务改造面。删除 `.DS_Store` 等系统缓存，不删除本地模型配置和业务输出。

## 页面范围

第一版只提供：无头/显示浏览器开关、允许部分来源开关、开始、停止、实时日志、结果摘要、JSON/Excel 下载。不在页面提供模型密钥编辑，继续使用环境变量或 `model-config.local.json`，避免密钥通过浏览器暴露。

## 测试与发布

- 选品模块：服务入口、日志回调、停止信号、输出文件单元测试。
- Web：启动/状态/停止/下载路由测试，页面控件和 API 字符串测试，使用桩服务避免真实抓取。
- 仓库：Windows 构建工作流必须安装选品依赖、加入包路径和隐式导入，并校验发布目录包含选品模块。
- 最终运行各子模块 `unittest`、`compileall`、`git diff --check`，再用本地 Web 测试客户端验证完整任务生命周期。
