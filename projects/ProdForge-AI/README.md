# ProdForge AI

ProdForge AI 是一个 AI 产品孵化工作台：从产品想法出发，逐步完成需求澄清、竞品证据整理、产品定位、PRD、研发任务拆解与项目资料导出。

## 技术栈

- 前端：Next.js 16、React 19、TypeScript
- 后端：FastAPI、SQLAlchemy、SQLite
- 模型：OpenAI 兼容 API（默认配置为阿里云百炼 DashScope）

## 本地运行

需要 Python 3.11+、Node.js 20+ 和 npm。首次运行时，在仓库根目录执行：

```bash
cp .env.example .env
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend && npm ci
```

如需启用 AI 生成能力，在根目录 `.env` 中配置 `MODEL_API_KEY`。不配置时，前后端仍可启动并运行测试，但依赖模型的生成请求不可用。

分别在两个终端启动服务（从仓库根目录执行）：

```bash
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8200
```

```bash
cd frontend && npm run dev
```

打开 [http://localhost:3300](http://localhost:3300)。前端将 `/api/v1` 和 `/health` 请求转发到 `http://127.0.0.1:8200`。自定义后端地址时，在启动前端前设置 `BACKEND_ORIGIN`。

## 测试与构建

```bash
backend/.venv/bin/python -m pytest backend/tests
cd frontend && npm run build
```

后端在 `backend/data/product_factory.db` 创建本地 SQLite 数据库。密钥、数据库、依赖和构建输出均为本地文件，不应提交到版本库。

## 项目结构

- `frontend/`：ProdForge AI Web 应用
- `backend/`：FastAPI API、业务逻辑与测试
- `PRD/`：产品需求文档
- `阶段文档/`：项目和技术阶段文档
- `evidence/`：开发与验收证据
- `.env.example`：环境变量模板（不含真实密钥）
