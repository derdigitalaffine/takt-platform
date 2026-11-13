"""Ortsrecht intake: immutable originals, owner isolation, human-only drafts."""
import hashlib
import re

from sqlalchemy import select

from app.db import LawText, SessionLocal, User
from app.law_ai_models import LawAiDraft
from app.security import hash_password
from conftest import csrf_of, login, settings

ADMIN = ("admin@example.org", "admin-passwort-123")
SAMPLE = b"# Hausordnung Testort\\n\\n### \xc2\xa7 1 Allgemeines\\n\\nDiese Hausordnung ist ein Test.\\n"


def _upload(c, *, name="import-test.md", content=SAMPLE):
    csrf = csrf_of(c.get("/laws-assistant").text)
    return c.post(
        "/laws-assistant/import", data={"csrf": csrf},
        files={"file": (name, content, "application/octet-stream")},
    )


def _draft_id(response):
    assert response.status_code == 303, response.text
    match = re.search(r"/laws-assistant/(\d+)", response.headers["location"])
    assert match is not None, response.headers["location"]
    return int(match.group(1))


def test_staged_markdown_requires_explicit_review_and_never_publishes():
    settings(module_laws="1", module_ai="0")
    c = login(*ADMIN)
    imported = _upload(c, name="hausordnung.md")
    did = _draft_id(imported)
    csrf = csrf_of(c.get(f"/laws-assistant/{did}").text)
    with SessionLocal() as db:
        draft = db.get(LawAiDraft, did)
        assert draft.owner_id
        assert draft.status == "staged"
        assert draft.accepted_law_id is None
        assert draft.original_sha256 == hashlib.sha256(SAMPLE).hexdigest()
        assert draft.proposed_md == SAMPLE.decode()
    original = c.get(f"/laws-assistant/{did}/original")
    assert original.status_code == 200
    assert original.content == SAMPLE
    assert "attachment" in original.headers["content-disposition"]
    assert original.headers["x-content-type-options"] == "nosniff"
    assert original.headers["cache-control"] == "private, no-store"
    post = {
        "csrf": csrf, "title": "Geprüfte Hausordnung",
        "doc_type": "satzung", "body_md": SAMPLE.decode(),
    }
    assert c.post(f"/laws-assistant/{did}/accept", data=post).status_code == 422
    assert c.post(f"/laws-assistant/{did}/accept",
                  data={**post, "confirmed": "1", "doc_type": "unknown"}).status_code == 422
    confirmed = c.post(f"/laws-assistant/{did}/accept",
                       data={**post, "confirmed": "1"})
    assert confirmed.status_code == 303, confirmed.text
    assert "/laws/" in confirmed.headers["location"]
    with SessionLocal() as db:
        draft = db.get(LawAiDraft, did)
        law = db.get(LawText, draft.accepted_law_id)
        assert draft.status == "accepted"
        assert draft.accepted_at is not None
        assert law.title == "Geprüfte Hausordnung"
        assert law.published is False
        assert law.planned_md == ""
        assert law.body_md == SAMPLE.decode()
    assert c.post(f"/laws-assistant/{did}/accept",
                  data={**post, "confirmed": "1"}).status_code == 409
    assert c.get(f"/laws-assistant/{did}/original").content == SAMPLE
    assert c.post(f"/laws-assistant/{did}/discard", data={
        "csrf": csrf, "discard_confirmed": "1",
    }).status_code == 409


def test_binary_files_are_only_staged_not_processed_in_web_worker():
    settings(module_laws="1")
    c = login(*ADMIN)
    imported = _upload(c, name="historischer-scan.pdf", content=b"%PDF-1.5\nnot parsed by portal")
    did = _draft_id(imported)
    with SessionLocal() as db:
        draft = db.get(LawAiDraft, did)
        assert draft.status == "needs_ocr"
        assert draft.proposed_md == ""
        assert draft.original_mime == "application/pdf"
    csrf = csrf_of(c.get("/laws-assistant").text)
    assert c.post(f"/laws-assistant/{did}/accept", data={
        "csrf": csrf, "title": "Scan", "body_md": "",
        "doc_type": "satzung", "confirmed": "1",
    }).status_code == 422
    assert c.get(f"/laws-assistant/{did}").status_code == 200
    assert c.post(f"/laws-assistant/{did}/discard", data={
        "csrf": csrf,
    }).status_code == 422
    discarded = c.post(f"/laws-assistant/{did}/discard", data={
        "csrf": csrf, "discard_confirmed": "1",
    })
    assert discarded.status_code == 303
    assert c.get(f"/laws-assistant/{did}").status_code == 404
    assert c.get(f"/laws-assistant/{did}/original").status_code == 404
    assert _upload(c, name="spoof.pdf", content=b"this is not a pdf").status_code == 415


def test_private_imports_do_not_cross_users_or_public_routes():
    settings(module_laws="1")
    c = login(*ADMIN)
    did = _draft_id(_upload(c, name="owner-private.md"))
    with SessionLocal() as db:
        person = db.scalar(select(User).where(
            User.email == "law-ai-editor@example.org"))
        if person is None:
            person = User(email="law-ai-editor@example.org", name="Law editor",
                          password_hash=hash_password("law-ai-password"),
                          permissions="laws", must_change_password=False,
                          active=True)
            db.add(person)
        person.permissions = "laws"
        person.active = True
        person.must_change_password = False
        db.commit()
    other = login("law-ai-editor@example.org", "law-ai-password")
    csrf = csrf_of(other.get("/laws-assistant").text)
    assert other.get(f"/laws-assistant/{did}").status_code == 404
    assert other.get(f"/laws-assistant/{did}/original").status_code == 404
    assert other.post(f"/laws-assistant/{did}/accept", data={
        "csrf": csrf, "title": "Stolen", "body_md": SAMPLE.decode(),
        "confirmed": "1",
    }).status_code == 404
    assert other.post(f"/laws-assistant/{did}/discard", data={
        "csrf": csrf, "discard_confirmed": "1",
    }).status_code == 404
    public = login(*ADMIN)
    csrf_owner = csrf_of(public.get("/laws-assistant").text)
    assert public.post(f"/laws-assistant/{did}/discard", data={
        "csrf": "invalid", "discard_confirmed": "1",
    }).status_code == 400
    assert public.post(f"/laws-assistant/{did}/discard", data={
        "csrf": csrf_owner, "discard_confirmed": "1",
    }).status_code == 303
