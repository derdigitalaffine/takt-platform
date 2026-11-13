"""Safe technical text comparison: permissions, anti-XSS and no publication."""
import re

from app import law_ai_editorial_diff
from app.db import LawText, SessionLocal, User
from app.law_ai_models import LawAiDraft
from app.security import hash_password
from conftest import csrf_of, login, settings
from sqlalchemy import select

ADMIN = ("admin@example.org", "admin-passwort-123")
SOURCE = b"# Satzung\n\nDer Betrag ist 10 EUR.\nDie Frist betraegt 14 Tage.\n"


def _draft(c):
    csrf = csrf_of(c.get("/laws-assistant").text)
    upload = c.post("/laws-assistant/import", data={"csrf": csrf},
                    files={"file": ("diff.md", SOURCE, "text/markdown")})
    assert upload.status_code == 303
    return int(re.search(r"/laws-assistant/(\d+)", upload.headers["location"]).group(1))


def test_bounded_diff_marks_amount_deadline_and_negation_changes():
    result = law_ai_editorial_diff.compare(
        "§ 1 Der Betrag ist 10 EUR.\nEs gilt keine Ausnahme.\n",
        "§ 1 Der Betrag ist 20 EUR.\nEs gilt eine Ausnahme.\n",
    )
    assert result["same"] is False
    assert result["preview_available"] is True
    assert result["added_lines"] >= 1 and result["removed_lines"] >= 1
    assert "Zahlen und Beträge" in result["sensitive_categories"]
    assert "Verneinungen" in result["sensitive_categories"]
    assert all(row["kind"] in {"add", "remove", "context", "meta"} for row in result["lines"])
    assert law_ai_editorial_diff.compare("identisch", "identisch")["same"] is True


def test_diff_safe_caps_never_claim_full_evidence_on_large_documents():
    text = "§ 1 Auszug\n" * 14000
    result = law_ai_editorial_diff.compare(text, text + "Änderung")
    assert result["preview_available"] is False
    assert result["same"] is False
    assert len(result["lines"]) == 0
    assert "amtlichen Original" not in result["note"] or isinstance(result["note"], str)


def test_review_diff_uses_imported_text_not_saved_text_and_never_publishes():
    settings(module_laws="1", module_ai="0")
    c = login(*ADMIN)
    did = _draft(c)
    csrf = csrf_of(c.get(f"/laws-assistant/{did}").text)
    comparison = c.post(f"/laws-assistant/{did}/compare", data={
        "csrf": csrf,
        "body_md": SOURCE.decode().replace("10 EUR", "20 EUR"),
    })
    assert comparison.status_code == 200, comparison.text
    assert comparison.headers["cache-control"] == "private, no-store"
    assert comparison.json()["added_lines"] >= 1
    assert "Zahlen und Beträge" in comparison.json()["sensitive_categories"]
    assert "diff.md" not in comparison.text
    page = c.get(f"/laws-assistant/{did}")
    assert 'data-law-diff-button' in page.text
    assert 'data-law-diff-panel' in page.text
    with SessionLocal() as db:
        row = db.get(LawAiDraft, did)
        assert row.proposed_md == SOURCE.decode()
        assert row.accepted_law_id is None
        assert db.scalar(select(LawText).where(LawText.title == "diff.md")) is None


def test_owner_csrf_and_oversize_are_enforced_for_comparison():
    settings(module_laws="1", module_ai="0")
    c = login(*ADMIN)
    did = _draft(c)
    assert c.post(f"/laws-assistant/{did}/compare", data={
        "csrf": "bad", "body_md": "bad"
    }).status_code == 400
    csrf = csrf_of(c.get(f"/laws-assistant/{did}").text)
    assert c.post(f"/laws-assistant/{did}/compare", data={
        "csrf": csrf, "body_md": "X" * (2 * 1024 * 1024 + 1),
    }).status_code == 413
    with SessionLocal() as db:
        other = db.scalar(select(User).where(User.email == "law-diff-other@example.org"))
        if other is None:
            other = User(email="law-diff-other@example.org", name="Another reviewer",
                         password_hash=hash_password("diff-user-pass"),
                         permissions="laws", active=True, must_change_password=False)
            db.add(other)
        other.permissions, other.active, other.must_change_password = "laws", True, False
        db.commit()
    other = login("law-diff-other@example.org", "diff-user-pass")
    other_csrf = csrf_of(other.get("/laws-assistant").text)
    forbidden = other.post(f"/laws-assistant/{did}/compare", data={
        "csrf": other_csrf, "body_md": SOURCE.decode(),
    })
    assert forbidden.status_code == 404
