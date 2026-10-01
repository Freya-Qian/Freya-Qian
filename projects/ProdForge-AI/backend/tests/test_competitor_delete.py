"""Competitor deletion and data isolation, using only the temporary test database."""
import json

import pytest
from sqlalchemy import event, select

from app import models as m
from app.config import DEFAULT_USER_ID
from app.core.db import Base
from app.services import task_worker


def snapshot():
    with task_worker.SessionLocal() as db:
        return {t.name: sorted(tuple(row) for row in db.execute(select(t)))
                for t in Base.metadata.sorted_tables}


@pytest.fixture
def seeded(client):
    with task_worker.SessionLocal() as db:
        db.add(m.User(id="other"))
        db.commit()
        db.add_all([m.Project(id=pid, user_id=owner, name=pid, idea="test")
                    for pid, owner in [("p", DEFAULT_USER_ID), ("q", DEFAULT_USER_ID), ("foreign", "other")]])
        db.commit()
        db.add_all([m.Competitor(id=cid, project_id=pid, user_id=owner, name=cid)
                    for cid, pid, owner in [("c", "p", DEFAULT_USER_ID), ("keep", "p", DEFAULT_USER_ID),
                                            ("q-c", "q", DEFAULT_USER_ID), ("foreign-c", "foreign", "other")]])
        db.commit()
        for cid, pid, owner in [("c", "p", DEFAULT_USER_ID), ("keep", "p", DEFAULT_USER_ID),
                                ("q-c", "q", DEFAULT_USER_ID), ("foreign-c", "foreign", "other")]:
            db.add(m.CompetitorEvidence(id=cid + "-ev", competitor_id=cid, project_id=pid,
                                       user_id=owner, ref_key="E1", source_type="website",
                                       source_url="https://example.com", evidence_type="feature"))
        db.get(m.Project, "p").default_competitor_id = "c"
        db.add(m.Task(id="finished", project_id="p", task_type="brief", status="success"))
        db.add(m.Task(id="unrelated-active", project_id="q", task_type="brief", status="processing"))
        db.commit()
    return client


def test_delete_cleans_evidence_clears_default_and_preserves_other_data(seeded):
    before = snapshot()
    response = seeded.delete("/api/v1/projects/p/competitors/c")
    assert response.status_code == 200
    assert response.json() == {"deleted": "c"}
    after = snapshot()
    for table in Base.metadata.sorted_tables:
        if table.name == "projects":
            index = list(table.c.keys()).index("default_competitor_id")
            expected = [tuple(None if i == index and row[i] == "c" else value
                              for i, value in enumerate(row)) for row in before[table.name]]
            updated = list(table.c.keys()).index("updated_at")
            for i, row in enumerate(expected):
                if row[0] == "p":
                    assert after[table.name][i][updated] >= row[updated]
                    expected[i] = tuple(after[table.name][i][updated] if j == updated else value
                                        for j, value in enumerate(row))
        else:
            expected = [row for row in before[table.name]
                        if not (table.name == "competitors" and row[0] == "c")
                        and not (table.name == "competitor_evidences" and row[0] == "c-ev")]
        assert after[table.name] == expected
    assert seeded.delete("/api/v1/projects/p/competitors/c").status_code == 404


def test_nondefault_delete_preserves_default_and_frees_capacity(seeded):
    url = "/api/v1/projects/p/competitors"
    assert seeded.post(url, json={"name": "third"}).status_code == 201
    assert seeded.post(url, json={"name": "fourth"}).status_code == 409
    assert seeded.delete(url + "/keep").status_code == 200
    assert seeded.post(url, json={"name": "replacement"}).status_code == 201
    assert len(seeded.get(url).json()) == 3
    with task_worker.SessionLocal() as db:
        assert db.get(m.Project, "p").default_competitor_id == "c"


@pytest.mark.parametrize("pid,cid", [
    ("missing", "c"), ("p", "missing"), ("p", "q-c"),
    ("q", "c"), ("foreign", "foreign-c"), ("p", "foreign-c"),
])
def test_missing_cross_project_and_foreign_access(seeded, pid, cid):
    before = snapshot()
    response = seeded.delete(f"/api/v1/projects/{pid}/competitors/{cid}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert snapshot() == before


@pytest.mark.parametrize("status", ["queued", "processing"])
@pytest.mark.parametrize("task_type", list(task_worker.TASK_HANDLERS))
def test_any_active_project_task_blocks_deletion(seeded, status, task_type):
    with task_worker.SessionLocal() as db:
        db.add(m.Task(project_id="p", task_type=task_type, status=status))
        db.commit()
    before = snapshot()
    response = seeded.delete("/api/v1/projects/p/competitors/c")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert snapshot() == before


@pytest.mark.parametrize("model,field,value", [
    (m.Positioning, "evidence_refs", '["E1"]'),
    (m.Positioning, "differentiators", '[{"evidence_refs":["E1"]}]'),
    (m.ProductDoc, "evidence_refs", '["E1"]'),
    (m.ProductDoc, "sections", '[{"evidence_refs":["E1"]}]'),
    (m.DevTask, "source_refs", '["E1"]'),
    (m.DecisionLog, "evidence_refs", '["E1"]'),
    (m.Positioning, "evidence_refs", 'invalid-json'),
])
def test_downstream_references_block_competitor_and_evidence_delete(seeded, model, field, value):
    attrs = {"project_id": "p", field: value}
    if model is m.DevTask:
        attrs.update(module="backend", title="task")
    if model is m.DecisionLog:
        attrs["decision"] = "test"
    with task_worker.SessionLocal() as db:
        db.add(model(**attrs))
        db.commit()
    before = snapshot()
    for suffix in ("", "/evidences/c-ev"):
        response = seeded.delete("/api/v1/projects/p/competitors/c" + suffix)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"
        assert snapshot() == before


def test_unrelated_references_and_other_project_references_do_not_block(seeded):
    with task_worker.SessionLocal() as db:
        db.add(m.Positioning(project_id="p", evidence_refs=json.dumps(["E2"])))
        db.add(m.ProductDoc(project_id="q", evidence_refs=json.dumps(["E1"])))
        db.commit()
    assert seeded.delete("/api/v1/projects/p/competitors/c").status_code == 200


def test_rollback_restores_evidence_and_default_on_delete_failure(seeded):
    before = snapshot()
    with task_worker.SessionLocal() as db:
        engine = db.get_bind()

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM competitors"):
            raise RuntimeError("injected failure")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected failure"):
            seeded.delete("/api/v1/projects/p/competitors/c")
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert snapshot() == before
