<div align="center">

# 直播运营工具

**直播业务本地运营工具统一入口，覆盖 SKU 测价、绑券、直播间创建、蓝屏截图与京东选品推荐**

*Web 页面操作 · Excel 驱动 · 京东官方模板输出 · 使用监控统计 · Windows 一键打包*

[![Build Live Tools Windows](https://github.com/Friday-Up/live-tools/actions/workflows/build-windows.yml/badge.svg)](https://github.com/Friday-Up/live-tools/actions/workflows/build-windows.yml)
[![Release](https://img.shields.io/github/v/release/Friday-Up/live-tools?color=blue&logo=github)](https://github.com/Friday-Up/live-tools/releases)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-lightgrey.svg)](#快速开始)

[功能特性](#功能特性) • [快速开始](#快速开始) • [使用指南](#使用指南) • [监控统计](#监控统计) • [项目结构](#项目结构) • [开发测试](#开发测试) • [打包发版](#打包发版)

</div>

---

## 简介

直播运营工具是面向直播业务的本地 Web 工具集合。业务同事只需要打开一个页面，就可以完成当前已接入的五类高频操作：

- **SKU 测价**：批量读取商品 SKU，打开京东页面抓取实时售价，生成测价结果。
- **绑定券码/促销 ID**：读取直播业务提报表，生成京东后台官方批量上传模板和异常报告。
- **批量创建直播间**：读取直播标题、开播时间等信息，自动登录京东直播后台批量创建直播间并输出结果报告。
- **蓝屏自动截图**：填写京东直播大屏链接，按整点自动截图并输出 ZIP 和截图清单。
- **选品 Agent**：并发抓取京东四个活动来源，按来源和页面类目由 AI 筛选推荐，并输出可追溯的 JSON/Excel。

项目按“统一入口 + 独立业务模块”的方式组织：`live-web` 只负责页面、上传、下载和任务编排；各业务能力分别保留在测价、绑券、直播间、蓝屏截图和选品模块中。这样后续继续增加工具时，不会把所有业务规则混在一个目录里。

从 `v0.3.18` 开始，统一入口默认上报工具使用事件，用于统计实际使用人数、任务量、成功率、处理规模和耗时。上报采用异步 best-effort 方式，远端不可用时不会阻断测价、绑券、直播间创建或截图任务。

---

## 功能特性

| 特性 | 说明 |
| --- | --- |
| **统一 Web 入口** | 一个页面承载多个直播运营工具，默认访问 `http://127.0.0.1:8080` |
| **SKU 测价** | 上传含 `商品SKU` 列的 Excel，自动批量抓取价格并输出结果 |
| **绑定券码/促销 ID** | 上传业务提报表，生成京东官方上传模板和异常报告 |
| **批量创建直播间** | 上传 Excel，自动登录京东直播后台串行创建直播间，输出结果报告 |
| **蓝屏自动截图** | 输入 `jlive.jd.com/bigScreen` 链接，立即截图或按整点自动截图 |
| **选品 Agent** | 从四个京东来源抓取每类目最多 30 个候选，AI 筛选最多 10 个并说明淘汰与不足原因 |
| **列映射确认** | 绑券上传后自动推荐 SKU 列、券码/促销编码列，也支持手动改选 |
| **官方模板复用** | 保留京东后台官方 `商品上传模版（2026切片版）.xlsx`，只写入必要列 |
| **异常报告** | 标记空值、无效文本、重复 SKU、多 KEY、多促销 ID、同 SKU 多绑定值等问题 |
| **业务化文件名** | 输出 `京东绑券上传模板_YYYYMMDD-HHmmss_.xlsx` 和 `异常报告_YYYYMMDD-HHmmss_.xlsx` |
| **测价并发可配置** | 页面可调整并发浏览器数（1-10，默认 5），Mac 可适度提高，Windows 建议 4 |
| **测价浏览器可见** | 页面开关控制是否显示测价浏览器窗口，方便调试；登录窗口不受影响 |
| **短卖点自动匹配** | 开关控制，按 `短卖点` / `利益点` / `卖点` 关键词自动识别并写入官方模板 B 列 |
| **使用监控统计** | 默认上报页面访问、上传、任务开始/结束和结果下载事件，支持统计人数、成功率、处理量和耗时 |
| **运行时清理** | 上传文件和生成结果进入 `live-web/runtime/`，超过 2 天自动清理 |
| **Windows 打包** | GitHub Actions 自动构建 `Live-Tools-Windows.zip`，业务用户解压即可使用 |

---

## 快速开始

### Windows 业务用户

1. 打开 [Releases](https://github.com/Friday-Up/live-tools/releases)，下载最新的 `Live-Tools-Windows.zip`。当前监控修复版本为 [v0.3.18](https://github.com/Friday-Up/live-tools/releases/tag/v0.3.18)。
2. 解压到本地文件夹。
3. 双击 `启动直播工具.bat`。
4. 浏览器会自动打开：

```text
http://127.0.0.1:8080
```

5. 在页面顶部选择功能：
   - `SKU 测价`
   - `绑定券码/促销ID`
   - `批量创建直播间`
   - `蓝屏自动截图`
   - `选品 Agent`
6. 用完后双击程序自动生成的 `关闭服务.bat`，或关闭启动窗口。

从旧版本升级时，请先彻底关闭旧服务，再把新 ZIP 解压到新的空目录中运行，避免旧 EXE 和新文件混用。

### macOS / 开发者源码运行

从仓库根目录启动统一页面：

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
cd live-web
./start.sh
```

如果还需要批量创建直播间，安装直播间模块依赖：

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
python3 -m pip install -r live-room-creator/requirements.txt
```

如果提示缺少依赖，先安装 Web 和绑券基础依赖：

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
python3 -m pip install -r live-web/requirements.txt
python3 -m pip install -r live-promotion-binding/requirements.txt
```

如果需要测试 SKU 测价，再安装测价依赖和浏览器：

```bash
python3 -m pip install -r live-sku-price-audit/requirements.txt
python3 -m pip install -r live-bigscreen-capture/requirements.txt
python3 -m pip install -r product-selection-agent/requirements.txt
python3 -m playwright install chromium
```

---

## 使用指南

### 功能一：SKU 测价

#### 准备 Excel

Excel 至少需要一列 `商品SKU`：

| 商品SKU |
| --- |
| 100264886683 |
| 10079660739051 |

#### 操作流程

| 步骤 | 操作 |
| --- | --- |
| 1 | 进入页面后选择 `SKU 测价` |
| 2 | 上传含 `商品SKU` 列的 `.xlsx` 文件 |
| 3 | 填写价格门槛 |
| 4 | （可选）调整并发浏览器数（默认 5）、是否显示测价浏览器窗口 |
| 5 | 点击 `开始测价` |
| 6 | 首次运行或登录态失效时，在弹出的京东页面完成登录 |
| 6 | 回到工具页面点击 `我已登录，继续` |
| 7 | 等待任务完成并下载结果 |

### 功能二：绑定券码/促销 ID

#### 准备 Excel

业务提报表中至少需要两类信息：

| 信息 | 说明 |
| --- | --- |
| SKU 列 | 系统会按 `sku`、`skuID`、`上播 SKU ID` 等关键词自动推荐，也可手动选择 |
| 券码/促销编码列 | 系统会按 `券码`、`价码`、`促销编码`、`专享券`、`专享价`、`达人id` 等关键词自动推荐，也可手动选择 |
| 短卖点列（可选） | 开启“自动匹配短卖点”后，系统会按 `短卖点`、`利益点`、`卖点` 等关键词自动推荐，也可手动选择 |

绑定值支持三种：

| 类型 | 示例 | 写入官方模板 |
| --- | --- | --- |
| 专享券 KEY（vender 开头） | `vender_BA#a9d9...` | C 列 `专享券KEY码` |
| 专享券 KEY（BA 开头） | `BA_9t7zua1` | C 列 `专享券KEY码` |
| 专享价促销 ID | `381421541016` | D 列 `专享价促销ID` |
| 短卖点 | `限时直降` | B 列 `利益点`（不超过 22 字符） |

#### 操作流程

| 步骤 | 操作 |
| --- | --- |
| 1 | 进入页面后选择 `绑定券码/促销ID` |
| 2 | 上传业务提报 `.xlsx` 文件 |
| 3 | 确认 `SKU 列` 和 `券码/促销编码列`，必要时手动改选 |
| 4 | （可选）勾选“自动匹配短卖点”；勾选后确认 `短卖点列` |
| 5 | 点击 `生成导入模板` |
| 6 | 下载 `京东上传模板` 和 `异常报告` |
| 7 | 将生成的上传模板导入京东直播后台 |

#### 输出文件

| 文件 | 说明 |
| --- | --- |
| `京东绑券上传模板_YYYYMMDD-HHmmss_.xlsx` | 可直接上传到京东后台的官方模板副本 |
| `异常报告_YYYYMMDD-HHmmss_.xlsx` | 本次跳过、重复、异常和可上传明细 |

#### 异常报告口径

| 问题 | 处理方式 |
| --- | --- |
| 空绑定值 | 跳过，并写入报告 |
| 无效文本 | 写入 `需处理异常` |
| 同一单元格多个 KEY | 写入 `需处理异常` |
| 同一单元格多个促销 ID | 写入 `需处理异常` |
| 同一 SKU 多个不同绑定值 | 写入 `需处理异常`，需人工确认 |
| 重复 SKU 且绑定值相同 | 默认保留第一条，重复行写入报告 |
| 短卖点超过 22 字符 | 写入 `短卖点警告`，仍保留原值进入模板 |

---


### 功能三：批量创建直播间

#### 准备 Excel

Excel 至少需要两列：

| 直播标题 | 开播时间 |
| --- | --- |
| 直播间一号 | 2026-07-01 20:00:00 |
| 直播间二号 | 2026-07-02 21:30:00 |

可选列（留空时使用默认值）：

| 列名 | 默认值 | 说明 |
| --- | --- | --- |
| 直播封面 | 默认封面 | 当前版本不单独维护，使用系统默认 |
| 直播形式 | 正式直播 | 可选 `正式直播` / `测试直播` |
| 画面方向 | 竖屏 | 可选 `竖屏` / `横屏` |
| 直播地点 | 不显示地点 | 默认不显示地点 |
| 直播品类 | 多品类 | 当前默认 `多品类` |

#### 操作流程

| 步骤 | 操作 |
| --- | --- |
| 1 | 进入页面后选择 `批量创建直播间` |
| 2 | 上传含 `直播标题`、`开播时间` 列的 `.xlsx` 文件 |
| 3 | 确认列映射（系统会自动识别） |
| 4 | 点击 `开始创建` |
| 5 | 首次运行或登录态失效时，在弹出的京东页面完成登录 |
| 6 | 回到工具页面点击 `我已登录，继续` |
| 7 | 等待任务完成并下载结果 |

#### 输出文件

| 文件 | 说明 |
| --- | --- |
| `直播间创建结果_YYYYMMDD-HHmmss_.xlsx` | 每行创建状态、失败原因与汇总统计 |

#### 限制与策略

| 项目 | 说明 |
| --- | --- |
| 每日上限 | 30 个，超出时硬性拦截并报错 |
| 并发 | 串行创建，每行之间带延迟，降低风控风险 |
| 失败处理 | 单条失败记录原因后继续处理剩余行 |
| 重复处理 | 同一 Excel 中标题+开播时间重复的行会跳过并标记 |

### 功能四：蓝屏自动截图

#### 准备链接

打开京东直播实时大屏，复制蓝屏页面链接：

```text
https://jlive.jd.com/bigScreen?id=46794566
```

#### 操作流程

| 步骤 | 操作 |
| --- | --- |
| 1 | 进入页面后选择 `蓝屏自动截图` |
| 2 | 填写蓝屏页面链接，点击 `识别链接` |
| 3 | 选择截图日期和需要执行的整点 |
| 4 | 可点击 `立即截图一次` 做试跑，也可点击 `开始自动截图` |
| 5 | 首次运行或登录态失效时，在弹出的京东页面完成登录 |
| 6 | 等待任务完成并下载截图 ZIP |

#### 截图内容

当前版本按并集截取 15 项：概览总览、渠道流量饼状图、渠道成交饼状图、挂袋数据、7 个流量趋势、访问/成交用户画像、订单 Top10 和 GMV Top10。

#### 输出文件

| 文件 | 说明 |
| --- | --- |
| `蓝屏数据截图_{id}__YYYYMMDD_HHmmss_序号_截图项.png` | 单项截图 |
| `截图清单.xlsx` | 每项截图的计划整点、实际执行时间、状态和失败原因 |
| `蓝屏数据截图_{id}__YYYYMMDD.zip` | 本次截图 ZIP |

### 功能五：选品 Agent

进入“选品 Agent”后选择是否显示浏览器，以及来源不完整时是否允许保留部分结果，然后点击“开始选品”。默认并发抓取国家补贴、黑色星期五、排行榜和京东特价；每个页面类目保留最多 30 个候选，再由 AI 单次筛选并排序最多 10 个。

页面会持续展示抓取和推荐日志。任务完成后需要同时关注“抓取完整”和“AI 完整”：任一项为否时，页面会明确标为部分结果，不能把规则回退误认为完整 AI 推荐。

| 文件 | 说明 |
| --- | --- |
| `selection_时间.json` | 候选池、最终入选、推荐说明和完整诊断 |
| `selection_时间.xlsx` | 候选池、选品明细、推荐结果和运行诊断 |

模型配置复制 `product-selection-agent/model-config.example.json` 为同目录的 `model-config.local.json`；本地配置已被 Git 忽略，也可使用 `SELECTION_AI_*` 环境变量。未配置模型或模型失败时会明确使用规则回退，不会伪装为 AI 完整结果。

---

## 监控统计

### 默认行为

`v0.3.18` 起，Windows 打包版和源码运行默认开启使用监控，上报地址为：

```text
http://114.67.72.156/AllSpark/api/live-tools/events
```

上报由 `live-web` 后台异步执行，超时时间默认 2 秒。上报失败只写入服务日志，不会中断本地工具任务。

### 采集内容

| 类别 | 内容 |
| --- | --- |
| 用户标识 | 当前 Windows/macOS 系统用户名原值 |
| 应用信息 | 应用名称、版本、会话 ID |
| 使用行为 | 页面访问、文件上传、任务开始、任务结束、结果下载 |
| 任务信息 | 工具编码、任务 ID、状态、处理总量、成功数、失败数、耗时 |
| 工具补充信息 | 测价门槛和并发数、蓝屏真实 `room_id` 和计划时段、绑券/直播间创建结果计数 |

不会上报：

- Excel 文件内容和完整 SKU 列表
- 京东登录 Cookie、账号密码和授权文件
- 截图图片、测价结果文件和生成的业务报表

上传文件名和结果文件名可能作为任务诊断信息记录。监控数据用于评估工具价值、统计稳定性和排查问题，不影响工具本身的处理结果。

### 配置覆盖

默认配置位于 `live-web/config.py`。需要临时关闭或切换环境时，可以在启动程序前设置环境变量：

```bat
set LIVE_USAGE_EVENT_ENABLED=false
启动直播工具.bat
```

切换上报地址和 token：

```bat
set LIVE_USAGE_EVENT_ENDPOINT=https://example.com/api/live-tools/events
set LIVE_USAGE_EVENT_TOKEN=replace-token
set LIVE_USAGE_EVENT_ENABLED=true
启动直播工具.bat
```

可用配置：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LIVE_USAGE_EVENT_ENABLED` | `true` | 是否启用监控上报 |
| `LIVE_USAGE_EVENT_ENDPOINT` | 当前 order 事件接口 | 完整上报地址 |
| `LIVE_USAGE_EVENT_TOKEN` | 内置第一版 token | Bearer token |
| `LIVE_USAGE_EVENT_TIMEOUT_SECONDS` | `2.0` | 单次请求超时秒数 |

## 项目结构

```text
live/
├── README.md                         # 项目总说明
├── 启动直播工具.bat                   # Windows 业务入口
├── live-web/                         # 统一 Web 入口
│   ├── app.py                        # Flask 服务和 API
│   ├── config.py                     # 本地服务配置
│   ├── usage_reporter.py              # 直播工具使用事件异步上报
│   ├── start.sh                      # macOS / Linux 启动脚本
│   ├── start.bat                     # Windows 源码启动脚本
│   ├── templates/index.html          # 统一页面
│   ├── requirements.txt              # Web 基础依赖
│   └── tests/                        # Web 路由和页面测试
├── live-promotion-binding/           # 绑定券码/促销 ID 业务模块
│   ├── assets/                       # 京东官方上传模板
│   ├── promotion_binding/            # 核心解析、生成、报告逻辑
│   ├── requirements.txt
│   └── tests/
├── live-sku-price-audit/             # SKU 测价业务模块
│   ├── utils/                        # 浏览器、抓取、Excel 写入逻辑
│   ├── requirements.txt
│   └── tests/
├── live-room-creator/                # 批量创建直播间业务模块
│   ├── room_creator/                 # Excel 读取、校验、浏览器自动化、报告生成
│   ├── requirements.txt
│   └── tests/
├── live-bigscreen-capture/           # 蓝屏自动截图业务模块
│   ├── bigscreen_capture/            # 链接解析、整点排期、截图步骤、ZIP 输出
│   ├── requirements.txt
│   └── tests/
├── product-selection-agent/          # 京东多来源选品模块
│   ├── product_selection_agent/      # 抓取、筛选、推荐、运行上下文和服务层
│   ├── main.py                       # 开发调试用薄 CLI
│   ├── model-config.example.json     # 模型配置示例（不含密钥）
│   ├── requirements.txt
│   └── tests/
├── docs/                             # SOP、方案和实施计划
│   └── plans/
└── tests/                            # 仓库级测试，例如 Windows 打包约束
```

### 运行时目录

源码启动后会在 `live-web/runtime/` 下生成临时文件：

```text
live-web/runtime/
├── input/
│   ├── price-audit/
│   ├── promotion-binding/
│   └── room-creator/
└── output/
    ├── price-audit/
    ├── promotion-binding/
    ├── room-creator/
    ├── bigscreen-capture/
    └── product-selection/<task_id>/
```

`runtime/` 不作为业务归档目录。服务启动、上传和生成前都会清理超过 2 天的历史临时文件。

---

## 技术栈

| 组件 | 用途 |
| --- | --- |
| Python | 主要运行语言 |
| Flask | 本地 Web 服务和 API |
| openpyxl | Excel 读取、模板写入和异常报告生成 |
| Playwright | SKU 测价、直播间创建、蓝屏截图和选品抓取时打开浏览器、复用京东登录态 |
| PyInstaller | Windows 一键包构建 |
| unittest | 单元测试 |
| GitHub Actions | Windows 自动打包和 Release 上传 |

---

## 开发测试

### 运行全部测试

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live

python3 -m unittest discover -s tests -v

cd live-promotion-binding
python3 -m unittest discover -s tests -v

cd ../live-web
python3 -m unittest discover -s tests -v

cd ../live-sku-price-audit
python3 -m unittest discover -s tests -v

cd ../live-room-creator
python3 -m unittest discover -s tests -v

cd ../live-bigscreen-capture
python3 -m unittest discover -s tests -v

cd ../product-selection-agent
python3 -m unittest discover -s tests -v
```

### 常用局部测试

```bash
# 绑定券码/促销 ID
cd live-promotion-binding
python3 -m unittest tests/test_workbook_reader.py tests/test_service.py -v

# 统一 Web 入口
cd ../live-web
python3 -m unittest tests/test_config.py tests/test_usage_reporter.py tests/test_usage_reporting_routes.py tests/test_routes.py tests/test_web_template.py -v

# 测价模块
cd ../live-sku-price-audit
python3 -m unittest tests/test_excel_handler.py tests/test_audit_runner.py -v

# 蓝屏自动截图
cd ../live-bigscreen-capture
python3 -m unittest tests/test_service.py tests/test_capture_steps.py -v

# 选品 Agent
cd ../product-selection-agent
python3 -m unittest discover -s tests -v
```

---

## 打包发版

Windows 包由 GitHub Actions 自动构建：

- workflow：`.github/workflows/build-windows.yml`
- 构建产物：`Live-Tools-Windows.zip`
- Release 条件：推送 `v*` 标签时自动上传到 GitHub Release

本地开发验证通过后，再按需要创建新版本标签：

```bash
git tag -a v0.3.19 -m "v0.3.19"
git push origin v0.3.19
```

> 注意：业务测试未完成前不要发版。先本地验证，再提交和推送。

---

## 常见问题

<details>
<summary><b>Q1：Mac 本地启动后 8080 被占用怎么办？</b></summary>

说明已经有一个本地服务在运行。先在原启动终端按 `Ctrl+C` 停掉，再重新执行：

```bash
cd live-web
./start.sh
```
</details>

<details>
<summary><b>Q2：绑定券码上传后列名没自动匹配怎么办？</b></summary>

上传后页面会展示 `SKU 列` 和 `券码/促销编码列` 两个下拉框。自动推荐没命中时，手动选择对应列即可，不需要修改 Excel 表头。
</details>

<details>
<summary><b>Q3：绑定券码为什么还会生成异常报告？</b></summary>

业务提报表中可能存在空值、中文活动词、重复 SKU、多 KEY、多促销 ID 等情况。工具不会静默吞掉这些数据，会把需要人工确认的内容写入异常报告。
</details>

<details>
<summary><b>Q4：绑定券码工具会自动上传京东后台吗？</b></summary>

当前版本不会自动上传，只生成京东后台可导入的官方模板和异常报告。自动登录、自动上传、上传失败结果回填属于后续阶段。
</details>

<details>
<summary><b>Q5：测价时为什么需要手动登录京东？</b></summary>

测价依赖京东页面登录态。首次运行或登录态失效时，需要在弹出的浏览器里手动完成登录，工具会保存登录态供后续复用。
</details>

<details>
<summary><b>Q6：Windows 测价慢怎么调？</b></summary>

Windows 建议并发浏览器数设为 4；超过 4 容易因 IPC/资源争用反而变慢。Mac 性能充裕时可尝试 5。
</details>

<details>
<summary><b>Q7：生成文件会一直堆在项目目录里吗？</b></summary>

不会。统一入口把上传文件和生成结果放在 `live-web/runtime/`，并按 2 天保留策略自动清理。
</details>

<details>
<summary><b>Q8：蓝屏自动截图只需要填什么？</b></summary>

只需要填写京东直播大屏链接。直播间 ID 会从链接里的 `id` 参数自动识别，截图整点在页面上勾选即可。
</details>

<details>
<summary><b>Q9：工具会向远端上报什么数据？</b></summary>

默认上报系统用户名、工具动作、任务状态、处理数量、耗时和必要的诊断信息，用于统计使用情况和稳定性。不会上传 Excel 内容、完整 SKU 列表、京东登录信息、截图或结果文件。上报失败不会影响本地任务。
</details>
