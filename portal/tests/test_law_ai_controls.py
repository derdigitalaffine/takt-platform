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
