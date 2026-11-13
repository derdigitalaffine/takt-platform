"""Ortsrecht targeted agents, local 24B–30B inference and explicit consent."""
import asyncio
import json
import re

import pytest
from sqlalchemy import select
from app import ai_provider, law_ai_agent_jobs, law_ai_coverage
from app.ai_models import AITaskProfile
from app.db import SessionLocal
from app.law_ai_agent_models import LawAiAnalysis
from app.law_ai_models import LawAiDraft
from conftest import csrf_of, login, settings

from test_law_ai_agents import agent_routes  # reuse stable model/provider fixture


ADMIN = ("admin@example.org", "admin-passwort-123")
SOURCE = "# Hausordnung\n§ 1 Gebühren 10 €\n"


def _draft(client, source=SOURCE):
    csrf = csrf_of(client.get("/laws-assistant").text)
    result = client.post(
        "/laws-assistant/import", data={"csrf": csrf},
        files={"file": ("local-model.md", source.encode(), "text/markdown")},
    )
    assert result.status_code == 303, result.text
    return int(re.search(r"/laws-assistant/(\d+)", result.headers["location"]).group(1))


def _start(client, did, *, tasks, quality_profile="local_24b", mode="simple",
           json_mode=False, marker=True):
    token = csrf_of(client.get(f"/laws-assistant/{did}").text)
    data = [
        ("csrf", token), ("mode", mode), ("transmission_confirmed", "1"),
        ("quality_profile", quality_profile),
    ]
    if marker:
        data.append(("tasks_present", "1"))
    if json_mode:
        data.append(("json_mode", "1"))
    data.extend(("tasks", t) for t in tasks)
    # Passing dict with list values makes Starlette's form parser preserve
    # repeated checkbox values in the same way as the browser.
    payload = dict(data)
    payload["tasks"] = tasks
    return client.post(f"/laws-assistant/{did}/agents", data=payload)


def _claim(did):
    with SessionLocal() as db:
        job = db.scalar(select(LawAiAnalysis).where(
            LawAiAnalysis.draft_id == did).order_by(LawAiAnalysis.id.desc()))
        assert job is not None
        job.status, job.step = "running", "preparing"
        db.commit()
        return job.id


def _context(messages):
    return messages[1]["content"].split(
        "\n<<<BEGIN_UNTRUSTED_ORTSRECHT>>>\n", 1)[1].split(
        "\n<<<END_UNTRUSTED_ORTSRECHT>>>", 1)[0]


def test_metadata_only_local_profile_calls_only_consented_model(monkeypatch, agent_routes):
    admin = login(*ADMIN)
    did = _draft(admin)
    page = admin.get(f"/laws-assistant/{did}")
    assert page.status_code == 200
    assert "Nur Stammdaten" in page.text
    assert 'value="local_24b"' in page.text
    result = _start(admin, did, tasks=["law_metadata"])
    assert result.status_code == 303, result.text
    jid = _claim(did)
    called = []

    async def fake(provider, messages, *, max_tokens=1024, **kwargs):
        called.append((provider.model_id, max_tokens, kwargs))
        return json.dumps({"fields": [
            {"field": "title", "value": "Hausordnung", "evidence": "Hausordnung"},
        ]})
    monkeypatch.setattr(ai_provider, "complete", fake)
    asyncio.run(law_ai_agent_jobs.process_one(jid))
    assert called == [("model-step-2", 1536, {})]
    with SessionLocal() as db:
        job = db.get(LawAiAnalysis, jid)
        assert job.status == "done", job.failure
        assert json.loads(job.selected_tasks_json) == ["law_metadata"]
        assert job.quality_profile == "local_24b"
        assert job.progress_total == job.progress_done == 1
        assert job.outline_json == "{}"
        assert job.verification_json == "{}"
        assert len(json.loads(job.metadata_json)["fields"]) == 1
        draft = db.get(LawAiDraft, did)
        assert draft.accepted_law_id is None
        assert draft.proposed_md == SOURCE
    review = admin.get(f"/laws-assistant/{did}")
    assert "Stammdaten ·" in review.text
    assert "Gliederung · 0" not in review.text
    assert "Texttreue · 0" not in review.text


def test_selected_agent_list_does_not_require_other_configured_profiles(monkeypatch, agent_routes):
    removed = []
    with SessionLocal() as db:
        for task in ("law_structure", "law_verify"):
            profile = db.get(AITaskProfile, task)
            removed.append((task, profile.provider_id, profile.model_id))
            db.delete(profile)
        db.commit()
    try:
        admin = login(*ADMIN)
        did = _draft(admin)
        html = admin.get(f"/laws-assistant/{did}").text
        assert "Modell fehlt" in html
        assert "Nur Stammdaten" in html
        assert _start(admin, did, tasks=["law_metadata"]).status_code == 303
        jid = _claim(did)

        async def fake(provider, messages, *, max_tokens=1024, **kwargs):
            assert provider.model_id == "model-step-2"
            return '{"fields":[]}'
        monkeypatch.setattr(ai_provider, "complete", fake)
        asyncio.run(law_ai_agent_jobs.process_one(jid))
        with SessionLocal() as db:
            assert db.get(LawAiAnalysis, jid).status == "done"
    finally:
        with SessionLocal() as db:
            for task, provider_id, model_id in removed:
                if db.get(AITaskProfile, task) is None:
                    db.add(AITaskProfile(task=task, provider_id=provider_id,
                                         model_id=model_id))
            db.commit()


@pytest.mark.parametrize("tasks", [
    [], ["unknown"], ["law_metadata", "law_metadata"],
])
def test_explicit_invalid_stage_plan_cannot_start_analysis(agent_routes, tasks):
    c = login(*ADMIN)
    did = _draft(c)
    assert _start(c, did, tasks=tasks).status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(LawAiAnalysis.id).where(
            LawAiAnalysis.draft_id == did)) is None


def test_legacy_client_keeps_existing_three_agent_default(agent_routes):
    c = login(*ADMIN)
    did = _draft(c)
    assert _start(c, did, tasks=[], marker=False,
                  quality_profile="standard").status_code == 303
    with SessionLocal() as db:
        job = db.scalar(select(LawAiAnalysis).where(LawAiAnalysis.draft_id == did))
        assert json.loads(job.selected_tasks_json) == list(law_ai_agent_jobs.ALL_TASKS)


def test_local_fulltext_uses_shorter_lossless_sections_and_correct_call_count(monkeypatch, agent_routes):
    source = SOURCE * 460
    standard = law_ai_coverage.sections(source)
    local = law_ai_coverage.sections(source, profile="local_24b")
    assert len(local) > len(standard)
    assert "".join(part.text for part in local) == source
    assert max(len(p.text) for p in local) <= 6000
    c = login(*ADMIN)
    did = _draft(c, source)
    assert _start(c, did, tasks=["law_metadata"], mode="advanced").status_code == 303
    jid = _claim(did)
    calls = []

    async def fake(provider, messages, *, max_tokens=1024, **kwargs):
        calls.append((provider.model_id, max_tokens, _context(messages)))
        return '{"fields":[]}'
    monkeypatch.setattr(ai_provider, "complete", fake)
    asyncio.run(law_ai_agent_jobs.process_one(jid))
    assert len(calls) == len(local)
    assert {model for model, _, _ in calls} == {"model-step-2"}
    assert {max_tokens for _, max_tokens, _ in calls} == {1536}
    assert "".join(text for _, _, text in calls) == source
    with SessionLocal() as db:
        job = db.get(LawAiAnalysis, jid)
        assert job.status == "done", job.failure
        assert job.progress_total == len(local)


def test_json_response_format_is_only_sent_after_explicit_opt_in(monkeypatch, agent_routes):
    admin = login(*ADMIN)
    did = _draft(admin)
    assert _start(admin, did, tasks=["law_metadata"], json_mode=True).status_code == 303
    jid = _claim(did)
    seen = []

    async def fake(provider, messages, *, max_tokens=1024, **kwargs):
        seen.append(kwargs)
        return '{"fields":[]}'
    monkeypatch.setattr(ai_provider, "complete", fake)
    asyncio.run(law_ai_agent_jobs.process_one(jid))
    assert seen == [{"response_format": {"type": "json_object"}}]
    with SessionLocal() as db:
        job = db.get(LawAiAnalysis, jid)
        assert job.status == "done"
        assert job.json_mode is True
