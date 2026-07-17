# SKU 测价模块

本目录提供直播运营工具的 SKU 测价核心能力。业务用户统一从仓库根目录的 `启动直播工具.bat`（Windows）或 `live-web/start.sh`（macOS / Linux）进入；Web 页面和任务编排位于 `../live-web/`，本目录不再维护重复的独立 Web 服务。

## 能力

- 从 Excel 或统一 Web 页面的 SKU 输入框读取商品 SKU。
- 复用京东登录态，并在失效时引导重新登录。
- 并发打开商品页，遍历商品系列和规格并读取实时价格。
- 低于门槛价时标记异常，并补充商品截图。
- 生成带价格、备注和截图的 Excel 结果。

## 目录

```text
live-sku-price-audit/
├── main.py                 # 开发调试用命令行入口
├── config.py               # 测价默认配置和运行目录
├── requirements.txt        # 模块依赖
├── utils/
│   ├── audit_runner.py     # 批量任务、停止和登录重试编排
│   ├── browser_manager.py  # Playwright 浏览器和登录态管理
│   ├── excel_handler.py    # Excel 读取、结果写入和图片嵌入
│   └── jd_crawler.py       # 京东商品价格与规格抓取
├── input/                  # CLI 输入目录
├── output/                 # CLI 临时结果目录
└── tests/                  # 核心模块和 CLI 测试
```

## 业务使用

推荐使用统一页面：

```bash
cd ../live-web
./start.sh
```

浏览器打开 `http://127.0.0.1:8080` 后进入“SKU 测价”。页面支持上传 `.xlsx` 或直接输入 SKU，并可设置价格门槛、并发浏览器数和是否显示浏览器窗口。

Windows 业务包直接双击仓库或发布包根目录的 `启动直播工具.bat`。

## CLI 调试

CLI 仅供开发和排障使用：

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
python3 main.py -f input/点菜清单.xlsx -t 6.0
```

不传 `-f` 或 `-t` 时，`main.py` 会从 `input/` 中列出文件并交互询问价格门槛。

输入文件必须是 `.xlsx`，并包含“商品SKU”列（兼容带括号说明的表头）。登录态保存在 `jd_auth.json`，该文件已被 Git 忽略。

## 配置

`config.py` 中的主要配置：

- `threshold_price`：默认价格门槛。
- `concurrent_workers`：并发浏览器数。
- `delay_min` / `delay_max`：商品处理间隔。
- `auth_file`：京东登录态文件。
- `input_dir` / `output_dir` / `screenshot_dir`：CLI 运行目录。

统一 Web 会复用这些核心模块，但将输入和结果存放在 `live-web/runtime/`，超过 2 天的临时文件会自动清理。

## 测试

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q .
```
