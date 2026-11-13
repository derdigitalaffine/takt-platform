"""Privacy and concurrency checks for editable, unpublished Ortsrecht working copies."""
import re

from sqlalchemy import select
from app.db import LawText, SessionLocal, User
from app.law_ai_models import LawAiDraft, LawAiEditorialDraft
from app.security import hash_password
from conftest import csrf_of, login, settings


ADMIN = ("admin@example.org", "admin-passwort-123")
ORIGINAL = b"# Ortssatzung\n\nHier bleibt das Original mit 10 Euro.\n"


def _upload(c):
    csrf = csrf_of(c.get("/laws-assistant").text)
    res = c.post("/laws-assistant/import", data={"csrf": csrf},
                 files={"file": ("version.md", ORIGINAL, "text/markdown")})
    assert res.status_code == 303
    return int(re.search(r"/laws-assistant/(\d+)", res.headers["location"]).group(1))


def _save(c, did, rev=0, body="# Redaktionelle Fassung\n\nBetrag 12 Euro", **fields):
    csrf = csrf_of(c.get(f"/laws-assistant/{did}").text)
    return c.post(f"/laws-assistant/{did}/save-edit", data={
        "csrf": csrf, "revision": str(rev), "title": "Geprüfte Ortssatzung",
        "doc_type": "satzung", "short_title": "OS",
        "body_md": body, **fields,
    })


def test_editorial_save_is_private_versioned_not_a_law():
    settings(module_laws="1", module_ai="0")
    c = login(*ADMIN)
    did = _upload(c)
    first = _save(c, did)
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == 1
    assert first.headers["cache-control"] == "private, no-store"
    page = c.get(f"/laws-assistant/{did}")
    assert 'name="edit_revision" value="1"' in page.text
    assert "Redaktionelle Fassung" in page.text
    assert "Geprüfte Ortssatzung" in page.text
    assert 'data-law-save-button' in page.text
    with SessionLocal() as db:
        original = db.get(LawAiDraft, did)
        edit = db.scalar(select(LawAiEditorialDraft).where(LawAiEditorialDraft.draft_id == did))
        assert original.proposed_md == ORIGINAL.decode()
        assert original.original_sha256
        assert original.accepted_law_id is None
        assert edit.revision == 1
        assert edit.source_sha256
        assert "Redaktionelle Fassung" in edit.body_md

    stale = _save(c, did, rev=0, body="# Überschreiben")
    assert stale.status_code == 409
    assert _save(c, did, rev=1, body="# Letzte Redaktion").json()["revision"] == 2
    with SessionLocal() as db:
        edit = db.scalar(select(LawAiEditorialDraft).where(LawAiEditorialDraft.draft_id == did))
        assert edit.revision == 2
        assert edit.body_md == "# Letzte Redaktion"
        assert db.get(LawAiDraft, did).proposed_md == ORIGINAL.decode()


def test_private_work_copy_only_becomes_unpublished_law_on_explicit_current_accept():
    settings(module_laws="1", module_ai="0")
    c = login(*ADMIN)
    did = _upload(c)
    assert _save(c, did).status_code == 200
    csrf = csrf_of(c.get(f"/laws-assistant/{did}").text)
    post = {
        "csrf": csrf, "title": "Redaktion", "body_md": "# Endgültig korrigiert",
        "confirmed": "1", "doc_type": "satzung",
    }
    assert c.post(f"/laws-assistant/{did}/accept", data={**post, "edit_revision": "0"}).status_code == 409
    accepted = c.post(f"/laws-assistant/{did}/accept",
                      data={**post, "edit_revision": "1"})
    assert accepted.status_code == 303, accepted.text
    with SessionLocal() as db:
        imported = db.get(LawAiDraft, did)
        law = db.get(LawText, imported.accepted_law_id)
        assert law is not None
        assert law.published is False
        assert law.body_md == "# Endgültig korrigiert"
        assert imported.original_sha256
        assert db.get(LawAiEditorialDraft, db.scalar(select(LawAiEditorialDraft.id).where(
            LawAiEditorialDraft.draft_id == did))).revision == 1
    assert _save(c, did, rev=1).status_code == 409


def test_foreign_user_cannot_save_another_editors_work():
    settings(module_laws="1", module_ai="0")
    c = login(*ADMIN)
    did = _upload(c)
    with SessionLocal() as db:
        other = db.scalar(select(User).where(User.email == "law-editorial-other@example.org"))
        if other is None:
            other = User(email="law-editorial-other@example.org", name="Other reviewer",
                         password_hash=hash_password("editor-pass-999"),
                         permissions="laws", active=True, must_change_password=False)
            db.add(other)
        other.permissions, other.active, other.must_change_password = "laws", True, False
        db.commit()
    user = login("law-editorial-other@example.org", "editor-pass-999")
    csrf = csrf_of(user.get("/laws-assistant").text)
    assert user.post(f"/laws-assistant/{did}/save-edit", data={
        "csrf": csrf, "revision": "0", "title": "Private",
        "body_md": "# Wrong owner",
    }).status_code == 404
    assert c.post(f"/laws-assistant/{did}/save-edit", data={
        "csrf": "invalid", "revision": "0", "title": "Bad",
        "body_md": "# Invalid",
    }).status_code == 400
    assert c.get(f"/laws-assistant/{did}").status_code == 200


def test_save_rejects_changed_source_or_invalid_input_without_mutating_source():
    settings(module_laws="1", module_ai="0")
    c = login(*ADMIN)
    did = _upload(c)
    assert _save(c, did).status_code == 200
    assert _save(c, did, rev=1, body="a" * (2 * 1024 * 1024 + 1)).status_code == 422
    with SessionLocal() as db:
        draft = db.get(LawAiDraft, did)
        draft.proposed_md = "# Neue OCR-Fassung"
        db.commit()
    assert _save(c, did, rev=1).status_code == 409
    with SessionLocal() as db:
        saved = db.scalar(select(LawAiEditorialDraft).where(LawAiEditorialDraft.draft_id == did))
        assert saved.revision == 1
        assert "# Redaktionelle Fassung" in saved.body_md
    assert "seit dem letzten gespeicherten Arbeitsstand" in c.get(f"/laws-assistant/{did}").text
