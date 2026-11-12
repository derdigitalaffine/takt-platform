"""Central signage campaign acceptance, privacy, scheduling and projection tests."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from conftest import client, csrf_of
from test_signage import _admin
from test_signage_passive import _post, _setup, place
from app import signage_campaign, signage_passive
from app.db import SessionLocal, utcnow, User
from app.signage_models import (
    SignageBuilding, SignageCampaign, SignageCampaignScreen, SignageFloor,
    SignagePassiveConfig, SignagePublicDestination, SignageRoom, SignageScreen,
    SignageSpecial,
)


def _payload(place, **options):
    building, floor, room, _ = place
    now = utcnow().replace(tzinfo=timezone.utc)
    fields = {
        "building_id": str(building), "room_id": str(room),
        "scope": "building", "preset": "council",
        "title": "Öffentliche Sitzung im Ratssaal",
        "priority": "80", "mode": "replace",
        "lead_minutes": "30", "tail_minutes": "15", "published": "1",
        "starts_at": (now + timedelta(minutes=10)).isoformat(),
        "ends_at": (now + timedelta(minutes=65)).isoformat(),
    }
    fields.update(options)
    return fields


def _create(c, place, **options):
    page = c.get("/signage/campaigns")
    assert page.status_code == 200, page.text[:500]
    res = _post(c, "/signage/campaigns/save", _payload(place, **options),
                "/signage/campaigns")
    assert res.status_code == 303, res.text[:600]
    with SessionLocal() as db:
        return db.scalar(select(SignageCampaign).order_by(SignageCampaign.id.desc())).id


def _another_screen(c, place, *, name="Weiterer Wegweiser"):
    building, floor, _, origin = place
    result = _post(c, "/signage/new", {
        "name": name, "kind": "sign_building",
        "building_id": str(building), "floor_id": str(floor),
        "node_id": str(origin), "facing": "north",
    })
    assert result.status_code == 303, result.text
    sid = int(result.headers["location"].split("/")[2])
    with SessionLocal() as db:
        db.get(SignageScreen, sid).visibility = "public"
        db.commit()
    return sid


def test_building_campaign_auto_assigns_new_screens_and_expires(place):
    c = _admin()
    first, _ = _setup(c, place, "sign_building")
    second = _another_screen(c, place)
    campaign = _create(c, place)
    for sid in (first, second):
        page = client().get(f"/signage/view/{sid}")
        assert page.status_code == 200
        assert "Öffentliche Sitzung im Ratssaal" in page.text
    third = _another_screen(c, place, name="Display neu montiert")
    assert "Öffentliche Sitzung im Ratssaal" in client().get(f"/signage/view/{third}").text
    with SessionLocal() as db:
        row = db.get(SignageCampaign, campaign)
        row.ends_at = utcnow() - timedelta(minutes=45)
        db.commit()
    for sid in (first, second, third):
        page = client().get(f"/signage/view/{sid}")
        assert "Öffentliche Sitzung im Ratssaal" not in page.text
        assert "Bürgerbüro Passiv" in page.text


def test_selected_scope_and_exclusion_only_affect_the_requested_display(place):
    c = _admin()
    first, _ = _setup(c, place, "sign_building")
    second = _another_screen(c, place)
    cid = _create(c, place, scope="selected", screen_ids=str(first), title="Nur Eingang")
    assert "Nur Eingang" in client().get(f"/signage/view/{first}").text
    assert "Nur Eingang" not in client().get(f"/signage/view/{second}").text
    # Change to building-wide mode and exclude a single monitor.
    response = _post(c, "/signage/campaigns/save",
                     {**_payload(place, title="Überall außer Eingang",
                                  excluded_ids=str(first)),
                      "campaign_id": str(cid)}, "/signage/campaigns")
    assert response.status_code == 303
    assert "Überall außer Eingang" not in client().get(f"/signage/view/{first}").text
    assert "Überall außer Eingang" in client().get(f"/signage/view/{second}").text


def test_private_target_never_published_and_wrong_building_rejected(place):
    c = _admin()
    sid, _ = _setup(c, place, "sign_building")
    building, floor, room, _ = place
    with SessionLocal() as db:
        private = db.scalar(select(SignageRoom).where(
            SignageRoom.floor_id == floor, SignageRoom.id != room))
        other_building = SignageBuilding(name="Nur intern, anderes Gebäude")
        db.add(other_building)
        db.flush()
        other_floor = SignageFloor(building_id=other_building.id, name="EG")
        db.add(other_floor)
        db.flush()
        other_room = SignageRoom(floor_id=other_floor.id, number="21",
                                name="Nicht berechtigte Veröffentlichung")
        db.add(other_room)
        db.commit()
        private_id, other_id = private.id, other_room.id
    assert _post(c, "/signage/campaigns/save",
                 _payload(place, room_id=str(private_id)), "/signage/campaigns").status_code == 422
    assert _post(c, "/signage/campaigns/save",
                 _payload(place, room_id=str(other_id)), "/signage/campaigns").status_code == 422
    assert _post(c, "/signage/campaigns/save",
                 _payload(place, scope="selected", screen_ids="999999"),
                 "/signage/campaigns").status_code == 403
    assert "Nicht berechtigte Veröffentlichung" not in client().get(f"/signage/view/{sid}").text


def test_campaign_priority_manual_override_and_withdraw(place):
    c = _admin()
    sid, _ = _setup(c, place, "sign_building")
    cid = _create(c, place, title="Automatische Aktion", priority="60")
    now = utcnow()
    with SessionLocal() as db:
        _, _, room, _ = place
        db.add(SignageSpecial(screen_id=sid, room_id=room, actor_id=None,
              title="Individuelle Override", preset="council", priority=60,
              mode="overlay", starts_at=now - timedelta(minutes=1),
              ends_at=now + timedelta(minutes=15), published=True))
        db.commit()
    assert "Individuelle Override" in client().get(f"/signage/view/{sid}").text
    assert "Automatische Aktion" not in client().get(f"/signage/view/{sid}").text
    assert _post(c, f"/signage/campaigns/{cid}/status",
                 {"action": "withdraw"}, "/signage/campaigns").status_code == 303
    with SessionLocal() as db:
        assert not db.get(SignageCampaign, cid).published


def test_calendar_campaign_rechecks_source_permission_and_uses_custom_title(place):
    from app.calendar_models import Calendar, CalendarEvent

    c = _admin()
    sid, _ = _setup(c, place, "sign_building")
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@example.org"))
        calendar = Calendar(owner_id=admin.id, title="Privater interner Terminplan",
                            visibility="private", source="free")
        db.add(calendar)
        db.flush()
        now = utcnow().replace(tzinfo=timezone.utc)
        event = CalendarEvent(
            calendar_id=calendar.id, uid="signage-campaign-event",
            starts_at=(now + timedelta(minutes=10)).isoformat(),
            ends_at=(now + timedelta(minutes=70)).isoformat(),
            title="VERTRAULICHER ORIGINALTITEL",
            description="PERSONALINFORMATION")
        db.add(event)
        db.commit()
        event_id, calendar_id = event.id, calendar.id
    cid = _create(c, place, title="Öffentliche Ausschusssitzung",
                  event_id=str(event_id), starts_at="", ends_at="")
    html = client().get(f"/signage/view/{sid}").text
    assert "Öffentliche Ausschusssitzung" in html
    assert "VERTRAULICHER ORIGINALTITEL" not in html
    assert "PERSONALINFORMATION" not in html
    with SessionLocal() as db:
        db.get(Calendar, calendar_id).source = "birthdays"
        db.commit()
    assert "Öffentliche Ausschusssitzung" not in client().get(f"/signage/view/{sid}").text


def test_campaign_simulation_and_management_permissions(place):
    c = _admin()
    sid, _ = _setup(c, place, "sign_building")
    cid = _create(c, place)
    building, _, _, _ = place
    next_hour = (utcnow() + timedelta(minutes=30)).replace(tzinfo=timezone.utc).isoformat()
    preview = c.get("/signage/campaigns/simulate",
                    params={"building_id": building, "at": next_hour})
    assert preview.status_code == 200, preview.text
    assert "Öffentliche Sitzung im Ratssaal" in preview.text
    assert client().get("/signage/campaigns").status_code in (303, 401, 403)
    assert client().post("/signage/campaigns/save", data=_payload(place)).status_code == 400
    assert c.get("/signage/campaigns/simulate",
                 params={"building_id": building, "at": "2100-01-01T00:00"}).status_code == 422
    page = c.get("/signage/campaigns")
    assert "Öffentliche Sitzung im Ratssaal" in page.text
    assert "Displays" in page.text
    assert str(cid) in page.text or "Bearbeiten" in page.text


def test_conflict_warnings_for_overlapping_published_campaigns(place):
    c = _admin()
    _setup(c, place, "sign_building")
    first = _create(c, place, title="Sitzung", priority="60")
    second = _create(c, place, title="Briefwahl", priority="80")
    with SessionLocal() as db:
        row = db.get(SignageCampaign, first)
        problems = signage_campaign.conflict_warnings(db, row)
        assert any("Briefwahl" in s for s in problems)
        assert signage_campaign.conflict_warnings(db, db.get(SignageCampaign, second)) == []


def test_campaign_never_crosses_building_ownership(place):
    c = _admin()
    _setup(c, place, "sign_building")
    building, floor, room, origin = place
    with SessionLocal() as db:
        building_b = SignageBuilding(name="Zweites Gebäude")
        db.add(building_b)
        db.flush()
        floor_b = SignageFloor(building_id=building_b.id, name="EG", level=0)
        db.add(floor_b)
        db.flush()
        room_b = SignageRoom(floor_id=floor_b.id, number="22", name="Öffentliches Büro B")
        db.add(room_b)
        db.flush()
        db.add(SignagePublicDestination(room_id=room_b.id))
        db.commit()
        building_b_id, floor_b_id = building_b.id, floor_b.id
    result = _post(c, "/signage/new", {"name": "Display B", "kind": "sign_building",
                                       "building_id": building_b_id,
                                       "floor_id": floor_b_id})
    assert result.status_code == 303
    screen_b = int(result.headers["location"].split("/")[2])
    with SessionLocal() as db:
        db.get(SignageScreen, screen_b).visibility = "public"
        db.commit()
    _create(c, place, title="Nur Gebäude A")
    assert "Nur Gebäude A" not in client().get(f"/signage/view/{screen_b}").text
