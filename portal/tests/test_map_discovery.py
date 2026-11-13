"""Public GIS discovery, consent-based railway overlays and RLP 3D products.

The catalog is metadata-only until an authenticated user explicitly selects
the exact supported capabilities layer. No private system layer is exposed.
"""
import json

import pytest
from sqlalchemy import select

from app import map_catalog, maps as mp
from app.db import MapLayer
from conftest import client, csrf_of, login, settings
from test_circulations import actors


@pytest.fixture
def admin(db, actors):
    settings(module_maps="1")
    actors[0].permissions += ",maps_admin,maps"
    db.commit()
    return login(actors[0].email, "passwort-test-123")


def test_public_catalog_is_read_only_and_categorized_without_network(db, monkeypatch):
    settings(module_maps="1")
    monkeypatch.setattr(mp, "query_service", lambda *args, **kw: pytest.fail(
        "The public directory must never request a remote GIS service"))
    internal = MapLayer(name="DO-NOT-SHOW-INTERNAL-LAYER", kind="wms",
                        role="overlay", url="https://internal.example.org/wms",
                        layers="secret", enabled=True, public=False)
    db.add(internal)
    db.commit()
    try:
        c = client()
        result = c.get("/maps/library")
        assert result.status_code == 200
        assert result.headers["cache-control"].startswith("public")
        data = result.json()
        assert len(data["services"]) >= 45
        assert "rp-dop20" in data["services"]
        assert "orm-standard" in data["services"]
        assert "rp-lod2" in data["datasets"]
        assert data["datasets"]["rp-lod2"]["format"] == "CityGML"
        assert data["datasets"]["rp-lod2"]["viewer_url"].startswith("https://")
        assert "DO-NOT-SHOW-INTERNAL-LAYER" not in result.text
        assert "https://internal.example.org" not in result.text
        filtered = c.get("/maps/library", params={
            "q": "lod2", "region": "Rheinland-Pfalz"}).json()
        assert "rp-lod2" in filtered["datasets"]
        assert not filtered["services"]
        rail = c.get("/maps/library", params={"topic": "Eisenbahn"}).json()
        assert len(rail["services"]) == 5
        assert all(s["kind"] == "xyz" for s in rail["services"].values())
        assert all(s["license_url"].startswith("https://") for s in data["services"].values())
    finally:
        db.delete(internal)
        db.commit()


def test_rp_survey_catalog_contains_attributed_ogc_and_citygml():
    assert map_catalog.CATALOG["rp-dop20"]["url"].startswith("https://www.geoportal.rlp.de/")
    assert map_catalog.CATALOG["rp-dop20"]["kind"] == "wms"
    for key in ("rp-relief1", "rp-contours", "rp-soil-estimate", "rp-dop-historic"):
        assert map_catalog.CATALOG[key]["license"] == "DL-DE BY 2.0"
    for dataset in ("rp-lod1", "rp-lod2"):
        item = map_catalog.DATASETS[dataset]
        assert item["kind"] == "download" and item["format"] == "CityGML"
        assert item["license"] == "DL-DE BY 2.0"
        assert "rlp.plexmap.de" in item["viewer_url"]
        assert item["download_url"].startswith("https://geoshop.rlp.de/")
    assert "OpenRailwayMap" in map_catalog.CATALOG["orm-standard"]["attribution"]
    assert "CC BY-SA 2.0" in map_catalog.CATALOG["orm-standard"]["license"]


def test_public_railway_activation_limited_to_curated_xyz_only(db, monkeypatch):
    settings(module_maps="1")
    monkeypatch.setattr(mp, "query_service", lambda *args, **kw:
                        pytest.fail("Railway discovery is a fixed XYZ tile template"))
    c = client()
    for key in ("orm-standard", "orm-signals", "orm-maxspeed",
                "orm-electrification", "orm-gauge"):
        r = c.get(f"/maps/library/{key}/overlay")
        assert r.status_code == 200
        data = r.json()["layer"]
        assert data["kind"] == "xyz"
        assert data["tileSize"] == 512
        assert "tiles.openrailwaymap.org" in json.dumps(data)
        assert data["attribution"]
        assert mp.unsign(data["token"])["url"] == map_catalog.CATALOG[key]["url"]
        assert data["custom"]["category"].startswith("Eisenbahn")
    for forbidden in ("rp-lod2", "rp-dop20", "de-basemap", "missing"):
        assert c.get(f"/maps/library/{forbidden}/overlay").status_code == 404
    assert c.get("/karte").status_code == 200


def test_private_capability_endpoint_requires_login_and_csrf(admin, monkeypatch):
    guest = client()
    assert guest.post("/maps/library/rp-dop20/layers").status_code in (303, 401, 403)
    assert admin.post("/maps/library/rp-dop20/layers").status_code == 400
    calls = []
    def capabilities(url, kind, guard):
        calls.append((url, kind, guard))
        return {"type": kind, "url": url, "version": "1.3.0",
                "layers": [{"name": "approved", "title": "Amtliche Ebene",
                            "supported": True},
                           {"name": "invalid", "title": "Nicht in EPSG:3857",
                            "supported": False}]}
    monkeypatch.setattr(mp, "query_service", capabilities)
    token = csrf_of(admin.get("/karte").text)
    rsp = admin.post("/maps/library/rp-dop20/layers", data={"csrf": token})
    assert rsp.status_code == 200
    assert [x["name"] for x in rsp.json()["layers"]] == ["approved"]
    assert calls == [(map_catalog.CATALOG["rp-dop20"]["url"], "wms", True)]
    assert rsp.json()["source"]["license"] == "DL-DE BY 2.0"
    assert admin.post("/maps/library/nonexistent/layers", data={"csrf": token}).status_code == 404


def test_unavailable_provider_is_friendly_and_does_not_change_system_layers(admin, monkeypatch, db):
    import httpx
    monkeypatch.setattr(mp, "query_service", lambda *a: (_ for _ in ()).throw(
        httpx.ConnectTimeout("no service")))
    before = db.scalar(select(MapLayer.id).limit(1))
    csrf = csrf_of(admin.get("/karte").text)
    r = admin.post("/maps/library/rp-dop20/layers", data={"csrf": csrf})
    assert r.status_code == 502
    assert r.json()["ok"] is False
    assert "momentan nicht verfügbar" in r.json()["error"]
    assert before == db.scalar(select(MapLayer.id).limit(1))


def test_xyz_source_never_queries_capabilities_or_creates_hidden_admin_layer(admin, monkeypatch, db):
    monkeypatch.setattr(mp, "query_service", lambda *a: pytest.fail(
        "XYZ must not call a WMS GetCapabilities endpoint"))
    token = csrf_of(admin.get("/karte").text)
    resp = admin.post("/maps/library/orm-standard/layers", data={"csrf": token})
    assert resp.status_code == 200
    assert resp.json()["type"] == "xyz"
    assert resp.json()["layers"][0]["service"]["tile_size"] == 512
    # Administrative import remains explicit, disabled and private until
    # independently reviewed by a manager.
    before = db.scalar(select(MapLayer.id).where(
        MapLayer.url == map_catalog.CATALOG["orm-standard"]["url"]))
    assert before is None
    imported = admin.post("/admin/maps/library/orm-standard/import",
                          data={"csrf": token, "layers": "orm-standard"})
    assert imported.status_code == 303
    db.expire_all()
    row = db.scalar(select(MapLayer).where(
        MapLayer.url == map_catalog.CATALOG["orm-standard"]["url"]))
    try:
        assert row is not None
        assert row.kind == "xyz" and row.tile_size == 512
        assert row.enabled is False and row.public is False
        assert row.default_visible is False
    finally:
        if row:
            db.delete(row)
            db.commit()


def test_browser_discovery_and_3d_controls_remain_in_read_only_view(admin):
    public_page = client().get("/karte")
    private_page = admin.get("/karte")
    for page in (public_page, private_page):
        assert page.status_code == 200
        for element in ('id="map-discovery-search"', 'id="map-discovery-region"',
                        'id="map-discovery-topic"', 'id="map-discovery-favorites-only"',
                        'id="overlay-only-active"', 'id="map-3d-view"',
                        'data-discovery-topic="Wasser und Hochwasser"',
                        'data-discovery-topic="3D-Gebäude"',
                        'id="map-discovery-source-links"'):
            assert element in page.text
    assert 'id="map-discovery-activate" type="button" disabled' in public_page.text
    assert 'id="map-discovery-activate" type="button" disabled' not in private_page.text
    # Actual public XYZ activation is allowed client-side only after click.


def test_3d_perspective_and_extrusion_settings_are_saved_safely():
    from app.routes_maps import _clean_state
    from app import maps as mp

    restored = _clean_state({
        "center": [7.77, 49.49], "zoom": 14, "pitch": 55,
        "base": "s1",
        "layers": [{"id": "s1", "visible": True, "opacity": 0.55,
                    "time": "", "extrude": True}],
        "custom": [{
            "def": {"kind": "wfs",
                    "url": "https://gis.example.org/wfs",
                    "layers": "building",
                    "name": "Gebäudekörper",
                    "category": "3D · Rheinland-Pfalz",
                    "extrude": True},
            "opacity": 0.72,
        }],
    })
    assert restored["pitch"] == 55
    assert restored["layers"][0]["extrude"] is True
    assert restored["custom"][0]["def"]["extrude"] is True
    assert restored["custom"][0]["def"]["category"] == "3D · Rheinland-Pfalz"
    cfg = mp.custom_config(restored["custom"][0]["def"],
                           mp.sign(restored["custom"][0]["def"]))
    assert cfg["extrude"] is True
    assert cfg["category"] == "3D · Rheinland-Pfalz"
    # No arbitrary client-side URI or HTML gets injected into metadata.
    malicious = mp.clean_custom({"kind": "wfs",
        "url": "https://gis.example.org/wfs", "layers": "buildings",
        "category": "<script>bad</script>"})
    assert "<" not in malicious["category"]
    assert malicious["extrude"] is False
