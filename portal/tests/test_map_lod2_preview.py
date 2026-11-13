"""Native roof-facet LoD2 preview and defensive import tests.

No external requests or real DGM model are necessary; tests use a tiny
CityGML 2.0 fixture with EPSG:25832 roof and wall facets.
"""
from pathlib import Path

import pytest

from app import map_lod2 as lod2
from conftest import client, csrf_of, login, settings
from test_circulations import actors


CITYGML = b"""<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0"
                xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
                xmlns:gml="http://www.opengis.net/gml"
                xmlns:xlink="http://www.w3.org/1999/xlink">
  <gml:boundedBy><gml:Envelope srsName="urn:ogc:def:crs:EPSG::25832"
                              srsDimension="3"/></gml:boundedBy>
  <core:cityObjectMember>
    <bldg:Building gml:id="b-1">
      <bldg:boundedBy><bldg:RoofSurface>
        <gml:Polygon gml:id="roof-a"><gml:exterior><gml:LinearRing>
          <gml:posList srsDimension="3">410000 5480000 122
            410010 5480000 122 410010 5480010 128
            410000 5480010 128 410000 5480000 122</gml:posList>
        </gml:LinearRing></gml:exterior></gml:Polygon>
      </bldg:RoofSurface></bldg:boundedBy>
      <bldg:boundedBy><bldg:WallSurface>
        <gml:Polygon gml:id="wall-a"><gml:exterior><gml:LinearRing>
          <gml:posList srsDimension="3">410000 5480000 104
            410010 5480000 104 410010 5480000 122
            410000 5480000 122 410000 5480000 104</gml:posList>
        </gml:LinearRing></gml:exterior></gml:Polygon>
      </bldg:WallSurface></bldg:boundedBy>
    </bldg:Building>
  </core:cityObjectMember>
</core:CityModel>
"""


def test_native_roof_triangulation_has_different_heights_from_flat_lod1():
    result = lod2.convert(CITYGML)
    assert result["format"] == "takt-lod2-mesh/1"
    assert result["horizontal_crs"] == "EPSG:25832"
    assert result["roof_polygons"] == result["wall_polygons"] == 1
    assert result["triangles"] == 4
    assert result["height_origin_m"] == 104
    assert len(result["vertices"]) == 12
    assert all(len(v) == 4 for v in result["vertices"])
    assert {v[2] for v in result["vertices"] if v[3] == 1} == {18, 24}
    assert result["bbox"][0] < result["bbox"][2]
    assert result["bbox"][1] < result["bbox"][3]
    assert result["attribution"].startswith("© GeoBasis-DE")


def test_input_is_bounded_and_rejects_external_entities():
    with pytest.raises(ValueError, match="4 MiB"):
        lod2.convert(b"x" * (lod2.MAX_UPLOAD + 1))
    with pytest.raises(ValueError, match="DTD"):
        lod2.convert(b'<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]>'
                     + CITYGML)
    with pytest.raises(ValueError, match="CityModel"):
        lod2.convert(b"<wrong/>")
    with pytest.raises(ValueError, match="EPSG:25832"):
        lod2.convert(CITYGML.replace(b"25832", b"4326"))


def test_no_silent_fallback_for_holes_and_roofless_models():
    with pytest.raises(ValueError, match="RoofSurface"):
        lod2.convert(CITYGML.replace(b"RoofSurface", b"GroundSurface"))
    hole = CITYGML.replace(
        b"</gml:exterior></gml:Polygon>",
        b"</gml:exterior><gml:interior><gml:LinearRing>"
        b"<gml:posList>410001 5480001 122 410002 5480001 122 "
        b"410001 5480002 122 410001 5480001 122</gml:posList>"
        b"</gml:LinearRing></gml:interior></gml:Polygon>", 1)
    with pytest.raises(ValueError, match="RoofSurface"):
        lod2.convert(hole)


def test_atomic_storage_status_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(lod2, "mesh_path", lambda: tmp_path / "maps3d" / "preview.json")
    assert not lod2.status()["available"]
    result = lod2.convert(CITYGML)
    lod2.save(result)
    meta = lod2.status()
    assert meta["available"] is True
    assert "vertices" not in meta
    assert meta["roof_polygons"] == 1
    original = lod2.mesh_path().read_bytes()
    with pytest.raises(ValueError):
        lod2.save({"format": "wrong"})
    assert lod2.mesh_path().read_bytes() == original
    lod2.remove()
    assert not lod2.status()["available"]


@pytest.fixture
def maps3d_admin(db, actors, tmp_path, monkeypatch):
    monkeypatch.setattr(lod2, "mesh_path", lambda: tmp_path / "maps3d" / "preview.json")
    settings(module_maps="1")
    actors[0].permissions += ",maps_admin,maps"
    db.commit()
    return login(actors[0].email, "passwort-test-123")


def test_lod2_preview_is_protected_import_is_opt_in(maps3d_admin):
    guest = client()
    assert guest.get("/maps/lod2/status").status_code in (303, 401, 403)
    assert guest.get("/maps/lod2/mesh").status_code in (303, 401, 403)
    assert guest.post("/admin/maps/lod2/import",
                      files={"file": ("x.gml", CITYGML)}).status_code in (303, 400, 401, 403)
    admin = maps3d_admin
    assert admin.get("/maps/lod2/status").json() == {"available": False}
    assert admin.get("/maps/lod2/mesh").status_code == 404
    assert admin.post("/admin/maps/lod2/import",
                      files={"file": ("x.gml", CITYGML)}).status_code == 400
    csrf = csrf_of(admin.get("/admin/maps").text)
    posted = admin.post("/admin/maps/lod2/import", data={"csrf": csrf},
                        files={"file": ("test-lod2.gml", CITYGML, "application/xml")})
    assert posted.status_code == 200, posted.text
    assert posted.json()["ok"] is True
    mesh = admin.get("/maps/lod2/mesh")
    assert mesh.status_code == 200
    assert mesh.headers["cache-control"] == "private, no-store"
    assert mesh.json()["roof_polygons"] == 1
    assert mesh.json()["vertices"]
    page = admin.get("/karte").text
    assert 'id="map-lod2-toggle"' in page
    assert "/static/map-lod2.js" in page
    assert 'id="lod2-import-form"' in admin.get("/admin/maps").text
    deleted = admin.post("/admin/maps/lod2/delete", data={"csrf": csrf})
    assert deleted.status_code == 303
    assert admin.get("/maps/lod2/status").json() == {"available": False}
