# 第 2 阶段技术开发文档｜M3 PRD 生成与任务拆解

> 配套文档：PRD V1.0、技术适配声明、通用技术栈手册。
> 本文档只覆盖 M3（PRD 生成 + 证据引用审计 + MVP 范围 + 研发任务拆解）；M4 资料包导出为后续子阶段。

## 一、阶段目标
- 交付范围（对齐 PRD 4.4/10.5/10.6/10.7/11.5/11.6）：带证据引用的 PRD 生成（11 章节）→ 证据引用审计 → 章节编辑/确认 → MVP 范围（PRD 版本规划章节）→ 研发任务拆解（DevTask）→ 确认进入资料包导出。
- 阶段产物：ProductDoc（结构化 PRD）+ DevTask（研发任务）+ 证据引用审计结果。
- 验收标准（对齐 PRD 10.5/10.6/10.7）：PRD 含 11 章节；关键结论有证据引用；无证据结论标"待确认"；任务可独立理解、有验收标准、P0 可追溯。
- 明确不做：资料包导出（M4）、迭代记录/Feedback（M4）、PRD 版本差异对比（V1）。
- 主链路：定位确认 → 生成 PRD（+审计）→ 编辑/确认 → 生成研发任务 → 确认 → 进入资料包导出。

## 二、技术适配摘要
- 沿用纵向切片路径 B，复用 M1/M2 的 Task 异步框架、LLMClient、parser、证据 ref_key 引用体系。
- 本阶段启用：ProductDoc/DevTask 新表、证据引用审计（确定性代码）。

## 三、技术栈与模型
- 同前：FastAPI + SQLite/SQLAlchemy + qwen-plus。PRD 生成 max_tokens=8000、任务拆解 max_tokens=4000，temperature 0.5，解析失败纠错重试一次。

## 四、环境与配置
- 无新增配置。数据库新增 product_docs、dev_tasks 两表。

## 五、项目结构（M3 新增）
```
backend/app/
├── models.py                 # + ProductDoc / DevTask
├── schemas.py                # + PrdOut/PrdUpdate/DevTaskOut
├── services/prd.py           # PRD 生成 + 证据引用审计 + 章节规整
├── services/tasks.py         # 研发任务拆解 + 规整
├── services/prompts.py       # + PRD_SYSTEM / TASKS_SYSTEM / PRD_CHAPTERS
├── services/task_worker.py   # + prd / tasks 任务分发
├── api/routes.py             # + PRD / 任务拆解路由
└── static/index.html         # + 第 6/7 步：PRD、研发任务
```

## 六、数据、资产与状态
- 新表：product_docs（sections/evidence_refs 存 JSON）、dev_tasks（dependencies/source_refs 存 JSON）。
- 状态机：current_stage：prd（定位确认后）→ mvp（PRD 确认后）→ package（任务确认后，M4）。
- 证据引用审计（三件套）：① evidence ref_key 存在性校验（过滤无效）；② used_in 标记"PRD"；③ 结论型章节（产品定位/竞品证据与分析/版本规划）无证据 → status="待确认"（无证据结论清单）。

## 七、API / 工具设计
| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /projects/{id}/prd | 生成 PRD（异步，202 → task_id） |
| GET | /projects/{id}/prd | 最新 PRD（11 章节 + 证据引用 + 待确认标记） |
| PUT | /projects/{id}/prd | 编辑章节 / confirm=true 确认并进入 MVP |
| POST | /projects/{id}/tasks | 生成研发任务（异步） |
| GET | /projects/{id}/tasks | 任务列表 |
| PUT | /projects/{id}/tasks | 确认任务，进入资料包导出 |

## 八、Prompt 设计
- `PRD_SYSTEM`：固定 11 章节顺序 + 关键结论必须引用证据 ref_key + 无证据标"待确认"。
- `TASKS_SYSTEM`：module 限【前端/后端/AI/数据/集成/测试】、priority 限 P0/P1/P2、任务 8-15 个、source_refs 追溯。
- 格式三件套：Prompt 给 JSON 与约束 → parser 括号配对 → 章节规整补齐 + 证据过滤。

## 九、验收界面
- 界面第 6 步（PRD：11 章节可编辑、待确认标记、证据引用展示、确认）与第 7 步（研发任务：优先级/模块/验收/依赖/来源展示、确认）。

## 十、测试要求
- mock 自动化测试：52/52 通过（M3 新增 7 项：PRD 需定位、PRD 生成 11 章+证据、PRD 确认进 MVP、审计标待确认、任务需 PRD、任务生成、任务确认进 package）。
- 真实模型冒烟：见 evidence/阶段2-M3/真实冒烟输出.txt（PRD 38s 生成 11 章节、审计正确标"产品定位待确认"、任务 14 个含 P0/P1）。

## 十一、验收清单（照着点）
1. 打开 http://127.0.0.1:8200/ ，走完第 2-5 步（澄清→摘要→竞品→定位）。
2. 第 6 步「生成 PRD」→ 看到 11 章节（含证据引用、待确认标记）。
3. 编辑任意章节 →「保存并确认」→ 项目进入 MVP。
4. 第 7 步「生成研发任务」→ 看到任务列表（优先级/模块/验收/依赖）。
5. 「确认任务」→ 项目进入资料包导出（M4）。

## 十二、风险与待确认项
- PRD 生成会为"番茄钟"类想法给出具体技术假设（如 IndexedDB/无服务器），需用户编辑纠正；后续可加"技术栈约束"入 prompt。
- PRD 单次生成约 38s，满足 PRD 17.1（≤3min）。

## 十三、交接给下一阶段
- M4 资料包导出与迭代记录：Markdown 导出（P0）+ 飞书复制友好格式（P0）+ GitHub issue 草稿（P1）+ Feedback/DecisionLog 迭代记录 + Export 埋点。
- M3 已就绪复用件：ProductDoc 章节结构、DevTask 任务结构、证据 ref_key 引用体系、Task 异步框架。
