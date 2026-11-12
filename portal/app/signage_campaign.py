"""Central, permission-filtered campaigns for multiple passive TAKT signs.

Screen allocation is calculated at display time from the building/scope, so
newly added monitors can join without copying secrets, events or addresses.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select

from . import calendar_recurrence
from .calendar_models import CalendarEvent
from .db import User
from .signage_models import (
    SignageBuilding, SignageCampaign, SignageCampaignScreen, SignageDisplayAnchor,
    SignageFloor, SignagePassiveConfig, SignagePublicDestination, SignageRoom,
    SignageScreen, SignageWayNode,
)


def eligible(db, campaign, screen, config=None):
    """Can a campaign target this screen? Never cross the building or employer."""
    from .signage_passive import KINDS

    if screen.kind not in KINDS or not screen.enabled:
        return False
    config = config or db.get(SignagePassiveConfig, screen.id)
    building = db.get(SignageBuilding, campaign.building_id)
    if (not config or not building or not building.active
            or config.building_id != building.id
            or screen.org_id != building.org_id):
        return False
    if campaign.scope == "floor":
        anchor = db.get(SignageDisplayAnchor, screen.id)
        node = db.get(SignageWayNode, anchor.node_id) if anchor else None
        screen_floor_id = node.floor_id if node else config.floor_id
        if not campaign.floor_id or screen_floor_id != campaign.floor_id:
            return False
    elif campaign.scope not in ("building", "selected"):
        return False
    selection = db.get(SignageCampaignScreen, (campaign.id, screen.id))
    if campaign.scope == "selected":
        return bool(selection and selection.included)
    return not selection or selection.included


def destination_approved(db, campaign):
    """A public campaign has to target a currently public room in its building."""
    building = db.get(SignageBuilding, campaign.building_id)
    if not building or not building.active:
        return False
    result = db.execute(select(SignageRoom.id)
        .join(SignageFloor, SignageRoom.floor_id == SignageFloor.id)
        .where(SignageRoom.id == campaign.room_id,
               SignageFloor.building_id == campaign.building_id)).first()
    return bool(result and db.get(SignagePublicDestination, campaign.room_id))


def window(db, campaign, now):
    """Return active window with bounded before/after periods.

    When linked to a calendar, an event is checked against the original ACL
    each time. Its title, attendees and description never enter the projection.
    """
    lead = timedelta(minutes=min(240, max(0, campaign.lead_minutes)))
    tail = timedelta(minutes=min(240, max(0, campaign.tail_minutes)))
    moment = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if campaign.event_id is None:
        if not campaign.starts_at or not campaign.ends_at:
            return None
        starts = campaign.starts_at.replace(tzinfo=timezone.utc)
        ends = campaign.ends_at.replace(tzinfo=timezone.utc)
        return (starts - lead, ends + tail) if starts - lead <= moment < ends + tail else None

    from . import signage_passive, signage
    event = db.get(CalendarEvent, campaign.event_id)
    actor = db.get(User, campaign.created_by) if campaign.created_by else None
    building = db.get(SignageBuilding, campaign.building_id)
    if not building or not signage_passive.source_access(
            db, actor, event, SimpleNamespace(org_id=building.org_id)):
        return None
    if not event:
        return None
    try:
        if event.ical_data:
            _, master, components = calendar_recurrence.validate(event.ical_data)
            if len(components) == 1 and str(master.get("STATUS", "")).upper() == "CANCELLED":
                return None
        intervals = calendar_recurrence.occurrences(
            event, moment - tail, moment + lead + timedelta(seconds=1))
        for occurrence in intervals:
            begin = signage._calendar_date(occurrence["start"]).astimezone(timezone.utc)
            end = signage._calendar_date(occurrence["end"]).astimezone(timezone.utc)
            if begin - lead <= moment < end + tail:
                return begin - lead, end + tail
    except (ValueError, TypeError, OverflowError, HTTPException):
        return None
    return None


def candidates(db, screen, now):
    """Approved and currently effective campaigns, bounded by current building."""
    config = db.get(SignagePassiveConfig, screen.id)
    if not config:
        return []
    rows = db.scalars(select(SignageCampaign).where(
        SignageCampaign.building_id == config.building_id,
        SignageCampaign.published.is_(True)
    ).order_by(SignageCampaign.priority.desc(), SignageCampaign.id).limit(1000)).all()
    out = []
    for item in rows:
        if not eligible(db, item, screen, config) or not destination_approved(db, item):
            continue
        active = window(db, item, now)
        if active:
            out.append((item, active))
    return out


def assigned_screen_ids(db, campaign):
    """All provisioned passive displays to which the central rule would apply."""
    rows = db.scalars(select(SignageScreen).join(
        SignagePassiveConfig, SignagePassiveConfig.screen_id == SignageScreen.id).where(
        SignagePassiveConfig.building_id == campaign.building_id).order_by(
        SignageScreen.name)).all()
    return [row.id for row in rows if eligible(db, campaign, row)]


def conflict_warnings(db, campaign):
    """Overlapping published manual campaigns in the same building/scope."""
    others = db.scalars(select(SignageCampaign).where(
        SignageCampaign.id != campaign.id,
        SignageCampaign.building_id == campaign.building_id,
        SignageCampaign.published.is_(True),
        SignageCampaign.priority >= campaign.priority
    ).limit(1000)).all()
    if campaign.event_id or not campaign.starts_at or not campaign.ends_at:
        return []
    chosen = set(assigned_screen_ids(db, campaign))
    warnings = []
    for item in others:
        if (not item.event_id and item.starts_at and item.ends_at
                and item.starts_at < campaign.ends_at and item.ends_at > campaign.starts_at
                and chosen.intersection(assigned_screen_ids(db, item))):
            warnings.append(f"Priorität {item.priority}: {item.title}")
    return warnings[:10]
