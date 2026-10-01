"""Deletion, ownership and transactional integrity against isolated test data."""
import asyncio

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from app import models as m
from app.config import DEFAULT_USER_ID
from app.api.routes import delete_project
from app.core.db import Base, enable_foreign_keys
from app.services import task_worker


RELATED = (
    m.ClarificationQA, m.RequirementBrief, m.ProductDoc, m.DevTask, m.Task,
    m.Competitor, m.CompetitorEvidence, m.Positioning, m.DecisionLog,
    m.Feedback, m.Export,
)


def seed_project(db, pid, user_id=DEFAULT_USER_ID):
    db.add(m.Project(id=pid, user_id=user_id, name=pid, idea="test"))
    db.flush()
    db.add(m.Competitor(id=pid + "-comp", project_id=pid, user_id=user_id, name="comp"))
    db.flush()
    db.add_all([
        m.ClarificationQA(project_id=pid, dimension="users", question="who?"),
        m.RequirementBrief(project_id=pid, version=1),
        m.RequirementBrief(project_id=pid, version=2),
        m.ProductDoc(project_id=pid, user_id=user_id),
        m.DevTask(project_id=pid, user_id=user_id, module="backend", title="test"),
        m.Task(id=pid + "-success", project_id=pid, task_type="brief", status="success"),
        m.Task(id=pid + "-failed", project_id=pid, task_type="brief", status="failed"),
        m.CompetitorEvidence(project_id=pid, competitor_id=pid + "-comp",
                             user_id=user_id, ref_key="E1", source_type="website",
                             source_url="https://example.com", evidence_type="feature"),
        m.Positioning(project_id=pid, user_id=user_id),
        m.DecisionLog(project_id=pid, user_id=user_id, decision="test"),
        m.Feedback(project_id=pid, user_id=user_id, content="test"),
        m.Export(project_id=pid, user_id=user_id, channel="markdown"),
    ])
    db.commit()


def snapshot(db):
    return {
        table.name: sorted(tuple(row) for row in db.execute(select(table)))
        for table in Base.metadata.sorted_tables
    }


def test_delete_all_related_rows_and_preserve_other_projects(client):
    # Fail when a future project-owned table is missing from this coverage.
    assert {t.name for t in Base.metadata.tables.values() if "project_id" in t.c} == {
        model.__tablename__ for model in RELATED
    }
    with task_worker.SessionLocal() as db:
        db.add(m.User(id="other"))
        db.commit()
        seed_project(db, "delete")
        seed_project(db, "keep")
        seed_project(db, "foreign", "other")
        db.add_all([
            m.DecisionLog(id="system", project_id=None, decision="global"),
            m.Task(id="global-task", project_id=None, task_type="test", status="queued"),
        ])
        db.commit()
        before = snapshot(db)

    response = client.delete("/api/v1/projects/delete")
    assert response.status_code == 200
    assert response.json() == {"deleted": "delete"}
    assert client.get("/api/v1/projects/delete").status_code == 404
    assert {p["id"] for p in client.get("/api/v1/projects").json()} == {"keep"}
    with task_worker.SessionLocal() as db:
        for model in RELATED:
            assert db.query(model).filter(model.project_id == "delete").count() == 0
        after = snapshot(db)
        for table in Base.metadata.sorted_tables:
            column = "project_id" if "project_id" in table.c else "id"
            index = list(table.c.keys()).index(column)
            assert after[table.name] == [row for row in before[table.name] if row[index] != "delete"]
    assert client.delete("/api/v1/projects/delete").status_code == 404
    # A stale queue entry cannot recreate deleted task results.
    asyncio.run(task_worker.process_task("delete-success"))


@pytest.mark.parametrize("pid", ["missing", "foreign"])
def test_delete_missing_or_foreign_project_is_404_without_changes(client, pid):
    with task_worker.SessionLocal() as db:
        db.add(m.User(id="other"))
        db.commit()
        seed_project(db, "foreign", "other")
        db.add(m.Task(project_id="foreign", task_type="brief", status="processing"))
        db.commit()
        before = snapshot(db)
    response = client.delete(f"/api/v1/projects/{pid}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    with task_worker.SessionLocal() as db:
        assert snapshot(db) == before


@pytest.mark.parametrize("status", ["queued", "processing"])
@pytest.mark.parametrize("task_type", list(task_worker.TASK_HANDLERS))
def test_delete_rejects_active_tasks_without_partial_cleanup(client, status, task_type):
    with task_worker.SessionLocal() as db:
        seed_project(db, "busy")
        db.add(m.Task(id="active", project_id="busy", task_type=task_type, status=status))
        db.commit()
        before = snapshot(db)
    response = client.delete("/api/v1/projects/busy")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    with task_worker.SessionLocal() as db:
        assert snapshot(db) == before
        db.get(m.Task, "active").status = "failed"
        db.commit()
    assert client.delete("/api/v1/projects/busy").status_code == 200


def test_delete_rolls_back_cleanup_on_database_error(client):
    with task_worker.SessionLocal() as db:
        seed_project(db, "rollback")
        before = snapshot(db)
        engine = db.get_bind()

    def fail_on_parent_delete(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM projects"):
            raise RuntimeError("injected deletion failure")

    event.listen(engine, "before_cursor_execute", fail_on_parent_delete)
    try:
        with pytest.raises(RuntimeError, match="injected deletion failure"):
            client.delete("/api/v1/projects/rollback")
    finally:
        event.remove(engine, "before_cursor_execute", fail_on_parent_delete)
    with task_worker.SessionLocal() as db:
        assert snapshot(db) == before
    assert client.delete("/api/v1/projects/rollback").status_code == 200


def test_stale_task_submission_cannot_write_after_delete(client):
    with task_worker.SessionLocal() as db:
        seed_project(db, "race")
    with task_worker.SessionLocal() as stale:
        assert stale.get(m.Project, "race") is not None
        assert client.delete("/api/v1/projects/race").status_code == 200
        stale.add(m.Task(project_id="race", task_type="brief", status="queued"))
        with pytest.raises(IntegrityError):
            stale.commit()
        stale.rollback()
        assert stale.query(m.Task).filter(m.Task.project_id == "race").count() == 0


def test_delete_serializes_task_writes_across_connections(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrency.db'}",
                           connect_args={"timeout": 0})
    event.listen(engine, "connect", enable_foreign_keys)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with Session() as db:
        db.add(m.User(id=DEFAULT_USER_ID))
        db.commit()
        seed_project(db, "concurrent")

    attempted = []

    def submit_during_check(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT tasks.id"):
            with Session() as writer:
                writer.add(m.Task(project_id="concurrent", task_type="brief"))
                with pytest.raises(OperationalError, match="database is locked"):
                    writer.commit()
                writer.rollback()
            attempted.append(True)

    event.listen(engine, "before_cursor_execute", submit_during_check)
    try:
        with Session() as db:
            assert delete_project("concurrent", db) == {"deleted": "concurrent"}
        assert attempted == [True]
        with Session() as writer:
            writer.add(m.Task(project_id="concurrent", task_type="brief"))
            with pytest.raises(IntegrityError):
                writer.commit()
            writer.rollback()
    finally:
        event.remove(engine, "before_cursor_execute", submit_during_check)
        engine.dispose()
