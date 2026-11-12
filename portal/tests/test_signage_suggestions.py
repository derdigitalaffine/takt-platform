"""Upcoming civic-event suggestions must never publish private calendar data."""
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from conftest import client
from test_signage import _admin
from app import signage_suggestions
from app.calendar_models import Calendar, CalendarEvent
from app.db import SessionLocal, User, utcnow
from app.signage_models import SignageBuilding, SignageCampaign, SignageFloor, SignageRoom


def _event(*, title="Gemeinderatssitzung vertrauliche Vorlage",
           starts_in_days=2, source="free", ical_data=""):
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@example.org"))
        calendar = Calendar(owner_id=admin.id, title="Gremien – interner Kalender",
                            source=source, visibility="private")
        db.add(calendar)
        db.flush()
        start = datetime.now(timezone.utc) + timedelta(days=starts_in_days)
        event = CalendarEvent(
            calendar_id=calendar.id,
            uid=f"signage-suggestions-{calendar.id}-{starts_in_days}",
            title=title,
            description="ABSOLUT VERTRAULICHE KALENDERBESCHREIBUNG",
            starts_at=start.isoformat(),
            ends_at=(start + timedelta(hours=2)).isoformat(),
            ical_data=ical_data)
        db.add(event)
        db.commit()
        return calendar.id, event.id


def test_classifier_only_recognizes_explicit_civic_events():
    classify = signage_suggestions.classify_title
    assert classify("Sitzung: Gemeinderatssitzung") == "council"
    assert classify("VerbandsGEMEINDERATSSITZUNG") == "council"
    assert classify("Briefwahlstelle im Rathaus") == "postal"
    assert classify("Wahllokal 01") == "poll"
    assert classify("Bürgerversammlung Rathaus") == "event"
    assert classify("Persönlicher Arzttermin") is None
    assert classify("Interne Personalbesprechung") is None
    assert classify("Wahl des Vereinsvorstands") is None
    assert classify("Private Runde ohne offiziellen Anlass") is None


def test_private_event_candidate_never_becomes_a_published_campaign():
    c = _admin()
    calendar_id, event_id = _event()
    page = c.get("/signage/campaigns")
    assert page.status_code == 200
    assert "Mögliche kommende Veranstaltungen" in page.text
    assert "Gemeinderatssitzung vertrauliche Vorlage" in page.text
    assert f"suggest={event_id}" in page.text
    assert "ABSOLUT VERTRAULICHE KALENDERBESCHREIBUNG" not in page.text
    assert client().get("/signage/campaigns").status_code in (303, 401, 403)
    draft = c.get(f"/signage/campaigns?calendar={calendar_id}&suggest={event_id}")
    assert draft.status_code == 200
    assert re.search(r'<option value="council"[^>]*selected', draft.text)
    assert 'name="title" maxlength="120" value="Ratssitzung"' in draft.text
    assert re.search(fr'<option value="{event_id}"[^>]*selected', draft.text)
    assert not re.search(r'<input[^>]+name="published"[^>]+checked', draft.text)
    with SessionLocal() as db:
        assert not db.scalar(select(SignageCampaign).where(SignageCampaign.event_id == event_id))
    # A public kiosk has no access to the draft's private calendar title.
    assert "ABSOLUT VERTRAULICHE KALENDERBESCHREIBUNG" not in draft.text


def test_candidate_disappears_when_already_assigned_even_if_still_draft():
    c = _admin()
    _, event_id = _event(title="Briefwahlstelle Rathaus")
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@example.org"))
        building = SignageBuilding(name="Rathaus Vorschläge")
        db.add(building); db.flush()
        floor = SignageFloor(building_id=building.id, name="EG", level=0)
        db.add(floor); db.flush()
        room = SignageRoom(floor_id=floor.id, number="0.02", name="Briefwahl")
        db.add(room); db.flush()
        db.add(SignageCampaign(building_id=building.id, room_id=room.id,
                               created_by=admin.id, event_id=event_id,
                               preset="postal", title="Briefwahlstelle",
                               priority=90, mode="overlay", published=False))
        db.commit()
        suggestions = signage_suggestions.suggest(db, admin)
        assert event_id not in {item["event_id"] for item in suggestions}


def test_non_free_cancelled_invalid_or_distant_events_are_not_proposed():
    c = _admin()
    source, hidden = _event(title="Ratssitzung Quelle deaktiviert", source="birthdays")
    _, distant = _event(title="Ratssitzung im nächsten Jahr", starts_in_days=180)
    _, malformed = _event(title="Ratssitzung defekter iCal Termin", ical_data="not a calendar")
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@example.org"))
        candidates = signage_suggestions.suggest(db, admin, limit=30)
        ids = {item["event_id"] for item in candidates}
        assert not ids.intersection({hidden, distant, malformed})


def test_bad_forged_suggestion_query_cannot_autofill_private_or_nonexistent_event():
    c = _admin()
    calendar_id, event_id = _event(title="Privater Termin ohne Event-Schlüssel")
    page = c.get(f"/signage/campaigns?calendar={calendar_id}&suggest={event_id}")
    assert page.status_code == 200
    assert 'name="title" maxlength="120" value=""' in page.text
    page = c.get("/signage/campaigns?calendar=99999&suggest=999999")
    assert page.status_code == 200
