"""Opt-in birthdays derived from encrypted profiles; never a public people directory.

Each request checks live memberships, organization configuration and personal consent.
The only generated information is the day/month, person's name and optional new age.
"""
from datetime import date, datetime, timedelta
from sqlalchemy import select
from .db import User, Organization, get_settings, set_setting
from .org_models import OrgMembership
from . import organization as org, profiles

VISIBILITIES = {"hidden", "date", "age"}
SCOPES = {"unit", "branch", "root"}
FEB29 = {"feb28", "mar1"}
CHANNELS = {"web", "caldav", "ics"}


def root_id(db, unit_id):
    path = org.active_path(db, unit_id)
    return path[-1] if path else None


def rules(db, rid, cfg=None):
    cfg = get_settings(db) if cfg is None else cfg
    prefix = "birthday_" + str(rid) + "_"
    scope = cfg.get(prefix + "scope", "unit")
    leap = cfg.get(prefix + "leap", "feb28")
    return {
        "scope": scope if scope in SCOPES else "unit",
        "leap": leap if leap in FEB29 else "feb28",
        "caldav": cfg.get(prefix + "caldav", "1") == "1",
        "ics": cfg.get(prefix + "ics", "0") == "1",
    }


def save_rules(db, rid, *, scope, leap, caldav, ics):
    if scope not in SCOPES or leap not in FEB29:
        raise ValueError("Ungültige Geburtstagseinstellungen.")
    set_setting(db, "birthday_" + str(rid) + "_scope", scope)
    set_setting(db, "birthday_" + str(rid) + "_leap", leap)
    set_setting(db, "birthday_" + str(rid) + "_caldav", "1" if caldav else "0")
    set_setting(db, "birthday_" + str(rid) + "_ics", "1" if ics else "0")


def managed_roots(db, user):
    """Only root organizations the actor is authorized to configure."""
    roots = db.scalars(
        select(Organization).where(
            Organization.parent_id.is_(None), Organization.active.is_(True)
        ).order_by(Organization.name)
    )
    return [row for row in roots if org.allows(db, user, row.id, "settings")]


def _viewer_paths(db, actor):
    if not actor or not actor.active:
        return []
    return [
        org.active_path(db, unit)
        for unit in db.scalars(
            select(OrgMembership.org_id).where(OrgMembership.user_id == actor.id)
        )
        if org.active_path(db, unit)
    ]


def external_allowed(db, actor, channel):
    """Whether a private per-user source can be offered at all."""
    if channel not in {"caldav", "ics"}:
        return False
    cfg = get_settings(db)
    return any(
        rules(db, path[-1], cfg)[channel]
        for path in _viewer_paths(db, actor)
    )


def observed_day(born, year, leap):
    try:
        return date(year, born.month, born.day)
    except ValueError:
        # Only 29 February can be valid in one year and invalid in another.
        if born.month != 2 or born.day != 29:
            raise
        return date(year, 2, 28) if leap == "feb28" else date(year, 3, 1)


def _visible(viewer_paths, target_path, scope):
    if not target_path:
        return False
    for path in viewer_paths:
        if path[-1] != target_path[-1]:
            continue
        if scope == "root":
            return True
        if scope == "unit" and path[0] == target_path[0]:
            return True
        if scope == "branch" and (
            path[0] in target_path or target_path[0] in path
        ):
            return True
    return False


def events(db, actor, start, end, *, channel="web"):
    """Return rights-scoped occurrences in [start, end); no birth year is sent."""
    if channel not in CHANNELS or not actor or not actor.active:
        return []
    viewer = _viewer_paths(db, actor)
    if not viewer or end <= start:
        return []
    start_day, end_day = start.date(), end.date()
    # DAV/ICS collection exports request centuries; emit a bounded rolling
    # window to avoid huge responses and accidental long-lived data copies.
    first, last = start_day.year, end_day.year
    if last - first > 6:
        first, last = date.today().year - 1, date.today().year + 4
    cfg = get_settings(db)
    output = []
    memberships = db.execute(
        select(User, OrgMembership.org_id).join(
            OrgMembership, OrgMembership.user_id == User.id
        ).where(User.active.is_(True), OrgMembership.is_primary.is_(True))
    )
    for person, uid in memberships:
        path = org.active_path(db, uid)
        if not path:
            continue
        policy = rules(db, path[-1], cfg)
        if channel != "web" and not policy[channel]:
            continue
        if not _visible(viewer, path, policy["scope"]):
            continue
        data = profiles.read(person)
        mode = data.get("birthday_visibility", "hidden")
        if mode not in {"date", "age"} or not data.get("birthdate"):
            continue
        try:
            born = date.fromisoformat(data["birthdate"])
        except ValueError:
            continue
        for year in range(first, last + 1):
            day = observed_day(born, year, policy["leap"])
            if not start_day <= day < end_day:
                continue
            age = year - born.year
            name = person.name or "Kollegin oder Kollege"
            title = name + (" wird " + str(age) if mode == "age" else "")
            output.append({
                "id": "birthdays:" + str(person.id) + ":" + str(year),
                "title": title,
                "start": day.isoformat(),
                "end": (day + timedelta(days=1)).isoformat(),
                "allDay": True,
                "extendedProps": {
                    "source": "birthdays",
                    "url": "",
                    "description": "Geburtstag" + (" · " + str(age) + " Jahre" if mode == "age" else ""),
                },
            })
            if len(output) > 10000:
                from fastapi import HTTPException
                raise HTTPException(507, "Zu viele Geburtstage im angefragten Zeitraum.")
    return sorted(output, key=lambda e: (e["start"], e["title"].casefold()))


def upcoming(db, actor, limit=3, today=None):
    today = today or date.today()
    start = datetime(today.year, today.month, today.day)
    end = start + timedelta(days=367)
    return [
        dict(
            title=e["title"], start=e["start"],
            days=(date.fromisoformat(e["start"]) - today).days,
        )
        for e in events(db, actor, start, end)
    ][:limit]
