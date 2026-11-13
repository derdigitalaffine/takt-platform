"""Private and source-version-checked printable agent report."""
import json
import re

from sqlalchemy import select
from app import law_ai_agents
from app.db import LawText, SessionLocal, User
from app.law_ai_models import LawAiDraft
from app.law_ai_agent_models import LawAiAnalysis
from app.security import hash_password
from conftest import csrf_of, login, settings

ADMIN = ("admin@example.org", "admin-passwort-123")
SOURCE = b"# Polizeiverordnung\n\n\xc2\xa7 1 Text.\nZahl: 10 EUR.\n"


def _report_fixture():
    settings(module_laws="1", module_ai="1")
    c = login(*ADMIN)
    csrf = csrf_of(c.get("/laws-assistant").text)
    upload = c.post("/laws-assistant/import", data={"csrf": csrf},
                    files={"file": ("bericht.md", SOURCE, "text/markdown")})
    assert upload.status_code == 303
    did = int(re.search(r"/laws-assistant/(\d+)", upload.headers["location"]).group(1))
    with SessionLocal() as db:
        draft = db.get(LawAiDraft, did)
        job = LawAiAnalysis(
            draft_id=did, requested_by=draft.owner_id, source_chars=len(draft.proposed_md),
            source_sha256=law_ai_agents.source_hash(draft.proposed_md),
            mode="advanced", status="done", step="done",
            provider_map_json=json.dumps({
                "law_structure": {"name": "Intern", "model_id": "model-1"},
                "law_metadata": {"name": "Intern", "model_id": "model-2"},
                "law_verify": {"name": "Intern", "model_id": "model-3"},
            }),
            outline_json=json.dumps({"headings": [{
                "quote": "§ 1 Text", "level": 2, "markdown_suggestion": "## § 1 Text",
                "source_start": 21, "source_end": 29,
            }]}),
            metadata_json=json.dumps({"fields": [{
                "field": "title", "value": "<script>alert(1)</script>",
                "evidence": "§ 1 Text", "source_start": 21, "source_end": 29,
            }]}),
            verification_json=json.dumps({
                "findings": [{"severity": "high", "quote": "10 EUR",
                              "reason": "Betrag mit Original abgleichen",
                              "suggestion": "Manuell gegenlesen",
                              "source_start": 38, "source_end": 44}],
                "coverage": {"mode": "full_text_submitted",
                             "sections_analyzed": 1, "sections_total": 1,
                             "source_chars": len(draft.proposed_md)},
            }),
        )
        db.add(job)
        db.commit()
        return c, did, job.id


def test_printable_agent_report_has_source_provenance_and_no_script_execution():
    c, did, jid = _report_fixture()
    report = c.get(f"/laws-assistant/{did}/agents/{jid}/report")
    assert report.status_code == 200, report.text
    assert report.headers["cache-control"] == "private, no-store"
    assert report.headers["x-robots-tag"] == "noindex, nofollow"
    assert "KI-Prüfprotokoll" in report.text
    assert "Original SHA-256" in report.text
    assert "Importtext SHA-256" in report.text
    assert "model-1" in report.text and "model-3" in report.text
    assert "Betrag mit Original abgleichen" in report.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report.text
    assert "<script>alert(1)</script>" not in report.text
    assert 'data-law-report-print' in report.text
    assert "/static/law-ai-report.js" in report.text
    assert "kein amtlicher Rechtstext" in report.text.lower()
    page = c.get(f"/laws-assistant/{did}")
    assert f"/laws-assistant/{did}/agents/{jid}/report" in page.text
    with SessionLocal() as db:
        assert db.get(LawAiDraft, did).accepted_law_id is None


def test_reports_require_owner_completed_job_and_matching_source():
    c, did, jid = _report_fixture()
    with SessionLocal() as db:
        other = db.scalar(select(User).where(User.email == "law-report-other@example.org"))
        if other is None:
            other = User(email="law-report-other@example.org", name="Other viewer",
                         password_hash=hash_password("report-view-pass"),
                         permissions="laws,ai_chat", active=True,
                         must_change_password=False)
            db.add(other)
        other.permissions, other.active, other.must_change_password = "laws,ai_chat", True, False
        db.commit()
    user = login("law-report-other@example.org", "report-view-pass")
    assert user.get(f"/laws-assistant/{did}/agents/{jid}/report").status_code == 404
    assert c.get(f"/laws-assistant/{did}/agents/{jid+1000}/report").status_code == 404
    with SessionLocal() as db:
        job = db.get(LawAiAnalysis, jid)
        job.status = "failed"
        db.commit()
    assert c.get(f"/laws-assistant/{did}/agents/{jid}/report").status_code == 409
    with SessionLocal() as db:
        job = db.get(LawAiAnalysis, jid)
        job.status = "done"
        db.get(LawAiDraft, did).proposed_md = "# Neue OCR-Quelle"
        db.commit()
    assert c.get(f"/laws-assistant/{did}/agents/{jid}/report").status_code == 409


def test_report_never_writes_law_or_edits_working_copy():
    c, did, jid = _report_fixture()
    with SessionLocal() as db:
        before = db.get(LawAiDraft, did).proposed_md
    for _ in range(2):
        response = c.get(f"/laws-assistant/{did}/agents/{jid}/report")
        assert response.status_code == 200
    with SessionLocal() as db:
        row = db.get(LawAiDraft, did)
        assert row.proposed_md == before
        assert row.accepted_law_id is None
        assert db.scalar(select(LawText).where(LawText.title == "Polizeiverordnung")) is None
