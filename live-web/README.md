# 直播本地工具统一入口

统一承载直播相关本地 Web 工具。

当前入口：

- 绑定券码/促销ID：已接入，支持上传业务表并生成京东官方上传模板和异常报告。
- SKU 测价：已接入，复用原测价核心逻辑和京东登录态。
- 批量创建直播间：已接入，复用直播间创建模块。
- 蓝屏自动截图：已接入，填写京东直播大屏链接后可立即截图或按整点自动截图。
- 选品 Agent：动态读取并分组展示京东四个来源的品类，按用户勾选范围并发抓取并交给 AI 筛选，输出业务 Excel；品类默认全选并缓存 30 分钟。

## 启动

macOS / Linux：

```bash
./start.sh
```

Windows：

```bat
start.bat
```

启动后访问：

```text
http://127.0.0.1:8080
```

## 目录

- `app.py`：Flask 服务和 API。
- `templates/index.html`：统一页面。
- `runtime/input/`：上传文件暂存。
- `runtime/output/`：生成文件输出。
- `runtime/output/product-selection/<task_id>/`：选品任务的 Excel 输出。
- `tests/`：Web 路由和页面测试。

## 说明

测价能力复用 `../live-sku-price-audit/utils/` 下的浏览器、爬取和 Excel 写入逻辑；绑定券码/促销ID能力复用 `../live-promotion-binding/` 下的模板生成逻辑。
蓝屏自动截图能力复用 `../live-bigscreen-capture/` 下的链接解析、整点排期、截图步骤和 ZIP 输出逻辑。
选品能力复用 `../product-selection-agent/product_selection_agent/` 下的抓取、筛选、推荐和报表服务；Web 只负责任务控制、日志和下载。

`runtime/` 是运行时临时目录，不作为业务归档目录。服务启动时和每次上传/生成前会清理超过 2 天的临时文件；历史遗留的 `input/`、`output/` 目录也会按同样规则清理。
