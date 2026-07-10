# 直播大屏下拉与排序控件修复设计

## 背景

`v0.3.22` 将页面交互改为 `el.click()` 后，普通标签和侧栏稳定，但两个 Ant Design 下拉框无法展开，两个商品表头也没有真正触发排序。

真实页面 DOM 排查确认：

- 下拉框当前值位于 `.ant-select-selection-item`，但展开事件由父级 `.ant-select-selector` 的 `mousedown` 处理。
- 下拉选项的交互节点是 `.ant-select-item-option`，文字位于其内部 `.ant-select-item-option-content`。
- 商品表排序事件绑定在表头内的 `[aria-label="caret-down"]` 箭头，而不是 `th`。
- 商品表包含空白测量行和“讲解中”置顶行，这些行不属于排序结果，不能参与降序验证。

## 方案

### 下拉框

1. 通过当前值定位唯一的 `.ant-select-selector`。
2. 向 selector 派发可冒泡、可取消的 `mousedown`，避免依赖屏幕坐标。
3. 等待 `.ant-select-item-option` 中目标选项可见。
4. 对目标 option 容器执行 DOM click。
5. 以 `.ant-select-selection-item` 当前文本变更作为成功条件，失败重试一次。

### 商品排序

1. 通过表头文字定位目标 `th`。
2. 在目标表头内定位 `[aria-label="caret-down"]`，对箭头执行 DOM click。
3. 等待表格数据稳定。
4. 只读取该表头所属 `.ant-table-container` 的 `.ant-table-body tbody`。
5. 忽略空白行和首列包含“讲解中”的置顶行，再验证目标列数值降序。
6. 两次点击后仍不能确认降序时抛出异常，使该截图记为失败，不再输出默认排序截图。

## 兼容性

- 保留页面 `80%` CSS 缩放。
- 所有新增交互均为 DOM 事件，不使用坐标，Mac 和 Windows 共用同一实现。
- 不更改截图清单、文件名、调度和 Excel 输出结构。

## 验证

- 单元测试覆盖 selector `mousedown`、option 父节点点击、排序箭头点击、置顶行过滤和排序失败抛错。
- 运行截图模块和全仓测试。
- 在真实直播大屏验证两个下拉框当前值和两个商品列降序结果。

