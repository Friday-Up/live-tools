# 京东多来源选品 Agent

从国家补贴、黑色星期五、排行榜、京东特价四个实时活动页抓取商品。按“来源 × 页面类目”构建最多 30 个候选，由 AI 直接筛选并排序最多 10 个；合格候选不足时不强行补齐。

## 已确认的数据口径

| 来源 | 当前真实结构 | 本项目策略 |
|---|---|---|
| 国家补贴 | 32 个页面类目 Tab，`qryJediPcBabelFloors.goodsList` | 逐 Tab 点击，每类目最多抓 30 个候选交给 AI 筛选 |
| 黑色星期五 | 当前没有业务类目 Tab，商品位于 `window.__react_data__` | 作为“全场精选”单组，保留页面顺序；页面未给出的销量不伪造 |
| 排行榜 | 类目 Tab 下是榜单卡片，不是商品 | 每类目进入当前首位榜单，再取详情页第 1～10 名商品 |
| 京东特价 | 15 个类目 Tab，`queryPcBabelFeeds.flexData` | 逐 Tab 点击，每类目最多抓 30 个候选交给 AI 筛选 |

这四页不能共用 `qryJediPcBabelFloors`。旧实现产生的“黑五类目商品”实际存在跨页面延迟响应串源风险，排行榜和京东特价也没有完整进入结果。

## 推荐入口：统一 Web 页面

业务使用从仓库根目录启动 `live-web`，打开页面后切换到“选品 Agent”。页面支持启动、停止、实时日志、完整性提示，以及 Excel 下载：

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
python3 -m pip install -r live-web/requirements.txt
python3 -m playwright install chromium
cd live-web && ./start.sh
```

默认访问 `http://127.0.0.1:8080`。Web 结果写入 `live-web/runtime/output/product-selection/<task_id>/`。

## 开发调试：命令行

`main.py` 只保留为薄命令行入口，实际能力在 `product_selection_agent/service.py`，Web 和 CLI 共用同一套抓取、推荐和报表逻辑。

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/product-selection-agent
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium

# 任一来源为空会直接失败
python3 main.py --headless

# 页面结构临时异常时，允许输出部分结果（报表会在“运行诊断”中标红）
python3 main.py --headless --allow-partial
```

默认四个来源使用 4 个独立浏览器并发；同步 Playwright Page 不跨线程共享。普通活动页每类目候选池默认上限为 30，可按机器性能调整：

```bash
SELECTION_FETCH_WORKERS=3 SELECTION_MAX_CANDIDATES_PER_CATEGORY=20 python3 main.py --headless
```

默认复用 `../live-sku-price-audit/jd_auth.json`。也可指定其他登录态：

```bash
JD_AUTH_PATH=/absolute/path/to/jd_auth.json python3 main.py --headless
```

命令行输出位于 `output/`：

- `selection_时间.xlsx`：包含 `候选池`、`选品明细`、`推荐结果`、`运行诊断` 四个 Sheet。

Web 运行结果属于临时文件，与其他直播运营工具一致保留 2 天；服务启动或执行新任务前会自动清理过期结果，避免长期占用本地磁盘。

“候选池”会保留每个商品的候选排名、规则参考分、AI 是否入选、AI 排名、淘汰理由和合格不足说明，方便追溯模型决策。“选品明细”和“推荐结果”只展示最终入选商品。

## 推荐模式

未配置模型或模型调用失败时使用 `explainable_scoring`：按可用字段动态归一化销量、折扣、类目内相对价格、页面/榜单位次、好评率，规则选取最多 10 个作为明确标记的回退结果；缺失字段不会被当作 0 分惩罚。

配置兼容 OpenAI Chat Completions 协议的模型网关后，自动切换为 `llm_enhanced`。每个类目的全部候选默认一次性发送。AI 只负责返回按推荐顺序排列的 `selected_sku_ids`，并可选返回 `selected_reasons`；推荐理由或文案缺失时，程序会依据真实价格、销量、折扣、页面位次等字段生成，不会删除已选 SKU。AI 只会硬淘汰串类、凑单或服务链接、赠品或非商品、重复变体；低销量、高价格、折扣弱、缺少好评率和非自营只能影响排序，不得作为淘汰理由。相关有效商品达到 10 个时必须选择 10 个，确实不足时才允许少选。最多 5 个类目并行执行，并由全局 5 RPS 限流器统一控速：

对已经从真实页面确认存在稳定京东二级类目 ID 的高风险 Tab，会在 AI 前做确定性预过滤。目前医疗器械只保留 `9197/13893`，电动车只保留 `27509`；被排除候选仍保存在“候选池”，淘汰原因标记为“平台类目ID与页面类目不匹配”。未配置或缺少类目 ID 的情况仍交给 AI 判断，不做猜测性过滤。

本地运行可复制 `model-config.example.json` 为 `model-config.local.json` 并填写配置。实际配置文件已被 Git 忽略，环境变量仍具有最高优先级。也可以直接使用环境变量：

```bash
export SELECTION_AI_API_URL='https://your-gateway.example/v1/chat/completions'
export SELECTION_AI_API_KEY='***'
export SELECTION_AI_MODEL='your-model'
python3 main.py --headless
```

模型调用失败会回退到可解释评分，并在 Excel 推荐模式和运行诊断中体现，不会静默伪装成 AI 结果。AI 正常返回少于 10 个时，`shortfall_reason` 和运行诊断会记录“合格候选不足”。重复、未知 SKU 导致数量不足或不足说明与实际数量矛盾时，会判定该类目协议失败并规则回退。模型偶尔返回旧的 `selected`、`items` 或纯数组协议时会自动转换为 `selected_sku_ids` 并保留协议告警。

完整性分开判断：`diagnostics.fetch_complete` 表示四个来源是否抓取完整，`diagnostics.ai_complete` 和顶层 `ai_complete` 表示所有类目是否都完成 AI 选品；`diagnostics.ai_failed_categories` 会列出发生规则回退的来源、类目和错误。控制台最后会同时打印“抓取完整”和“AI完整”。

模型请求使用 SSE 流式接收。单次网络读取默认超时 90 秒，可通过 `SELECTION_AI_TIMEOUT_SECONDS` 调整；类目并发数和每秒请求上限可通过 `SELECTION_AI_CATEGORY_WORKERS`、`SELECTION_AI_RPS_LIMIT` 调整。默认按平台限制执行 5 RPS 滑动窗口限流。只有连续 3 个类目发生网络故障才熔断，可通过 `SELECTION_AI_CIRCUIT_FAILURE_THRESHOLD` 调整；业务性少选和 JSON 内容错误不会误触发网络熔断。

## 验收与测试

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q .
```

一次完整在线运行的验收条件：

1. `diagnostics.complete = true`，四个来源都为 `ok`；
2. `diagnostics.fetch_complete = true`；如要求全量 AI 结果，还必须满足 `ai_complete = true`；
3. 国家补贴/京东特价按真实 Tab 分组；
4. 排行榜每条商品带 `rank_board`、`rank_board_url` 和榜单名次；
5. 普通活动页每组候选最多 30 条，排行榜最多 10 条；最终每组最多 10 条；
6. 最终不足 10 条时会在 `short_categories` 中记录数量和原因，不使用串类或非商品补齐；
7. 黑色星期五明确标注“页面无类目 Tab / 未提供销量”，不补造数据。
