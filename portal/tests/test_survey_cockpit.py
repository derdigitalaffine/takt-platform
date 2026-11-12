"""Manager cockpit: permission boundaries and aggregate-only live/vote data."""
import pytest
from sqlalchemy import select

from app import survey_cockpit
from app.db import (Form, FormResponse, FormShare, LiveAnswer, LiveQuestion,
                    SessionLocal, User, VoteBallot)
from conftest import login, settings
from test_my_surveys import workspace


def test_owner_sees_all_four_survey_engines_but_no_private_content(workspace):
    with SessionLocal() as db:
        db.add(FormResponse(form_id=workspace["form"], source="invite",
                            answers_json='{"secret": "DO_NOT_SHOW_PERSONAL_ANSWER"}',
                            email="private-survey-email@example.org"))
        db.add(VoteBallot(id="report-cockpit-secret-ballot", vote_id=workspace["vote"],
                          receipt="SECRET-RECEIPT", answers_json='{"secret": "DO_NOT_SHOW_BALLOT"}'))
        question = LiveQuestion(poll_id=workspace["live"], title="Live-Anonymität", position=0)
        db.add(question)
        db.flush()
        db.add(LiveAnswer(poll_id=workspace["live"], question_id=question.id,
                          device="DO_NOT_SHOW_DEVICE_HASH",
                          value_json='{"secret": "DO_NOT_SHOW_LIVE_ANSWER"}'))
        db.commit()
        owner = db.scalar(select(User).where(User.email == "admin@example.org"))
        rows = survey_cockpit.collect(db, owner, {"forms", "polls"})
        assert set(r["kind"] for r in rows if r["id"] in workspace.values()) == {
            "form", "poll", "vote", "live"}
        live = next(r for r in rows if r["kind"] == "live" and r["id"] == workspace["live"])
        assert live["answers"] == 1
        assert live["invited"] is None and live["rate"] is None
    c = login("admin@example.org", "admin-passwort-123")
    html = c.get("/teilnahme-cockpit")
    assert html.status_code == 200
    assert html.headers["cache-control"] == "no-store"
    for title in ("Meine Feedbackrunde", "Meine Terminumfrage",
                  "Meine vertrauliche Abstimmung", "Nicht persönlich zurechenbare Live-Umfrage"):
        assert title in html.text
    for forbidden in ("DO_NOT_SHOW_PERSONAL_ANSWER", "DO_NOT_SHOW_BALLOT",
                      "DO_NOT_SHOW_DEVICE_HASH", "DO_NOT_SHOW_LIVE_ANSWER",
                      "SECRET-RECEIPT", "private-survey-email@example.org"):
        assert forbidden not in html.text
    assert "Teilnahme-Cockpit" in c.get("/umfragen").text
    assert "Teilnahme-Cockpit" in c.get("/forms").text


def test_invited_participant_cannot_inspect_manager_cockpit(workspace):
    member = login("my-surveys-member@example.org", "personal-survey-test-123")
    page = member.get("/teilnahme-cockpit")
    assert page.status_code == 200
    for title in ("Meine Feedbackrunde", "Meine Terminumfrage", "Meine vertrauliche Abstimmung"):
        assert title not in page.text
    with SessionLocal() as db:
        user = db.get(User, workspace["member"])
        db.add(FormShare(form_id=workspace["form"], user_id=user.id, level=1))
        db.commit()
    assert "Meine Feedbackrunde" not in member.get("/teilnahme-cockpit").text
    with SessionLocal() as db:
        share = db.scalar(select(FormShare).where(
            FormShare.form_id == workspace["form"], FormShare.user_id == workspace["member"]))
        share.level = 2
        db.commit()
    assert "Meine Feedbackrunde" in member.get("/teilnahme-cockpit").text


def test_cockpit_respects_independent_modules(workspace):
    admin = login("admin@example.org", "admin-passwort-123")
    settings(module_forms="0", module_polls="1")
    page = admin.get("/teilnahme-cockpit")
    assert page.status_code == 200
    assert "Meine Feedbackrunde" not in page.text
    assert "Meine Terminumfrage" in page.text
    settings(module_forms="1", module_polls="0")
    page = admin.get("/teilnahme-cockpit")
    assert page.status_code == 200
    assert "Meine Feedbackrunde" in page.text
    assert "Meine Terminumfrage" not in page.text
    settings(module_forms="0", module_polls="0")
    assert admin.get("/teilnahme-cockpit").status_code == 404
