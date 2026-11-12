"""Regression: answered surveys must not invite duplicate submissions.

Live polls (/l/) use their own device/question protocol and remain untouched.
"""
import json

import pytest
from sqlalchemy import func, select

from app import forms as fm, home
from app.db import Form, FormInvite, FormResponse, SessionLocal, User
from conftest import client, csrf_of, login, settings

TOKEN = "survey-participation-public-20261112"
INVITE_TOKEN = "survey-participation-personal-20261112"


@pytest.fixture
def survey():
    settings(module_forms="1")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        form = Form(
            owner_id=user.id, title="Test Teilnahmeerkennung", kind="survey",
            active=True, multiple=False, anonymous=False, notify=False,
            public_token=TOKEN,
            schema_json=json.dumps(fm.clean_schema([
                {"id": "feedback", "type": "short", "title": "Deine Antwort", "required": True}
            ])),
        )
        db.add(form)
        db.flush()
        invite = FormInvite(
            form_id=form.id, user_id=user.id, name=user.name,
            email=user.email, token=INVITE_TOKEN,
        )
        db.add(invite)
        db.commit()
        fid = form.id
    yield fid
    with SessionLocal() as db:
        form = db.get(Form, fid)
        if form:
            db.delete(form)
            db.commit()


def _count(fid):
    with SessionLocal() as db:
        return db.scalar(select(func.count(FormResponse.id)).where(FormResponse.form_id == fid))


def _post(c, path, value="Ja"):
    page = c.get(path)
    assert page.status_code == 200
    token = csrf_of(page.text)
    return c.post(path, data={"csrf": token, "q_feedback": value})


def test_logged_in_public_submission_marks_invitation_and_prevents_repeat(survey):
    c = login("admin@example.org", "admin-passwort-123")
    assert 'id="fill-form"' in c.get(f"/f/{TOKEN}").text
    result = _post(c, f"/f/{TOKEN}")
    assert result.status_code == 200 and "gespeichert" in result.text
    assert _count(survey) == 1
    with SessionLocal() as db:
        inv = db.scalar(select(FormInvite).where(FormInvite.form_id == survey))
        assert inv.submitted_at is not None
        assert db.scalar(select(FormResponse.user_id).where(FormResponse.form_id == survey)) == inv.user_id
        assert home._inbox(db, db.get(User, inv.user_id))["count"] == 0
    assert "bereits ausgefüllt" in c.get(f"/f/{TOKEN}").text
    assert "bereits ausgefüllt" in c.get(f"/f/i/{INVITE_TOKEN}").text
    assert "ausgefüllt" in c.get("/forms/inbox").text
    assert _post(c, f"/f/{TOKEN}", "Nein").status_code == 200
    assert _count(survey) == 1


def test_preexisting_response_is_recognized_without_new_invite_marker(survey):
    with SessionLocal() as db:
        inv = db.scalar(select(FormInvite).where(FormInvite.form_id == survey))
        db.add(FormResponse(form_id=survey, user_id=inv.user_id,
                            source="user", answers_json='{"feedback":"alt"}'))
        db.commit()
        assert inv.submitted_at is None
        assert home._inbox(db, db.get(User, inv.user_id))["count"] == 0
    c = login("admin@example.org", "admin-passwort-123")
    assert "ausgefüllt" in c.get("/forms/inbox").text
    assert "bereits ausgefüllt" in c.get(f"/f/i/{INVITE_TOKEN}").text
    assert _post(c, f"/f/{TOKEN}").status_code == 200
    assert _count(survey) == 1


def test_guest_browser_receipt_and_fresh_browser(survey):
    guest = client()
    assert _post(guest, f"/f/{TOKEN}").status_code == 200
    assert _count(survey) == 1
    done = guest.get(f"/f/{TOKEN}")
    assert "Über diesen Browser wurde bereits" in done.text
    assert _post(guest, f"/f/{TOKEN}").status_code == 200
    assert _count(survey) == 1
    # Anonymous access cannot prove that a different browser is the same person.
    other = client()
    assert 'id="fill-form"' in other.get(f"/f/{TOKEN}").text


def test_repeated_answers_remain_available_when_explicitly_enabled(survey):
    with SessionLocal() as db:
        db.get(Form, survey).multiple = True
        db.commit()
    c = login("admin@example.org", "admin-passwort-123")
    assert _post(c, f"/f/{TOKEN}", "Erste").status_code == 200
    page = c.get(f"/f/{TOKEN}")
    assert "Bereits teilgenommen" in page.text
    assert "zusätzliche Antwort" in page.text
    assert _post(c, f"/f/{TOKEN}", "Zweite").status_code == 200
    assert _count(survey) == 2


def test_anonymous_submission_does_not_reidentify_responses(survey):
    with SessionLocal() as db:
        db.get(Form, survey).anonymous = True
        db.commit()
    c = login("admin@example.org", "admin-passwort-123")
    assert _post(c, f"/f/{TOKEN}").status_code == 200
    assert "Über diesen Browser wurde bereits" in c.get(f"/f/{TOKEN}").text
    with SessionLocal() as db:
        resp = db.scalar(select(FormResponse).where(FormResponse.form_id == survey))
        inv = db.scalar(select(FormInvite).where(FormInvite.form_id == survey))
        assert resp.user_id is None and not resp.email and not resp.name
        assert inv.submitted_at is None  # cannot infer a personal answer from a public anonymous submission
    # A separate personal invite is not retrospectively linked to the anonymous answer.
    assert 'id="fill-form"' in c.get(f"/f/i/{INVITE_TOKEN}").text


def test_online_application_remains_repeatable_even_with_prior_response(survey):
    with SessionLocal() as db:
        form = db.get(Form, survey)
        form.kind = "application"
        inv = db.scalar(select(FormInvite).where(FormInvite.form_id == survey))
        db.add(FormResponse(form_id=survey, user_id=inv.user_id, source="user",
                            answers_json='{"feedback":"vorher"}'))
        db.commit()
    c = login("admin@example.org", "admin-passwort-123")
    assert 'id="fill-form"' in c.get(f"/f/{TOKEN}").text


def test_completed_surveys_remain_recognizable_after_they_close(survey):
    user = login("admin@example.org", "admin-passwort-123")
    assert _post(user, f"/f/{TOKEN}").status_code == 200
    with SessionLocal() as db:
        db.get(Form, survey).active = False
        db.commit()
    for url in (f"/f/{TOKEN}", f"/f/i/{INVITE_TOKEN}"):
        page = user.get(url)
        assert page.status_code == 200
        assert "bereits ausgefüllt" in page.text
        assert "ausgefüllt" in page.text
        assert "noch einmal" not in page.text
    post = user.post(f"/f/{TOKEN}", data={"csrf": csrf_of(user.get(f"/f/{TOKEN}").text)})
    assert post.status_code == 200
    assert _count(survey) == 1


def test_guest_receipt_after_closing_and_fresh_guest_still_gets_closed_page(survey):
    guest = client()
    assert _post(guest, f"/f/{TOKEN}").status_code == 200
    with SessionLocal() as db:
        db.get(Form, survey).active = False
        db.commit()
    done = guest.get(f"/f/{TOKEN}")
    assert done.status_code == 200
    assert "Über diesen Browser wurde bereits" in done.text
    other = client()
    closed = other.get(f"/f/{TOKEN}")
    assert closed.status_code == 200
    assert "nimmt keine Antworten mehr an" in closed.text
    assert _count(survey) == 1


def test_expired_survey_with_multiple_allowed_still_shows_receipt(survey):
    with SessionLocal() as db:
        form = db.get(Form, survey)
        form.multiple = True
        db.commit()
    user = login("admin@example.org", "admin-passwort-123")
    assert _post(user, f"/f/{TOKEN}").status_code == 200
    with SessionLocal() as db:
        db.get(Form, survey).active = False
        db.commit()
    page = user.get(f"/f/{TOKEN}")
    assert page.status_code == 200
    assert "bereits ausgefüllt" in page.text
    assert "id=\"fill-form\"" not in page.text
