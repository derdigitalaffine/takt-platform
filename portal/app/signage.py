"""Read-only, allowlisted projections for kiosk pages (privacy by default)."""
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from .db import LOCAL_TZ, ResourceBooking, User, utcnow
from .signage_models import SignageBuilding, SignageFloor, SignageOffice, SignageRoom, SignageScreen

KINDS = {"agenda": "Terminübersicht", "room": "Digitales Türschild",
         "directory": "Personen und Büros", "wayfinder": "Wegweiser",
         "info": "Informationen"}
WIDGETS = {"clock": "Uhrzeit & Datum", "status": "Raumstatus",
           "agenda": "Termine", "directory": "Personenverzeichnis",
           "wayfinder": "Wegweiser", "message": "Hinweistext"}
TEMPLATES = {
    "agenda": ["clock", "agenda", "message"],
    "room": ["clock", "status", "agenda"],
    "directory": ["clock", "directory"],
    "wayfinder": ["clock", "wayfinder"],
    "info": ["clock", "message"],
}
THEME_DEFAULTS = {"background": "#111e30", "foreground": "#f8fafc", "accent": "#42d4ad"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def token() -> str:
    return secrets.token_urlsafe(32)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def theme(raw) -> dict[str, str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return {key: value if isinstance((value := raw.get(key)), str) and HEX.fullmatch(value) else fallback
            for key, fallback in THEME_DEFAULTS.items()}


def widgets(raw, kind="agenda") -> list[str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = None
    if not isinstance(raw, list):
        return TEMPLATES.get(kind, TEMPLATES["agenda"])[:]
    chosen = [x for x in raw if isinstance(x, str) and x in WIDGETS]
    return list(dict.fromkeys(chosen))[:8] or TEMPLATES.get(kind, TEMPLATES["agenda"])[:]


def _local(dt):
    return dt.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ) if dt.tzinfo is None else dt.astimezone(LOCAL_TZ)


def events(db, screen: SignageScreen, *, public=True, now=None) -> list[dict]:
    """Confirmed resource bookings. Never project applicant/participant contact details."""
    resource_id = screen.resource_id
    if not resource_id and screen.room_id:
        room = db.get(SignageRoom, screen.room_id)
        resource_id = room.resource_id if room else None
    if not resource_id:
        return []
    now = now or datetime.now(LOCAL_TZ)
    begin = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = begin + timedelta(days=1)
    start_utc = begin.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end.astimezone(timezone.utc).replace(tzinfo=None)
    rows = db.scalars(select(ResourceBooking).where(
        ResourceBooking.resource_id == resource_id,
        ResourceBooking.status == "confirmed",
        ResourceBooking.starts_at < end_utc,
        ResourceBooking.ends_at > start_utc
    ).order_by(ResourceBooking.starts_at).limit(40)).all()
    show_titles = not public and screen.data_level == "title"
    return [{
        "start": _local(row.starts_at),
        "end": _local(row.ends_at),
        "title": (row.title or "Belegt") if show_titles else "Belegt",
        "ongoing": _local(row.starts_at) <= now < _local(row.ends_at),
    } for row in rows]


def staff_directory(db, screen: SignageScreen) -> list[dict]:
    """Only explicit public staff opt-ins, independent from private profile_data_enc."""
    rows = db.execute(select(SignageOffice, User, SignageRoom, SignageFloor, SignageBuilding)
        .join(User, User.id == SignageOffice.user_id)
        .join(SignageRoom, SignageRoom.id == SignageOffice.room_id)
        .join(SignageFloor, SignageFloor.id == SignageRoom.floor_id)
        .join(SignageBuilding, SignageBuilding.id == SignageFloor.building_id)
        .where(SignageOffice.public.is_(True), User.active.is_(True), SignageBuilding.active.is_(True))
        .order_by(User.name).limit(200)).all()
    return [
        dict(name=user.name, building=building.name, floor=floor.name,
             room=room.number, room_name=room.name)
        for _, user, room, floor, building in rows
        if screen.org_id is None or building.org_id == screen.org_id
    ]


def waypoints(db, screen: SignageScreen) -> list[dict]:
    rows = db.execute(select(SignageRoom, SignageFloor, SignageBuilding)
        .join(SignageFloor, SignageRoom.floor_id == SignageFloor.id)
        .join(SignageBuilding, SignageFloor.building_id == SignageBuilding.id)
        .where(SignageBuilding.active.is_(True))
        .order_by(SignageBuilding.name, SignageFloor.level, SignageRoom.number).limit(150)).all()
    return [dict(number=room.number, label=room.name or "Raum", building=building.name,
                 floor=floor.name, accessible=room.accessible)
            for room, floor, building in rows
            if screen.org_id is None or building.org_id == screen.org_id]


def context(db, screen: SignageScreen, public=True) -> dict:
    now = datetime.now(LOCAL_TZ)
    day = events(db, screen, public=public, now=now)
    busy = next((ev for ev in day if ev["ongoing"]), None)
    later = [ev for ev in day if ev["start"] > now]
    room = db.get(SignageRoom, screen.room_id) if screen.room_id else None
    return dict(screen=screen, theme=theme(screen.theme_json),
                widgets=widgets(screen.layout_json, screen.kind),
                now=now, events=day, busy=busy, next_event=later[0] if later else None,
                room=room, staff=staff_directory(db, screen) if screen.kind == "directory" else [],
                waypoints=waypoints(db, screen) if screen.kind == "wayfinder" else [],
                public=public)
