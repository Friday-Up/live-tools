<div align="center">

# 🛒 直播 SKU 价格巡检工具

**京东直播选品自动化测价 —— 批量抓取 SKU 实时售价，自动判定是否符合上菜门槛**

*Playwright 自动化 · Excel 驱动 · 截图留证 · 一键启动*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/python/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](#-快速开始)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/Friday-Up/live-sku-price-audit/pulls)
[![GitHub Stars](https://img.shields.io/github/stars/Friday-Up/live-sku-price-audit?style=social)](https://github.com/Friday-Up/live-sku-price-audit)

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [使用指南](#-使用指南) • [配置说明](#-配置说明) • [常见问题](#-常见问题)

</div>

---

## 📖 简介

直播运营每天需要审核大量选品 SKU，核心痛点是**确认商品当前售价是否低于门槛价**。手动打开京东页面逐个查看，几百个 SKU 耗时耗力。

**直播 SKU 价格巡检工具**通过浏览器自动化，批量抓取每个 SKU 的实时售价，自动与门槛价比对，生成带截图的结果表格。

> 把"逐个点开网页看价格"变成"一键出结果"。

> 本模块已集成到 `live-web` 统一入口。业务用户推荐直接使用仓库根目录的 `启动直播工具.bat`（Windows）或 `live-web/start.sh`（macOS）。

---

## ✨ 功能特性

| 特性 | 说明 |
| --- | --- |
| 📁 **输入方式清晰** | 命令行模式自动列出 `input/` 目录下的 `.xlsx` 文件；Web 模式仅支持用户手动上传 Excel |
| 💰 **门槛价灵活设定** | 支持命令行参数或交互式输入，随时调整 |
| 🔐 **登录态持久化** | 首次人工登录后自动保存，后续自动复用；失效时暂停等待人工登录 |
| 🏷️ **多系列多规格遍历** | 自动识别商品系列标签（如镇店爆款/品质纯奶），遍历每个系列下的所有规格 |
| 🕷️ **价格自动抓取** | 自动抓取京东商品页当前售价，支持备用选择器容错 |
| 📸 **智能截图策略** | 仅对低于门槛价的 SKU 截图，发现后立即截图并停止遍历，节省时间和磁盘 |
| ⚠️ **自动门槛判定** | 低于门槛自动标记"不符合上菜" |
| 🧹 **截图自动清理** | 每次运行前清空旧截图，防止脏数据累积 |
| 🖥️ **双模式支持** | 命令行模式（`main.py`）+ Web GUI 模式（`app.py`），满足不同场景 |
| 🖥️ **Web GUI 界面** | 提供可视化网页操作界面，上传文件、查看进度、下载结果，无需命令行 |
| ⚡ **快扫模式** | 发现任意规格低于门槛价即停止该 SKU 遍历，减少不必要点击 |
| 🔢 **并发可配置** | 支持 1-10 个浏览器并发，默认 3；Mac 可适当提高，Windows 建议 4 |
| 👁️ **浏览器可见开关** | 页面可控制是否显示测价浏览器窗口，方便调试；登录窗口不受影响 |
| 🪟 **Windows 性能优化** | 浏览器级图片禁用 + 精准 route 拦截 + 响应按需匹配，降低 IPC 开销 |
| 🔧 **环境自动检测** | 自动检测 Python、依赖、浏览器，缺失时引导安装 |
| ⏱️ **防爬策略** | 保留随机延迟配置，配合快扫与并发策略使用 |

---

## 🛠️ 环境要求

- **Python 3.8+**
- **Playwright**（Chromium 浏览器）

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium
```

---

## 🚀 快速开始

### 方式一：Web GUI 模式（推荐，可视化操作）

#### Windows 免安装版（业务人员推荐）

1. **下载 Release**
   - 访问 [Releases 页面](https://github.com/Friday-Up/live-sku-price-audit/releases)
   - 下载 `SKU-Price-Audit-Web-Windows.zip`

2. **解压运行**
   ```text
   解压 ZIP → 双击 "启动测价工具.bat"
   ```

3. **浏览器操作**
   - 自动打开浏览器访问 `http://localhost:8080`
   - 在网页上上传 Excel、设置门槛价、开始测价

> 💡 **无需安装 Python**，解压即用

#### 源码运行（开发者）

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 启动 Web 服务（Windows 推荐双击 start_web.bat）
python app.py
```

源码模式下如缺少依赖，请先执行：

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

---

### 方式二：命令行模式

#### 1. 克隆项目

```bash
git clone https://github.com/Friday-Up/live-sku-price-audit.git
cd live-sku-price-audit
```

#### 2. 准备输入文件

将业务表格放入 `input/` 目录：

```text
input/
└── 6月8日点菜.xlsx    # 包含「商品SKU」列的业务表格
```

> 📝 `input/` 目录下的 `.xlsx` 业务数据已被 `.gitignore` 排除，不会上传到 Git。

#### 3. 一键启动（推荐）

**macOS / Linux**

```bash
chmod +x start.sh
./start.sh
```

**Windows**

```bash
start.bat
```

**启动脚本交互流程**：

```
1. 自动检测环境（Python/依赖/浏览器）
2. 📁 列出 input/ 目录下所有 .xlsx 文件
   [1] 6月5日青春采销点菜.xlsx
   [2] 6月8日点菜.xlsx
   请输入编号（1-2）：2
3. 💰 输入价格门槛（回车默认 6.0）
4. 启动浏览器 → 人工登录（首次）→ 批量测价 → 输出结果
```

#### 4. 查看结果

```text
output/
├── 6月8日点菜_result.xlsx    # 结果表格（含价格、截图、备注）
└── screenshots/               # 商品页面截图
    ├── 100264886683.png
    └── ...
```

---

## 📚 使用指南

### 输入表格格式

| 提交时间 | 商品SKU | 提交者 | 价格 | 图片 | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026/6/8 20:00 | 100264886683 | 用户A | （空） | （空） | （空） |

> **注意**：只需填写 `商品SKU` 列，其他列由程序自动填充。

### 命令行参数

```bash
python main.py [-h] [-t THRESHOLD] [-f FILE]

选项：
  -h, --help            显示帮助信息
  -t THRESHOLD, --threshold THRESHOLD
                        价格门槛（如：10.0, 20.5）
  -f FILE, --file FILE  输入 Excel 文件路径（如：input/6月8日点菜.xlsx）
```

### 常用命令

```bash
# 指定文件和门槛价
python main.py -f input/6月8日点菜.xlsx -t 15.0

# 只指定门槛价（文件交互式选择）
python main.py -t 20.0

# 全部交互式
python main.py
```

### 登录态管理

| 场景 | 行为 | 用户操作 |
|:---|:---|:---|
| **首次运行** | 打开浏览器 → 提示登录 → 人工登录 → 保存 `jd_auth.json` | 扫码/密码登录 |
| **后续运行（登录态有效）** | 自动加载 `jd_auth.json` → 无需重新登录 | **无需操作** |
| **登录态失效（Web 模式）** | 自动检测到失效 → **弹出"我已登录"弹窗** → 在浏览器中重新登录 → 点击"我已登录，继续" | 在浏览器中重新登录，点击按钮继续 |
| **登录态失效（命令行模式）** | 自动检测到失效 → **暂停程序，保留浏览器窗口** → 等待人工登录 → 按回车继续 | 在浏览器中重新登录，按回车继续 |

> **注意**：无需手动删除 `jd_auth.json`，程序会自动处理登录态失效。

---

## ⚙️ 配置说明

编辑 `config.py`：

```python
CONFIG = {
    'input_dir': 'input',                    # 输入目录
    'output_dir': 'output',                  # 输出目录
    'screenshot_dir': 'output/screenshots',  # 截图目录
    'threshold_price': 6.0,                  # 默认门槛价
    'concurrent_workers': 3,                 # 并发浏览器数（Mac 可设 4-5，Windows 建议 4）
    'delay_min': 1,                          # 最小延迟（秒）
    'delay_max': 3,                          # 最大延迟（秒）
    'auth_file': 'jd_auth.json',             # 登录态文件
    'sku_column': '商品SKU',                  # SKU 列名
    'price_column': '价格',                   # 价格列名
    'image_column': '图片',                   # 图片列名
    'remark_column': '备注',                  # 备注列名
}
```

---

## ❓ 常见问题

<details>
<summary><b>Q1：首次运行需要做什么？</b></summary>

启动后会自动打开 Chromium 浏览器，请在弹出的京东页面**手动登录**（扫码或密码）。登录成功后，程序会自动保存登录态，后续运行无需再次登录。
</details>

<details>
<summary><b>Q2：登录态失效了怎么办？</b></summary>

**Web GUI 模式**：程序会自动弹出"我已登录"弹窗，请在浏览器中重新登录京东，然后点击弹窗上的"✓ 我已登录，继续"按钮。登录恢复后会重试当前 SKU，不会跳过。

**命令行模式**：程序会自动检测到失效，重新打开登录页面，请在浏览器中重新登录后，回到终端按回车键继续。

无需手动删除 `jd_auth.json`。
</details>

<details>
<summary><b>Q3：Windows 双击后网页打不开怎么办？</b></summary>

请打开程序目录下的 `logs/web.log` 查看启动日志。源码模式的 `start_web.bat` 会自动检查并安装 Python 依赖和 Playwright Chromium；如果网络限制导致安装失败，日志里会显示具体错误。
</details>

<details>
<summary><b>Q4：支持哪些 Excel 格式？</b></summary>

仅支持 `.xlsx` 格式，不支持 `.xls`。表格必须包含 `商品SKU` 列，也兼容 `商品SKU（必填）` 这类带说明的表头；如果找不到 SKU 列会直接报错，不会猜测列位置。
</details>

<details>
<summary><b>Q5：运行一次大概多久？</b></summary>

耗时取决于 SKU 数量、每个商品页的系列/规格数量，以及机器性能。实测参考（v0.3.14 之后）：

- Mac：20 SKU 约 1.5 分钟（5 并发）
- Windows：19 SKU 约 3 分钟（4 并发）

Windows 不建议超过 4 并发，否则 IPC/资源争用会导致整体变慢；Mac 可尝试 5 并发。
</details>

<details>
<summary><b>Q6：截图会被保留吗？</b></summary>

每次运行前会自动清空 `output/screenshots/` 目录，只保留当前运行的截图。结果文件（`*_result.xlsx`）不会自动删除。
</details>

<details>
<summary><b>Q7：为什么有些 SKU 只检测了几个规格就跳过了？</b></summary>

这是正常行为。工具在遍历规格时，一旦发现**任意规格低于门槛价**，会立即截图并停止遍历该 SKU 的剩余规格，以节省时间和减少不必要的页面点击。
</details>

<details>
<summary><b>Q8：多系列商品（如镇店爆款/品质纯奶）会全部检测吗？</b></summary>

会。工具会自动识别商品页面上的系列标签，逐个点击每个系列，再遍历该系列下的所有规格，确保不遗漏。
</details>

<details>
<summary><b>Q9：Web GUI 模式和命令行模式有什么区别？</b></summary>

| 对比项 | Web GUI 模式 | 命令行模式 |
|:---|:---|:---|
| **操作方式** | 浏览器网页操作 | 终端命令行交互 |
| **适用人群** | 业务人员（推荐） | 开发者/技术人员 |
| **启动命令** | `python app.py` 或双击 `启动测价工具.bat` | `python main.py` 或 `start.bat` |
| **文件选择** | 网页拖拽/点击上传 Excel | 终端输入编号选择 |
| **进度查看** | 网页实时进度条+日志 | 终端文字输出 |
| **登录弹窗** | 网页"我已登录"按钮 | 终端按回车确认 |

两种模式功能完全一致，只是交互方式不同。
</details>

---

## 🛠️ 技术栈

| 组件 | 用途 |
| --- | --- |
| 🐍 [Python 3.8+](https://www.python.org/) | 运行环境 |
| 🎭 [Playwright](https://playwright.dev/python/) | 浏览器自动化（价格抓取/截图） |
| 📊 [openpyxl](https://openpyxl.readthedocs.io/) | Excel 读写（结果输出/图片嵌入） |
| 🖼️ [Pillow](https://pillow.readthedocs.io/) | 图片处理 |
| 🌐 [Flask](https://flask.palletsprojects.com/) | Web GUI 服务（可视化操作界面） |

---

## 🗂️ 项目结构

```text
live-sku-price-audit/
├── main.py                 # 命令行模式入口
├── app.py                  # Web GUI 模式入口（Flask 服务）
├── config.py               # 配置文件
├── requirements.txt        # Python 依赖
├── start.sh                # macOS/Linux 命令行启动脚本
├── start.bat               # Windows 命令行启动脚本
├── start_web.bat           # Windows Web GUI 启动脚本
├── templates/              # Web 前端页面
│   └── index.html          # 主页面（上传/进度/结果）
├── utils/                  # 核心逻辑
│   ├── browser_manager.py  # 浏览器管理（登录态复用/重新登录）
│   ├── audit_runner.py     # 批量任务编排（停止/登录重试/结果汇总）
│   ├── jd_crawler.py       # 京东价格爬取（价格提取/截图/弹窗关闭）
│   ├── excel_handler.py    # Excel 读写（SKU 读取/结果写入/图片嵌入）
│   └── cleanup.py          # 临时文件清理
├── tests/                  # 单元测试
├── input/                  # 输入文件目录（.gitignore 排除业务数据）
│   ├── README.md           # 输入格式说明
│   └── 点菜清单模板.xlsx    # 模板文件
├── output/                 # 输出目录（.gitignore 排除）
│   └── README.md           # 输出说明
├── docs/                   # 项目文档（.gitignore 排除内部文档）
│   └── README.md
├── jd_auth.json            # 登录态文件（.gitignore 排除）
├── LICENSE                 # MIT 协议
└── README.md               # 本文件
```

---

## 🤝 贡献

欢迎任何形式的贡献！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/amazing-feature`
3. 提交变更：`git commit -m 'feat: add amazing feature'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 提交 Pull Request

提交信息请遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范。

---

## 📜 License

本项目基于 [MIT License](./LICENSE) 开源协议发布。

---

## 🌟 致谢

- [Playwright](https://playwright.dev/) —— 现代浏览器自动化引擎
- [openpyxl](https://openpyxl.readthedocs.io/) —— Python Excel 处理库
- 所有为本项目提供反馈和建议的小伙伴 ❤️

<div align="center">

由 [Friday Up](https://github.com/Friday-Up) 维护

**如果这个工具帮到了你，欢迎点一个 ⭐ Star 支持一下！**

</div>
