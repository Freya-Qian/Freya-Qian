# AI Avatar Twin（数字人短视频工作台）

面向 AI 行业内容创作者的「选题发现 → 脚本生成 → 数字人口播视频制作 → 发布素材包导出」工作台。

> 当前阶段：阶段 3 正式前端 · M4 已实现核心页面，待产品经理用真实素材验收。

## 目录
- `PRD/`：产品需求文档
- `阶段文档/`：项目状态、PRD 补全清单、技术适配声明、阶段技术开发文档
- `backend/`：后端代码（FastAPI + SQLite + Agent Harness，详见 `backend/README.md`）
- `frontend/`：正式前端（Next.js + TypeScript）
- `evidence/`：每阶段证据包
- `阶段文档/`：项目状态、PRD 补全清单、技术适配声明、阶段技术开发文档、Agent Harness 后端补齐清单
- `.env`：本项目专属 API Key（不入库，勿泄露）
- `.env.example`：环境变量模板

## 一、首次准备
1. 在项目根目录执行 `cp .env.example .env`，再在本地 `.env` 填入自己的模型凭据。`.env` 不随源码交付，不能提交到 GitHub。
2. 本地演示使用 `DEV_MODE=true`；正式部署前必须接入真实短信登录。模型、风格化、语音及视频生成可能产生费用，调用前核实账号权限和服务价格。
3. 建 Python 环境 + 装依赖：
   ```bash
   cd backend
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

## 二、启动后端
```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```
打开验收界面 **http://127.0.0.1:8100/**（8100 端口，与「脑洞游戏」8000 隔离）。

## 三、跑测试（不依赖 Key，离线）
```bash
cd backend
.venv/bin/python -m pytest
```

## 四、启动正式前端
```bash
cd frontend
npm ci
npm run dev
```
打开 **http://127.0.0.1:3000/**。如果 3000 已被占用，按终端提示使用已有地址或改端口启动。

前端生产检查：
```bash
cd frontend
npm run lint
npm run typecheck
npm run build
```

## 五、验收方法（照着点）
1. 打开 http://127.0.0.1:3000/ ，输入手机号（测试环境任意 6-20 位数字）→「获取验证码」→ 页面显示测试验证码 → 输入 →「登录」。
2. 建项目 → 建数字人 Profile（名称/风格/内容方向/口头禅/禁用词）。
3. 在「数字人设置」上传本人照片并确认授权，看到 3D 风格化预览图。
4. 加信息源（网页 URL / RSS / 手动文本）→「抓取」。
5. 抓取条目 →「摘要」→「生成选题」→ 选一个 →「生成脚本」（按 Profile 风格）。
6. 改脚本保存 / 回退 / 导出 Markdown·纯文本。
7. 到「生成视频」创建视频任务；完成后在「我的视频」预览、下载 MP4 和素材包 ZIP。
8. 刷新带 `?project=<项目ID>` 的页面，确认仍恢复到当前项目。
9. 退出登录验证：未登录访问被拒；换账号登录看不到上一个账号的数据。

## 六、数据与说明
- 三张默认模板随源码交付于 `backend/data/templates/`；用户照片、SQLite、配音、生成视频及导出包属于本地运行数据，不提交到 GitHub。
- 当前交付适用于本地开发及源码存档，真实短信、付费视频出片和正式部署验收仍待完成。数字人或语音服务失败可能产生静态/静音降级成片，任务 `success` 不等于口型与配音均完成，需检查视频及降级提示。
- 安全抓取仅连接经过解析校验的公网 IP；不使用系统代理环境变量，DNS 必须返回真实公网地址（VPN 的 fake-IP 解析会被拒绝），首个公网 IP 不可达时会返回抓取错误。
- SQLite：`backend/data/avatar_twin.db`（账户/项目/Profile/信息源/条目/选题/脚本全持久化，重启可恢复）。
- 文字模型：阿里云百炼 DashScope（OpenAI 兼容，默认 `qwen-plus`）。
- 登录：本地验证码 mock（`DEV_MODE=true` 时验证码直接返回），真实短信服务上线前接入。
- M3 已做：照片上传（校验+授权）、照片→3D 渲染风风格化（wan2.6-image）、异步视频任务（队列+重启恢复）、即梦 OmniHuman 口型驱动、字幕 SRT、封面、素材包 ZIP 导出。
- 已实现 **照片 → 3D 风格化形象 → 口型驱动 → 口播视频** 的代码链路及离线回归测试。最近一次数字人服务故障后的真实付费出片尚待验证；已有示例视频和 mock 测试不能证明当前账号一定能够成功生成。费用按服务商当前价格及账号套餐核实。
- Agent 化：一句话目标 → Agent 自主完成（`POST /api/v1/agent/run`，含硬闭环门：finish 前强制评估、不达标自动重写）。
- 后端待办（详见 `阶段文档/Agent Harness 后端补齐清单.md`）：记忆接线、埋点/指标、上下文压缩、断点续跑、ask 权限分级、定时抓取。
- 未做：抖音授权发布（V1 不做）、自建 EchoMimic 降本（上线后）。

## 七、接口速览（统一错误 `{"error":{"code","message"}}`；除登录外均需 `Authorization: Bearer <token>`）
- Agent：`POST /api/v1/agent/run`（SSE：`start`→`step`→`tool_result`→`eval`→`done`）
- 账户：`POST /api/v1/auth/code`、`POST /api/v1/auth/verify`、`POST /api/v1/auth/logout`、`GET /api/v1/auth/me`
- 项目：`POST/GET /api/v1/projects`、`PATCH /api/v1/projects/{id}`
- Profile：`POST/GET /api/v1/projects/{pid}/profiles`、`PATCH/DELETE /api/v1/profiles/{id}`
- 信息源：`POST/GET /api/v1/sources`、`PATCH/DELETE /api/v1/sources/{id}`、`POST /api/v1/sources/{id}/fetch`
- 条目：`GET /api/v1/items`、`POST /api/v1/items/{id}/summarize`、`POST /api/v1/items/{id}/topics`
- 脚本：`POST /api/v1/topics/{id}/scripts`（SSE：`chunk`→`done`/`error`）、`PATCH /api/v1/scripts/{id}`、`GET /api/v1/scripts/{id}/versions`、`POST /api/v1/scripts/{id}/revert`、`GET /api/v1/scripts/{id}/export?format=md|txt`
- 视频：`POST /api/v1/profiles/{id}/photo`（照片上传）、`GET /api/v1/profiles/{id}/avatar-preview`（3D 风格化预览）、`POST /api/v1/scripts/{id}/videos`、`GET /api/v1/videos/{id}`、`POST /api/v1/videos/{id}/retry`、`GET /api/v1/videos/{id}/file|cover|subtitle|export`

## 工作台交互复测（2026-09-23）

访问 http://127.0.0.1:3000/workspace 。当前前端默认代理后端 8100 端口，后端可用 `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8100` 启动。
在“我的角色”分别选择模板 2、3 创建角色并刷新，核对模板标签与预览；在“选题与脚本”检查当前任务草稿恢复、历史抓取/主题标签及当前脚本编辑；在“形象与视频”确认必须选择形象才能提交。
检查范围及未完成的视觉验收见 `evidence/阶段3-M4/工作台交互复核-2026-09-23.md`。
