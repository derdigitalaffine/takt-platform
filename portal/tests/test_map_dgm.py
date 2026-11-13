"""RLP DGM XYZ relief preview: geodetic alignment, decimation and access tests."""
import pytest

from app import map_dgm as dgm, map_lod2 as lod2
from conftest import client, csrf_of, login, settings
from test_circulations import actors
from test_map_lod2_preview import CITYGML


def xyz(nx=3, ny=3, spacing=5, offset=0):
    return "\n".join(
        f"{410000 + offset + x * spacing} {5480000 + y * spacing} "
        f"{103 + x * 2 + y}"
        for y in range(ny) for x in range(nx)
    ).encode("ascii")


def building():
    return lod2.convert(CITYGML) | {"available": True}


def test_dgm_alignment_uses_same_height_origin_as_lod2():
    base = building()
    model = dgm.convert_xyz(xyz(), base)
    assert model["format"] == "takt-dgm-mesh/1"
    assert model["height_origin_m"] == base["height_origin_m"] == 104
    assert model["loD2_sha256"] == base["sha256"]
    assert model["height_crs"].startswith("EPSG:7837")
    assert model["horizontal_crs"] == "EPSG:25832"
    assert model["grid_spacing_m"] == 5
    assert model["triangles"] == 8
    assert model["decimation_stride"] == 1
    assert len(model["vertices"]) == 24
    assert model["min_height_relative_m"] == -1
    assert model["max_height_relative_m"] == 5
    assert all(v[3] == 2 for v in model["vertices"])
    assert any(v[2] < 0 for v in model["vertices"])
    assert model["bbox"][0] < base["bbox"][2]


def test_dgm_larger_grid_is_decimated_without_exceeding_webgl_limit():
    model = dgm.convert_xyz(xyz(nx=121, ny=121), building())
    assert model["sample_count"] == 14641
    assert model["decimation_stride"] > 1
    assert 0 < model["triangles"] <= dgm.MAX_TRIANGLES
    assert len(model["vertices"]) == 3 * model["triangles"]
    assert model["skipped_cells"] == 0


def test_missing_dgm_cells_are_not_interpolated():
    subset = xyz(nx=4, ny=4).decode().splitlines()
    subset = [line for line in subset if not line.startswith("410005 5480005 ")]
    model = dgm.convert_xyz("\n".join(subset).encode(), building())
    assert model["skipped_cells"] > 0
    assert model["triangles"] > 0


@pytest.mark.parametrize("input_data,pattern", [
    (b"", "12 MiB"),
    (b"\x00\x01\x02", "ASCII"),
    (b"410000 5480000 nope", "Zahlen"),
    (b"410000,5480000,103", "X Y Z"),
    (b"410000 5480000 NaN", "Nicht endliche"),
    (b"410000 5480000 -9999", "Unplausible"),
    (b"1 2 3", "UTM32"),
])
def test_dgm_rejects_corrupt_or_non_xyz(input_data, pattern):
    with pytest.raises(ValueError, match=pattern):
        dgm.convert_xyz(input_data, building())


def test_dgm_requires_supported_regular_grid_and_overlapping_buildings():
    with pytest.raises(ValueError, match="Rasterweite"):
        dgm.convert_xyz(xyz(spacing=3), building())
    with pytest.raises(ValueError, match="überlappt"):
        dgm.convert_xyz(xyz(offset=3000), building())
    with pytest.raises(ValueError, match="Zuerst"):
        dgm.convert_xyz(xyz(), {"available": False})
    duplicated = xyz().decode() + "\n410000 5480000 900"
    with pytest.raises(ValueError, match="Widersprüchliche Höhen"):
        dgm.convert_xyz(duplicated.encode(), building())


def test_dgm_has_atomically_saved_version_bound_to_current_lod2(tmp_path, monkeypatch):
    monkeypatch.setattr(lod2, "mesh_path", lambda: tmp_path/"lod2.json")
    monkeypatch.setattr(dgm, "mesh_path", lambda: tmp_path/"dgm.json")
    lod2.save(building())
    model = dgm.convert_xyz(xyz(), lod2.status())
    dgm.save(model)
    assert dgm.status()["available"] is True
    assert "vertices" not in dgm.status()
    previous = dgm.mesh_path().read_bytes()
    with pytest.raises(ValueError, match="verknüpft"):
        dgm.save(model | {"loD2_sha256": "0" * 64})
    assert dgm.mesh_path().read_bytes() == previous
    # An old terrain file must never be silently attached to new buildings.
    updated = CITYGML.replace(b"410010 5480010 128", b"410010 5480010 129")
    lod2.save(lod2.convert(updated))
    assert dgm.status() == {"available": False}
    dgm.remove()
    assert not dgm.mesh_path().exists()


@pytest.fixture
def maps_dgm_admin(db, actors, tmp_path, monkeypatch):
    monkeypatch.setattr(lod2, "mesh_path", lambda: tmp_path/"lod2.json")
    monkeypatch.setattr(dgm, "mesh_path", lambda: tmp_path/"dgm.json")
    settings(module_maps="1")
    actors[0].permissions += ",maps_admin,maps"
    db.commit()
    return login(actors[0].email, "passwort-test-123")


def test_dgm_import_routes_enforce_login_csrf_height_consent_and_upload_limits(maps_dgm_admin):
    guest = client()
    assert guest.get("/maps/dgm/status").status_code in (303, 401, 403)
    assert guest.get("/maps/dgm/mesh").status_code in (303, 401, 403)
    admin = maps_dgm_admin
    assert admin.get("/maps/dgm/status").json() == {"available": False}
    assert admin.get("/maps/dgm/mesh").status_code == 404
    csrf = csrf_of(admin.get("/admin/maps").text)
    assert admin.post("/admin/maps/dgm/import", data={"csrf": csrf},
                      files={"file": ("test.xyz", xyz())}).status_code == 422
    assert admin.post("/admin/maps/dgm/import",
                      data={"confirm_dhhn2016": "1"},
                      files={"file": ("test.xyz", xyz())}).status_code == 400
    assert admin.post("/admin/maps/dgm/import",
                      data={"csrf": csrf, "confirm_dhhn2016": "1"},
                      files={"file": ("bad.gml", xyz())}).status_code == 422
    # Uploading a DGM without matching LoD2 is forbidden by the converter.
    assert admin.post("/admin/maps/dgm/import",
                      data={"csrf": csrf, "confirm_dhhn2016": "1"},
                      files={"file": ("test.xyz", xyz())}).status_code == 422

    lod2.save(building())
    result = admin.post("/admin/maps/dgm/import",
                        data={"csrf": csrf, "confirm_dhhn2016": "1"},
                        files={"file": ("test.xyz", xyz(), "text/plain")})
    assert result.status_code == 200, result.text
    assert result.json()["ok"] is True
    mesh = admin.get("/maps/dgm/mesh")
    assert mesh.status_code == 200
    assert mesh.headers["cache-control"] == "private, no-store"
    assert mesh.json()["triangles"] == 8
    assert 'id="dgm-import-form"' in admin.get("/admin/maps").text
    page = admin.get("/karte").text
    assert 'id="map-dgm-toggle"' in page
    assert "/static/map-dgm-admin.js" in admin.get("/admin/maps").text
    assert "/static/map-lod2.js" in page
    response = admin.post("/admin/maps/dgm/delete", data={"csrf": csrf})
    assert response.status_code == 303
    assert admin.get("/maps/dgm/status").json() == {"available": False}
