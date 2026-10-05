# AI Avatar Twin · 后端

面向 AI 行业内容创作者的「选题发现 → 脚本生成 → 数字人口播视频 → 发布素材包导出」工作台后端。

- 技术栈：Python 3.13 + FastAPI + SQLite（SQLAlchemy）+ SSE 流式
- 端口：**8100**（与「脑洞游戏」8000 隔离）
- 定位：**Agent + Harness 产品**——模型为驾驶者（自主决策），Harness 为载具（工具/知识/观察/行动/权限）

---

## 一、目录结构

```
backend/
├── app/
│   ├── main.py               # FastAPI 入口、路由挂载、静态验收页
│   ├── config.py             # 环境变量（模型/TTS/数字人/风格化/脚本时长）
│   ├── models.py             # SQLAlchemy 模型（含 UserPreference 表）
│   ├── schemas.py            # Pydantic 模型（含 AgentRunRequest）
│   ├── api/routes.py         # 全部 HTTP/SSE 接口（含 /agent/run）
│   ├── core/                 # llm.py（LLMClient）、auth.py（鉴权）、db.py
│   └── services/
│       ├── agent.py          # ★ s01 Agent Loop + s17 硬闭环门
│       ├── tools.py          # ★ s02 工具池（TOOLS 注册表 + 分派）
│       ├── evaluator.py      # ★ s17 脚本质量评估器（独立 judge）
│       ├── guard.py          # ★ s03 内容安全（敏感词/破坏性模式）
│       ├── hooks.py          # ★ s04 钩子（pre_tool/post_tool）
│       ├── engine.py         # 业务能力：摘要/选题/脚本/事实核查兜底
│       ├── prompts.py        # 全部 Prompt（含 AGENT_SYSTEM）
│       ├── fetcher.py        # 网页抓取
│       ├── parser.py         # 宽容 JSON 解析
│       ├── sources.py        # 信息源（URL/RSS/手动）抓取
│       ├── tts.py            # TTS 配音（CosyVoice）
│       ├── stylize.py        # 照片→3D 渲染风风格化
│       ├── digital_human.py  # 数字人封装
│       ├── jimeng.py         # 即梦 OmniHuman 口型驱动
│       ├── video.py / video_worker.py / packaging.py  # 视频任务/素材包
├── tests/                    # pytest（124 项）
├── data/                     # SQLite 库、轨迹（JSONL）
└── requirements.txt
```

---

## 二、Agent Harness 架构（当前实现状态）

`Agent = 模型 + Harness`；Harness 五要素 = 工具 / 知识 / 观察 / 行动 / 权限。

| 组件 | 状态 | 实现位置 | 说明 |
|---|---|---|---|
| s01 Agent Loop | ✅ 已实现 | `services/agent.py` | 模型自主循环：`messages → model → tool_use → 结果 → 循环`，`AGENT_MAX_STEPS=20` 防死循环，工具异常兜底不崩溃 |
| s02 工具系统 | ✅ 已实现 | `services/tools.py` | `TOOLS` 注册表（6 工具）+ `execute_tool` 统一分派 |
| s03 权限系统 | 🟡 部分 | `core/auth.py` + `guard.py` | token 鉴权 + user_id 数据隔离 + 内容 guard 已有；**ask 权限分级待做**（见补齐清单 #5） |
| s04 钩子系统 | 🟡 框架已建 | `services/hooks.py` | `pre_tool`/`post_tool` 扩展点、异常吞掉；**埋点/指标待挂**（见补齐清单 #2） |
| s17 目标闭环 | ✅ 已实现 | `agent.py` + `evaluator.py` | **硬闭环门**：finish 前强制独立评估，不达标自动重写（见下） |
| s09 记忆系统 | ❌ 表在未接线 | `models.py:190` `UserPreference` | 表已建零读写（见补齐清单 #1） |
| s08 上下文压缩 | ❌ 硬截断 | `tools.py:118` | 正文截 6000 字，无分层摘要（见补齐清单 #3） |
| s12 定时调度 | ❌ 暂缓 | — | PRD 7.2 要求每日 2 次 RSS（见补齐清单 #6） |
| s16 工作流 | 🟡 部分 | `video_worker.py` | 异步队列+状态机+重启恢复已有；断点续跑待做（见补齐清单 #4） |

> 未引入 s06 子Agent / s10 任务系统 / s13 Agent团队 / s14 MCP 插件——单 Agent MVP 场景下判定「正确的不引入」。

**剩余待改项完整方案见：`阶段文档/Agent Harness 后端补齐清单.md`。**

---

## 三、Agent 循环流程（含硬闭环门）

```
用户一句话目标 → POST /agent/run（SSE）
  └─ Agent Loop（最多 20 步）
       └─ 每步：模型输出 {thought, action, action_input}
            ├─ action = 工具名 → execute_tool（pre/post 钩子包裹）
            └─ action = finish → 进入硬闭环门（见下）
```

**硬闭环门（s17，已实现）**——模型说 `finish` 不再直接交还：

```
finish
  └─ 无脚本 → done(status=incomplete)
  └─ 有脚本 → 强制调 evaluator 独立评估
       ├─ 通过 → done(status=done)
       ├─ 不通过且重写 < 2 次 → 评估理由回写 history，continue 让模型重写
       └─ 不通过且重写 ≥ 2 次 → 脚本标「质量待人工审核」→ done(status=done)
```

- 重写上限：`MAX_SCRIPT_REWRITES = 2`（`agent.py`）
- `generate_script` 成功后重置质量门，新脚本重新评估
- 评估器本身不可用（LLM 异常）时视为通过、交人工，不阻断业务（`evaluator.py`）

---

## 四、Agent 工具清单（s02）

| 工具 | 输入 | 说明 | 权限 |
|---|---|---|---|
| `fetch_source` | `url` | 抓取网页正文（过 guard，正文截 6000 字） | allow |
| `summarize` | — | 结构化摘要（标题/摘要/关键词/可信度） | allow |
| `generate_topics` | — | 基于摘要生成 3 个候选选题 | allow |
| `fact_check` | `topic_index` | 来源标注 + 单一来源兜底 | allow |
| `generate_script` | `topic_index` | 生成口播脚本（含来源/风险标注） | allow |
| `evaluate_script` | — | 自检脚本是否达标 | allow |

- 花钱/发布类工具（视频生成、发布）**未进工具池**，Agent 物理够不到，需用户手动确认（对齐 PRD 7.7 红线）。

---

## 五、接口速览

统一错误格式 `{"error":{"code","message"}}`；除登录外均需 `Authorization: Bearer <token>`。

### Agent 入口（重点）

`POST /api/v1/agent/run`（SSE 流式）

请求体（`AgentRunRequest`）：
```json
{ "goal": "帮我做一期关于 X 的 30 秒中文口播脚本", "profile_id": "可选" }
```

SSE 事件流（`data: {json}\n\n`）：

| 事件 type | 字段 | 说明 |
|---|---|---|
| `start` | `goal` | 开始 |
| `step` | `step/thought/action` | 每步决策 |
| `tool_result` | `tool/result` | 工具执行结果 |
| `eval` | `passed/reason/scores` | 硬闭环门强制评估 |
| `done` | `status/script/steps` | `status` = `done`（有脚本，含风险标注）/ `incomplete`（无脚本）/ `max_steps`（达步数上限） |

### 业务接口

- 账户：`POST /api/v1/auth/code`、`POST /api/v1/auth/verify`、`POST /api/v1/auth/logout`、`GET /api/v1/auth/me`
- 项目：`POST/GET /api/v1/projects`、`PATCH /api/v1/projects/{id}`、`DELETE /api/v1/projects/{id}`
- Profile：`POST/GET /api/v1/projects/{pid}/profiles`、`PATCH/DELETE /api/v1/profiles/{id}`、`POST /api/v1/profiles/{id}/photo`、`GET /api/v1/profiles/{id}/avatar-preview`
- 信息源：`POST/GET /api/v1/sources`、`PATCH/DELETE /api/v1/sources/{id}`、`POST /api/v1/sources/{id}/fetch`
- 条目：`GET /api/v1/items`、`POST /api/v1/items/{id}/summarize`、`POST /api/v1/items/{id}/topics`
- 脚本：`POST /api/v1/topics/{id}/scripts`（SSE：`chunk`→`done`/`error`）、`PATCH/DELETE /api/v1/scripts/{id}`、`GET /api/v1/scripts/{id}/versions`、`POST /api/v1/scripts/{id}/revert`、`GET /api/v1/scripts/{id}/export?format=md|txt`
- 视频：`POST /api/v1/scripts/{id}/videos`、`GET /api/v1/videos/{id}`、`POST /api/v1/videos/{id}/retry`、`GET /api/v1/videos/{id}/file|cover|subtitle|export`

---

## 六、测试

```bash
cd backend
.venv/bin/python -m pytest          # 124 项，全部离线（不依赖 Key）
```

| 测试文件 | 覆盖 |
|---|---|
| `test_agent.py` | guard / hooks / 工具注册表 / evaluator / **硬闭环门**（重写通过 + 耗尽标风险）/ /agent/run 脚本持久化 |
| `test_engine.py` | 摘要/选题/脚本/事实核查兜底 |
| `test_fetcher.py` | 抓取 |
| `test_ownership.py` | 数据隔离 |
| `test_api.py` / `test_m3.py` | 接口 / 视频链路 |

**硬闭环门测试要点**（`test_agent.py`）：
- `test_agent_quality_gate_rewrites_until_pass`：finish 强制评估 → 不通过回写重写 → 再评估通过 → done
- `test_agent_quality_gate_gives_up_with_risk_flag`：持续不通过 → 重写上限耗尽 → 脚本标「质量待人工审核」→ done

---

## 七、关键环境变量（`backend/../.env`）

| 变量 | 说明 |
|---|---|
| `MODEL_API_KEY` / `MODEL_BASE_URL` / `MODEL_NAME` | 文字模型（默认 qwen-plus） |
| `TTS_API_KEY` / `TTS_MODEL` | TTS（CosyVoice） |
| `DIGITAL_HUMAN_API_KEY` / `DIGITAL_HUMAN_MODEL` | 数字人（即梦 OmniHuman） |
| `STYLIZE_API_KEY` / `STYLIZE_MODEL` | 风格化（wan2.6-image） |
| `SCRIPT_DURATION` | 脚本时长（默认 30 秒） |
| `DEV_MODE` | 本地验证码 mock（true 时验证码直接返回） |
