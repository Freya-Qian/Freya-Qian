# AI Avatar Twin · Agent Harness 后端补齐清单

> 定位：Agent + Harness 产品（模型为驾驶者，Harness 为载具）
> 依据：agent-blueprint 方法论（17 组件 + 五要素：工具/知识/观察/行动/权限）
> 状态：H1 已闭环，本清单为 H2/H3 与工程化补齐项，供后端按序实施
> 日期：2026-09-22

---

## 〇、已闭环（本次无需再改，仅备查）

| 组件 | 结论 | 说明 |
|---|---|---|
| s01 Agent Loop | ✅ 已实现 | `services/agent.py`：模型自主循环（thought/action/action_input），`AGENT_MAX_STEPS=20` |
| s02 工具系统 | ✅ 已实现 | `services/tools.py`：`TOOLS` 注册表 + `execute_tool` 分派，6 个工具 |
| s17 硬闭环门 | ✅ 已补齐 | `agent.py` finish 前强制独立评估，不达标回写重写（`MAX_SCRIPT_REWRITES=2`），耗尽标「质量待人工审核」 |
| s04 钩子框架 | ✅ 已建 | `services/hooks.py`：`pre_tool`/`post_tool`，异常吞掉不阻断主循环 |

**当前测试基线：后端 pytest 56/56 通过。**

---

## 一、待改项总览

| # | 项 | 组件 | 优先级 | 改动文件（后端） | 性质 |
|---|---|---|---|---|---|
| 1 | 记忆接线 | s09 | 🔴 P0 | models.py / engine.py / tools.py / routes.py | 产品价值 |
| 2 | 埋点/指标/轨迹 | s04 | 🟡 P1 | hooks.py 或新 metrics.py / agent.py / video_worker.py | 可观测 |
| 3 | 上下文压缩 | s08 | 🟡 P1 | engine.py / prompts.py / tools.py | 质量保障 |
| 4 | 断点续跑 | s16 | 🟡 P1 | video_worker.py / models.py | 成本优化 |
| 5 | ask 权限分级 | s03 | 🟡 P1 | tools.py / agent.py | 安全扩展 |
| 6 | 定时抓取 | s12 | ⚪ P2 | 新 scheduler.py / sources.py / main.py | PRD 承诺 |

> 非后端项（不在本清单展开）：前端测试（frontend/，0 测试）、部署（无 Dockerfile）。

---

## 二、逐项方案（具体到文件/函数）

### #1 记忆接线（s09）—— P0，产品价值

**问题**：`models.py:190` `UserPreference` 表已建（`user_id` + `topic_preferences`/`ignored_topics`/`performance_history` 三个 JSON 字段），但全项目**零读写**。PRD 核心闭环「回收反馈 → 反向优化下一期选题」落空。

**改动文件**：
- `app/models.py`：表已存在，无需改。
- `app/services/engine.py:172` `generate_topics(client, source)`：注入偏好。
- `app/services/tools.py:144`（Agent 路径）与 `app/api/routes.py`（手动路径）：读取偏好 + 回写。
- `app/services/prompts.py` `TOPICS_USER`：加「用户偏好」段。

**具体改法**：

1. 新增偏好读写辅助（建议放 `engine.py` 或新 `services/preferences.py`）：
   - `get_preference(db, user_id)`：无记录则返回空偏好。
   - `record_topic_feedback(db, user_id, topic_title, feedback)`：`feedback ∈ {liked, ignored}`。liked → 把选题关键词计入 `topic_preferences` 加权；ignored → 计入 `ignored_topics`。

2. `generate_topics` 增加可选参数 `preferences`（默认空），注入 `TOPICS_USER`：
   - 在 `prompts.py` `TOPICS_USER` 末尾追加：
     ```
     用户偏好：
     - 偏好方向：{topic_preferences}（选题优先贴合这些方向）
     - 已忽略类型：{ignored_topics}（避免再出同类选题）
     ```

3. 回写时机：
   - 选题被收藏/忽略时（现有收藏/忽略接口，若无则新增 `POST /topics/{id}/feedback`）调用 `record_topic_feedback`。
   - 视频发布/导出后，把脚本表现录入 `performance_history`（可后置到 #4 一起做）。

**验收**：用户忽略某类选题 3 次后，该类选题评分明显下降 / 不再出现在推荐前列。

---

### #2 埋点/指标/轨迹（s04）—— P1，可观测

**问题**：`hooks.py` 的 `_HOOKS` 列表为空，无任何 `register_hook` 调用；无轨迹 JSONL、无指标聚合。PRD 12 章指标（P75 时延 / 生成成功率 / 单条成本 / 事实标注覆盖率）无法采集。

**改动文件**：
- `app/services/hooks.py`：已有框架，无需改。
- 新增 `app/services/metrics.py`（或直接在 `main.py` 挂载）：轨迹写入 + 指标聚合。
- `app/services/agent.py`：`run_agent` 启动时注册钩子（或改在 `routes.py` 的 `/agent/run` 入口注册）。
- `app/services/video_worker.py`：视频任务事件埋点。

**具体改法**：

1. `metrics.py` 实现：
   - `append_trace(event: dict)`：追加一行 JSONL（字段：`ts/tool/duration_ms/ok/error`），落盘 `data/traces/agent.jsonl` 与 `data/traces/video.jsonl`。
   - `record_metric(name, value)`：内存聚合 + 定期落盘（或启动时加载、结束时写回）。

2. 挂载钩子（在 `agent.py` 的 `run_agent` 开头，或 `routes.py` 的 `events()` 前注册一次）：
   - `post_tool` 钩子 → `append_trace`（记录 `tool/args/result/耗时`）。
   - `pre_tool` 钩子 → 记录开始时间。

3. 视频埋点：`video_worker.py` 的 `_process_video` 在 `rendering/success/failed` 状态切换处 `append_trace`。

4. 指标聚合（对齐 PRD 12 章）：
   - P75 脚本生成时延、视频生成成功率、单条成本（即梦计费）、`risk_flags` 覆盖率。

**验收**：跑一次 Agent 后，`data/traces/agent.jsonl` 出现完整工具调用轨迹；能统计出 P75 时延与成功率。

---

### #3 上下文压缩（s08）—— P1，长文质量保障

**问题**：`tools.py:118` 抓取正文 `content_text[:6000]` 硬截断；`engine.py` 摘要/脚本 prompt 直接注入原始截断正文。长文（深度报告/论文）关键事实可能被截掉。

**改动文件**：
- `app/services/tools.py:112-124`（`fetch_source` 工具）：截断逻辑。
- `app/services/engine.py` `summarize_source`：产出分层摘要。
- `app/services/prompts.py` `SCRIPT_USER` / `TOPICS_USER`：注入分层摘要而非原始正文。

**具体改法**：

1. `fetch_source` 工具：`content[:6000]` 改为保留「标题 + 首段 + 正文」并额外存一份 `content_full`（限制如 30000 字，防内存）。
2. `summarize_source` 的 `SUMMARY_USER` 增加输出字段：
   - `key_facts`（关键事实列表）、`key_data`（数据点）、`sections`（分节要点）。
3. `SCRIPT_USER` 注入改为「分层摘要 + key_facts」，而非原始截断正文。
4. 保留原始链接作为权威信息，不被压缩。

**验收**：>6000 字长文的选题/脚本关键事实不丢失（用一条长文样例重跑验证）。

---

### #4 断点续跑（s16）—— P1，成本优化

**问题**：`video_worker.py:52` `_process_video` 失败直接 `status="failed"`（120 行），重试是整体重来。即梦 1 元/秒，整体重试浪费成本。

**改动文件**：
- `app/services/video_worker.py`：失败步记录 + 续跑。
- `app/models.py` `VideoProject`：新增进度字段（如 `stage`、`checkpoint`）。

**具体改法**：

1. `VideoProject` 增加 `stage` 字段（`fetch_photo` / `stylize` / `tts` / `lip_sync` / `package`）与 `checkpoint`（JSON，各步中间产物路径）。
2. `_process_video` 每完成一步即更新 `stage` + `checkpoint`。
3. `retry` 逻辑改为：从 `checkpoint` 记录的最后成功步续跑，而非从头。
4. 各步产物（风格化图 / 音频 / 口型视频）保留到 `checkpoint` 清理，成功后再清理中间产物。

**验收**：中途失败后 retry，已完成的 TTS/风格化步骤不重复执行（可加单测：mock 前几步成功、后一步失败，断言 retry 只重跑失败步）。

---

### #5 ask 权限分级（s03）—— P1，安全扩展

**问题**：`tools.py` `TOOLS` 元信息有 `permission` 字段，但 6 个工具全是 `allow`；花钱/发布工具（`generate_video`/`export_package`）**没进工具池**，靠「不进池」规避风险。将来要把视频生成交给 Agent 时，`ask` 机制缺失。

**改动文件**：
- `app/services/tools.py`：工具元信息补 `permission: ask` 的语义。
- `app/services/agent.py`：调用 `ask` 工具前暂停、交还用户确认。

**具体改法**（可只做机制、暂不开放 ask 工具）：

1. `agent.py` 的 `run_agent` 增加：`execute_tool` 前查 `tools.TOOLS[name]["permission"]`，若为 `ask`，`yield {"type": "confirm", "tool": name, "args": ...}` 并挂起等待外部确认（通过 SSE 事件 + 前端确认后回传，或 MVP 阶段直接拒绝并提示走手动流程）。
2. 暂不把 `generate_video`/`export_package` 加入 `TOOLS`，仅保留 `permission` 语义与 `confirm` 事件通道，验证机制可用。

**验收**：新增一个 `permission: ask` 的 mock 工具后，Agent 调用它时会被拦截并产出 `confirm` 事件，不会直接执行。

---

### #6 定时抓取（s12）—— P2，PRD 承诺

**问题**：PRD 7.2 要求每日 2 次 RSS 自动抓取，当前「暂缓」。`sources.py:81` `fetch_source_items` 已有抓取能力，只缺调度。

**改动文件**：
- 新增 `app/services/scheduler.py`：轻量定时器。
- `app/main.py`：启动时拉起 scheduler。
- `app/services/sources.py`：复用 `fetch_source_items`，无需改逻辑。

**具体改法**：

1. `scheduler.py` 用 `asyncio` + `loop.call_later`（或引入 `apscheduler`，需在 `requirements.txt` 加依赖）实现：每 12 小时遍历所有 RSS 源 → `fetch_source_items`。
2. 抓取结果去重（`sources.py` 已有 `_exists` 去重）→ 生成新 `SourceItem`。
3. 抓取失败只记日志，不阻断定时器；单源失败不影响其他源。

**验收**：配置 1 个 RSS 源后，12 小时内有新条目自动入库（可用短间隔 mock 验证调度逻辑）。

---

## 三、建议实施顺序

```
P0  #1 记忆接线（产品价值，核心闭环最后一步）
P1  #2 埋点指标 → #3 上下文压缩 → #4 断点续跑 → #5 ask 机制
P2  #6 定时抓取
```

- **P0** 做完，Agent 产品「越用越聪明」闭环兑现。
- **P1** 做完，可观测/可度量/可降本，支撑规模化。
- **P2** 做完，兑现 PRD「自动追踪信息」承诺，可内测多源自动更新。

> 每项完成后请更新 `阶段文档/项目状态.md` 的阶段历史，并同步 pytest 数量。
