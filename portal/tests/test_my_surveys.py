"""Personal surveys: status, ACL isolation, modularity and task integration."""
import json

import pytest
from sqlalchemy import select

from app import my_surveys, task_overview
from app.db import (Form, FormInvite, FormResponse, LivePoll, Poll,
                    PollParticipant, SessionLocal, User, Vote, VoteVoter, utcnow)
from app.security import hash_password
from conftest import client, login, settings

PASSWORD = "personal-survey-test-123"
SUFFIX = "my-surveys-20261112"


@pytest.fixture
def workspace():
    settings(module_forms="1", module_polls="1")
    with SessionLocal() as db:
        member = User(name="Personal Survey Member", email="my-surveys-member@example.org",
                      password_hash=hash_password(PASSWORD), permissions="",
                      active=True, must_change_password=False)
        outsider = User(name="Personal Survey Outsider", email="my-surveys-outsider@example.org",
                       password_hash=hash_password(PASSWORD), permissions="",
                       active=True, must_change_password=False)
        db.add_all([member, outsider])
        db.flush()
        form = Form(owner_id=1, title="Meine Feedbackrunde", active=True, anonymous=False,
                    public_token=SUFFIX + "-form", kind="survey",
                    notify=False, schema_json="[]")
        poll = Poll(owner_id=1, title="Meine Terminumfrage", public_token=SUFFIX + "-poll",
                    published_at=utcnow(), closed=False)
        vote = Vote(owner_id=1, title="Meine vertrauliche Abstimmung", status="open",
                    secrecy="secret", access="invite", public_token=SUFFIX + "-vote")
        live = LivePoll(owner_id=1, title="Nicht persönlich zurechenbare Live-Umfrage",
                        public_token=SUFFIX + "-live", status="open")
        db.add_all([form, poll, vote, live])
        db.flush()
        invite = FormInvite(form_id=form.id, email=member.email, user_id=member.id,
                            name=member.name, token=SUFFIX + "-inv", invited_at=utcnow())
        attendee = PollParticipant(poll_id=poll.id, user_id=member.id, email=member.email,
                                   name=member.name, edit_token=SUFFIX + "-attendance",
                                   invited_at=utcnow())
        voter = VoteVoter(vote_id=vote.id, user_id=member.id, email=member.email,
                          name=member.name, token=SUFFIX + "-voter", source="invite",
                          confirmed=True, voted=False)
        db.add_all([invite, attendee, voter])
        db.commit()
        ids = dict(member=member.id, outsider=outsider.id, form=form.id,
                   poll=poll.id, vote=vote.id, live=live.id)
    yield ids
    settings(module_forms="1", module_polls="1")
    with SessionLocal() as db:
        for model, key in [(Form, "form"), (Poll, "poll"), (Vote, "vote"), (LivePoll, "live"),
                           (User, "member"), (User, "outsider")]:
            row = db.get(model, ids[key])
            if row:
                db.delete(row)
        db.commit()


def _logged_in():
    return login("my-surveys-member@example.org", PASSWORD)


def test_personal_workspace_lists_authorized_open_participations_and_live_stays_anonymous(workspace):
    c = _logged_in()
    page = c.get("/meine-umfragen")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    for phrase in ("Meine Feedbackrunde", "Meine Terminumfrage",
                   "Meine vertrauliche Abstimmung", "Frist", "Meine Umfragen"):
        if phrase != "Frist":
            assert phrase in page.text
    assert "Nicht persönlich zurechenbare Live-Umfrage" not in page.text
    assert "/f/i/" + SUFFIX + "-inv" in page.text
    assert "/t/p/" + SUFFIX + "-attendance" in page.text
    assert "/v/p/" + SUFFIX + "-voter" in page.text
    assert "Live-Umfragen über QR-Code" in page.text
    assert "keine Einsicht in den Stimmzettel" in page.text
    assert "answers_json" not in page.text
    assert "/meine-umfragen" in c.get("/").text
    tasks = c.get("/tasks")
    assert tasks.status_code == 200
    for title in ("Meine Feedbackrunde", "Meine Terminumfrage",
                  "Meine vertrauliche Abstimmung"):
        assert title in tasks.text
    with SessionLocal() as db:
        row = db.get(User, workspace["member"])
        view = task_overview.collect(db, row, {"forms", "polls"})
        assert [task["source"] for task in view["ready"]] == ["survey"] * 3
        assert view["count"] == 3
        assert view["available"] is True


def test_completed_participations_leave_tasks_but_remain_in_history(workspace):
    with SessionLocal() as db:
        db.add(FormResponse(form_id=workspace["form"], user_id=workspace["member"],
                            source="user", answers_json=json.dumps({"confidential": "do not render"})))
        attendee = db.scalar(select(PollParticipant).where(
            PollParticipant.poll_id == workspace["poll"]))
        attendee.answered_at = utcnow()
        voter = db.scalar(select(VoteVoter).where(VoteVoter.vote_id == workspace["vote"]))
        voter.voted = True
        db.commit()
    c = _logged_in()
    page = c.get("/meine-umfragen")
    assert page.status_code == 200
    assert "do not render" not in page.text
    assert "Abgeschlossen" in page.text
    assert "Stimme ändern" not in page.text  # secret ballot must remain immutable
    assert "Teilnahmestatus ansehen" in page.text
    with SessionLocal() as db:
        member = db.get(User, workspace["member"])
        entries = my_surveys.collect(db, member, {"forms", "polls"})
        assert len(entries) == 3
        assert all(e["status"] == "done" for e in entries)
        assert task_overview.collect(db, member, {"forms", "polls"})["count"] == 0
    assert "Meine Feedbackrunde" in c.get("/meine-umfragen?status=done").text
    assert "Meine Feedbackrunde" not in c.get("/meine-umfragen?status=open").text


def test_private_participations_do_not_leak_to_other_users_or_public_signups(workspace):
    with SessionLocal() as db:
        owner = db.get(User, workspace["member"])
        db.add(PollParticipant(poll_id=workspace["poll"], user_id=None,
                               name="Fake public answer", email=owner.email,
                               edit_token=SUFFIX + "-spoof-poll", invited_at=None))
        db.add(VoteVoter(vote_id=workspace["vote"], user_id=None, email=owner.email,
                         source="public", confirmed=True, token=SUFFIX + "-spoof-vote"))
        db.commit()
        entries = my_surveys.collect(db, owner, {"forms", "polls"})
        assert len(entries) == 3
    other = login("my-surveys-outsider@example.org", PASSWORD)
    page = other.get("/meine-umfragen")
    assert page.status_code == 200
    assert "Meine Feedbackrunde" not in page.text
    assert SUFFIX + "-inv" not in page.text
    assert SUFFIX + "-attendance" not in page.text
    assert SUFFIX + "-voter" not in page.text


def test_modules_independent_and_no_private_content_when_disabled(workspace):
    c = _logged_in()
    settings(module_forms="0", module_polls="1")
    page = c.get("/meine-umfragen")
    assert page.status_code == 200
    assert "Meine Feedbackrunde" not in page.text
    assert "Meine Terminumfrage" in page.text
    assert "/meine-umfragen" in c.get("/").text
    settings(module_forms="1", module_polls="0")
    page = c.get("/meine-umfragen")
    assert page.status_code == 200
    assert "Meine Feedbackrunde" in page.text
    assert "Meine vertrauliche Abstimmung" not in page.text
    settings(module_forms="0", module_polls="0")
    assert c.get("/meine-umfragen").status_code == 404
    assert "/meine-umfragen" not in c.get("/").text


def test_anonymous_invitation_shows_status_but_never_fetches_personal_answer(workspace):
    with SessionLocal() as db:
        form = db.get(Form, workspace["form"])
        form.anonymous = True
        invitation = db.scalar(select(FormInvite).where(FormInvite.form_id == form.id))
        invitation.submitted_at = utcnow()
        db.add(FormResponse(form_id=form.id, source="invite", user_id=None,
                            email="", answers_json='{"secret": "do not reveal"}'))
        db.commit()
    c = _logged_in()
    page = c.get("/meine-umfragen")
    assert page.status_code == 200
    assert "Meine Feedbackrunde" in page.text
    assert "Anonyme Teilnahme" in page.text
    assert "do not reveal" not in page.text
    with SessionLocal() as db:
        member = db.get(User, workspace["member"])
        entries = my_surveys.collect(db, member, {"forms", "polls"})
        form_entry = next(e for e in entries if e["kind"] == "form")
        assert form_entry["status"] == "done"
        assert not form_entry["url"]
