from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from conftest import client, csrf_of
from test_signage import _admin
from app.db import SessionLocal, utcnow
from app.signage_models import (
    SignageBuilding, SignageFloor, SignageRoom, SignageScreen, SignageWayNode, SignageWayEdge,
)


@pytest.fixture
def place():
    with SessionLocal() as db:
        building = SignageBuilding(name="Passives Rathaus")
        db.add(building)
        db.flush()
        floor = SignageFloor(building_id=building.id, name="Erdgeschoss")
        db.add(floor)
        db.flush()
        target = SignageRoom(floor_id=floor.id, number="P1", name="Bürgerbüro Passiv")
        private = SignageRoom(floor_id=floor.id, number="P2", name="Vertraulicher Raum Passiv")
        db.add_all([target, private])
        db.flush()
        origin = SignageWayNode(floor_id=floor.id, label="Passiver Eingang", x_pct=50, y_pct=50)
        arrival = SignageWayNode(floor_id=floor.id, room_id=target.id, label="Interne Graphbezeichnung",
                                 x_pct=70, y_pct=50)
        db.add_all([origin, arrival])
        db.flush()
        db.add(SignageWayEdge(from_node_id=origin.id, to_node_id=arrival.id))
        result = building.id, floor.id, target.id, origin.id
        db.commit()
    return result


def _post(c, path, fields, page="/signage"):
    return c.post(path, data={"csrf": csrf_of(c.get(page).text), **fields})


def _setup(c, place, kind="sign_corridor"):
    building, floor, room, origin = place
    response = _post(c, f"/signage/room/{room}/destination", {"listed": "1"})
    assert response.status_code == 303
    response = _post(c, "/signage/new", {"name": "Passiver Test", "kind": kind,
                                        "building_id": building, "floor_id": floor,
                                        "node_id": origin, "facing": "north"})
    assert response.status_code == 303, response.text
    edit = response.headers["location"]
    sid = int(edit.split("/")[2])
    with SessionLocal() as db:
        screen = db.get(SignageScreen, sid)
        screen.visibility = "public"
        db.commit()
    return sid, edit


def test_corridor_public_projection_and_display_orientation(place):
    c = _admin()
    sid, edit = _setup(c, place)
    page = client().get(f"/signage/view/{sid}")
    assert page.status_code == 200
    assert "Bürgerbüro Passiv" in page.text and "Rechts" in page.text
    assert "Vertraulicher Raum Passiv" not in page.text
    assert "Interne Graphbezeichnung" not in page.text
    assert "<input" not in page.text and "<details" not in page.text
    _, _, room, _ = place
    assert _post(c, f"/signage/{sid}/destination", {"room_id": room, "arrow": "left",
                 "label": "Bürgerservice", "rank": 10}, edit).status_code == 303
    page = client().get(f"/signage/view/{sid}")
    assert "Links" in page.text and "Bürgerservice" in page.text


def test_special_priority_and_return_to_normal(place):
    from app.signage_models import SignageSpecial

    c = _admin()
    sid, edit = _setup(c, place, "sign_building")
    _, _, room, _ = place
    now = utcnow()
    for title, priority in (("Niedrige Anzeige", 1), ("Briefwahl geöffnet", 90)):
        result = _post(c, f"/signage/{sid}/special", {
            "preset": "postal", "title": title, "room_id": room, "priority": priority,
            "mode": "replace", "published": "1",
            "starts_at": (now - timedelta(hours=1)).replace(tzinfo=timezone.utc).isoformat(),
            "ends_at": (now + timedelta(hours=1)).replace(tzinfo=timezone.utc).isoformat(),
        }, edit)
        assert result.status_code == 303, result.text
    page = client().get(f"/signage/view/{sid}")
    assert "Briefwahl geöffnet" in page.text and "Niedrige Anzeige" not in page.text
    with SessionLocal() as db:
        for special in db.scalars(select(SignageSpecial).where(SignageSpecial.screen_id == sid)):
            special.ends_at = now - timedelta(seconds=1)
        db.commit()
    assert "Briefwahl geöffnet" not in client().get(f"/signage/view/{sid}").text
    assert "Bürgerbüro Passiv" in client().get(f"/signage/view/{sid}").text


def test_manual_time_rejects_ambiguous_or_nonexistent_berlin_times():
    from app.signage_passive import schedule_time

    for value in ("2026-10-25T02:30", "2026-03-29T02:30"):
        with pytest.raises(ValueError):
            schedule_time(value)
    assert schedule_time("2026-10-25T02:30+02:00") == datetime(2026, 10, 25, 0, 30)


def test_calendar_release_follows_time_and_respects_source_visibility(place):
    from app.calendar_models import Calendar, CalendarEvent
    from app.db import User

    c = _admin()
    sid, edit = _setup(c, place, "sign_building")
    _, _, room, _ = place
    now = utcnow().replace(tzinfo=timezone.utc)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        calendar = Calendar(owner_id=user.id, title="Sonderbetrieb Testkalender")
        db.add(calendar)
        db.flush()
        event = CalendarEvent(calendar_id=calendar.id, uid="passive-calendar",
                              starts_at=(now - timedelta(minutes=30)).isoformat(),
                              ends_at=(now + timedelta(minutes=30)).isoformat(),
                              title="Interner Sitzungstitel", description="Internes Protokoll")
        db.add(event)
        db.flush()
        event_id, calendar_id = event.id, calendar.id
        db.commit()
    assert "Interner Sitzungstitel" in c.get(f"{edit}?calendar={calendar_id}").text
    payload = {"preset": "council", "room_id": room, "event_id": event_id, "title": "Öffentliche Sitzung"}
    result = _post(c, f"/signage/{sid}/special", payload, edit)
    assert result.status_code == 303, result.text
    public_url = f"/signage/view/{sid}"
    assert "Öffentliche Sitzung" not in client().get(public_url).text
    result = _post(c, f"/signage/{sid}/special", {**payload, "published": "1"}, edit)
    assert result.status_code == 303, result.text
    page = client().get(public_url).text
    assert "Öffentliche Sitzung" in page and "Bürgerbüro Passiv" in page
    assert "Interner Sitzungstitel" not in page and "Internes Protokoll" not in page

    with SessionLocal() as db:
        event = db.get(CalendarEvent, event_id)
        event.starts_at = (now + timedelta(hours=1)).isoformat()
        event.ends_at = (now + timedelta(hours=2)).isoformat()
        db.commit()
    assert "Öffentliche Sitzung" not in client().get(public_url).text

    with SessionLocal() as db:
        event = db.get(CalendarEvent, event_id)
        event.starts_at = (now - timedelta(hours=1)).isoformat()
        db.get(Calendar, calendar_id).source = "birthdays"
        db.commit()
    assert "Öffentliche Sitzung" not in client().get(public_url).text


def test_passive_scope_and_room_revocation(place):
    c = _admin()
    sid, edit = _setup(c, place, "sign_floor")
    building, floor, room, origin = place
    with SessionLocal() as db:
        other = SignageBuilding(name="Anderes Gebäude")
        db.add(other)
        db.flush()
        other_id = other.id
        db.commit()
    response = _post(c, f"/signage/{sid}/passive",
                     {"building_id": other_id, "floor_id": floor, "node_id": origin}, edit)
    assert response.status_code == 422
    assert client().post(f"/signage/{sid}/passive", data={"building_id": building}).status_code == 400
    assert _post(c, f"/signage/room/{room}/destination", {}).status_code == 303
    assert "Bürgerbüro Passiv" not in client().get(f"/signage/view/{sid}").text


def test_static_direction_uses_manual_arrow_without_graph(place):
    c = _admin()
    sid, edit = _setup(c, place, "sign_direction")
    building, _, _, _ = place
    response = _post(c, f"/signage/{sid}/passive", {
        "building_id": building, "manual_label": "Ausgang zum Innenhof", "manual_arrow": "left",
        "manual_only": "1",
    }, edit)
    assert response.status_code == 303, response.text
    page = client().get(f"/signage/view/{sid}").text
    assert "Ausgang zum Innenhof" in page and "Links" in page
    assert "Bürgerbüro Passiv" not in page


def test_room_rename_updates_live_projection_without_republishing(place):
    c = _admin()
    sid, _ = _setup(c, place, "sign_building")
    _, _, room, _ = place
    result = _post(c, f"/signage/structure/room/{room}",
                   {"name": "P1A", "label": "Bürgerservice aktualisiert", "accessible": "1"})
    assert result.status_code == 303
    page = client().get(f"/signage/view/{sid}").text
    assert "Bürgerservice aktualisiert" in page and "Raum P1A" in page
    assert "Bürgerbüro Passiv" not in page
