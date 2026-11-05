"""Shared work/closure/account projection; capacities are fractions of a full half-day.

A pattern has 14 values (Monday AM, PM ... Sunday PM), each from zero to one.
No extra FTE multiplier is applied. Assignment percentages distribute that capacity.
"""

import json, math
from datetime import date, timedelta
from sqlalchemy import select
from fastapi import HTTPException
from .db import User, Organization
from .org_models import OrgMembership
from .leave_extensions import (
    WorkPattern,
    WorkDay,
    Closure,
    EmergencyAssignment,
    LeaveAccount,
    LeaveInbox,
    LeavePreference,
)
from .leave_models import LeaveRequest, LeavePolicy
from . import organization as org, staffing


def validate_pattern(raw):
    try:
        values = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(values, list) or len(values) != 14:
            raise ValueError()
        values = [float(v) for v in values]
        if any(not math.isfinite(v) or not 0 <= v <= 1 for v in values):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(
            422, "14 Tageshälften mit Kapazität zwischen 0 und 1 angeben."
        )
    return values


def capacity(patterns, uid, day, half, simple=False):
    special = getattr(patterns, "exceptions", {}).get((uid, day.isoformat()))
    if special is not None:
        return special[half == "pm"]
    if day in getattr(patterns, "days_off", {}).get(uid, {}):
        return 0
    matched = [
        p
        for p in patterns
        if p.person_id == uid and p.starts_on <= day.isoformat() <= p.ends_on
    ]
    if len(matched) > 1:
        raise HTTPException(
            409, "Überlappende Arbeitsmodelle müssen zuerst korrigiert werden."
        )
    values = (
        validate_pattern(matched[0].weekly_json)
        if matched and not simple
        else [1.0] * 10 + [0.0] * 4
    )
    return values[day.weekday() * 2 + (half == "pm")]


def days_used(period, patterns=None):
    result = {}
    for offset in range((period.end - period.start).days + 1):
        day = period.start + timedelta(days=offset)
        scheduled = [
            half
            for half in ("am", "pm")
            if (
                day.weekday() < 5
                if patterns is None
                else capacity(patterns, period.person_id, day, half) > 0
            )
        ]
        if not scheduled:
            continue
        used = sum(period.contains(day, half) for half in scheduled) / len(scheduled)
        result[day.year] = result.get(day.year, 0) + used
    return result


def account_check(db, person_id, candidate, keep):
    from .leave import period

    used = {}
    patterns = work_snapshot(db, candidate.start, candidate.end, [person_id])
    for row in db.scalars(
        select(LeaveRequest).where(
            LeaveRequest.person_id == person_id, LeaveRequest.id != keep
        )
    ):
        if row.effective_json:
            data = json.loads(row.effective_json)
            charges = data.get("account_charge")
            if charges is None:
                previous = period(person_id, data)
                charges = days_used(
                    previous,
                    work_snapshot(db, previous.start, previous.end, [person_id]),
                )
            for year, days in charges.items():
                year = int(year)
                used[year] = used.get(year, 0) + days
    for year, days in days_used(candidate, patterns).items():
        account = db.get(LeaveAccount, (person_id, year))
        if (
            not account
            or used.get(year, 0) + days > account.entitlement + account.carry
        ):
            raise HTTPException(
                409, "Urlaubskonto für " + str(year) + " fehlt oder reicht nicht aus."
            )


def extra_conflicts(db, candidate, keep=None):
    """Return capacity and emergency-staff conflicts without private absence reasons."""
    from .leave import period

    nodes = org.context(db, db.get(User, candidate.person_id))["nodes"]
    memberships = [
        m
        for m in db.scalars(
            select(OrgMembership)
            .join(User, User.id == OrgMembership.user_id)
            .where(User.active.is_(True), OrgMembership.counts_staff.is_(True))
        )
        if org.active_path(db, m.org_id, nodes)
    ]
    affected = {
        unit
        for m in memberships
        if m.user_id == candidate.person_id
        for unit in org.active_path(db, m.org_id, nodes)
    }
    policies = [
        p
        for p in db.scalars(select(LeavePolicy))
        if p.org_id in affected and p.advanced and p.minimum_capacity
    ]
    closures = list(
        db.scalars(
            select(Closure).where(
                Closure.starts_on <= candidate.end.isoformat(),
                Closure.ends_on >= candidate.start.isoformat(),
            )
        )
    )
    assignments = {
        closed.id: eligible_emergency_ids(db, closed, nodes) for closed in closures
    }
    absences = []
    for row in db.scalars(select(LeaveRequest).where(LeaveRequest.id != keep)):
        if row.effective_json:
            absences.append(period(row.person_id, json.loads(row.effective_json)))
    # Effective manual absences have the same availability impact as binding leave.
    from .db import Absence

    mirrors = set(
        db.scalars(
            select(LeaveRequest.absence_id).where(LeaveRequest.absence_id.is_not(None))
        )
    )
    for row in db.scalars(select(Absence).where(Absence.status == "confirmed")):
        if row.id not in mirrors:
            absences.append(
                period(row.user_id, dict(starts_on=row.starts_on, ends_on=row.ends_on))
            )
    patterns = work_snapshot(db, candidate.start, candidate.end)
    tentative_periods = [
        period(
            row.person_id,
            dict(
                starts_on=row.starts_on,
                ends_on=row.ends_on,
                start_half=row.start_half,
                end_half=row.end_half,
            ),
        )
        for row in db.scalars(
            select(LeaveRequest).where(
                LeaveRequest.id != keep,
                LeaveRequest.status.in_(["planned", "requested"]),
            )
        )
    ]
    result = []
    for offset in range((candidate.end - candidate.start).days + 1):
        day = candidate.start + timedelta(days=offset)
        for half in ("am", "pm"):
            if not candidate.contains(day, half):
                continue
            if capacity(patterns, candidate.person_id, day, half) <= 0:
                continue
            absent = {p.person_id for p in absences if p.contains(day, half)} | {
                candidate.person_id
            }
            for rule in policies:
                if any(
                    cl.org_id in org.active_path(db, rule.org_id, nodes)
                    and cl.starts_on <= day.isoformat() <= cl.ends_on
                    for cl in closures
                ):
                    continue
                shares = {}
                for m in memberships:
                    if rule.org_id in org.active_path(db, m.org_id, nodes):
                        shares[m.user_id] = min(
                            100, shares.get(m.user_id, 0) + m.capacity_percent
                        )
                scheduled = sum(
                    capacity(patterns, uid, day, half) * share / 100
                    for uid, share in shares.items()
                )
                if not scheduled:
                    continue
                available = sum(
                    capacity(patterns, uid, day, half) * share / 100
                    for uid, share in shares.items()
                    if uid not in absent
                )
                if available * 100 + 1e-8 < rule.minimum_capacity:
                    result.append(
                        staffing.Conflict(
                            rule.org_id,
                            day,
                            half,
                            round(available, 3),
                            rule.minimum_capacity / 100,
                            rule.conflict_mode,
                            False,
                        )
                    )
                tentative = {
                    p.person_id for p in tentative_periods if p.contains(day, half)
                }
                forecast_available = sum(
                    capacity(patterns, uid, day, half) * share / 100
                    for uid, share in shares.items()
                    if uid not in absent | tentative
                )
                if (
                    forecast_available < available
                    and forecast_available * 100 + 1e-8 < rule.minimum_capacity
                ):
                    result.append(
                        staffing.Conflict(
                            rule.org_id,
                            day,
                            half,
                            round(forecast_available, 3),
                            rule.minimum_capacity / 100,
                            rule.conflict_mode,
                            True,
                        )
                    )
            for closed in closures:
                if not closed.starts_on <= day.isoformat() <= closed.ends_on:
                    continue
                assigned = assignments.get(closed.id, set())
                if candidate.person_id in assigned:
                    raise HTTPException(
                        409,
                        "Die Person ist für die Notbesetzung einer Schließzeit eingeteilt.",
                    )
                if closed.org_id not in affected:
                    continue
                available = len(
                    [
                        uid
                        for uid in assigned
                        if uid not in absent and capacity(patterns, uid, day, half) > 0
                    ]
                )
                if available < closed.emergency_minimum:
                    result.append(
                        staffing.Conflict(
                            closed.org_id,
                            day,
                            half,
                            available,
                            closed.emergency_minimum,
                            "block",
                            False,
                        )
                    )
    return result


def notify_request(db, row, actor, title, units):
    """In-app receipt is mandatory; optional email uses the existing outbox."""
    from . import notify

    person = db.get(User, row.person_id)
    title = title + " · " + person.name + " · " + row.starts_on + "–" + row.ends_on
    recipients = {row.person_id}
    for user in db.scalars(select(User).where(User.active.is_(True))):
        if any(org.allows(db, user, unit, "approve") for unit in units):
            recipients.add(user.id)
    for uid in recipients:
        notice = LeaveInbox(user_id=uid, request_id=row.id, title=title[:250])
        db.add(notice)
        user = db.get(User, uid)
        from .db import get_settings

        pref = db.get(LeavePreference, uid)
        mode = (
            pref.email_mode
            if pref
            else (
                "immediate"
                if get_settings(db).get("leave_email", "0") == "1"
                else "none"
            )
        )
        if mode == "immediate":
            notice.emailed = True
            notify.enqueue(
                db,
                user.email,
                title,
                "Der Vorgang ist in Takt unter /urlaub zu finden.",
                "leave",
            )


def account_balances(db, person_id):
    from .leave import period

    used = {}
    for row in db.scalars(
        select(LeaveRequest).where(LeaveRequest.person_id == person_id)
    ):
        if not row.effective_json:
            continue
        data = json.loads(row.effective_json)
        charges = data.get("account_charge")
        if charges is None:
            previous = period(person_id, data)
            charges = days_used(
                previous, work_snapshot(db, previous.start, previous.end, [person_id])
            )
        for year, amount in charges.items():
            used[int(year)] = used.get(int(year), 0) + amount
    return [
        dict(
            year=a.year,
            entitlement=a.entitlement,
            carry=a.carry,
            used=used.get(a.year, 0),
            remaining=a.entitlement + a.carry - used.get(a.year, 0),
        )
        for a in db.scalars(
            select(LeaveAccount)
            .where(LeaveAccount.person_id == person_id)
            .order_by(LeaveAccount.year)
        )
    ]


def closure_obligations(db, closed, people):
    """Required leave is a planning marker, never an invented application or approval."""
    from .leave import period

    patterns = work_snapshot(
        db, date.fromisoformat(closed.starts_on), date.fromisoformat(closed.ends_on)
    )
    assigned = eligible_emergency_ids(db, closed)
    rows = list(
        db.scalars(
            select(LeaveRequest).where(
                LeaveRequest.person_id.in_([p.id for p in people])
            )
        )
    )
    effective = [
        (row.person_id, period(row.person_id, json.loads(row.effective_json)))
        for row in rows
        if row.effective_json
    ]
    tentative = [
        (
            row.person_id,
            period(
                row.person_id,
                dict(
                    starts_on=row.starts_on,
                    ends_on=row.ends_on,
                    start_half=row.start_half,
                    end_half=row.end_half,
                ),
            ),
        )
        for row in rows
        if row.status in ("planned", "requested")
    ]
    relevant = {
        m.user_id
        for m in db.scalars(select(OrgMembership))
        if (m.is_primary or m.counts_staff)
        and closed.org_id in org.active_path(db, m.org_id)
    }
    result = []
    for person in people:
        if person.id not in relevant:
            continue
        missing = []
        unplanned = []
        planned = 0
        if person.id not in assigned:
            for offset in range(
                (
                    date.fromisoformat(closed.ends_on)
                    - date.fromisoformat(closed.starts_on)
                ).days
                + 1
            ):
                day = date.fromisoformat(closed.starts_on) + timedelta(days=offset)
                for half in ("am", "pm"):
                    if capacity(patterns, person.id, day, half) <= 0:
                        continue
                    if any(
                        uid == person.id and p.contains(day, half)
                        for uid, p in effective
                    ):
                        continue
                    missing.append(dict(day=day.isoformat(), half=half))
                    if any(
                        uid == person.id and p.contains(day, half)
                        for uid, p in tentative
                    ):
                        planned += 1
                    else:
                        unplanned.append(dict(day=day.isoformat(), half=half))
        proposal = None
        if unplanned:
            run = [unplanned[0]]

            def slot(item):
                return date.fromisoformat(item["day"]).toordinal() * 2 + (
                    item["half"] == "pm"
                )

            for item in unplanned[1:]:
                if slot(item) != slot(run[-1]) + 1:
                    break
                run.append(item)
            proposal = dict(
                starts_on=run[0]["day"],
                start_half=run[0]["half"],
                ends_on=run[-1]["day"],
                end_half=run[-1]["half"],
            )
        result.append(
            dict(
                person_id=person.id,
                name=person.name,
                emergency=person.id in assigned,
                missing=missing,
                planned=planned,
                proposal=proposal,
            )
        )
    return result


def send_digests():
    from .db import SessionLocal, utcnow, to_local, get_settings
    from . import notify, leave
    from .config import settings

    with SessionLocal() as db:
        if get_settings(db).get("module_calendars", "0") != "1" or not db.scalar(
            select(LeavePreference.user_id)
            .where(LeavePreference.email_mode == "daily")
            .limit(1)
        ):
            return 0
        leave.lock(db)
        today = to_local(utcnow()).date()
        count = 0
        for pref in db.scalars(
            select(LeavePreference).where(LeavePreference.email_mode == "daily")
        ):
            user = db.get(User, pref.user_id)
            if not user or not user.active:
                continue
            notices = [
                n
                for n in db.scalars(
                    select(LeaveInbox).where(
                        LeaveInbox.user_id == user.id, LeaveInbox.emailed.is_(False)
                    )
                )
                if to_local(n.created_at).date() < today
            ]
            unread = [n for n in notices if not n.read]
            if unread:
                notify.enqueue(
                    db,
                    user.email,
                    "Urlaubsplanung: Zusammenfassung",
                    str(len(unread))
                    + " neue Hinweise. Bitte in Takt prüfen: "
                    + settings.portal_base_url
                    + "/urlaub",
                    "leave",
                )
                count += 1
            for notice in notices:
                notice.emailed = True
        db.commit()
        return count


def planning_summary(db, unit, start, end):
    """Half-day availability in the selected unit, without absence reasons."""
    from .leave import period
    from .db import Absence

    nodes = {n.id: n for n in db.scalars(select(Organization))}
    ids = {
        m.user_id
        for m in db.scalars(
            select(OrgMembership)
            .join(User, User.id == OrgMembership.user_id)
            .where(OrgMembership.counts_staff.is_(True), User.active.is_(True))
        )
        if unit in org.active_path(db, m.org_id, nodes)
    }
    cfg = db.get(LeavePolicy, unit)
    from .leave import policy

    effective_cfg = policy(db, unit)
    patterns = work_snapshot(db, start, end)
    unavailable = []
    mirrors = set()
    for row in db.scalars(select(LeaveRequest)):
        if row.absence_id:
            mirrors.add(row.absence_id)
        if row.person_id in ids and row.effective_json:
            unavailable.append(period(row.person_id, json.loads(row.effective_json)))
    for row in db.scalars(
        select(Absence).where(Absence.user_id.in_(ids), Absence.status == "confirmed")
    ):
        if row.id not in mirrors:
            unavailable.append(
                period(row.user_id, dict(starts_on=row.starts_on, ends_on=row.ends_on))
            )
    days = []
    for offset in range((end - start).days):
        day = start + timedelta(days=offset)
        counts = []
        for half in ("am", "pm"):
            available = {
                uid
                for uid in ids
                if capacity(patterns, uid, day, half, simple=not effective_cfg.advanced)
                > 0
            }
            if not available:
                continue
            absent = {p.person_id for p in unavailable if p.contains(day, half)}
            counts.append(len(available - absent))
        days.append(
            dict(
                date=day.isoformat(),
                available=min(counts) if counts else None,
                minimum=cfg.minimum if cfg else 0,
            )
        )
    return [dict(label="Verfügbare Personen · niedrigster Halbtag", days=days)]


def eligible_emergency_ids(db, closed, nodes=None):
    if nodes is None:
        nodes = {n.id: n for n in db.scalars(select(Organization))}
    eligible = {
        m.user_id
        for m in db.scalars(
            select(OrgMembership)
            .join(User, User.id == OrgMembership.user_id)
            .where(OrgMembership.is_primary.is_(True), User.active.is_(True))
        )
        if closed.org_id in org.active_path(db, m.org_id, nodes)
    }
    return eligible.intersection(
        db.scalars(
            select(EmergencyAssignment.person_id).where(
                EmergencyAssignment.closure_id == closed.id
            )
        )
    )


def closure_status(db, closed):
    from .leave import period
    from .db import Absence

    assigned = eligible_emergency_ids(db, closed)
    patterns = work_snapshot(
        db,
        date.fromisoformat(closed.starts_on),
        date.fromisoformat(closed.ends_on),
        assigned,
    )
    unavailable = []
    mirrors = set()
    for row in db.scalars(
        select(LeaveRequest).where(LeaveRequest.person_id.in_(assigned))
    ):
        if row.absence_id:
            mirrors.add(row.absence_id)
        if row.effective_json:
            unavailable.append(period(row.person_id, json.loads(row.effective_json)))
    for row in db.scalars(
        select(Absence).where(
            Absence.user_id.in_(assigned), Absence.status == "confirmed"
        )
    ):
        if row.id not in mirrors:
            unavailable.append(
                period(row.user_id, dict(starts_on=row.starts_on, ends_on=row.ends_on))
            )
    shortages = []
    start = date.fromisoformat(closed.starts_on)
    end = date.fromisoformat(closed.ends_on)
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        for half in ("am", "pm"):
            working = {
                uid for uid in assigned if capacity(patterns, uid, day, half) > 0
            }
            if not working and (
                day.weekday() >= 5 or day in holiday_days(db, closed.org_id, day, day)
            ):
                continue
            available = working - {
                p.person_id for p in unavailable if p.contains(day, half)
            }
            if len(available) < closed.emergency_minimum:
                shortages.append(
                    dict(day=day.isoformat(), half=half, available=len(available))
                )
    return dict(assigned=len(assigned), shortages=shortages)


class WorkSnapshot(list):
    def __init__(self, patterns, days_off, exceptions):
        super().__init__(patterns)
        self.days_off = days_off
        self.exceptions = exceptions


def holiday_days(
    db, unit, start, end, *, policies=None, nodes=None, default_state=None
):
    """Reuse the legal-date calculation, never resource-price-only custom holidays."""
    from . import holidays
    from .db import get_settings

    if policies is None:
        policies = {p.org_id: p for p in db.scalars(select(LeavePolicy))}
    if nodes is None:
        nodes = {n.id: n for n in db.scalars(select(Organization))}
    default_state = default_state or get_settings(db).get("leave_holiday_state", "RP")
    state = next(
        (
            policies[oid].holiday_state
            for oid in org.active_path(db, unit, nodes)
            if oid in policies and policies[oid].holiday_state not in (None, "inherit")
        ),
        default_state,
    )
    if state == "none":
        return {}
    if state not in holidays.STATES:
        state = "RP"
    return {
        day: label
        for year in range(start.year, end.year + 1)
        for day, label in holidays.legal(year, state).items()
        if start <= day <= end
    }


def work_snapshot(db, start, end, person_ids=None):
    from .db import get_settings

    patterns = list(db.scalars(select(WorkPattern)))
    primary = {
        m.user_id: m.org_id
        for m in db.scalars(
            select(OrgMembership).where(OrgMembership.is_primary.is_(True))
        )
    }
    ids = set(person_ids) if person_ids is not None else set(primary)
    policies = {p.org_id: p for p in db.scalars(select(LeavePolicy))}
    nodes = {n.id: n for n in db.scalars(select(Organization))}
    default = get_settings(db).get("leave_holiday_state", "RP")
    off = {
        uid: holiday_days(
            db,
            primary.get(uid),
            start,
            end,
            policies=policies,
            nodes=nodes,
            default_state=default,
        )
        for uid in ids
    }
    exceptions = {
        (d.person_id, d.day): (d.am, d.pm)
        for d in db.scalars(
            select(WorkDay).where(
                WorkDay.person_id.in_(ids),
                WorkDay.day >= start.isoformat(),
                WorkDay.day <= end.isoformat(),
            )
        )
    }
    return WorkSnapshot(patterns, off, exceptions)
