"""Digital Signage: focused pages, nested buildings and safe destructive CRUD."""
import re

from sqlalchemy import select

from conftest import client, csrf_of
from test_signage import _admin, _screen
from test_signage_passive import _post, place, _setup
from app.db import SessionLocal
from app.signage_models import (
    SignageBuilding, SignageBuildingPart, SignagePartFloor,
    SignageFloor, SignageRoom, SignageScreen, SignageWayNode,
    SignageDevice, SignageLink, SignageRevision,
    SignageGeneratedScreen, SignagePassiveConfig, SignageCampaign,
    SignageCampaignScreen,
)


def _create(c, kind, **data):
    res = _post(c, "/signage/hierarchy/create",
                {"kind": kind, **data}, "/signage/buildings")
    assert res.status_code == 303, res.text[:550]
    path = res.headers["location"]
    match = re.search(r"select=(building|part|floor|room):(\d+)", path)
    assert match, path
    return int(match.group(2))


def test_signage_navigation_has_focused_pages_without_old_overload(place):
    c = _admin()
    overview = c.get("/signage")
    assert overview.status_code == 200
    assert "Besucherinformationen. Einfach organisiert." in overview.text
    assert 'action="/signage/structure"' not in overview.text
    assert 'action="/signage/route/node"' not in overview.text
    assert 'action="/signage/new"' in overview.text
    for path, text in (
        ("/signage/screens", "Neue Anzeige erstellen"),
        ("/signage/buildings", "Gebäudebrowser"),
        ("/signage/wayfinding", "Digitale Wegepläne"),
        ("/signage/campaigns", "Eine Veranstaltung, alle passenden Wegweiser"),
        ("/signage/fleet", "Geräte & Betriebszustand"),
    ):
        res = c.get(path)
        assert res.status_code == 200, (path, res.text[:500])
        assert text in res.text
        assert 'aria-label="Digital-Signage-Bereiche"' in res.text
    assert "Wegenetz & Büros" not in overview.text or "Wegenetz" in overview.text
    assert client().get("/signage/buildings").status_code in (303, 401, 403)


def test_nested_building_parts_and_floor_assignment_preserve_room_ids(place):
    c = _admin()
    building, floor, room, _ = place
    wing = _create(c, "part", building_id=building, name="Nordflügel",
                   code="N", part_kind="wing")
    annex = _create(c, "part", building_id=building, parent_id=wing,
                    name="Neuer Anbau", part_kind="annex")
    with SessionLocal() as db:
        assert db.get(SignageBuildingPart, annex).parent_id == wing
    response = _post(c, f"/signage/hierarchy/floor/{floor}/save",
                     {"name": "Erdgeschoss", "level": "0", "part_id": str(annex)},
                     "/signage/buildings")
    assert response.status_code == 303, response.text
    html = c.get(f"/signage/buildings?select=room:{room}").text
    assert "Nordflügel" in html and "Neuer Anbau" in html
    assert "Bürgerbüro Passiv" in html and 'aria-current="true"' in html
    with SessionLocal() as db:
        assert db.get(SignagePartFloor, floor).part_id == annex
        assert db.get(SignageRoom, room).floor_id == floor
    wrong = _post(c, f"/signage/hierarchy/part/{wing}/save",
                  {"name": "Nordflügel", "part_kind": "wing",
                   "parent_id": str(annex)}, "/signage/buildings")
    assert wrong.status_code == 422


def test_hierarchy_rejects_cross_building_mapping_and_delete_with_dependencies(place):
    c = _admin()
    building, floor, room, _ = place
    other = _create(c, "building", name="Nebengebäude für Tests")
    part = _create(c, "part", building_id=other, name="Westanbau")
    res = _post(c, f"/signage/hierarchy/floor/{floor}/save",
                {"name": "Erdgeschoss", "level": "0", "part_id": part}, "/signage/buildings")
    assert res.status_code == 422
    res = _post(c, f"/signage/hierarchy/building/{building}/delete",
                {"confirm": "Passives Rathaus"}, "/signage/buildings")
    assert res.status_code == 409
    res = _post(c, f"/signage/hierarchy/floor/{floor}/delete",
                {"confirm": "Erdgeschoss"}, "/signage/buildings")
    assert res.status_code == 409
    res = _post(c, f"/signage/hierarchy/room/{room}/delete",
                {"confirm": "P1"}, "/signage/buildings")
    assert res.status_code == 409  # room has a route node
    assert c.get(f"/signage/buildings?select=floor:{floor}").status_code == 200


def test_clean_hierarchy_crud_full_lifecycle_and_typed_delete(place):
    c = _admin()
    bid = _create(c, "building", name="Testhaus CRUD", code="TH")
    part = _create(c, "part", building_id=bid, name="Altbau",
                   part_kind="wing", code="A")
    floor = _create(c, "floor", building_id=bid, part_id=part,
                    name="Erdgeschoss", level="0")
    room = _create(c, "room", floor_id=floor, name="100",
                   label="Besprechungszimmer", accessible="1")
    with SessionLocal() as db:
        assert db.get(SignagePartFloor, floor).part_id == part
        assert db.get(SignageRoom, room).accessible
    res = _post(c, f"/signage/hierarchy/room/{room}/save",
                {"name": "101", "label": "Ratssaal", "accessible": "1",
                 "resource_id": "", "calendar_id": ""}, "/signage/buildings")
    assert res.status_code == 303
    assert "Ratssaal" in c.get(f"/signage/buildings?select=room:{room}").text
    assert _post(c, f"/signage/hierarchy/room/{room}/delete",
                 {"confirm": "100"}, "/signage/buildings").status_code == 422
    assert _post(c, f"/signage/hierarchy/room/{room}/delete",
                 {"confirm": "101"}, "/signage/buildings").status_code == 303
    assert _post(c, f"/signage/hierarchy/floor/{floor}/delete",
                 {"confirm": "Erdgeschoss"}, "/signage/buildings").status_code == 303
    assert _post(c, f"/signage/hierarchy/part/{part}/delete",
                 {"confirm": "Altbau"}, "/signage/buildings").status_code == 303
    assert _post(c, f"/signage/hierarchy/building/{bid}/delete",
                 {"confirm": "Testhaus CRUD"}, "/signage/buildings").status_code == 303
    with SessionLocal() as db:
        assert db.get(SignageBuilding, bid) is None


def test_screen_delete_invalidates_device_link_and_versions():
    c = _admin()
    sid = _screen(c, name="Wegweiser löschen", visibility="public")
    csrf = csrf_of(c.get(f"/signage/{sid}/edit").text)
    response = c.post(f"/signage/{sid}/device", data={"csrf": csrf, "name": "Terminal EG"})
    assert response.status_code == 200
    match = re.search(r"Gerät-ID: (\d+)\s+Bearer: ([\w-]+)", response.text)
    assert match
    did, token = int(match.group(1)), match.group(2)
    page = c.get(f"/signage/{sid}/delete")
    assert page.status_code == 200
    assert "Wegweiser löschen" in page.text
    assert "gekoppelte Geräte" in page.text
    with SessionLocal() as db:
        version = db.get(SignageScreen, sid).version
    assert _post(c, f"/signage/{sid}/delete",
                 {"confirm": "falscher Name", "version": str(version)},
                 f"/signage/{sid}/delete").status_code == 409
    assert _post(c, f"/signage/{sid}/delete",
                 {"confirm": "Wegweiser löschen", "version": str(version + 1)},
                 f"/signage/{sid}/delete").status_code == 409
    assert _post(c, f"/signage/{sid}/delete",
                 {"confirm": "Wegweiser löschen", "version": str(version)},
                 f"/signage/{sid}/delete").status_code == 303
    assert client().get(f"/signage/view/{sid}").status_code == 404
    assert c.get(f"/signage/{sid}/edit").status_code == 404
    assert client().get(f"/signage/api/device/{did}/manifest",
                        headers={"Authorization": f"Bearer {token}"}).status_code == 403
    with SessionLocal() as db:
        assert db.get(SignageScreen, sid) is None
        assert db.get(SignageDevice, did) is None
        assert not list(db.scalars(select(SignageRevision).where(SignageRevision.screen_id == sid)))


def test_screen_delete_cleans_generated_link_and_campaign_assignment(place):
    c = _admin()
    sid, _ = _setup(c, place, "sign_building")
    building, floor, room, origin = place
    with SessionLocal() as db:
        db.add(SignageGeneratedScreen(generator_key=f"cleanup:{sid}", screen_id=sid))
        campaign = SignageCampaign(
            building_id=building, room_id=room, created_by=None,
            preset="council", title="Testkampagne", published=False)
        db.add(campaign);db.flush()
        cid = campaign.id
        db.add(SignageCampaignScreen(screen_id=sid, campaign_id=cid, included=True))
        db.commit()
        version = db.get(SignageScreen, sid).version
        name = db.get(SignageScreen, sid).name
    assert _post(c, f"/signage/{sid}/delete",
                 {"confirm": name, "version": version},
                 f"/signage/{sid}/delete").status_code == 303
    with SessionLocal() as db:
        assert db.get(SignageCampaign, cid) is not None
        assert not db.scalar(select(SignageGeneratedScreen).where(
            SignageGeneratedScreen.screen_id == sid))
        assert not list(db.scalars(select(SignageCampaignScreen).where(
            SignageCampaignScreen.screen_id == sid)))
