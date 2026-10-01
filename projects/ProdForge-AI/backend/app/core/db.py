"""SQLAlchemy 引擎与会话。MVP 用 SQLite（create_all 建表，暂缓 Alembic）。"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DB_PATH, DEFAULT_USER_ID

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def enable_foreign_keys(connection, _record):
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


event.listen(engine, "connect", enable_foreign_keys)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """建表（幂等）+ 预埋匿名本地用户 + 回填系统级决策。生产上线前补 Alembic 迁移。"""
    from app import models  # noqa: F401  确保模型已注册

    Base.metadata.create_all(bind=engine)
    _migrate()
    with SessionLocal() as db:
        if not db.get(models.User, DEFAULT_USER_ID):
            db.add(models.User(id=DEFAULT_USER_ID))
            db.commit()
        _seed_decision_logs(db)


def _migrate() -> None:
    """轻量迁移：为已存在的 tasks 表补 token 列（SQLite 的 create_all 不改已有表）。"""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "tasks" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("tasks")}
    with engine.begin() as conn:
        for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if name not in cols:
                conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {name} INTEGER DEFAULT 0"))


def _seed_decision_logs(db) -> None:
    """回填系统级决策（表为空时插入一次），让决策台账有据可查（PRD 11.7）。"""
    from app import models

    if db.query(models.DecisionLog).count() > 0:
        return
    seeds = [
        ("竞品由用户自选、上限 ≤3 个", "产品经理确认（WorkBuddy 彻底移除，通用竞品分析工作台）", "产品经理确认"),
        ("MVP 范围并入 PRD「版本规划」章节，无独立 mvp 阶段", "产品经理确认方案 B", "产品经理确认"),
        ("用户自备 API Key、平台托管放 V1", "国内厂商优先、数据不出境", "决策台账 D4"),
        ("无账号、匿名本地用户", "MVP 匿名本地用户，账号体系放 V1", "决策台账 D5"),
    ]
    for decision, reason, source in seeds:
        db.add(models.DecisionLog(project_id=None, decision=decision, reason=reason, source=source))
    db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
