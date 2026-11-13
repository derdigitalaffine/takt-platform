"""Additional regressions for granular Ortsrecht AI requests."""
from sqlalchemy import select

from app.db import SessionLocal
from app.law_ai_agent_models import LawAiAnalysis
from conftest import csrf_of, login, settings
from test_law_ai_agents import _upload, agent_routes, ADMIN


def test_stage_selection_requires_valid_id_and_explicit_consent(agent_routes):
    admin = login(*ADMIN)
    draft_id = _upload(admin)
    csrf = csrf_of(admin.get(f"/laws-assistant/{draft_id}").text)
    bad = admin.post(f"/laws-assistant/{draft_id}/agents", data={
        "csrf": csrf, "mode": "simple", "stage": "untrusted",
        "transmission_confirmed": "1",
    })
    assert bad.status_code == 422
    denied = admin.post(f"/laws-assistant/{draft_id}/agents", data={
        "csrf": csrf, "mode": "simple", "stage": "law_metadata",
    })
    assert denied.status_code == 422
    response = admin.post(f"/laws-assistant/{draft_id}/agents", data={
        "csrf": csrf, "mode": "simple", "stage": "law_metadata",
        "transmission_confirmed": "1",
    })
    assert response.status_code == 303, response.text
    with SessionLocal() as db:
        job = db.scalar(select(LawAiAnalysis).where(
            LawAiAnalysis.draft_id == draft_id).order_by(LawAiAnalysis.id.desc()))
        assert job is not None
        assert job.mode == "simple:m"


def test_workspace_exposes_three_granular_stages(agent_routes):
    admin = login(*ADMIN)
    draft_id = _upload(admin)
    response = admin.get(f"/laws-assistant/{draft_id}?bereich=ki")
    assert response.status_code == 200
    for item in ("law_structure", "law_metadata", "law_verify"):
        assert 'value="' + item + '"' in response.text
    assert "/static/law-ai-diff.js" in response.text
    assert "law-original-diff" in response.text


def test_discard_unused_draft_from_list_without_accepting():
    from app.law_ai_models import LawAiDraft
    admin = login(*ADMIN)
    draft_id = _upload(admin)
    landing = admin.get("/laws-assistant")
    assert f"/laws-assistant/{draft_id}/discard" in landing.text
    csrf = csrf_of(landing.text)
    invalid = admin.post(f"/laws-assistant/{draft_id}/discard",
                         data={"csrf": csrf, "discard_confirmed": ""})
    assert invalid.status_code == 422
    with SessionLocal() as db:
        assert db.get(LawAiDraft, draft_id) is not None
    removed = admin.post(f"/laws-assistant/{draft_id}/discard",
                         data={"csrf": csrf, "discard_confirmed": "1"})
    assert removed.status_code == 303, removed.text
    with SessionLocal() as db:
        assert db.get(LawAiDraft, draft_id) is None
    assert admin.get(f"/laws-assistant/{draft_id}").status_code == 404


def test_single_agent_worker_only_runs_selected_step(monkeypatch, agent_routes):
    import asyncio
    import json
    from app import law_ai_agent_jobs

    admin = login(*ADMIN)
    did = _upload(admin)
    csrf = csrf_of(admin.get(f"/laws-assistant/{did}").text)
    response = admin.post(f"/laws-assistant/{did}/agents", data={
        "csrf": csrf, "mode": "simple", "stage": "law_metadata",
        "transmission_confirmed": "1",
    })
    assert response.status_code == 303
    with SessionLocal() as db:
        job = db.scalar(select(LawAiAnalysis).where(
            LawAiAnalysis.draft_id == did).order_by(LawAiAnalysis.id.desc()))
        assert set(json.loads(job.provider_map_json)) == {"law_metadata"}
        job.status = "running"
        job_id = job.id
        db.commit()

    calls = []
    async def model_answer(provider, messages, job_id, step, **kwargs):
        calls.append(step)
        return '{"fields":[]}'
    monkeypatch.setattr(law_ai_agent_jobs, "_answer", model_answer)
    asyncio.run(law_ai_agent_jobs.process_one(job_id))
    with SessionLocal() as db:
        row = db.get(LawAiAnalysis, job_id)
        assert row.status == "done", row.failure
        assert row.progress_done == row.progress_total == 1
        assert json.loads(row.metadata_json)["schema"] == 2
        assert json.loads(row.outline_json) == {}
        assert json.loads(row.verification_json) == {}
    assert len(calls) == 1
