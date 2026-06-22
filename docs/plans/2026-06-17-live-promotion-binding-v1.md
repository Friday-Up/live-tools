# 直播绑定券码/促销ID 第一版技术方案

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在现有直播本地工具体系中新增“绑定券码/促销ID”能力，第一版先完成业务表格解析、京东官方批量上传模板生成、异常报告生成，并为后续自动上传京东直播后台预留接口。

**Architecture:** 建议把“启动脚本 + Web 页面 + 任务状态”从现有测价目录中抽成统一入口目录，测价和绑定券分别作为独立业务模块维护。绑定券第一版只依赖 Excel 解析和模板写入，不依赖京东后台页面自动化，降低首版风险。

**Tech Stack:** Python 3.8+、Flask、openpyxl、Playwright（第二阶段自动上传时复用）、pytest。

---

## 背景和结论

当前 `live/live-sku-price-audit/` 既是测价业务代码目录，也是 Web GUI、启动脚本、模板页面、浏览器登录态的承载目录。这样继续加“绑定券码/促销ID”会让测价目录变成事实上的总入口，后续功能会越来越混。

本次建议做一次轻量产品结构调整：

- 新增统一 Web 工具入口目录，承载启动脚本、Flask app、页面、公共上传下载和任务状态。
- 保留 `live/live-sku-price-audit/` 作为“点菜测价”业务模块。
- 新增 `live/live-promotion-binding/` 作为“绑定券码/促销ID”业务模块。
- 第一版不做京东后台自动上传，只生成可直接上传京东后台的官方模板文件和异常报告。

这样用户仍然只需要启动一个页面，但代码所有权是清晰的。

## 第一版目标

第一版交付范围：

1. 页面新增“绑定券码/促销ID”入口。
2. 用户上传事业部提报表格。
3. 用户选择或使用内置京东官方模板：`商品上传模版（2026切片版） .xlsx`。
4. 程序读取两列：
   - `上播·SKU ID*【必填】`
   - `券码/价码 达人id：22766602`
5. 程序识别两类有效值：
   - 专享券 KEY：形如 `vender_BA#...`
   - 专享价促销 ID：纯数字长 ID
6. 程序复制官方模板，填充：
   - A 列：`SKUID`
   - C 列：`专享券KEY码`
   - D 列：`专享价促销ID`
7. 程序生成异常报告，列出无效文本、空值、重复 SKU、多 KEY、冲突等问题。
8. 页面提供两个下载：
   - 京东上传模板结果文件
   - 异常报告文件

第一版不做：

- 不自动打开京东直播后台。
- 不自动点击“添加商品”或上传模板。
- 不处理京东后台上传后的失败结果回填。
- 不做多直播间批量自动绑定。

## 关键业务规则

官方模板第一行已确认：

| 列 | 模板字段 | 第一版写入规则 |
| --- | --- | --- |
| A | `SKUID（必填...）` | 写业务表的上播 SKU |
| C | `专享券KEY码（非必填）` | 识别到 `vender_BA#...` 时写入 |
| D | `专享价促销ID（非必填...）` | 识别到纯数字促销 ID 时写入 |

重要限制：

- 官方模板说明明确写了：同一行同一 SKU 的专享价促销 ID 与专享券 KEY 码不能同时填报。
- 因此“一个模板绑定两个东西”的正确理解是：同一个模板可以同时包含 KEY 行和促销 ID 行，但同一行只能填其中一种。
- 专享券 KEY 和专享赠可以叠加，但本次只处理专享券 KEY 和专享价促销 ID，不处理专享赠。

测试文件 `直播绑定券码-测试.xlsx` 的样本统计：

- 有 SKU 的行：127。
- 有券码/价码内容的行：79。
- 可识别绑定行：69。
- 拆分多 KEY 后候选绑定：70。
- 空券码/价码：48，跳过并可在报告中统计。
- 明显无效文本：10，包括 `百补`、`百亿补贴`、`秒杀`、`BA_9nznsrc`。
- 重复 SKU：2 组，样本里重复绑定值一致，第一版按重复行报告并默认去重。

## 推荐目录规划

建议调整为：

```text
live/
  docs/
    plans/
      2026-06-17-live-promotion-binding-v1.md
    sop/
      直播-批量绑定促销券_促销编码.md

  live-web/
    app.py
    config.py
    requirements.txt
    start.sh
    start.bat
    start_web.bat
    templates/
      index.html
    static/
      app.css
      app.js
    tests/
      test_routes.py
      test_web_template.py

  live-sku-price-audit/
    README.md
    price_audit/
      __init__.py
      browser_manager.py
      jd_crawler.py
      excel_handler.py
      audit_runner.py
    tests/
    input/
    output/

  live-promotion-binding/
    README.md
    promotion_binding/
      __init__.py
      config.py
      workbook_reader.py
      code_parser.py
      template_writer.py
      report_writer.py
      service.py
    assets/
      商品上传模版（2026切片版）.xlsx
    input/
    output/
    tests/
      test_workbook_reader.py
      test_code_parser.py
      test_template_writer.py
      test_report_writer.py
      test_service.py
```

### 为什么新增 `live-web/`

如果继续把页面和启动脚本放在 `live-sku-price-audit/`，产品入口会被“测价”这个具体功能命名绑死。绑定券只是第二个功能，后面如果再加直播间商品导入、结果回查、切片处理，目录会继续失真。

`live-web/` 应该只负责：

- 页面展示。
- 文件上传。
- 任务启动。
- 任务状态轮询。
- 下载结果。
- 登录态提示和浏览器生命周期管理。

业务规则放到各自模块里：

- 测价规则放 `live-sku-price-audit/`。
- 绑定券规则放 `live-promotion-binding/`。

### 是否立刻移动旧测价文件

第一版建议“轻量迁移入口，不重构测价核心”：

1. 新建 `live-web/`。
2. 把现有测价 Web 壳的能力迁到 `live-web/`：
   - `app.py`
   - `templates/index.html`
   - `start.sh`
   - `start.bat`
   - `start_web.bat`
   - 公共上传、状态、下载接口
3. 测价核心暂时通过适配层调用旧目录里的已有函数，避免首版同时重构测价爬虫。
4. `live-sku-price-audit/` 原启动脚本短期保留，标记为兼容入口；等新入口验证稳定后再移除或改成跳转到 `live-web/`。

这样既能让新功能不塞进测价目录，又不会一次性搬动太多测价代码。

## 第一版数据流

```text
用户打开本地页面
  -> 切换到“绑定券码/促销ID”
  -> 上传事业部提报 Excel
  -> 后端保存到 live-promotion-binding/input/
  -> workbook_reader 读取表头并定位 SKU/券码列
  -> code_parser 解析每行有效 KEY/促销 ID
  -> service 去重、拆分、分类、生成结果模型
  -> template_writer 复制京东官方模板并写 A/C/D 列
  -> report_writer 生成异常报告
  -> 页面展示统计并提供下载
```

## 模块职责

### `promotion_binding/workbook_reader.py`

职责：

- 打开业务 Excel。
- 默认读取第一个 sheet。
- 识别表头行。第一版先默认第一行为表头。
- 通过归一化匹配找到 SKU 列和券码/价码列：
  - 去掉空格、换行、全角/特殊空白。
  - SKU 列匹配 `上播·SKU ID`、`上播·SKUID`。
  - 券码列匹配 `券码/价码`。
- 返回标准行模型。

行模型建议：

```python
{
    "source_row": 3,
    "sku": "10079660739051",
    "raw_code": "vender_BA#a9d94c41368e441094132b17a3b40fd6",
}
```

### `promotion_binding/code_parser.py`

职责：

- 从 `raw_code` 中解析专享券 KEY。
- 从 `raw_code` 中解析专享价促销 ID。
- 过滤中文说明和无效文案。
- 标记异常类型。

第一版规则：

- KEY 正则：`vender[_\\s-]*BA\\s*#\\s*[A-Za-z0-9]{32}`。
- 促销 ID 正则：`(?<!\\d)\\d{10,}(?!\\d)`。
- 解析促销 ID 时先移除 KEY 匹配片段，避免 KEY 里的数字被误识别成促销 ID。
- 如果同一单元格出现多个 KEY，标记 `MULTIPLE_KEYS`。
- 如果同一单元格出现多个促销 ID，标记 `MULTIPLE_PROMO_IDS`。
- 如果同一单元格同时出现 KEY 和促销 ID，标记 `KEY_PROMO_CONFLICT`，不写入模板。

### `promotion_binding/template_writer.py`

职责：

- 复制官方模板。
- 清空模板第 2 行开始的旧数据。
- 按输出模型写 A/C/D 列。
- SKU 和促销 ID 均以文本格式写入，避免科学计数法。
- 不改模板表头、不改说明列、不重建 workbook。

输出模型建议：

```python
{
    "sku": "100089021178",
    "binding_type": "PROMO_ID",
    "binding_value": "381421541016",
    "source_row": 8,
}
```

### `promotion_binding/report_writer.py`

职责：

- 生成异常报告 Excel。
- 至少包含三个 sheet：
  - `汇总`
  - `可绑定明细`
  - `异常明细`

异常明细字段：

| 字段 | 说明 |
| --- | --- |
| source_row | 原始行号 |
| sku | SKU |
| raw_code | 原始券码/价码内容 |
| issue_type | 异常类型 |
| message | 业务可读说明 |
| action | 建议动作 |

### `promotion_binding/service.py`

职责：

- 串联 reader、parser、writer。
- 形成统一结果：
  - `success_count`
  - `skipped_empty_count`
  - `invalid_count`
  - `duplicate_count`
  - `output_template_path`
  - `report_path`
- 负责去重策略。

第一版去重策略：

- 相同 `sku + binding_type + binding_value`：只写一次，重复行进入报告。
- 相同 SKU 但不同绑定值：不写入模板，进入冲突异常。
- 多 KEY 行：默认不拆分写入，进入异常报告；除非产品明确要求“默认取第一个”。

## Web 页面设计

统一页面建议使用 Tab：

- `SKU 测价`
- `绑定券码/促销ID`

绑定券页面控件：

- 上传业务表格。
- 展示官方模板名称和更新时间。
- `生成导入模板` 按钮。
- 生成后展示统计：
  - 可绑定条数。
  - KEY 数。
  - 促销 ID 数。
  - 空值跳过数。
  - 异常数。
  - 重复数。
- 下载按钮：
  - `下载京东上传模板`
  - `下载异常报告`

页面第一版不需要直播间 ID 输入。直播间 ID 是第二阶段自动上传需要的。

## API 规划

`live-web/app.py` 中新增或拆分路由：

```text
POST /api/promotion-binding/upload
POST /api/promotion-binding/generate
GET  /api/promotion-binding/status
GET  /api/promotion-binding/download/template
GET  /api/promotion-binding/download/report
```

第一版任务可以同步执行，也可以沿用测价的后台线程状态模型。考虑文件生成很快，第一版建议同步执行，返回生成结果；只有后续自动上传才需要长任务状态。

## 测试规划

### 单元测试

`test_code_parser.py`

- 识别标准 KEY。
- 识别标准促销 ID。
- 中文混杂文本中提取有效 KEY。
- `百补`、`百亿补贴`、`秒杀` 判定为无效。
- KEY 中的数字不误判为促销 ID。
- 多 KEY 判定为异常。

`test_workbook_reader.py`

- 能找到 `上播·SKU ID*【必填】` 列。
- 能找到 `券码/价码 达人id：22766602` 列。
- SKU 数字格式不会变成科学计数法。
- 空 SKU 行跳过或进入报告，按第一版规则固定。

`test_template_writer.py`

- 输出文件保留官方模板表头。
- A/C/D 列写入正确。
- SKU 和促销 ID 单元格格式为文本。
- 不写 C/D 同一行冲突数据。

`test_service.py`

- 使用 `直播绑定券码-测试.xlsx` 小样本验证统计口径。
- 重复 `sku + type + value` 去重。
- 同 SKU 不同值进入冲突异常。

### 集成测试

- 上传真实测试表 `直播绑定券码-测试.xlsx`。
- 使用官方模板 `商品上传模版（2026切片版） .xlsx`。
- 生成模板后人工打开检查：
  - 表头未变。
  - A/C/D 列有数据。
  - 无效文案未进入上传模板。
  - 异常报告能定位原始行号。

## 实施任务拆分

### Task 1: 建立目录和测试骨架

**Files:**

- Create: `live/live-promotion-binding/README.md`
- Create: `live/live-promotion-binding/promotion_binding/__init__.py`
- Create: `live/live-promotion-binding/tests/__init__.py`
- Create: `live/live-promotion-binding/assets/.gitkeep`
- Create: `live/live-promotion-binding/input/.gitkeep`
- Create: `live/live-promotion-binding/output/.gitkeep`

**验证:**

```bash
python -m pytest live/live-promotion-binding/tests -q
```

预期：没有测试或空测试通过。

### Task 2: 实现券码解析

**Files:**

- Create: `live/live-promotion-binding/promotion_binding/code_parser.py`
- Create: `live/live-promotion-binding/tests/test_code_parser.py`

**重点:**

- 先写失败测试。
- 再实现最小解析逻辑。
- 覆盖 KEY、促销 ID、无效中文、多 KEY、KEY 数字误判。

### Task 3: 实现业务表读取

**Files:**

- Create: `live/live-promotion-binding/promotion_binding/workbook_reader.py`
- Create: `live/live-promotion-binding/tests/test_workbook_reader.py`

**重点:**

- 表头归一化。
- SKU 格式化。
- 原始行号保留。

### Task 4: 实现官方模板写入

**Files:**

- Create: `live/live-promotion-binding/promotion_binding/template_writer.py`
- Create: `live/live-promotion-binding/tests/test_template_writer.py`

**重点:**

- 从官方模板复制输出。
- 仅写 A/C/D。
- 文本格式写入。

### Task 5: 实现异常报告

**Files:**

- Create: `live/live-promotion-binding/promotion_binding/report_writer.py`
- Create: `live/live-promotion-binding/tests/test_report_writer.py`

**重点:**

- 汇总 sheet。
- 可绑定明细 sheet。
- 异常明细 sheet。

### Task 6: 实现绑定券服务编排

**Files:**

- Create: `live/live-promotion-binding/promotion_binding/service.py`
- Create: `live/live-promotion-binding/tests/test_service.py`

**重点:**

- 串联读取、解析、去重、写模板、写报告。
- 输出统一统计。

### Task 7: 新增统一 Web 入口

**Files:**

- Create: `live/live-web/app.py`
- Create: `live/live-web/config.py`
- Create: `live/live-web/templates/index.html`
- Create: `live/live-web/start.sh`
- Create: `live/live-web/start.bat`
- Create: `live/live-web/tests/test_routes.py`

**重点:**

- 页面先支持绑定券 Tab。
- 测价 Tab 可以先保留入口文案或通过兼容链接跳到旧测价入口。
- 等绑定券第一版稳定后，再把测价页面完整迁入统一入口。

### Task 8: 接入绑定券 API 和页面下载

**Files:**

- Modify: `live/live-web/app.py`
- Modify: `live/live-web/templates/index.html`
- Test: `live/live-web/tests/test_routes.py`

**重点:**

- 上传业务 Excel。
- 调用 `promotion_binding.service.generate_binding_files(...)`。
- 返回统计和下载路径。
- 下载模板和异常报告。

### Task 9: 文档和兼容入口

**Files:**

- Modify: `live/live-promotion-binding/README.md`
- Modify: `live/live-web/README.md`
- Modify: `live/live-sku-price-audit/README.md`

**重点:**

- 标注推荐入口是 `live/live-web/start.*`。
- 旧测价启动脚本作为兼容入口保留一版。
- 说明绑定券第一版只生成模板，不自动上传京东后台。

## 验收标准

第一版完成后，应该满足：

1. 用户只启动一个 Web 页面。
2. 绑定券代码不放进 `live-sku-price-audit/`。
3. 上传 `直播绑定券码-测试.xlsx` 能生成京东官方上传模板。
4. 无效文本不会进入京东上传模板。
5. 异常报告能定位每条异常的原始行。
6. 官方模板表头不被改动。
7. 所有核心解析和模板写入逻辑有 pytest 覆盖。

## 第二阶段预留

第二阶段再做京东后台自动上传：

- 页面增加直播间链接或直播间 ID 输入。
- 复用 Playwright 登录态。
- 打开 `https://jlive.jd.com/my/room?id={room_id}`。
- 点击添加商品。
- 上传第一版生成的官方模板。
- 捕获上传成功/失败提示。
- 将京东后台失败结果回写到报告。

第二阶段再考虑把 Playwright 相关能力抽到 `live-web/shared/browser_manager.py`，不要让绑定券直接依赖测价模块里的浏览器管理文件。
