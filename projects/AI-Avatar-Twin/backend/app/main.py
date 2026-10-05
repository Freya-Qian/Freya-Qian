"""FastAPI 入口：挂载 API 与最小验收界面，启动视频后台 worker 与中断恢复。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.db import SessionLocal, init_db
from app.core.llm import ERROR_STATUS, LLMError
from app.models import VideoProject
from app.services import video_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动恢复：把中断的 queued/rendering 视频任务标为 failed（不自动重做）
    db = SessionLocal()
    try:
        db.query(VideoProject).filter(VideoProject.status.in_(["queued", "rendering"])).update(
            {VideoProject.status: "failed", VideoProject.error_message: "服务重启导致任务中断，请重试"},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()
    video_worker.start_worker()
    yield


app = FastAPI(title="AI Avatar Twin API", lifespan=lifespan)

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
