"""Smart person picker and room-centered Signage directory acceptance tests."""
import json
import re

from sqlalchemy import select

from conftest import client, csrf_of, login, settings
from test_signage import _admin
from test_signage_passive import place
from app import person_picker
from app.db import Organization, SessionLocal, User
from app.org_models import OrgMembership
from app.security import hash_password
from app.signage_models import (
    SignageBuilding, SignageFloor, SignageRoom, SignageOffice
)


def _person(name, suffix):
    with SessionLocal() as db:
        row = User(name=name, email=f"{suffix}-sgpicker@example.org",
                   password_hash=hash_password("person-pass-123"),
                   permissions="video", active=True)
        db.add(row)
        db.commit()
        return row.id


def _submit(c, url, data, page="/signage/rooms"):
    return c.post(url, data={"csrf": csrf_of(c.get(page).text), **data})


def test_surname_key_and_context_sort_users_not_unrelated_lists():
    a = User(id=10001, name="Anna Zimmer", email="a@example.org", active=True)
    b = User(id=10002, name="Bernd Acker", email="b@example.org", active=True)
    c = User(id=10003, name="David Müller", email="c@example.org", active=True)
    assert [u.id for u in person_picker.sort_people([a, c, b])] == [b.id, c.id, a.id]
    assert person_picker.surname_key("Meyer, Frieda") < person_picker.surname_key("Zimmer, Anna")
    ctx = {"staff": [a, b, c], "roles": ["Zugriff 4", "Zugriff 1"]}
    prepared = person_picker.prepare_context(ctx)
    assert [u.id for u in ctx["staff"]] == [b.id, c.id, a.id]
    assert ctx["roles"] == ["Zugriff 4", "Zugriff 1"]
    assert set(prepared["people"]) == {"10001", "10002", "10003"}


def test_room_bulk_assignment_keeps_personal_consent_private(place):
    c = _admin()
    building, floor, room, origin = place
    a = _person("Jana Zander", "jana")
    b = _person("Leon Berg", "leon")
    page = c.get("/signage/rooms")
    assert page.status_code == 200
    assert "Alle Räume & Personen" in page.text
    assert 'data-person-picker="1"' in page.text
    result = _submit(c, f"/signage/rooms/{room}/people",
                     {"action": "add", "user_ids": [str(a), str(b)], "primary": "1"})
    assert result.status_code == 303, result.text
    with SessionLocal() as db:
        offices = list(db.scalars(select(SignageOffice).where(
            SignageOffice.room_id == room, SignageOffice.user_id.in_([a, b]))))
        assert len(offices) == 2
        assert all(x.is_primary and not x.public for x in offices)
    html = c.get(f"/signage/rooms?room={room}").text
    assert "Leon Berg" in html and "Jana Zander" in html
    assert html.index("Leon Berg") < html.index("Jana Zander")
    assert "Nur intern" in html
    repeat = _submit(c, f"/signage/rooms/{room}/people",
                     {"action": "add", "user_ids": [str(a), str(b)]})
    assert repeat.status_code == 303
    with SessionLocal() as db:
        assert len(list(db.scalars(select(SignageOffice).where(
            SignageOffice.room_id == room, SignageOffice.user_id.in_([a, b]))))) == 2


def test_room_assignment_remove_reassign_primary_and_refuse_other_room(place):
    c = _admin()
    _, floor, room, _ = place
    a = _person("Franz Nachname", "franz")
    with SessionLocal() as db:
        room_2 = SignageRoom(floor_id=floor, number="R209", name="Nebenbüro")
        db.add(room_2); db.commit()
        room_2_id = room_2.id
    for rid in (room, room_2_id):
        assert _submit(c, f"/signage/rooms/{rid}/people",
                       {"action": "add", "user_ids": str(a)}).status_code == 303
    assert _submit(c, f"/signage/rooms/{room_2_id}/people",
                   {"action": "primary", "user_id": str(a)}).status_code == 303
    with SessionLocal() as db:
        rows = list(db.scalars(select(SignageOffice).where(SignageOffice.user_id == a)))
        assert len([x for x in rows if x.is_primary]) == 1
        assert next(x for x in rows if x.is_primary).room_id == room_2_id
    assert _submit(c, f"/signage/rooms/{room_2_id}/people",
                   {"action": "remove", "user_id": str(a)}).status_code == 303
    with SessionLocal() as db:
        rows = list(db.scalars(select(SignageOffice).where(SignageOffice.user_id == a)))
        assert len(rows) == 1 and rows[0].room_id == room and rows[0].is_primary
    assert _submit(c, f"/signage/rooms/{room_2_id}/people",
                   {"action": "remove", "user_id": str(a)}).status_code == 404


def test_profile_self_assignment_public_opt_in_and_own_remove(place):
    _admin()
    person_id = _person("Beate Selbst", "beate")
    building, floor, room, _ = place
    user_client = login("beate-sgpicker@example.org", "person-pass-123")
    page = user_client.get("/profile")
    assert page.status_code == 200
    assert 'action="/profile/signage/office"' in page.text
    assert f'<option value="{room}">' in page.text
    added = _submit(user_client, "/profile/signage/office",
                    {"room_id": str(room), "primary": "1"}, "/profile")
    assert added.status_code == 303
    with SessionLocal() as db:
        row = db.scalar(select(SignageOffice).where(
            SignageOffice.user_id == person_id, SignageOffice.room_id == room))
        assert row and row.is_primary and not row.public
        office_id = row.id
    profile = user_client.get("/profile")
    assert "Nicht öffentlich" in profile.text
    assert _submit(user_client, f"/profile/signage/office/{office_id}/visibility",
                   {"public": "1"}, "/profile").status_code == 303
    with SessionLocal() as db:
        assert db.get(SignageOffice, office_id).public
    assert _submit(user_client, f"/profile/signage/office/{office_id}/remove",
                   {}, "/profile").status_code == 303
    with SessionLocal() as db:
        assert db.get(SignageOffice, office_id) is None
    assert _submit(user_client, f"/profile/signage/office/{office_id}/visibility",
                   {"public": "1"}, "/profile").status_code == 404


def test_room_permissions_and_org_hierarchy_filter_for_profile(place):
    c = _admin()
    person_id = _person("Ruth Finanzen", "ruth")
    with SessionLocal() as db:
        parent = Organization(name="Fachbereich Pickertest", kind="fachbereich")
        other = Organization(name="Fremde Pickertest-Verwaltung", kind="fachbereich")
        db.add_all([parent, other]); db.flush()
        child = Organization(name="Team Abteilung Pickertest", parent_id=parent.id, kind="team")
        db.add(child); db.flush()
        person = db.get(User, person_id)
        db.add(OrgMembership(user_id=person.id, org_id=child.id, is_primary=True))
        authorized_building = SignageBuilding(name="Süd-Verwaltung", org_id=parent.id)
        alien_building = SignageBuilding(name="Fremdes Fachamt", org_id=other.id)
        db.add_all([authorized_building, alien_building]); db.flush()
        floor_ok = SignageFloor(building_id=authorized_building.id, name="EG")
        floor_bad = SignageFloor(building_id=alien_building.id, name="EG")
        db.add_all([floor_ok, floor_bad]); db.flush()
        room_ok = SignageRoom(floor_id=floor_ok.id, number="A11", name="Büro Süd")
        room_bad = SignageRoom(floor_id=floor_bad.id, number="B11", name="Büro geheim")
        db.add_all([room_ok, room_bad]); db.commit()
        good_id, bad_id = room_ok.id, room_bad.id
    scoped = login("ruth-sgpicker@example.org", "person-pass-123")
    html = scoped.get("/profile").text
    assert "Süd-Verwaltung" in html and "Fremdes Fachamt" not in html
    assert _submit(scoped, "/profile/signage/office",
                   {"room_id": str(bad_id)}, "/profile").status_code == 403
    assert _submit(scoped, "/profile/signage/office",
                   {"room_id": str(good_id)}, "/profile").status_code == 303
    # Organizational metadata is generated for *visible* picker users only.
    admin_html = c.get("/signage/rooms").text
    match = re.search(r'<script id="takt-person-picker-meta" type="application/json">(.*?)</script>', admin_html, re.S)
    assert match, "The common person picker must be part of portal base layout"
    metadata = json.loads(match.group(1))
    assert parent.id in metadata["people"][str(person_id)]["orgs"]
    assert any(o["id"] == parent.id for o in metadata["organizations"])


def test_invalid_room_multi_values_are_atomic_and_external_user_cannot_edit(place):
    c = _admin()
    _, _, room, _ = place
    first = _person("Jochen Erster", "jochen")
    assert _submit(c, f"/signage/rooms/{room}/people",
                   {"action": "add", "user_ids": [str(first), "999999999"]}).status_code == 422
    with SessionLocal() as db:
        assert not db.scalar(select(SignageOffice).where(
            SignageOffice.user_id == first, SignageOffice.room_id == room))
    assert client().get("/signage/rooms").status_code in (303, 401, 403)
    visitor = login("jochen-sgpicker@example.org", "person-pass-123")
    assert visitor.get("/signage/rooms").status_code == 403
    assert _submit(visitor, f"/signage/rooms/{room}/people",
                   {"action": "add", "user_ids": str(first)}, "/profile").status_code == 403
