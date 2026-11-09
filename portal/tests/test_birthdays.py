"""Consent, live access control, leap-day behavior and external birthday channels."""
from datetime import datetime, date, timezone
import uuid

import pytest
from sqlalchemy import select

from app import birthdays, calendar_sources, calendars, profiles
from app.db import User, Organization, Setting, set_setting, get_settings
from app.org_models import OrgMembership
from app.calendar_models import Calendar
from app.security import hash_password
from conftest import login, csrf_of


@pytest.fixture
def birthday_people(db):
    token = uuid.uuid4().hex[:8]
    root = Organization(name="Birthday-VG-" + token, kind="vg")
    outside_root = Organization(name="Fremde VG " + token, kind="vg")
    db.add_all([root, outside_root])
    db.flush()
    team_a = Organization(name="Personal " + token, parent_id=root.id, kind="team")
    team_b = Organization(name="Bauhof " + token, parent_id=root.id, kind="team")
    db.add_all([team_a, team_b])
    db.flush()
    people = [
        User(name="Person Geburtstagskind", email="birthday-child-" + token + "@example.org",
             password_hash=hash_password("birthday-pass-123"),
             profile_data_enc=profiles.store({
                 "birthdate": "1992-02-29", "birthday_visibility": "age"
             })),
        User(name="Kollegin A", email="birthday-reader-" + token + "@example.org",
             password_hash=hash_password("birthday-pass-123")),
        User(name="Kollege B", email="birthday-sibling-" + token + "@example.org",
             password_hash=hash_password("birthday-pass-123")),
        User(name="Fremde Person", email="birthday-outsider-" + token + "@example.org",
             password_hash=hash_password("birthday-pass-123")),
    ]
    db.add_all(people)
    db.flush()
    db.add_all([
        OrgMembership(user_id=people[0].id, org_id=team_a.id, is_primary=True),
        OrgMembership(user_id=people[1].id, org_id=team_a.id, is_primary=True),
        OrgMembership(user_id=people[2].id, org_id=team_b.id, is_primary=True),
        OrgMembership(user_id=people[3].id, org_id=outside_root.id, is_primary=True),
    ])
    previous_calendar = get_settings(db).get("module_calendars")
    set_setting(db, "module_calendars", "1")
    db.commit()
    try:
        yield root, outside_root, team_a, team_b, people
    finally:
        for row in db.scalars(select(Calendar).where(Calendar.owner_id.in_([p.id for p in people]))):
            db.delete(row)
        db.flush()
        for row in db.scalars(select(OrgMembership).where(OrgMembership.user_id.in_([p.id for p in people]))):
            db.delete(row)
        db.flush()
        for person in people:
            db.delete(person)
        db.flush()
        db.delete(team_a)
        db.delete(team_b)
        db.flush()
        db.delete(root)
        db.delete(outside_root)
        for key in ("scope", "leap", "caldav", "ics"):
            row = db.get(Setting, "birthday_" + str(root.id) + "_" + key)
            if row is not None:
                db.delete(row)
        if previous_calendar is None:
            row = db.get(Setting, "module_calendars")
            if row is not None:
                db.delete(row)
        else:
            set_setting(db, "module_calendars", previous_calendar)
        db.commit()


def window():
    return (datetime(2027, 2, 1, tzinfo=timezone.utc),
            datetime(2027, 3, 10, tzinfo=timezone.utc))


def test_birthday_opt_in_scoped_age_revocation_and_user_status(db, birthday_people):
    root, _, team, sibling, (person, reader, other, stranger) = birthday_people
    a, b = window()
    visible = birthdays.events(db, reader, a, b)
    assert len(visible) == 1
    assert visible[0]["start"] == "2027-02-28"
    assert "35" in visible[0]["title"]
    assert "1992" not in str(visible)
    assert birthdays.events(db, other, a, b) == []
    assert birthdays.events(db, stranger, a, b) == []
    person.profile_data_enc = profiles.store({
        "birthdate": "1992-02-29", "birthday_visibility": "date"
    })
    db.flush()
    no_age = birthdays.events(db, reader, a, b)
    assert len(no_age) == 1 and "35" not in no_age[0]["title"]
    person.profile_data_enc = profiles.store({
        "birthdate": "1992-02-29", "birthday_visibility": "hidden"
    })
    db.flush()
    assert birthdays.events(db, reader, a, b) == []
    person.profile_data_enc = profiles.store({
        "birthdate": "1992-02-29", "birthday_visibility": "age"
    })
    person.active = False
    db.flush()
    assert birthdays.events(db, reader, a, b) == []


def test_birthday_root_policy_leap_day_and_external_consent(db, birthday_people):
    root, _, _, _, (person, reader, sibling, outsider) = birthday_people
    a, b = window()
    assert birthdays.events(db, sibling, a, b) == []
    birthdays.save_rules(db, root.id, scope="root", leap="mar1", caldav=True, ics=False)
    db.flush()
    assert birthdays.events(db, sibling, a, b)[0]["start"] == "2027-03-01"
    assert birthdays.events(db, outsider, a, b) == []
    assert birthdays.events(db, reader, a, b, channel="ics") == []
    assert birthdays.events(db, reader, a, b, channel="caldav")
    birthdays.save_rules(db, root.id, scope="root", leap="mar1", caldav=False, ics=True)
    db.flush()
    assert birthdays.events(db, reader, a, b, channel="caldav") == []
    assert birthdays.events(db, reader, a, b, channel="ics")
    assert birthdays.observed_day(date(1992, 2, 29), 2028, "mar1") == date(2028, 2, 29)


def test_birthday_calendar_endpoint_and_ics_guards(db, birthday_people):
    root, _, _, _, (person, reader, sibling, outsider) = birthday_people
    c = login(reader.email, "birthday-pass-123")
    assert c.get("/kalender/geburtstage").status_code == 200
    assert c.get("/kalender/geburtstage/einstellungen").status_code == 403
    q = "/kalender/quellen/birthdays/data?start=2027-02-01&end=2027-03-10"
    result = c.get(q)
    assert result.status_code == 200, result.text
    assert len(result.json()["events"]) == 1
    assert c.get("/kalender/geburtstage").headers["cache-control"] == "no-store"
    assert login(outsider.email, "birthday-pass-123").get(q).json()["events"] == []
    calendar = Calendar(owner_id=reader.id, title="Geburtstage", source="birthdays", visibility="private")
    db.add(calendar)
    db.commit()
    assert calendars.access(db, reader, calendar)
    assert not calendars.access(db, outsider, calendar)
    assert not calendars.access(db, reader, calendar, write=True)
    assert not birthdays.external_allowed(db, reader, "ics")
    assert "Geburtstage" in c.get("/kalender/geburtstage").text
    # Revoking an existing consent is an authenticated, CSRF-protected write.
    p = login(person.email, "birthday-pass-123")
    csrf = csrf_of(p.get("/profile").text)
    assert p.post("/profile/birthday/hide", data={"csrf": "invalid"}).status_code == 400
    assert p.post("/profile/birthday/hide", data={"csrf": csrf}).status_code == 303
    db.refresh(person)
    assert profiles.read(person)["birthday_visibility"] == "hidden"
    assert c.get(q).json()["events"] == []


def test_profile_visibility_validation_and_legacy_contract():
    assert profiles.clean({"given_name": "Ada"}) == {
        "prefill_enabled": False, "given_name": "Ada"
    }
    assert profiles.clean({"birthday_visibility": "age"})["birthday_visibility"] == "age"
    with pytest.raises(ValueError):
        profiles.clean({"birthday_visibility": "public"})
