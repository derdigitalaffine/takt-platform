"""Read-only, allowlisted projections for kiosk pages (privacy by default)."""
import hashlib
import heapq
import json
import re
import secrets
from datetime import date, datetime, time, timedelta, timezone
from sqlalchemy import select
from .db import LOCAL_TZ, Resource, ResourceBooking, User, utcnow
from .signage_models import (SignageBuilding, SignageFloor, SignageOffice, SignageRoom, SignageScreen,
                             SignageWayNode, SignageWayEdge, SignageDisplayAnchor)
from .calendar_models import Calendar, CalendarEvent

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


def _calendar_date(value: str) -> datetime:
    """Convert TAKT calendar ISO date/datetime values to the portal's local zone."""
    if len(value) == 10:
        return datetime.combine(date.fromisoformat(value), time.min, LOCAL_TZ)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=LOCAL_TZ) if parsed.tzinfo is None else parsed.astimezone(LOCAL_TZ)


def events(db, screen: SignageScreen, *, public=True, now=None, viewer=None) -> list[dict]:
    """Busy-only projection by default from canonical bookings and explicit room calendar.

    A manager must explicitly bind the room calendar. Its original owner must
    retain view permission; public/link readers can never see title or contact.
    """
    now = now or datetime.now(LOCAL_TZ)
    begin = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = begin + timedelta(days=1)
    start_utc = begin.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end.astimezone(timezone.utc).replace(tzinfo=None)
    room = db.get(SignageRoom, screen.room_id) if screen.room_id else None
    resource_id = screen.resource_id or (room.resource_id if room else None)
    result = []

    if resource_id:
        from . import resources as resource_acl
        resource = db.get(Resource, resource_id)
        if resource:
            show_titles = bool(not public and viewer and screen.data_level == "title"
                               and resource_acl.level(db, viewer, resource) >= 2)
            rows = db.scalars(select(ResourceBooking).where(
                ResourceBooking.resource_id == resource_id,
                ResourceBooking.status == "confirmed",
                ResourceBooking.starts_at < end_utc,
                ResourceBooking.ends_at > start_utc
            ).order_by(ResourceBooking.starts_at).limit(40)).all()
            for row in rows:
                result.append(dict(
                    start=_local(row.starts_at), end=_local(row.ends_at),
                    title=(row.title or "Belegt") if show_titles else "Belegt",
                    source="resource"))

    if room and room.calendar_id:
        from . import calendars, calendar_recurrence
        calendar = db.get(Calendar, room.calendar_id)
        # No birthdays, source projections or implicit publication of private
        # calendars: only an explicit free calendar whose active manager can read.
        manager = db.get(User, screen.owner_id) if screen.owner_id else None
        if (calendar and calendar.source == "free" and manager
                and calendars.access(db, manager, calendar)):
            can_title = bool(not public and viewer and screen.data_level == "title"
                             and calendars.access(db, viewer, calendar))
            # recurrence.occurrences handles exceptions and exact day overlap.
            rows = db.scalars(select(CalendarEvent).where(
                CalendarEvent.calendar_id == calendar.id).order_by(CalendarEvent.id).limit(1000)).all()
            for row in rows:
                if not calendars.event_access(db, manager, calendar, row):
                    continue
                try:
                    occurrences = calendar_recurrence.occurrences(
                        row, begin.astimezone(timezone.utc), end.astimezone(timezone.utc))
                except (ValueError, TypeError):
                    # A corrupt legacy event must not break every room display.
                    continue
                for event in occurrences:
                    start = _calendar_date(event["start"])
                    finish = _calendar_date(event["end"])
                    if start < end and finish > begin:
                        result.append(dict(
                            start=start, end=finish,
                            title=(event.get("title") or "Belegt") if can_title else "Belegt",
                            source="calendar"))
                    if len(result) >= 150:
                        break
                if len(result) >= 150:
                    break

    # Overlapping bookings and events are both shown as occupancy; never
    # interpolate people, descriptions or raw iCalendar data into templates.
    result.sort(key=lambda ev: (ev["start"], ev["end"]))
    return [{**ev, "ongoing": ev["start"] <= now < ev["end"]} for ev in result[:100]]


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


def shortest_paths(nodes, edges, start_id: int, *, barrier_free=False) -> dict[int, dict]:
    """Bounded Dijkstra with explicit one-way and accessibility rules.

    Works with SQLAlchemy node objects or simple test fixtures. Never route
    wheelchair users through stairs, regardless of edge configuration.
    """
    by_id = {node.id: node for node in nodes}
    if start_id not in by_id:
        return {}
    allowed = {node.id for node in nodes
               if not barrier_free or (node.accessible and node.kind != "stairs")}
    if start_id not in allowed:
        return {}
    adjacent = {nid: [] for nid in allowed}
    for edge in edges:
        if (edge.from_node_id not in allowed or edge.to_node_id not in allowed
                or barrier_free and not edge.accessible or not 1 <= edge.distance_m <= 5000):
            continue
        adjacent[edge.from_node_id].append((edge.to_node_id, edge.distance_m))
        if edge.bidirectional:
            adjacent[edge.to_node_id].append((edge.from_node_id, edge.distance_m))
    heap = [(0, start_id)]
    best = {start_id: 0}
    previous = {}
    while heap:
        distance, node_id = heapq.heappop(heap)
        if distance != best.get(node_id):
            continue
        for target, step in adjacent[node_id]:
            new_distance = distance + step
            if new_distance < best.get(target, 10**15):
                best[target] = new_distance
                previous[target] = node_id
                heapq.heappush(heap, (new_distance, target))
    result = {}
    for target, distance in best.items():
        sequence = [target]
        while sequence[-1] != start_id:
            sequence.append(previous[sequence[-1]])
        result[target] = {"distance_m": distance, "nodes": list(reversed(sequence))}
    return result


def waypoints(db, screen: SignageScreen) -> list[dict]:
    rows = db.execute(select(SignageRoom, SignageFloor, SignageBuilding)
        .join(SignageFloor, SignageRoom.floor_id == SignageFloor.id)
        .join(SignageBuilding, SignageFloor.building_id == SignageBuilding.id)
        .where(SignageBuilding.active.is_(True))
        .order_by(SignageBuilding.name, SignageFloor.level, SignageRoom.number).limit(150)).all()
    origin = db.get(SignageDisplayAnchor, screen.id)
    nodes = db.scalars(select(SignageWayNode).join(
        SignageFloor, SignageWayNode.floor_id == SignageFloor.id).join(
        SignageBuilding, SignageFloor.building_id == SignageBuilding.id).where(
        SignageBuilding.active.is_(True)).limit(3000)).all() if origin else []
    edge_rows = db.scalars(select(SignageWayEdge).limit(7000)).all() if nodes else []
    nodes_by_id = {node.id: node for node in nodes}
    simple_paths = shortest_paths(nodes, edge_rows, origin.node_id) if origin else {}
    accessible_paths = shortest_paths(nodes, edge_rows, origin.node_id,
                                      barrier_free=True) if origin else {}
    room_node = {}
    for node in nodes:
        if node.room_id:
            room_node.setdefault(node.room_id, node.id)

    def describe(info):
        if not info:
            return None
        sequence = [nodes_by_id[nid] for nid in info["nodes"]]
        return {
            "distance_m": info["distance_m"],
            "steps": [n.label for n in sequence[1:]] or ["Sie befinden sich bereits am Ziel"],
        }

    return [
        dict(number=room.number, label=room.name or "Raum", building=building.name,
             floor=floor.name, accessible=room.accessible,
             route=describe(simple_paths.get(room_node.get(room.id))),
             accessible_route=describe(accessible_paths.get(room_node.get(room.id))))
        for room, floor, building in rows
        if screen.org_id is None or building.org_id == screen.org_id
    ]


def context(db, screen: SignageScreen, public=True, viewer=None) -> dict:
    now = datetime.now(LOCAL_TZ)
    day = events(db, screen, public=public, now=now, viewer=viewer)
    busy = next((ev for ev in day if ev["ongoing"]), None)
    later = [ev for ev in day if ev["start"] > now]
    room = db.get(SignageRoom, screen.room_id) if screen.room_id else None
    return dict(screen=screen, theme=theme(screen.theme_json),
                widgets=widgets(screen.layout_json, screen.kind),
                now=now, events=day, busy=busy, next_event=later[0] if later else None,
                room=room, staff=staff_directory(db, screen) if screen.kind == "directory" else [],
                waypoints=waypoints(db, screen) if screen.kind == "wayfinder" else [],
                public=public)


def design_snapshot(screen: SignageScreen) -> str:
    """Only presentation state is versioned; publication/ACL/links are not."""
    return json.dumps({
        "name": screen.name,
        "kind": screen.kind,
        "subtitle": screen.subtitle,
        "direction": screen.direction,
        "theme": theme(screen.theme_json),
        "widgets": widgets(screen.layout_json, screen.kind),
    }, ensure_ascii=False, sort_keys=True)


def apply_design_snapshot(screen: SignageScreen, snapshot: str) -> None:
    """Restore allowlisted presentation fields, never visibility or source ACLs."""
    state = json.loads(snapshot)
    if not isinstance(state, dict):
        raise ValueError("Invalid design revision")
    kind = state.get("kind")
    if kind not in KINDS:
        raise ValueError("Invalid design revision kind")
    screen.kind = kind
    screen.name = str(state.get("name") or screen.name).strip()[:180] or screen.name
    screen.subtitle = str(state.get("subtitle") or "")[:250]
    screen.direction = str(state.get("direction") or "")[:100]
    screen.theme_json = json.dumps(theme(state.get("theme")))
    screen.layout_json = json.dumps(widgets(state.get("widgets"), kind))
