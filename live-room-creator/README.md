# 直播间批量创建工具

读取业务 Excel，自动登录京东直播后台，批量创建直播间。

## 输入表格要求

Excel 至少需要以下两列：

| 列名 | 必填 | 说明 |
| --- | --- | --- |
| 直播标题 | 是 | 5~15 字符 |
| 开播时间 | 是 | 如 `2026-07-01 20:00:00` |
| 直播封面 | 否 | 当前版本使用默认封面，可留空 |
| 直播形式 | 否 | 默认 `正式直播`，可选 `测试直播` |
| 画面方向 | 否 | 默认 `竖屏`，可选 `横屏` |
| 直播地点 | 否 | 默认 `不显示地点` |
| 直播品类 | 否 | 默认 `多品类` |

## 核心模块

- `room_creator/excel_reader.py`：读取 Excel、推荐列映射。
- `room_creator/validator.py`：校验标题长度、字段取值、重复行。
- `room_creator/browser.py`：Playwright 浏览器自动化。
- `room_creator/runner.py`：串行任务编排，控制每日上限与失败跳过。
- `room_creator/report_writer.py`：生成结果 Excel。

## 输出文件

- `直播间创建结果_YYYYMMDD-HHmmss_.xlsx`：每行创建状态与失败原因。
