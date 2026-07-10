# Bigscreen Dropdown And Sort Controls Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复直播大屏两个下拉框无法展开和两个商品表头未真正降序的问题。

**Architecture:** 保留 80% 页面缩放和 DOM 事件方案。针对 Ant Select 派发 `mousedown` 并点击 option 容器；针对商品表点击真实排序箭头，并基于目标表格过滤置顶行后验证降序。

**Tech Stack:** Python 3、Playwright Sync API、unittest、Ant Design DOM。

---

### Task 1: 修复 Ant Select 下拉框

**Files:**
- Modify: `live-bigscreen-capture/tests/test_browser.py`
- Modify: `live-bigscreen-capture/bigscreen_capture/browser.py`

1. 增加失败测试，要求对 `.ant-select-selector` 派发 `mousedown`，并点击 `.ant-select-item-option` 容器。
2. 运行相关测试，确认因当前仍点击文字子节点而失败。
3. 增加 DOM `mousedown` helper，改造 `_select_ant_dropdown` 的触发器和选项定位。
4. 保留当前值变更验证与一次重试。
5. 运行浏览器测试并提交。

### Task 2: 修复商品表排序

**Files:**
- Modify: `live-bigscreen-capture/tests/test_browser.py`
- Modify: `live-bigscreen-capture/bigscreen_capture/browser.py`

1. 增加失败测试，要求点击目标表头内的 `caret-down` 箭头。
2. 增加失败测试，要求降序验证忽略空白行和“讲解中”置顶行。
3. 增加失败测试，要求两次排序仍未确认时抛出异常。
4. 运行相关测试确认红灯。
5. 修改排序点击目标和表格作用域，严格处理失败。
6. 运行浏览器测试并提交。

### Task 3: 回归与发布

**Files:**
- Verify only

1. 运行 `live-bigscreen-capture` 全量测试。
2. 运行其余模块和根目录全量测试。
3. 运行 `compileall`、`git diff --check` 和点击路径静态检查。
4. 在真实直播大屏验证挂袋商品、成交用户、成交件数和成交金额。
5. 合并到 `master`，推送并发布补丁 Release。

