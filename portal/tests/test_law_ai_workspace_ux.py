"""Ortsrecht workbench: navigation, review controls and safe browser UX assets."""
import re

from app.db import LawText, SessionLocal
from conftest import csrf_of, login, settings


ADMIN = ("admin@example.org", "admin-passwort-123")


def _upload(client, name="ux-test.md", data=b"# Satzung\n\nParagraph 1: Test\n"):
    token = csrf_of(client.get("/laws-assistant").text)
    resp = client.post("/laws-assistant/import", data={"csrf": token},
                       files={"file": (name, data, "application/octet-stream")})
    assert resp.status_code == 303, resp.text
    return int(re.search(r"/laws-assistant/(\d+)", resp.headers["location"]).group(1))


def test_ortsrecht_workspace_has_guided_flow_search_and_safe_editor():
    settings(module_laws="1", module_ai="0")
    c = login(*ADMIN)
    did = _upload(c)
    landing = c.get("/laws-assistant")
    assert landing.status_code == 200
    assert "/static/law-ai-workspace.css" in landing.text
    assert "/static/law-ai-workspace.js" in landing.text
    assert 'data-law-drafts-search' in landing.text
    assert 'data-law-drafts-filter' in landing.text
    assert 'data-law-upload-zone' in landing.text
    assert 'data-law-draft-name="ux-test.md"' in landing.text

    page = c.get(f"/laws-assistant/{did}")
    assert page.status_code == 200
    assert "Bearbeitungsschritte" in page.text
    assert "Geschützter Arbeitsbereich" in page.text
    assert "Nächster sinnvoller Schritt" in page.text
    assert 'data-law-review-form' in page.text
    assert 'data-law-editor-count' in page.text
    assert 'data-law-editor-outline' in page.text
    assert 'data-law-editor-dirty' in page.text
    assert 'id="law-ai-body"' in page.text
    assert 'maxlength="2097152" spellcheck="false" required' in page.text
    assert 'name="confirmed"' in page.text
    assert "Import endgültig verwerfen" in page.text
    assert "# Satzung" in page.text
    assert page.headers["cache-control"] == "private, no-store"


def test_uploaded_pdf_workflow_shows_action_without_ai_publication():
    settings(module_laws="1", module_ai="0")
    c = login(*ADMIN)
    did = _upload(c, "scan-2026.pdf", b"%PDF-1.7\nsynthetic test\n")
    page = c.get(f"/laws-assistant/{did}")
    assert page.status_code == 200
    assert "OCR erforderlich" in page.text
    assert "Lokale Texterkennung starten" in page.text
    assert "Original herunterladen" in page.text
    assert 'id="law-ai-body"' in page.text
    # The upload and workbench are advisory; there is no automatic publication.
    with SessionLocal() as db:
        from app.law_ai_models import LawAiDraft
        draft = db.get(LawAiDraft, did)
        assert draft.accepted_law_id is None
        assert draft.status == "needs_ocr"


def test_workspace_assets_only_offer_client_guidance_not_legal_autosave():
    settings(module_laws="1")
    c = login(*ADMIN)
    js = c.get("/static/law-ai-workspace.js")
    assert js.status_code == 200
    assert "LawReviewUX" in js.text
    assert "deferRefresh" in js.text
    assert "beforeunload" in js.text
    assert "localStorage" not in js.text.replace("localStorage/sessionStorage", "")
    assert "textContent" in js.text  # legal text not inserted as raw HTML
    assert c.get("/static/law-ai-workspace.css").status_code == 200
    assert "LawReviewUX?.deferRefresh" in c.get("/static/law-ai-agents.js").text
    assert "LawReviewUX?.deferRefresh" in c.get("/static/law-ai-ocr-progress.js").text
