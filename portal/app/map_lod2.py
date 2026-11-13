"""Bounded CityGML LoD2 preview importer for the existing TAKT MapLibre browser.

This is intentionally NOT a nationwide LoD2 tile pipeline. One small, trusted
administrative import is turned into projected roof/wall triangles on disk.
A datum-aware DGM renderer, large datasets, holes/xlinks and arbitrary CRS
transformations are not implied by this module.
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
from xml.etree import ElementTree as ET

from .config import settings

MAX_UPLOAD = 4 * 1024 * 1024
MAX_POLYGONS = 3500
MAX_TRIANGLES = 16000
MAX_VERTICES_PER_POLYGON = 160
MAX_RENDER_BYTES = 4 * 1024 * 1024
MESH_NAME = "lod2-preview.json"
FORMAT = "takt-lod2-mesh/1"


def mesh_path() -> Path:
    return settings.data_dir / "maps3d" / MESH_NAME


def _name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def utm32_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """ETRS89 UTM zone 32N to WGS84 for a *bounded RLP visual preview*.

    This is not a geodetic transformation or a vertical datum correction.
    Exact surveying work must use a certified projection pipeline.
    """
    if not (250000 <= easting <= 750000 and 5300000 <= northing <= 5750000):
        raise ValueError("Koordinaten außerhalb des unterstützten UTM32-Gebiets.")
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    x = easting - 500000
    mu = (northing / k0) / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    phi = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
           + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
           + 151 * e1**3 / 96 * math.sin(6 * mu))
    N = a / math.sqrt(1 - e2 * math.sin(phi)**2)
    T, C = math.tan(phi)**2, ep2 * math.cos(phi)**2
    R = a * (1 - e2) / (1 - e2 * math.sin(phi)**2)**1.5
    D = x / (N * k0)
    lat = phi - (N * math.tan(phi) / R) * (
        D**2 / 2 - (5 + 3 * T + 10 * C - 4 * C**2 - 9 * ep2) * D**4 / 24)
    lon = math.radians(9) + (
        D - (1 + 2 * T + C) * D**3 / 6
        + (5 - 2 * C + 28 * T - 3 * C**2 + 8 * ep2 + 24 * T**2)
        * D**5 / 120) / math.cos(phi)
    return round(math.degrees(lon), 8), round(math.degrees(lat), 8)


def _triangulate(points: list[tuple[float, float, float]]) -> list[tuple]:
    """Ear clipping on the dominant face plane; refuse holes and degenerate faces."""
    n = len(points)
    if n < 3 or n > MAX_VERTICES_PER_POLYGON:
        raise ValueError("Nicht unterstützte Polygon-Größe.")
    # Select a stable 2D projection even for near-vertical wall faces.
    nx = ny = nz = 0.0
    for i, p in enumerate(points):
        q = points[(i + 1) % n]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    dominant = max(range(3), key=lambda k: abs((nx, ny, nz)[k]))
    if max(abs(nx), abs(ny), abs(nz)) < 1e-5:
        raise ValueError("Degenerierte Fläche.")
    uv = [(p[(dominant + 1) % 3], p[(dominant + 2) % 3]) for p in points]
    area = sum(uv[i][0] * uv[(i + 1) % n][1]
               - uv[(i + 1) % n][0] * uv[i][1] for i in range(n))
    if abs(area) < 1e-7:
        raise ValueError("Polygonfläche zu klein.")
    sign = 1 if area > 0 else -1

    def cross(a, b, c):
        return (uv[b][0] - uv[a][0]) * (uv[c][1] - uv[a][1]) - (
            uv[b][1] - uv[a][1]) * (uv[c][0] - uv[a][0])

    def inside(a, b, c, p):
        return (sign * cross(a, b, p) >= -1e-9
                and sign * cross(b, c, p) >= -1e-9
                and sign * cross(c, a, p) >= -1e-9)

    indices = list(range(n))
    result = []
    for _ in range(n):
        if len(indices) == 3:
            result.append(tuple(points[i] for i in indices))
            return result
        found = False
        for j in range(len(indices)):
            a, b, c = (indices[(j - 1) % len(indices)], indices[j],
                       indices[(j + 1) % len(indices)])
            if sign * cross(a, b, c) <= 1e-9:
                continue
            if any(inside(a, b, c, p) for p in indices if p not in (a, b, c)):
                continue
            result.append((points[a], points[b], points[c]))
            indices.pop(j)
            found = True
            break
        if not found:
            raise ValueError("Polygon kann ohne Geometrieverlust nicht trianguliert werden.")
    raise ValueError("Geometrie ist ungültig.")


def convert(raw: bytes) -> dict:
    """Convert a small, local 3D CityGML 2.0/3.0 EPSG:25832 excerpt."""
    if not raw or len(raw) > MAX_UPLOAD:
        raise ValueError("Bitte eine CityGML-Datei bis 4 MiB auswählen.")
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)", raw, re.I):
        raise ValueError("DTD und XML-Entitäten sind bei CityGML nicht erlaubt.")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("Die CityGML-Datei enthält ungültiges XML.") from exc
    if _name(root.tag) != "CityModel":
        raise ValueError("Erwartet wird eine CityGML-CityModel-Datei.")
    references = {v for el in root.iter()
                  for k, v in el.attrib.items() if _name(k) == "srsName"}
    if not references or any(
        not re.search(r"(?:EPSG[:/]+|/EPSG/0/)25832$", ref, re.I)
        for ref in references
    ):
        raise ValueError("Nur ausdrücklich deklarierte CityGML-Daten in EPSG:25832 werden unterstützt.")
    if len(list(root.iter())) > 150000:
        raise ValueError("Zu viele XML-Elemente für die interaktive Vorschau.")

    faces: list[tuple[int, list[tuple]]] = []
    skipped = 0
    roof_count = wall_count = 0
    seen = set()
    # Each boundedBy surface is visited once; no remote xlink dereferencing.
    for surface in root.iter():
        kind = _name(surface.tag)
        if kind not in ("RoofSurface", "WallSurface", "GroundSurface"):
            continue
        material = 1 if kind == "RoofSurface" else 0
        for polygon in surface.iter():
            if _name(polygon.tag) != "Polygon":
                continue
            if len(faces) >= MAX_POLYGONS:
                raise ValueError("Zu viele Flächen. Bitte kleinere CityGML-Kachel importieren.")
            if any(_name(e.tag) == "interior" for e in polygon.iter()):
                skipped += 1
                continue
            exteriors = [e for e in polygon if _name(e.tag) == "exterior"]
            if len(exteriors) != 1:
                skipped += 1
                continue
            pos_lists = [e for e in exteriors[0].iter() if _name(e.tag) == "posList"]
            if len(pos_lists) != 1:
                skipped += 1
                continue
            node = pos_lists[0]
            dim = node.get("srsDimension") or node.get("dimension") or "3"
            if dim != "3":
                skipped += 1
                continue
            try:
                values = [float(s) for s in (node.text or "").split()]
                if len(values) % 3 or len(values) < 9 or len(values) > (MAX_VERTICES_PER_POLYGON + 1) * 3:
                    raise ValueError("Bad coordinate count")
                points = [tuple(values[i:i + 3]) for i in range(0, len(values), 3)]
                if not all(math.isfinite(x) for xyz in points for x in xyz):
                    raise ValueError("Not finite")
                # Restrict absurd altitudes before attempting any projection.
                if any(not (-100 <= p[2] <= 2000) for p in points):
                    raise ValueError("Invalid elevation")
                if points[0] == points[-1]:
                    points.pop()
                # Adjacent repeated coordinates and identical surfaces cause
                # invalid triangles and unnecessary WebGL work.
                points = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
                key = (kind, tuple(points))
                if key in seen:
                    continue
                seen.add(key)
                triangles = _triangulate(points)
                for xyz in points:
                    utm32_wgs84(xyz[0], xyz[1])
            except (ValueError, OverflowError):
                skipped += 1
                continue
            if sum(len(group[1]) for group in faces) + len(triangles) > MAX_TRIANGLES:
                raise ValueError("Zu viele Dreiecke für die Vorschau.")
            faces.append((material if kind != "GroundSurface" else -1, triangles))
            if kind == "RoofSurface":
                roof_count += 1
            elif kind == "WallSurface":
                wall_count += 1

    if not roof_count or not wall_count:
        raise ValueError("LoD2-Vorschau benötigt echte RoofSurface- und WallSurface-Geometrien.")
    all_z = [p[2] for _, polygons in faces for triangle in polygons for p in triangle]
    baseline = min(all_z)
    vertices: list[list[float]] = []
    bbox = [180.0, 90.0, -180.0, -90.0]
    for material, polygons in faces:
        if material == -1:
            continue
        for triangle in polygons:
            for east, north, z in triangle:
                lon, lat = utm32_wgs84(east, north)
                bbox[0] = min(bbox[0], lon)
                bbox[1] = min(bbox[1], lat)
                bbox[2] = max(bbox[2], lon)
                bbox[3] = max(bbox[3], lat)
                vertices.append([lon, lat, round(z - baseline, 3), material])
    result = {
        "format": FORMAT, "source": "LVermGeo Rheinland-Pfalz / nutzerseitig bereitgestellte CityGML",
        "attribution": "© GeoBasis-DE / LVermGeoRP, dl-de/by-2-0, www.lvermgeo.rlp.de [Daten bearbeitet]",
        "licence": "DL-DE BY 2.0", "horizontal_crs": "EPSG:25832",
        "height_reference": "relative-preview; DHHN2016 is not transformed to terrain",
        "height_origin_m": round(baseline, 3),
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "sha256": sha256(raw).hexdigest(), "bbox": bbox, "roof_polygons": roof_count,
        "wall_polygons": wall_count, "skipped_polygons": skipped,
        "triangles": len(vertices) // 3, "vertices": vertices,
    }
    if len(json.dumps(result, separators=(",", ":")).encode()) > MAX_RENDER_BYTES:
        raise ValueError("Die konvertierte Geometrie ist für die Vorschau zu groß.")
    return result


def save(mesh: dict) -> None:
    """Persist only a validated local preview; atomic replacement keeps the last good model."""
    if mesh.get("format") != FORMAT or not mesh.get("vertices"):
        raise ValueError("Ungültiges 3D-Vorschaumodell.")
    target = mesh_path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=target.parent, prefix=".lod2-",
            suffix=".tmp", delete=False
        ) as stream:
            tmp_name = stream.name
            os.chmod(tmp_name, 0o600)
            json.dump(mesh, stream, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp_name, target)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def status() -> dict:
    target = mesh_path()
    if not target.is_file():
        return {"available": False}
    try:
        if target.stat().st_size > MAX_RENDER_BYTES:
            raise ValueError("too large")
        data = json.loads(target.read_text(encoding="utf-8"))
        if data.get("format") != FORMAT or not isinstance(data.get("vertices"), list):
            raise ValueError("bad file")
        return {key: data[key] for key in (
            "format", "source", "attribution", "licence", "horizontal_crs",
            "height_reference", "height_origin_m", "imported_at", "sha256",
            "bbox", "roof_polygons", "wall_polygons", "skipped_polygons", "triangles"
        )} | {"available": True}
    except (OSError, ValueError, KeyError, TypeError):
        return {"available": False}


def remove() -> None:
    mesh_path().unlink(missing_ok=True)
