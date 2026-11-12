"""Public appointment participation: durable receipt, own answers, ICS and dedupe."""
import json
import pytest
from sqlalchemy import func, select

from app.db import Poll, PollOption, PollParticipant, SessionLocal, User, utcnow
from conftest import csrf_of, login, settings

TOKEN = "persistent-poll-receipt-20261112"


@pytest.fixture
def appointment():
    settings(module_polls="1")
    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == "admin@example.org"))
        poll = Poll(owner_id=owner.id, title="Terminbestätigung Test",
                    public_token=TOKEN, published_at=utcnow(), closed=False,
                    hidden=True)
        db.add(poll)
        db.flush()
        option = PollOption(poll_id=poll.id, starts_at=utcnow(), note="Teamtag")
        db.add(option)
        db.commit()
        ids = (poll.id, option.id)
    yield ids
    with SessionLocal() as db:
        row = db.get(Poll, ids[0])
        if row:
            db.delete(row)
            db.commit()


def _submit(c, url, choice):
    page = c.get(url)
    assert page.status_code == 200
    return c.post(url, data={"csrf": csrf_of(page.text),
                             "name": "Tester", "o_" + str(choice): "yes"})


def test_public_vote_has_durable_success_and_own_results_after_closing(appointment):
    poll_id, option_id = appointment
    user = login("admin@example.org", "admin-passwort-123")
    res = _submit(user, f"/t/{TOKEN}", option_id)
    assert res.status_code in (302, 303)
    private = res.headers["location"]
    assert private.startswith("/t/p/")
    page = user.get(private)
    assert page.status_code == 200
    assert "Deine Teilnahme wurde gespeichert." in page.text
    assert "Deine gespeicherten Terminwünsche" in page.text
    assert "Teamtag" in page.text
    assert "Link kopieren" in page.text
    assert "/meine-umfragen" in page.text
    with SessionLocal() as db:
        poll = db.get(Poll, poll_id)
        assert len([p for p in poll.participants if p.answered_at]) == 1
        poll.closed = True
        poll.final_option_id = option_id
        db.commit()
    after = user.get(private)
    assert after.status_code == 200
    assert "Die Teilnahme ist abgeschlossen und bleibt hier einsehbar" in after.text
    assert "In Kalender übernehmen" in after.text
    assert "Deine gespeicherten Terminwünsche" in after.text
    url = private + "/termin.ics"
    ics = user.get(url)
    assert ics.status_code == 200
    assert "text/calendar" in ics.headers["content-type"]
    assert ics.headers["cache-control"] == "private, no-store"
    assert "BEGIN:VCALENDAR" in ics.text
    assert "Terminbestätigung Test" in ics.text


def test_account_revisiting_public_link_without_cookie_cannot_duplicate_response(appointment):
    poll_id, opt = appointment
    user = login("admin@example.org", "admin-passwort-123")
    first = _submit(user, f"/t/{TOKEN}", opt)
    assert first.status_code in (302, 303)
    fresh_browser = login("admin@example.org", "admin-passwort-123")
    seen = fresh_browser.get(f"/t/{TOKEN}")
    assert seen.status_code == 303
    assert seen.headers["location"].startswith("/t/p/")
    personal = fresh_browser.get(seen.headers["location"])
    assert personal.status_code == 200
    assert "Deine Teilnahme wurde gespeichert" in personal.text
    post = fresh_browser.post(f"/t/{TOKEN}", data={
        "csrf": csrf_of(personal.text), "name": "Tester", "o_" + str(opt): "no"})
    assert post.status_code in (302, 303)
    with SessionLocal() as db:
        count = db.scalar(select(func.count(PollParticipant.id)).where(
            PollParticipant.poll_id == poll_id))
        person = db.scalar(select(PollParticipant).where(
            PollParticipant.poll_id == poll_id))
        assert count == 1
        assert person.answers[str(opt)] == "no"


def test_calendar_only_exists_for_personal_completed_poll_with_final_option(appointment):
    poll_id, option_id = appointment
    user = login("admin@example.org", "admin-passwort-123")
    assert user.get("/t/p/invalid-private-token/termin.ics").status_code == 404
    private = _submit(user, f"/t/{TOKEN}", option_id).headers["location"]
    assert user.get(private + "/termin.ics").status_code == 404
