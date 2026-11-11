"""Public projection for passive signs and explicitly approved special operation."""
from datetime import datetime, timedelta, timezone
from math import atan2, degrees, hypot

from fastapi import HTTPException
from sqlalchemy import select

from . import calendars, calendar_recurrence
from .calendar_models import Calendar, CalendarEvent
from .db import LOCAL_TZ, User
from .signage_models import (
    SignageBuilding, SignageDestinationOverride, SignageDisplayAnchor, SignageFloor,
    SignagePassiveConfig, SignagePublicDestination, SignageRoom, SignageSpecial,
    SignageWayEdge, SignageWayNode,
)

KINDS = {
    "sign_building": "Gebäudeübersicht",
    "sign_floor": "Geschossübersicht",
    "sign_corridor": "Flurübersicht",
    "sign_direction": "Passive Richtungsanzeige",
}
PRESETS = {
    "council": ("Ratssitzung", 50),
    "poll": ("Wahlraum", 90),
    "postal": ("Briefwahlstelle", 90),
    "event": ("Veranstaltung", 30),
}
FACINGS = {"north": "Plan oben", "east": "Plan rechts", "south": "Plan unten", "west": "Plan links"}
ARROWS = {
    "straight": ("↑", "Geradeaus"), "right": ("→", "Rechts"),
    "back": ("↓", "Hinter Ihnen"), "left": ("←", "Links"),
    "here": ("●", "Hier"),
}


def schedule_time(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        early = parsed.replace(tzinfo=LOCAL_TZ, fold=0)
        late = parsed.replace(tzinfo=LOCAL_TZ, fold=1)
        if early.utcoffset() != late.utcoffset():
            raise ValueError("Mehrdeutige oder nicht vorhandene Ortszeit")
        parsed = early
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def direction(origin, step, facing):
    if not facing or origin.floor_id != step.floor_id:
        return None
    dx, dy = step.x_pct - origin.x_pct, step.y_pct - origin.y_pct
    if hypot(dx, dy) < 0.5:
        return None
    bearing = degrees(atan2(dx, -dy))
    relative = bearing - list(FACINGS).index(facing) * 90
    return ("straight", "right", "back", "left")[int((relative + 405) % 360 // 90)]


def destination_rows(db, screen, building_id=None):
    query = select(SignageRoom, SignageFloor, SignageBuilding, SignagePublicDestination).join(
        SignagePublicDestination, SignagePublicDestination.room_id == SignageRoom.id
    ).join(SignageFloor, SignageRoom.floor_id == SignageFloor.id).join(
        SignageBuilding, SignageFloor.building_id == SignageBuilding.id
    ).where(SignageBuilding.active.is_(True))
    if building_id is not None:
        query = query.where(SignageBuilding.id == building_id)
    if screen.org_id is not None:
        query = query.where(SignageBuilding.org_id == screen.org_id)
    return query


def source_access(db, actor, event, screen):
    calendar = db.get(Calendar, event.calendar_id) if event else None
    return bool(actor and actor.active and actor.can("signage_manage") and calendar and calendar.source == "free"
                and (not screen.org_id or all(oid in (None, screen.org_id)
                                              for oid in (calendar.org_id, event.org_id)))
                and calendars.event_access(db, actor, calendar, event))


def active_window(db, item, screen, now):
    if item.event_id is None:
        instant = now.astimezone(timezone.utc).replace(tzinfo=None)
        if item.starts_at and item.ends_at and item.starts_at <= instant < item.ends_at:
            return (item.starts_at.replace(tzinfo=timezone.utc), item.ends_at.replace(tzinfo=timezone.utc))
        return None
    event = db.get(CalendarEvent, item.event_id)
    actor = db.get(User, item.actor_id) if item.actor_id else None
    if not source_access(db, actor, event, screen):
        return None
    from .signage import _calendar_date

    try:
        # Calendar recurrence handles exceptions; single events take its fast path,
        # so also check cancellation on their original calendar component.
        if event.ical_data:
            _, master, components = calendar_recurrence.validate(event.ical_data)
            if len(components) == 1 and str(master.get("STATUS", "")).upper() == "CANCELLED":
                return None
        windows = []
        for occurrence in calendar_recurrence.occurrences(
                event, now - timedelta(days=1) if event.all_day else now,
                now + timedelta(days=1) if event.all_day else now + timedelta(seconds=1)):
            begin = _calendar_date(occurrence["start"]).astimezone(timezone.utc)
            end = _calendar_date(occurrence["end"]).astimezone(timezone.utc)
            if begin <= now < end:
                windows.append((begin, end))
        return min(windows, default=None)
    except (HTTPException, ValueError, TypeError, OverflowError):
        return None


def project(db, screen, now):
    config = db.get(SignagePassiveConfig, screen.id)
    passive = screen.kind in KINDS
    specials = db.scalars(select(SignageSpecial).where(
        SignageSpecial.screen_id == screen.id, SignageSpecial.published.is_(True)
    )).all()
    if not passive and not specials:
        return [], None, None
    building_id = config.building_id if passive and config else None
    building = db.get(SignageBuilding, building_id) if building_id else None
    if passive and (not building or not building.active or building.org_id != screen.org_id):
        return [], None, None
    manual = None
    if screen.kind == "sign_direction" and config.manual_label:
        manual = {"label": config.manual_label, "arrow": ARROWS.get(config.manual_arrow)}
    query = destination_rows(db, screen, building_id)
    if not passive:
        query = query.where(SignageRoom.id.in_({item.room_id for item in specials}))
    rows = db.execute(query.order_by(
        SignageBuilding.name, SignageFloor.level, SignageRoom.number, SignageRoom.id
    )).all()
    overrides = {row.room_id: row for row in db.scalars(select(SignageDestinationOverride).where(
        SignageDestinationOverride.screen_id == screen.id))}
    points = {room.id: (room, floor, building, publication)
              for room, floor, building, publication in rows}
    anchor = db.get(SignageDisplayAnchor, screen.id)
    nodes, paths = graph(db, screen, config, anchor) if passive else ({}, {})
    origin = nodes.get(anchor.node_id) if anchor else None

    best_by_room = {}
    for nid, path in paths.items():
        room_id = nodes[nid].room_id
        if room_id not in points or nodes[nid].floor_id != points[room_id][0].floor_id:
            continue
        candidate = path["distance_m"], nid, path["nodes"]
        if room_id not in best_by_room or candidate < best_by_room[room_id]:
            best_by_room[room_id] = candidate

    def target(room_id):
        room, floor, building, publication = points[room_id]
        rule = overrides.get(room_id)
        path = best_by_room.get(room_id)
        if config and config.barrier_free and not room.accessible:
            path = None
        automatic = None
        if path:
            sequence = path[2]
            automatic = "here" if len(sequence) == 1 else direction(
                origin, nodes[sequence[1]], config.facing if config else "")
        arrow = (rule.arrow or automatic) if rule else automatic
        if arrow == "none" or (config and config.barrier_free and not path):
            arrow = None
        return {
            "label": (rule.label if rule else "") or publication.label or room.name or "Raum",
            "number": room.number, "floor": floor.name, "building": building.name,
            "arrow": ARROWS.get(arrow), "rank": rule.rank if rule else 0,
            "accessible": bool(config and config.barrier_free and path and not (rule and rule.arrow)),
        }

    regular = []
    if passive and not (manual and config.manual_only):
        for room_id, (_, floor, _, _) in points.items():
            if room_id in overrides and overrides[room_id].hidden:
                continue
            if screen.kind in ("sign_floor", "sign_corridor") and floor.id != config.floor_id:
                continue
            if screen.kind == "sign_corridor":
                path = best_by_room.get(room_id)
                if not (origin and origin.floor_id == floor.id and path and path[0] <= config.radius_m
                        and all(nodes[nid].floor_id == floor.id for nid in path[2])):
                    continue
            regular.append(target(room_id))
        regular.sort(key=lambda point: -point["rank"])

    active = []
    for item in specials:
        if item.room_id not in points:
            continue
        window = active_window(db, item, screen, now)
        if window:
            active.append((-item.priority, window[0], item.id, window[1], item))
    if not active:
        return regular, None, manual
    _, _, _, end, winner = min(active)
    expiry = min(end, now.astimezone(timezone.utc) + timedelta(seconds=45))
    return regular, {"title": winner.title, "message": winner.message, "mode": winner.mode,
                     "valid_until": expiry.isoformat(), "target": target(winner.room_id)}, manual


def graph(db, screen, config, anchor):
    if not anchor:
        return {}, {}
    from .signage import shortest_paths

    query = select(SignageWayNode).join(SignageFloor).join(SignageBuilding).where(
        SignageBuilding.active.is_(True))
    if config:
        query = query.where(SignageBuilding.id == config.building_id)
        if screen.kind == "sign_corridor":
            query = query.where(SignageWayNode.floor_id == config.floor_id)
    if screen.org_id is not None:
        query = query.where(SignageBuilding.org_id == screen.org_id)
    nodes = {node.id: node for node in db.scalars(query.order_by(SignageWayNode.id).limit(3001))}
    if anchor.node_id not in nodes or len(nodes) > 3000:
        return {}, {}
    ids = query.with_only_columns(SignageWayNode.id)
    edges = db.scalars(select(SignageWayEdge).where(
        SignageWayEdge.from_node_id.in_(ids), SignageWayEdge.to_node_id.in_(ids)
    ).order_by(SignageWayEdge.id).limit(7001)).all()
    if len(edges) > 7000:
        return {}, {}
    return nodes, shortest_paths(nodes.values(), edges, anchor.node_id,
                                 barrier_free=bool(config and config.barrier_free))
