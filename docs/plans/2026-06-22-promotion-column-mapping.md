# 绑定券列映射确认实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让绑定券工具不再依赖固定 Excel 表头，上传后自动推荐 SKU 列和绑定值列，并允许用户手动确认或改选。

**Architecture:** 核心模块新增工作簿表头检查和显式列映射读取能力；Web 层新增预览接口，保存上传文件并返回列清单、样例值和推荐列；页面生成前必须带上用户确认后的列序号。旧 multipart 生成接口保留自动推荐兜底，避免已有调用方式直接失效。

**Tech Stack:** Python、Flask、openpyxl、原生 HTML/CSS/JavaScript、unittest。

---

## 关键词口径

- SKU 列推荐关键词：`sku`、`skuID`、`上播 SKU ID`。
- 绑定值列推荐关键词：`券码`、`价码`、`促销编码`、`专享券`、`专享价`、`达人id`。
- 商品名称列为可选列，推荐关键词：`商品名称`。

## 执行步骤

1. 在 `live-promotion-binding/tests/test_workbook_reader.py` 增加失败测试：
   - 检查当前真实业务表头能推荐出 SKU、绑定值、商品名称列。
   - 检查表头完全不命中关键词时，传入显式列映射仍能读取。
2. 在 `live-web/tests/test_routes.py` 增加失败测试：
   - `/api/promotion-binding/preview` 上传 Excel 后返回 `task_id`、列清单、样例值和推荐列。
   - `/api/promotion-binding/generate` 接收 JSON `task_id + column_mapping` 后按用户选择生成文件。
3. 实现 `workbook_reader`：
   - 新增 `ColumnMapping`、`WorkbookColumn`、`WorkbookInspection`。
   - 新增 `inspect_business_workbook()`。
   - `read_business_rows()` 支持显式列序号；无显式映射时继续自动推荐。
4. 更新 `service.generate_binding_files()`：
   - 增加可选 `column_mapping` 参数。
   - 保持旧调用默认自动推荐。
5. 更新 `live-web/app.py`：
   - 新增预览接口保存上传文件。
   - 新增内存态 `PROMOTION_UPLOADS`。
   - 生成接口同时支持旧 multipart 和新 JSON。
6. 更新 `live-web/templates/index.html`：
   - 上传后调用预览接口。
   - 展示 SKU 列、绑定值列、商品名称列三个下拉框。
   - 自动选中推荐列，但用户可改。
   - 生成时提交 `task_id` 和列映射。
7. 跑测试：
   - `python3 -m unittest discover -s tests -v`
   - `python3 -m unittest discover -s tests -v` in each module.
   - `git diff --check`。
8. 用 `git commit --amend` 覆盖上一版硬编码别名提交，再推送并打新版本标签。
