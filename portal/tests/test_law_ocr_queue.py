"""Ortsrecht OCR queue integration: worker has no DB, web only accepts reviewed drafts."""
import hashlib
import json
import re

from app import routes_law_ai
from app.db import LawText, SessionLocal
from app.law_ai_models import LawAiDraft
from conftest import csrf_of, login, settings

ADMIN = ("admin@example.org", "admin-passwort-123")
SCAN = b"%PDF-1.7\nqueued but never parsed in portal"


def _upload(client):
    csrf = csrf_of(client.get("/laws-assistant").text)
    response = client.post(
        "/laws-assistant/import", data={"csrf": csrf},
        files={"file": ("staged.pdf", SCAN, "application/pdf")},
    )
    assert response.status_code == 303, response.text
    return int(re.search(r"/laws-assistant/(\d+)", response.headers["location"]).group(1))


def _enqueue(client, draft_id):
    csrf = csrf_of(client.get("/laws-assistant").text)
    res = client.post(f"/laws-assistant/{draft_id}/ocr", data={
        "csrf": csrf, "language": "deu",
    })
    assert res.status_code == 303, res.text
    with SessionLocal() as db:
        draft = db.get(LawAiDraft, draft_id)
        assert draft.status == "ocr_queued"
        return draft.ocr_job_key, draft.original_storage_key


def test_ocr_job_to_review_without_automatic_publication(monkeypatch, tmp_path):
    settings(module_laws="1", module_ai="0")
    queue = tmp_path / "queue"
    results = tmp_path / "results"
    monkeypatch.setattr(routes_law_ai, "OCR_QUEUE", queue)
    monkeypatch.setattr(routes_law_ai, "OCR_RESULTS", results)
    admin = login(*ADMIN)
    draft_id = _upload(admin)
    job_key, source_key = _enqueue(admin, draft_id)
    job = json.loads((queue / (job_key + ".job.json")).read_text())
    assert job["storage_key"] == source_key
    assert job["sha256"] == hashlib.sha256(SCAN).hexdigest()
    assert job["language"] == "deu"
    # An OCR worker cannot publish, even with a valid result.
    csrf = csrf_of(admin.get("/laws-assistant").text)
    waiting = admin.post(f"/laws-assistant/{draft_id}/accept", data={
        "csrf": csrf, "title": "Premature law",
        "body_md": "§ 1 Fake", "confirmed": "1",
    })
    assert waiting.status_code == 409
    results.mkdir()
    extraction = {
        "schema": 1, "job_key": job_key, "sha256": job["sha256"],
        "status": "done",
        "markdown": "# Hausordnung\n\n§ 1 Originalbetrag 15 €",
        "pages": [{"page": 1, "engine": "tesseract",
                   "text": "§ 1 Originalbetrag 15 €", "confidence": 62.4,
                   "words": [{"text": "15", "x": 17, "y": 23, "w": 10, "h": 8,
                              "confidence": 62.4}]}],
        "warnings": ["Seite 1: OCR unsicher"],
    }
    (results / (job_key + ".result.json")).write_text(
        json.dumps(extraction, ensure_ascii=False), encoding="utf-8",
    )
    refreshed = admin.get(f"/laws-assistant/{draft_id}/ocr/status")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["ready"] is True
    assert refreshed.json()["status"] == "ocr_review"
    assert not (results / (job_key + ".result.json")).exists()
    with SessionLocal() as db:
        row = db.get(LawAiDraft, draft_id)
        assert row.proposed_md == extraction["markdown"]
        assert row.accepted_law_id is None
        assert json.loads(row.ocr_pages_json)[0]["page"] == 1
    page = admin.get(f"/laws-assistant/{draft_id}")
    assert page.status_code == 200
    assert "MarkItDown" in page.text and "Tesseract" in page.text
    assert "OCR unsicher" in page.text
    assert 'data-law-ocr-pending' not in page.text

    # Human reviewer corrects the draft, explicitly confirms, then the
    # established law system receives an *unpublished* new record.
    csrf = csrf_of(page.text)
    created = admin.post(f"/laws-assistant/{draft_id}/accept", data={
        "csrf": csrf, "title": "Manuell geprüfte Satzung",
        "body_md": "# Satzung\n\n§ 1 Originalbetrag 16 €",
        "doc_type": "satzung", "confirmed": "1",
    })
    assert created.status_code == 303, created.text
    with SessionLocal() as db:
        row = db.get(LawAiDraft, draft_id)
        law = db.get(LawText, row.accepted_law_id)
        assert row.status == "accepted"
        assert law is not None
        assert law.published is False
        assert law.planned_md == ""
        assert "16 €" in law.body_md
    original = admin.get(f"/laws-assistant/{draft_id}/original")
    assert original.content == SCAN


def test_ocr_result_requires_matching_original_checksum(monkeypatch, tmp_path):
    settings(module_laws="1")
    queue, results = tmp_path / "queue", tmp_path / "results"
    monkeypatch.setattr(routes_law_ai, "OCR_QUEUE", queue)
    monkeypatch.setattr(routes_law_ai, "OCR_RESULTS", results)
    admin = login(*ADMIN)
    did = _upload(admin)
    key, _ = _enqueue(admin, did)
    results.mkdir()
    (results / (key + ".result.json")).write_text(json.dumps({
        "schema": 1, "job_key": key, "sha256": "0" * 64,
        "status": "done", "markdown": "# Falsche Fassung",
        "pages": [], "warnings": [],
    }))
    check = admin.get(f"/laws-assistant/{did}/ocr/status")
    assert check.status_code == 502
    with SessionLocal() as db:
        row = db.get(LawAiDraft, did)
        assert row.status == "ocr_queued"
        assert row.proposed_md == ""
        assert row.accepted_law_id is None
