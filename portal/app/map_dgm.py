"""Strict, local DGM ASCII-XYZ preview for LVermGeo Rheinland-Pfalz.

DGM elevations (DHHN2016 NH, EPSG:7837) can be combined *relatively* with
a locally imported LoD2 building excerpt only when the admin confirms that
both inputs use the same official vertical datum. The conversion is a bounded
triangulated relief, NOT a certified geodetic transform or a terrain-RGB/3D
Tiles provider. Never downloads remote data or executes uploaded content.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import tempfile

from . import map_lod2 as lod2
from .config import settings

FORMAT = "takt-dgm-mesh/1"
MESH_NAME = "dgm-preview.json"
MAX_UPLOAD = 12 * 1024 * 1024
MAX_SAMPLES = 180000
MAX_TRIANGLES = 12000
MAX_RENDER_BYTES = 4 * 1024 * 1024
MAX_SPAN_M = 1500
GRID_TOLERANCE_M = 0.025
SUPPORTED_GRID_M = (1, 2, 5, 10, 25, 50)


def mesh_path() -> Path:
    return settings.data_dir / "maps3d" / MESH_NAME


def _grid_spacing(values: list[float]) -> float:
    if len(values) < 2:
        raise ValueError("Die Geländedaten benötigen mindestens zwei Gitterlinien je Richtung.")
    diffs = [round(b - a, 3) for a, b in zip(values, values[1:])]
    step = min(diffs)
    if step < 0.5 or step > 50:
        raise ValueError("Ungültige Rasterweite. Bitte ein DGM-Raster von 1–50 m auswählen.")
    supported = min(SUPPORTED_GRID_M, key=lambda n: abs(n - step))
    if abs(step - supported) > GRID_TOLERANCE_M:
        raise ValueError("Keine unterstützte DGM-Rasterweite erkannt.")
    if any(abs((value / supported) - round(value / supported)) > GRID_TOLERANCE_M / supported
           for value in diffs):
        raise ValueError("Unregelmäßige Gitterabstände; kein rechteckiges DGM-XYZ-Raster.")
    return float(supported)


def _validate_building(building: dict) -> None:
    if (not building.get("available")
            or building.get("format") != lod2.FORMAT
            or building.get("horizontal_crs") != "EPSG:25832"
            or not isinstance(building.get("height_origin_m"), (float, int))
            or not isinstance(building.get("sha256"), str)
            or len(building["sha256"]) != 64):
        raise ValueError("Zuerst eine gültige LoD2-Gebäudevorschau importieren.")


def convert_xyz(raw: bytes, building: dict) -> dict:
    """Build a small, decimated DGM relief in the LoD2 model's *relative* Z frame.

    Input is official ASCII XYZ: one easting northing height triple per line.
    Samples with missing neighbours are not bridged or interpolated. Vertical
    equivalence is declared by the uploader, not inferred from the XYZ format.
    """
    _validate_building(building)
    if not raw or len(raw) > MAX_UPLOAD:
        raise ValueError("Bitte eine örtliche DGM-XYZ-Datei bis 12 MiB auswählen.")
    if b"\x00" in raw:
        raise ValueError("Bitte eine ASCII-XYZ-Textdatei statt eines Binärformats hochladen.")
    try:
        txt = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("DGM-XYZ muss als UTF-8/ASCII-Text vorliegen.") from exc

    samples: dict[tuple[float, float], float] = {}
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = re.split(r"[\s;]+", line)
        if len(cols) != 3:
            raise ValueError("Jede DGM-XYZ-Zeile muss X Y Z enthalten.")
        try:
            east, north, height = (float(v) for v in cols)
        except ValueError as exc:
            raise ValueError("Ungültige Zahlen in den DGM-XYZ-Koordinaten.") from exc
        if not all(math.isfinite(v) for v in (east, north, height)):
            raise ValueError("Nicht endliche DGM-Koordinaten sind nicht erlaubt.")
        if not (250000 <= east <= 750000 and 5300000 <= north <= 5750000):
            raise ValueError("XYZ liegt außerhalb des unterstützten UTM32-Gebiets.")
        if not (-100 <= height <= 2000):
            raise ValueError("Unplausible NH-Höhenangaben in der DGM-Datei.")
        east, north = round(east, 3), round(north, 3)
        key = east, north
        if key in samples and abs(samples[key] - height) > 0.001:
            raise ValueError("Widersprüchliche Höhen an einem identischen Rasterpunkt.")
        samples[key] = height
        if len(samples) > MAX_SAMPLES:
            raise ValueError("Zu viele Höhenpunkte; bitte eine kleinere oder gröbere DGM-Kachel wählen.")
    if len(samples) < 4:
        raise ValueError("Mindestens vier DGM-Rasterpunkte sind erforderlich.")

    xs = sorted({xy[0] for xy in samples})
    ys = sorted({xy[1] for xy in samples})
    if xs[-1] - xs[0] > MAX_SPAN_M or ys[-1] - ys[0] > MAX_SPAN_M:
        raise ValueError("Die lokale Vorschau ist auf 1,5 km Kantenlänge begrenzt.")
    step_x, step_y = _grid_spacing(xs), _grid_spacing(ys)
    if abs(step_x - step_y) > GRID_TOLERANCE_M:
        raise ValueError("Rasterweite in X und Y muss übereinstimmen.")
    if len(xs) * len(ys) > MAX_SAMPLES:
        raise ValueError("Das DGM-Raster ist für eine lokale 3D-Vorschau zu groß.")

    sw = lod2.utm32_wgs84(xs[0], ys[0])
    ne = lod2.utm32_wgs84(xs[-1], ys[-1])
    bounds = [min(sw[0], ne[0]), min(sw[1], ne[1]),
              max(sw[0], ne[0]), max(sw[1], ne[1])]
    footprint = building.get("bbox")
    if (not isinstance(footprint, list) or len(footprint) != 4
            or bounds[0] > footprint[2] or bounds[2] < footprint[0]
            or bounds[1] > footprint[3] or bounds[3] < footprint[1]):
        raise ValueError("Das DGM überlappt nicht den LoD2-Gebäudeausschnitt.")

    # Decimate reproducibly to stay below mobile WebGL memory and file limits,
    # retaining both boundary rows and columns.
    stride = 1
    while (2 * math.ceil((len(xs)-1)/stride) *
           math.ceil((len(ys)-1)/stride) > MAX_TRIANGLES):
        stride += 1
    x_indices = list(range(0, len(xs)-1, stride)) + [len(xs)-1]
    y_indices = list(range(0, len(ys)-1, stride)) + [len(ys)-1]

    origin = float(building["height_origin_m"])
    triangulated: list[list[float]] = []
    skipped = 0
    used: dict[tuple[float, float], list[float]] = {}

    def vertex(x: float, y: float) -> list[float]:
        key = (x, y)
        if key not in used:
            lon, lat = lod2.utm32_wgs84(x, y)
            z = round(samples[key] - origin, 3)
            used[key] = [lon, lat, z, 2]  # 2: terrain, 1: roof, 0: wall
        return used[key]

    for ia, ib in zip(x_indices, x_indices[1:]):
        for ja, jb in zip(y_indices, y_indices[1:]):
            # Do not bridge NoData gaps, even if a *complete* grid line is
            # missing from XYZ (otherwise there is no matching xs/ys index).
            if (any(xs[i+1] - xs[i] > step_x + GRID_TOLERANCE_M
                    for i in range(ia, ib)) or
                any(ys[j+1] - ys[j] > step_y + GRID_TOLERANCE_M
                    for j in range(ja, jb)) or
                any((xs[i], ys[j]) not in samples
                    for i in range(ia, ib+1) for j in range(ja, jb+1))):
                skipped += 1
                continue
            p00 = vertex(xs[ia], ys[ja])
            p10 = vertex(xs[ib], ys[ja])
            p11 = vertex(xs[ib], ys[jb])
            p01 = vertex(xs[ia], ys[jb])
            triangulated.extend((p00, p10, p11, p00, p11, p01))

    if not triangulated:
        raise ValueError("Keine zusammenhängenden DGM-Rasterflächen gefunden.")
    result = {
        "format": FORMAT, "source": "LVermGeo Rheinland-Pfalz / manuell bereitgestellte DGM-XYZ-Datei",
        "attribution": "© GeoBasis-DE / LVermGeoRP, dl-de/by-2-0, www.lvermgeo.rlp.de [Daten bearbeitet]",
        "licence": "DL-DE BY 2.0", "horizontal_crs": "EPSG:25832",
        "height_crs": "EPSG:7837 (von Administration bestätigt, nicht automatisch verifiziert)",
        "height_reference": "relative to LoD2 height_origin_m; not ellipsoidal terrain height",
        "height_origin_m": origin,
        "loD2_sha256": building["sha256"],
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "sha256": sha256(raw).hexdigest(), "bbox": bounds, "grid_spacing_m": step_x,
        "sample_count": len(samples), "sampled_vertices": len(used),
        "skipped_cells": skipped, "decimation_stride": stride,
        "min_height_relative_m": min(p[2] for p in used.values()),
        "max_height_relative_m": max(p[2] for p in used.values()),
        "triangles": len(triangulated) // 3, "vertices": triangulated,
    }
    if result["triangles"] > MAX_TRIANGLES:
        raise ValueError("DGM-Geländemodell überschreitet die Dreiecksgrenze.")
    if len(json.dumps(result, separators=(",", ":")).encode()) > MAX_RENDER_BYTES:
        raise ValueError("Die konvertierte DGM-Vorschau ist zu groß.")
    return result


def save(mesh: dict) -> None:
    """Atomic replacement; corrupt uploads do not affect the previous model."""
    if (mesh.get("format") != FORMAT or not mesh.get("vertices")
            or mesh.get("loD2_sha256") != lod2.status().get("sha256")):
        raise ValueError("DGM-Modell ist nicht mit der aktuellen LoD2-Vorschau verknüpft.")
    target = mesh_path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=target.parent, prefix=".dgm-",
                suffix=".tmp", delete=False) as stream:
            tmp = stream.name
            os.chmod(tmp, 0o600)
            json.dump(mesh, stream, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, target)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def status() -> dict:
    target = mesh_path()
    if not target.is_file():
        return {"available": False}
    try:
        if target.stat().st_size > MAX_RENDER_BYTES:
            raise ValueError("too large")
        data = json.loads(target.read_text(encoding="utf-8"))
        if (data.get("format") != FORMAT or
                not isinstance(data.get("vertices"), list) or
                data.get("loD2_sha256") != lod2.status().get("sha256") or
                not lod2.status().get("available")):
            raise ValueError("stale terrain")
        return {key: data[key] for key in (
            "format", "source", "attribution", "licence", "horizontal_crs",
            "height_crs", "height_reference", "height_origin_m", "loD2_sha256",
            "imported_at", "sha256", "bbox", "grid_spacing_m", "sample_count",
            "sampled_vertices", "skipped_cells", "decimation_stride",
            "min_height_relative_m", "max_height_relative_m", "triangles"
        )} | {"available": True}
    except (OSError, ValueError, KeyError, TypeError):
        return {"available": False}


def remove() -> None:
    mesh_path().unlink(missing_ok=True)
