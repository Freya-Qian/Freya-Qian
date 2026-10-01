"""FastAPI 入口：挂载 API 与最小验收界面，启动后台任务 worker 与中断恢复。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.db import SessionLocal, init_db
from app.core.llm import ERROR_STATUS, LLMError
from app.models import Task
from app.services import task_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动恢复：把中断的 queued/processing 任务标为 failed（不自动重做，由用户重试）
    db = SessionLocal()
    try:
        db.query(Task).filter(Task.status.in_(["queued", "processing"])).update(
            {Task.status: "failed", Task.error: "服务重启导致任务中断，请重试"},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()
    task_worker.start_worker()
    yield
    task_worker.stop_worker()


app = FastAPI(title="AI 产品工厂 API", lifespan=lifespan)

init_db()

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(LLMError)
async def llm_error_handler(request, exc: LLMError):
    status = ERROR_STATUS.get(exc.code, 500)
    return JSONResponse(status_code=status, content={"error": {"code": exc.code, "message": exc.message}})


# 静态验收界面最后挂载，避免遮住上面的路由
_static = Path(__file__).resolve().parent / "static"
if _static.exists():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="static")
