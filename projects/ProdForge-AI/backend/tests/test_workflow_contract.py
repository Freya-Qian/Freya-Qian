"""Workflow regressions use the isolated database and FakeLLMClient only."""
import asyncio
import json

import pytest
from sqlalchemy import select

from app import models as m
from app.config import DEFAULT_USER_ID
from app.core.db import Base
from app.services import task_worker


def generate(client, base, endpoint):
    response = client.post(f"{base}/{endpoint}")
    assert response.status_code == 202, response.text
    tid = response.json()["id"]
    asyncio.run(task_worker.process_task(tid))
    result = client.get(f"/api/v1/tasks/{tid}").json()
    assert result["status"] == "success", result
    return tid


@pytest.fixture
def package(client):
    pid = client.post("/api/v1/projects", json={"name": "workflow", "idea": "test"}).json()["id"]
    base = f"/api/v1/projects/{pid}"
    generate(client, base, "clarify/questions")
    questions = client.get(base + "/clarify/questions").json()
    assert client.post(base + "/clarify/answers", json={"answers": [
        {"question_id": q["id"], "answer": "answer"} for q in questions
    ]}).status_code == 200
    generate(client, base, "brief")
    assert client.put(base + "/brief", json={"confirm": True}).status_code == 200
    cid = client.post(base + "/competitors", json={"name": "source"}).json()["id"]
    for claim in ("first", "second"):
        assert client.post(base + f"/competitors/{cid}/evidences", json={
            "source_url": "https://example.com", "structured_claim": claim,
        }).status_code == 201
    for endpoint in ("positioning", "prd"):
        generate(client, base, endpoint)
        assert client.put(base + f"/{endpoint}", json={"confirm": True}).status_code == 200
    generate(client, base, "tasks")
    assert client.put(base + "/tasks").status_code == 200
    return pid, base, cid


def snapshot():
    with task_worker.SessionLocal() as db:
        return {table.name: sorted(tuple(row) for row in db.execute(select(table)))
                for table in Base.metadata.sorted_tables}


def test_positioning_without_evidence_rejects_before_queue(client):
    pid = client.post("/api/v1/projects", json={"name": "empty", "idea": "test"}).json()["id"]
    with task_worker.SessionLocal() as db:
        db.add(m.RequirementBrief(project_id=pid, status="confirmed"))
        db.add(m.Competitor(project_id=pid, name="no evidence"))
        db.commit()
    before = snapshot()
    response = client.post(f"/api/v1/projects/{pid}/positioning")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_READY"
    assert "证据卡" in response.json()["error"]["message"]
    assert snapshot() == before


@pytest.mark.parametrize("endpoint,stage", [("brief", "clarify"), ("positioning", "position"),
                                            ("prd", "prd"), ("tasks", "tasks")])
def test_regeneration_exits_package_and_blocks_confirmation_while_running(client, package, endpoint, stage):
    pid, base, _ = package
    response = client.post(base + "/" + endpoint)
    assert response.status_code == 202
    assert client.get(base).json()["current_stage"] == stage
    assert client.put(base + "/tasks").status_code == 409
    if endpoint != "tasks":
        assert client.put(base + "/" + endpoint, json={"confirm": True}).status_code == 409
    asyncio.run(task_worker.process_task(response.json()["id"]))
    assert client.get(base).json()["current_stage"] == stage
    if endpoint != "tasks":
        assert client.get(base + "/" + endpoint).json()["status"] == "draft"
        assert client.put(base + "/tasks").status_code == 409


def test_brief_v2_cannot_reuse_old_positioning_or_prd(client, package):
    pid, base, _ = package
    with task_worker.SessionLocal() as db:
        db.add(m.Positioning(project_id=pid, version=0, status="confirmed", one_liner="history"))
        db.add(m.ProductDoc(project_id=pid, version=0, status="confirmed", sections="[]"))
        db.commit()
    generate(client, base, "brief")
    assert client.get(base + "/brief").json()["version"] == 2
    assert client.put(base + "/brief", json={"confirm": True}).status_code == 200
    for endpoint in ("positioning", "prd"):
        assert client.get(base + "/" + endpoint).json()["status"] == "stale"
        assert client.put(base + "/" + endpoint, json={"confirm": True}).status_code == 409
    assert client.post(base + "/prd").status_code == 409
    assert client.put(base + "/tasks").status_code == 409
    with task_worker.SessionLocal() as db:
        assert db.query(m.RequirementBrief).filter_by(project_id=pid, version=1).one().status == "confirmed"
        for model in (m.Positioning, m.ProductDoc):
            assert db.query(model).filter_by(project_id=pid, version=0).one().status == "confirmed"
    generate(client, base, "positioning")
    assert client.put(base + "/positioning", json={"confirm": True}).status_code == 200
    generate(client, base, "prd")
    assert client.put(base + "/prd", json={"confirm": True}).status_code == 200
    # The old five tasks are not evidence of completion against the new PRD.
    response = client.put(base + "/tasks")
    assert response.status_code == 409
    assert "重新生成研发任务" in response.json()["error"]["message"]
    generate(client, base, "tasks")
    assert client.put(base + "/tasks").json() == {"current_stage": "package"}


def test_edited_confirmed_brief_invalidates_latest_downstream(client, package):
    _, base, _ = package
    response = client.put(base + "/brief", json={"one_liner": "revised"})
    assert response.json()["status"] == "draft"
    assert client.get(base).json()["current_stage"] == "clarify"
    assert client.get(base + "/positioning").json()["status"] == "stale"
    assert client.get(base + "/prd").json()["status"] == "stale"
    assert client.put(base + "/brief", json={"confirm": True}).status_code == 200
    assert client.post(base + "/prd").status_code == 409


def test_repeat_confirmations_preserve_valid_package(client, package):
    _, base, _ = package
    for endpoint in ("brief", "positioning", "prd"):
        response = client.put(base + "/" + endpoint, json={"confirm": True})
        assert response.status_code == 200
        assert client.get(base).json()["current_stage"] == "package"
    assert client.put(base + "/tasks").status_code == 200


@pytest.mark.parametrize("model", [m.RequirementBrief, m.Positioning, m.ProductDoc])
def test_package_confirmation_uses_latest_version(client, package, model):
    pid, base, _ = package
    with task_worker.SessionLocal() as db:
        db.add(model(project_id=pid, version=2, status="draft"))
        db.commit()
    before = snapshot()
    response = client.put(base + "/tasks")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOT_READY"
    assert snapshot() == before


def test_task_polling_is_owned_and_projectless_tasks_are_hidden(client):
    with task_worker.SessionLocal() as db:
        db.add(m.User(id="other"))
        db.commit()
        db.add_all([m.Project(id="owned", user_id=DEFAULT_USER_ID, name="owned", idea="test"),
                    m.Project(id="foreign", user_id="other", name="foreign", idea="test")])
        db.commit()
        for tid, pid in [("ours", "owned"), ("theirs", "foreign"), ("system", None)]:
            db.add(m.Task(id=tid, project_id=pid, task_type="brief", status="success", result_json='{"secret":true}'))
        db.commit()
    assert client.get("/api/v1/tasks/ours").status_code == 200
    for tid in ("theirs", "system", "missing"):
        response = client.get(f"/api/v1/tasks/{tid}")
        assert response.status_code == 404
        assert "secret" not in response.text


def test_detach_preserves_content_all_versions_and_frees_cap(client, package):
    pid, base, cid = package
    with task_worker.SessionLocal() as db:
        db.add(m.Positioning(project_id=pid, version=0, status="confirmed", one_liner="historic prose",
                             evidence_refs='["E1","OTHER"]', differentiators='[{"point":"keep","evidence_refs":["E2"]}]'))
        db.add(m.DecisionLog(project_id=pid, decision="user content", evidence_refs='["E1"]'))
        db.commit()
    for name in ("second", "third"):
        assert client.post(base + "/competitors", json={"name": name}).status_code == 201
    assert client.post(base + "/competitors", json={"name": "fourth"}).status_code == 409
    assert client.delete(base + f"/competitors/{cid}").status_code == 409
    before = snapshot()
    response = client.post(base + f"/competitors/{cid}/detach-references")
    assert response.status_code == 200, response.text
    assert response.json()["detached_refs"] == ["E1", "E2"]
    assert response.json()["shared_refs"] == []
    with task_worker.SessionLocal() as db:
        historic = db.query(m.Positioning).filter_by(project_id=pid, version=0).one()
        assert historic.one_liner == "historic prose"
        assert json.loads(historic.evidence_refs) == ["OTHER"]
        assert json.loads(historic.differentiators) == [{"point": "keep", "evidence_refs": []}]
        assert db.query(m.DecisionLog).filter_by(decision="user content").one().evidence_refs == "[]"
        for model, text_field in [(m.Positioning, "one_liner"), (m.ProductDoc, "sections"), (m.DevTask, "description")]:
            table = model.__table__
            idx = list(table.c.keys()).index(text_field)
            old = {row[0]: row[idx] for row in before[table.name]}
            for row in db.query(model).filter_by(project_id=pid).all():
                value = getattr(row, text_field)
                if model is m.ProductDoc:
                    assert [s["content"] for s in json.loads(value)] == [s["content"] for s in json.loads(old[row.id])]
                else:
                    assert value == old[row.id]
    assert client.get(base + "/positioning").json()["status"] == "stale"
    assert client.get(base + "/prd").json()["status"] == "stale"
    assert client.delete(base + f"/competitors/{cid}").status_code == 200
    assert client.post(base + "/competitors", json={"name": "replacement"}).status_code == 201


def test_detach_shared_keys_requires_explicit_opt_in(client, package):
    pid, base, cid = package
    other = client.post(base + "/competitors", json={"name": "shared key"}).json()["id"]
    # Reproduce legacy data explicitly; new allocations are project-wide now.
    with task_worker.SessionLocal() as db:
        db.add(m.CompetitorEvidence(project_id=pid, competitor_id=other, ref_key="E1",
                                   source_type="用户输入", evidence_type="定位",
                                   source_url="https://example.com", structured_claim="keep"))
        db.commit()
    before = snapshot()
    path = base + f"/competitors/{cid}/detach-references"
    response = client.post(path)
    assert response.status_code == 409
    assert "allow_shared_refs=true" in response.json()["error"]["message"]
    assert snapshot() == before
    response = client.post(path + "?allow_shared_refs=true")
    assert response.status_code == 200
    assert response.json()["shared_refs"] == ["E1"]
    assert client.delete(base + f"/competitors/{cid}").status_code == 200
    assert len(client.get(base + f"/competitors/{other}/evidences").json()) == 1


@pytest.mark.parametrize("blocker", ["active", "malformed"])
def test_detach_rolls_back_without_partial_changes(client, package, blocker):
    pid, base, cid = package
    with task_worker.SessionLocal() as db:
        if blocker == "active":
            db.add(m.Task(project_id=pid, task_type="brief", status="processing"))
        else:
            db.add(m.DecisionLog(project_id=pid, decision="malformed", evidence_refs="invalid"))
        db.commit()
    before = snapshot()
    response = client.post(base + f"/competitors/{cid}/detach-references")
    assert response.status_code == 409
    assert snapshot() == before


def test_detach_cannot_cross_project_or_user_boundary(client, package):
    _, base, cid = package
    with task_worker.SessionLocal() as db:
        db.add(m.User(id="foreign-user"))
        db.commit()
        db.add(m.Project(id="foreign", user_id="foreign-user", name="foreign", idea="test"))
        db.commit()
        db.add(m.Competitor(id="foreign-comp", project_id="foreign", user_id="foreign-user", name="foreign"))
        db.commit()
    before = snapshot()
    for path in (base + "/competitors/foreign-comp/detach-references",
                 "/api/v1/projects/foreign/competitors/foreign-comp/detach-references",
                 f"/api/v1/projects/missing/competitors/{cid}/detach-references"):
        assert client.post(path).status_code == 404
    assert snapshot() == before


@pytest.mark.parametrize("task_type,stage", [("brief", "clarify"), ("positioning", "position"),
                                             ("prd", "prd"), ("tasks", "tasks")])
def test_worker_resets_stage_when_processing_preexisting_job(client, package, task_type, stage):
    pid, base, _ = package
    with task_worker.SessionLocal() as db:
        job = m.Task(project_id=pid, task_type=task_type, status="queued")
        db.add(job)
        db.commit()
        tid = job.id
    asyncio.run(task_worker.process_task(tid))
    assert client.get(f"/api/v1/tasks/{tid}").json()["status"] == "success"
    assert client.get(base).json()["current_stage"] == stage
    if task_type == "brief":
        assert client.get(base + "/positioning").json()["status"] == "stale"
    if task_type in ("brief", "positioning"):
        assert client.get(base + "/prd").json()["status"] == "stale"
