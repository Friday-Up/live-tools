# 蓝屏自动截图模块

`live-bigscreen-capture` 是统一直播工具里的独立业务模块，负责京东直播蓝屏页面的链接解析、整点排期、截图步骤编排、截图清单和 ZIP 输出。

统一入口由 `../live-web` 提供；业务用户不需要单独进入本目录。

## 本地测试

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-bigscreen-capture
python3 -m unittest discover -s tests -p "test_*.py" -v
```

## 输出

- 单项截图：`蓝屏数据截图_{id}__YYYYMMDD_HHmmss_序号_截图项.png`
- 结果表：`截图清单.xlsx`
  - `截图结果` sheet：按整点时间横向嵌入 15 个原始截图，并按预览尺寸显示
  - `截图清单` sheet：保留每张截图的执行明细、文件名、状态和失败原因
- 压缩包：`蓝屏数据截图_{id}__YYYYMMDD.zip`
