"""Operational safety and small, allowlisted diagnostics for Digital Signage devices."""
import re
from datetime import datetime, timedelta
from fastapi import HTTPException

from .db import utcnow

PLATFORMS = {"browser", "windows", "linux", "android", "raspberry", "other"}
DIAGNOSTIC_CODES = {
    "ok": "Betriebsbereit",
    "offline_cache": "Zwischenspeicher verwendet",
    "render_error": "Darstellungsfehler",
    "clock_skew": "Geräteuhr prüfen",
    "storage_full": "Speicherplatz prüfen",
    "network_error": "Netzwerk prüfen",
}
CLIENT_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
ALLOWED_FIELDS = {
    "platform", "client_version", "screen_width", "screen_height",
    "reported_screen_version", "diagnostic_code",
}


def validate_telemetry(value):
    """Reject arbitrary PII, free text, URLs, nested payloads and oversized metrics."""
    if not isinstance(value, dict) or set(value) - ALLOWED_FIELDS:
        raise HTTPException(422, "Unzulässige Diagnosedaten.")
    result = {}
    if "platform" in value:
        if not isinstance(value["platform"], str) or value["platform"] not in PLATFORMS:
            raise HTTPException(422, "Ungültige Plattform.")
        result["platform"] = value["platform"]
    if "client_version" in value:
        item = value["client_version"]
        if not isinstance(item, str) or not CLIENT_VERSION.fullmatch(item):
            raise HTTPException(422, "Ungültige Player-Version.")
        result["client_version"] = item
    for name, maximum in (("screen_width", 16384), ("screen_height", 16384),
                          ("reported_screen_version", 1_000_000)):
        if name not in value:
            continue
        item = value[name]
        if isinstance(item, bool) or not isinstance(item, int):
            raise HTTPException(422, "Ungültige numerische Diagnosedaten.")
        lower = 320 if name != "reported_screen_version" else 0
        if item < lower or item > maximum:
            raise HTTPException(422, "Diagnosewert außerhalb des erlaubten Bereichs.")
        result[name] = item
    if "diagnostic_code" in value:
        item = value["diagnostic_code"]
        if not isinstance(item, str) or item not in DIAGNOSTIC_CODES:
            raise HTTPException(422, "Ungültiger Diagnosecode.")
        result["diagnostic_code"] = item
    return result


def health(device, telemetry=None, now=None):
    """Server-clock-based status. Untrusted client timestamps are never used."""
    now = now or utcnow()
    if device.revoked:
        return {"code": "revoked", "label": "Gesperrt", "age_seconds": None, "fresh": False}
    if not device.last_seen_at:
        return {"code": "new", "label": "Noch nie verbunden", "age_seconds": None, "fresh": False}
    age = max(0, int((now - device.last_seen_at).total_seconds()))
    if age <= 180:
        code, label = "online", "Online"
    elif age <= 900:
        code, label = "delayed", "Verbindung verzögert"
    else:
        code, label = "offline", "Offline"
    return {"code": code, "label": label, "age_seconds": age,
            "fresh": code == "online",
            "diagnostic": (
                telemetry.diagnostic_code if telemetry
                and telemetry.diagnostic_code in DIAGNOSTIC_CODES
                and telemetry.observed_at
                and now - telemetry.observed_at < timedelta(minutes=30) else None)}
