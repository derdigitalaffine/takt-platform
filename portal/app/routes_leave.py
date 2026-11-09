"""First complete server-rendered entry points for the leave domain."""

import json
from datetime import date
from dataclasses import asdict
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import people_choices
from .main import app, current_user, get_db, check_csrf, render, redirect, flash
from .db import User, Organization, Absence, get_settings
from .org_models import OrgMembership
from .holidays import STATES
from .leave_models import LeaveRequest, LeavePolicy
from . import leave, leave_rules, organization as org
from .leave_extensions import (
    Closure,
    EmergencyAssignment,
    LeaveInbox,
    LeaveAccount,
    WorkPattern,
    WorkDay,
    LeavePreference,
)


def readable(db, actor, unit):
    if not actor.active or not org.active_path(db, unit):
        return False
    if actor.is_admin:
        return True
    if db.scalar(
        select(OrgMembership.id).where(
            OrgMembership.user_id == actor.id, OrgMembership.org_id == unit
        )
    ):
        return True
    return any(
        g.org_id in org.active_path(db, unit)
        and (g.org_id == unit or g.include_children)
        and g.role in org.ROLES
        for g in org.grants(db, actor)
    )


def can_view_person(db, actor, uid):
    if actor.is_admin or actor.id == uid:
        return True
    memberships = list(db.scalars(select(OrgMembership)))
    own = {m.org_id for m in memberships if m.user_id == actor.id}
    for member in memberships:
        if member.user_id != uid:
            continue
        path = org.active_path(db, member.org_id)
        if own.intersection(path):
            return True
        for grant in org.grants(db, actor):
            if grant.org_id in path and (
                grant.org_id == member.org_id or grant.include_children
            ):
                return True
    return False


def can_read_request(db, actor, row):
    if row.cancel_requested and org.allows(
        db, actor, leave.cancellation_unit(db, row), "approve"
    ):
        return True
    if can_view_person(db, actor, row.person_id):
        return True
    import json

    path = json.loads(row.approval_path or "[]")
    return (
        row.status == "requested"
        and bool(path)
        and org.allows(
            db, actor, path[min(row.approval_step or 0, len(path) - 1)], "approve"
        )
    )


def can_see_leave_details(db, actor, person_id):
    """Only the person and explicitly responsible planners/approvers see leave details.

    An ordinary colleague's organizational membership is not permission to see
    absence reasons. This rule also applies to the timeline JSON feed.
    """
    if actor.id == person_id or actor.is_admin:
        return True
    try:
        unit = leave.primary(db, person_id)
    except HTTPException:
        return False
    return any(org.allows(db, actor, unit, cap) for cap in ("plan", "approve", "absence_manage"))


def can_decide_request(db, actor, row):
    """Only the explicitly assigned decision unit sees a pending request.

    This also covers parent-level approvers whose role is intentionally scoped
    to the parent (include_children=False), without expanding their general
    access to every subordinate employee's leave details.
    """
    if actor.id == row.person_id:
        return False
    return (
        row.status == "requested"
        and org.allows(db, actor, leave.decision_unit(row), "approve")
    ) or (
        row.cancel_requested
        and org.allows(db, actor, leave.cancellation_unit(db, row), "approve")
    )


def can_see_illness(db, actor, person_id):
    """Only the person and leadership may see the non-medical 'Krank' label."""
    if actor.id == person_id or actor.is_admin or actor.can("krank_admin"):
        return True
    try:
        path = org.active_path(db, leave.primary(db, person_id))
    except HTTPException:
        return False
    return any(
        grant.role in ("lead", "deputy") and grant.org_id in path
        and (grant.org_id == path[0] or grant.include_children)
        for grant in org.grants(db, actor)
    )


def can_read_history(db, actor, row):
    return (
        actor.id == row.person_id
        or org.allows(db, actor, leave.decision_unit(row), "approve")
        or (
            row.cancel_requested
            and org.allows(db, actor, leave.cancellation_unit(db, row), "approve")
        )
    )


def visible_people(db, actor, unit):
    if not readable(db, actor, unit):
        raise HTTPException(403)
    ids = [
        m.user_id
        for m in db.scalars(select(OrgMembership))
        if unit in org.active_path(db, m.org_id)
    ]
    pending = {
        r.person_id
        for r in db.scalars(
            select(LeaveRequest).where(
                (LeaveRequest.status == "requested")
                | LeaveRequest.cancel_requested.is_(True)
            )
        )
        if can_read_request(db, actor, r)
    }
    return [
        p
        for p in db.scalars(
            select(User)
            .where(User.id.in_(ids), User.active.is_(True))
            .order_by(User.name)
        )
        if can_view_person(db, actor, p.id) or p.id in pending
    ]


LEAVE_SECTIONS = {"planer", "mein-urlaub", "genehmigungen", "schliesszeiten", "verwaltung"}
LEAVE_TOPICS = {"verfahren", "besetzung", "arbeitsmodelle", "feiertage", "urlaubskonten"}


@app.get("/urlaub")
@app.get("/urlaub/planer")
@app.get("/urlaub/mein-urlaub")
@app.get("/urlaub/genehmigungen")
@app.get("/urlaub/schliesszeiten")
@app.get("/urlaub/verwaltung")
@app.get("/urlaub/verwaltung/{topic}")
def page(
    request: Request,
    unit: int | None = None,
    topic: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    units = [
        n
        for n in db.scalars(select(Organization).order_by(Organization.name))
        if readable(db, user, n.id)
    ]
    if unit is None:
        own = db.scalar(
            select(OrgMembership.org_id).where(
                OrgMembership.user_id == user.id, OrgMembership.is_primary.is_(True)
            )
        )
        try:
            remembered = json.loads(user.nav_json or "{}").get("last_org_unit")
        except (ValueError, AttributeError):
            remembered = None
        allowed = {n.id for n in units}
        unit = remembered if remembered in allowed else own or (units[0].id if units else None)
    path = request.url.path
    if topic is not None and topic not in LEAVE_TOPICS:
        raise HTTPException(404)
    section = (
        "verwaltung" if path.startswith("/urlaub/verwaltung") else
        path.removeprefix("/urlaub/") if path != "/urlaub" else
        ("planer" if unit and org.allows(db, user, unit, "plan") else "mein-urlaub")
    )
    if section not in LEAVE_SECTIONS:
        raise HTTPException(404)
    config_topic = topic or "verfahren"
    can_settings = bool(unit and org.allows(db, user, unit, "leave_settings"))
    can_approve = bool(unit and org.allows(db, user, unit, "approve"))
    if section == "verwaltung" and not can_settings:
        raise HTTPException(403)
    if section == "genehmigungen" and not can_approve:
        raise HTTPException(403)
    people = visible_people(db, user, unit) if unit else []
    try:
        personal_unit = leave.primary(db, user.id)
    except HTTPException:
        personal_unit = None
    # "Mein Urlaub" is always personal, even when leadership has selected a
    # different team or department in the shared organization context.
    if section == "mein-urlaub" and personal_unit and all(p.id != user.id for p in people):
        people.append(user)
    ids = [p.id for p in people]
    from .leave_admin import removed_ids
    rows = []
    if section in {"planer", "mein-urlaub", "genehmigungen"}:
        query = select(LeaveRequest).where(LeaveRequest.person_id.in_(ids), LeaveRequest.id.not_in(removed_ids()))
        if section == "mein-urlaub":
            query = query.where(LeaveRequest.person_id == user.id)
        elif section == "genehmigungen":
            query = query.where(
                (LeaveRequest.status == "requested")
                | LeaveRequest.cancel_requested.is_(True)
            )
        rows = [
            r for r in db.scalars(
                query.order_by(LeaveRequest.starts_on, LeaveRequest.id)
            )
            if can_read_request(db, user, r)
            and (can_see_leave_details(db, user, r.person_id) or can_decide_request(db, user, r))
        ]
    visible_closures = (
        [c for c in db.scalars(select(Closure)) if c.org_id in org.active_path(db, unit)]
        if unit and section == "schliesszeiten" else []
    )
    preference = db.get(LeavePreference, user.id) if section == "mein-urlaub" else None
    return render(
        request,
        "leave.html",
        user,
        units=units,
        approval_options=(
            [db.get(Organization, oid) for oid in org.active_path(db, unit)]
            if unit
            else []
        ),
        approval_selected=(
            json.loads(leave.policy(db, unit).approval_units or "[]") if unit else []
        ),
        unit=unit,
        personal_unit=personal_unit,
        active_section=section,
        config_topic=config_topic,
        can_approve=can_approve,
        current_year=date.today().year,
        holiday_states=STATES,
        portal_holiday_state=get_settings(db).get("leave_holiday_state", "RP"),
        people=people,
        work_choices=people_choices.users(
            [
                p
                for p in people
                if org.allows(db, user, leave.primary(db, p.id), "leave_settings")
            ]
        ),
        can_create=any(leave.can_plan(db, user, p.id) for p in people),
        rows=rows,
        row_policies={r.id: leave.policy(db, r.org_id) for r in rows},
        closures=visible_closures,
        closure_managers={
            c.id: org.allows(db, user, c.org_id, "leave_settings")
            for c in visible_closures
        },
        closure_enrollers={
            c.id: org.allows(db, user, c.org_id, "plan") or
                  org.allows(db, user, c.org_id, "leave_settings")
            for c in visible_closures
        },
        closure_obligations={
            c.id: leave_rules.closure_obligations(db, c, people)
            for c in visible_closures
        },
        emergency={
            c.id: leave_rules.eligible_emergency_ids(db, c)
            for c in visible_closures
        },
        closure_statuses={
            c.id: leave_rules.closure_status(db, c)
            for c in visible_closures
        },
        email_mode=preference.email_mode if preference else "none",
        notices=(
            list(db.scalars(
                select(LeaveInbox)
                .where(LeaveInbox.user_id == user.id, LeaveInbox.read.is_(False))
                .order_by(LeaveInbox.id.desc())
                .limit(50)
            )) if section == "mein-urlaub" else []
        ),
        accounts=(
            leave_rules.account_balances(db, user.id)
            if section == "mein-urlaub" and personal_unit
            and leave.policy(db, personal_unit).internal_account
            else []
        ),
        work_patterns=(
            list(db.scalars(select(WorkPattern).where(WorkPattern.person_id.in_(ids))))
            if unit and section == "verwaltung" and config_topic == "arbeitsmodelle"
            and org.allows(db, user, unit, "leave_settings")
            else []
        ),
        local_policy=db.get(LeavePolicy, unit) if unit else None,
        work_days=(
            list(
                db.scalars(
                    select(WorkDay)
                    .where(WorkDay.person_id.in_(ids))
                    .order_by(WorkDay.day)
                )
            )
            if unit and section == "verwaltung" and config_topic == "arbeitsmodelle"
            and org.allows(db, user, unit, "leave_settings")
            else []
        ),
        policy=leave.policy(db, unit) if unit else None,
        can_settings=can_settings,
        planners={p.id: leave.can_plan(db, user, p.id) for p in people},
        approvers={
            r.id: r.person_id != user.id and org.allows(
                db, user, leave.decision_unit(r), "approve"
            ) for r in rows
        },
        cancel_approvers={
            r.id: r.person_id != user.id and org.allows(
                db, user, leave.cancellation_unit(db, r), "approve"
            ) for r in rows
        },
        admin_absences=(list(db.scalars(select(Absence).where(
            Absence.user_id.in_(ids),
            Absence.id.not_in(select(LeaveRequest.absence_id).where(LeaveRequest.absence_id.is_not(None)))
        ))) if user.is_admin and section == "planer" else []),
        history_rights={r.id: can_read_history(db, user, r) for r in rows},
    )


@app.get("/urlaub/data")
def data(unit: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    people = visible_people(db, user, unit)
    ids = [p.id for p in people]
    from .db import Absence
    from .leave_models import LeaveAbsencePeriod

    # Absence and leave remain the source of truth: no new mirrored rows.
    mirrors = set(
        db.scalars(
            select(LeaveAbsencePeriod.absence_id)
            .where(LeaveAbsencePeriod.absence_id.is_not(None))
        )
    )
    # The direct LeaveRequest.absence_id link is used by older and current records.
    mirrors.update(
        db.scalars(
            select(LeaveRequest.absence_id).where(LeaveRequest.absence_id.is_not(None))
        )
    )
    absence_rows = [
        a for a in db.scalars(
            select(Absence).where(
                Absence.user_id.in_(ids), Absence.status == "confirmed"
            )
        )
        if a.id not in mirrors
    ]
    absences = [
        dict(id=a.id, person_id=a.user_id,
             starts_on=a.starts_on, ends_on=a.ends_on,
             start_half="am", end_half="pm", title="Abwesend")
        for a in absence_rows
    ]
    requests = []
    bindings = []
    from .leave_admin import removed_ids
    for req in db.scalars(
        select(LeaveRequest).where(LeaveRequest.person_id.in_(ids), LeaveRequest.id.not_in(removed_ids()))
    ):
        if not can_read_request(db, user, req):
            continue
        if can_see_leave_details(db, user, req.person_id) or can_decide_request(db, user, req):
            requests.append(leave.serialize(req))
        elif req.effective_json:
            # Colleagues only see availability, not an individual status or reason.
            try:
                interval = json.loads(req.effective_json)
            except ValueError:
                continue
            absences.append(dict(
                id="leave:" + str(req.id), person_id=req.person_id,
                starts_on=interval["starts_on"], ends_on=interval["ends_on"],
                start_half=interval.get("start_half", "am"),
                end_half=interval.get("end_half", "pm"), title="Abwesend",
            ))
        if req.effective_json:
            try:
                bindings.append((req.person_id, json.loads(req.effective_json)))
            except ValueError:
                pass

    # Canonical, read-only Fachmodul projections. An absence already covering
    # the session has priority, so no person has a duplicate visual event.
    from .leave_sources import staffing_periods
    for index, source in enumerate(staffing_periods(db, ids)):
        start = source["starts_on"]
        finish = source["ends_on"]
        person_id = source["person_id"]
        overlap = any(
            a.user_id == person_id and a.starts_on <= finish and a.ends_on >= start
            for a in absence_rows
        ) or any(
            uid == person_id
            and times.get("starts_on", "9999") <= finish
            and times.get("ends_on", "0000") >= start
            for uid, times in bindings
        )
        if overlap:
            continue
        reason_allowed = (
            can_see_illness(db, user, person_id)
            if source["kind"] == "illness"
            else can_see_leave_details(db, user, person_id)
        )
        absences.append(dict(
            id="presence:" + str(index), person_id=person_id,
            starts_on=start, ends_on=finish,
            start_half=source["start_half"], end_half=source["end_half"],
            title=source["title"] if reason_allowed else "Abwesend",
        ))

    def leadership(person):
        path = org.active_path(db, unit)
        roles = {
            g.role for g in org.grants(db, person)
            if g.org_id in path and (g.org_id == unit or g.include_children)
        }
        return "Leitung" if "lead" in roles else (
            "Stellvertretung" if "deputy" in roles else ""
        )

    return dict(
        absences=absences,
        people=[
            dict(
                id=p.id, name=p.name,
                canSelect=leave.can_plan(db, user, p.id),
                roleTag=leadership(p),
            )
            for p in people
        ],
        requests=requests,
    )


def _return_to(request, fallback, unit):
    # Only fixed leave pages on the same host are valid return destinations.
    from urllib.parse import urlsplit
    ref = urlsplit(request.headers.get("referer", ""))
    path = ref.path
    valid = path in {"/urlaub", *(f"/urlaub/{s}" for s in LEAVE_SECTIONS)} or (
        path.startswith("/urlaub/verwaltung/") and
        path.rsplit("/", 1)[-1] in LEAVE_TOPICS
    )
    if ref.netloc == request.url.netloc and valid:
        return path + "?unit=" + str(unit)
    return fallback + "?unit=" + str(unit)


@app.post("/urlaub/preview", dependencies=[Depends(check_csrf)])
async def preview(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    from .calendars import json_payload

    payload = await json_payload(request)
    try:
        uid = int(payload.get("person_id") or user.id)
    except (TypeError, ValueError):
        raise HTTPException(422)
    if not leave.can_plan(db, user, uid):
        raise HTTPException(403)
    keep = payload.get("request_id")
    if keep is not None:
        try:
            keep = int(keep)
        except (ValueError, TypeError):
            raise HTTPException(422)
        existing = db.get(LeaveRequest, keep)
        if not existing or existing.person_id != uid:
            raise HTTPException(404)
    return dict(
        conflicts=[
            asdict(c) for c in leave.conflicts(db, leave.period(uid, payload), keep)
        ]
    )


@app.post("/urlaub", dependencies=[Depends(check_csrf)])
async def create(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = leave.save(db, user, dict(await request.form()))
    db.commit()
    if request.headers.get("accept") == "application/json":
        return leave.serialize(row)
    flash(request, "Urlaubsentwurf gespeichert.")
    return redirect(_return_to(request, "/urlaub/planer", row.org_id))


@app.post("/urlaub/{rid:int}", dependencies=[Depends(check_csrf)])
async def update(
    request: Request,
    rid: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    payload = dict(await request.form())
    action = payload.get("action")
    if action == "save":
        row = leave.save(db, user, payload, rid)
    else:
        row = leave.command(
            db, user, rid, action, payload.get("version"), payload.get("reason", "")
        )
    db.commit()
    if request.headers.get("accept") == "application/json":
        return leave.serialize(row)
    flash(request, "Urlaub gespeichert.")
    return redirect(_return_to(request, "/urlaub/planer", row.org_id))


@app.post("/urlaub/regeln/{unit:int}", dependencies=[Depends(check_csrf)])
async def settings_save(
    request: Request,
    unit: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Persist exactly the settings tab being edited, never hidden sibling tabs.

    Without 'topic' the existing full-policy form remains supported for older
    clients. The policy row remains the one canonical record per unit.
    """
    import math
    from urllib.parse import urlparse

    if not org.allows(db, user, unit, "leave_settings"):
        raise HTTPException(403)
    data = await request.form()
    topic = str(data.get("topic", ""))
    valid_topics = {"verfahren", "besetzung", "feiertage", "urlaubskonten"}
    if topic and topic not in valid_topics:
        raise HTTPException(422, "Unbekannter Einstellungsbereich.")
    action = data.get("action", "save")
    if action not in {"save", "inherit"}:
        raise HTTPException(422, "Aktion nicht verfügbar.")

    leave.lock(db)
    inherited = leave.policy(db, unit)
    if data.get("policy_version") != f"{inherited.org_id}:{inherited.version or 0}":
        raise HTTPException(
            409, "Die Urlaubsregeln wurden inzwischen geändert. Bitte neu laden."
        )
    if action == "inherit":
        # The existing schema inherits an entire policy, never individual
        # fields: only offer an explicit, complete reset in the procedure tab.
        if topic not in {"", "verfahren"}:
            raise HTTPException(
                422, "Alle Bereichsregeln können nur im Verfahren zurückgesetzt werden."
            )
        row = db.get(LeavePolicy, unit)
        if row:
            db.delete(row)
    else:
        row = db.get(LeavePolicy, unit)
        if row is None:
            # A scoped first edit must not reset unrelated inherited settings.
            # Copy the *effective* configuration into the canonical local row.
            row = LeavePolicy(org_id=unit)
            defaults = {
                "workflow": "planning",
                "sync_absence": False,
                "minimum": 0,
                "conflict_mode": "warning",
                "external_url": "",
                "external_attestation": False,
                "advanced": False,
                "minimum_capacity": 0,
                "internal_account": False,
                "approval_units": "[]",
                "notify_only_warnings": False,
                "holiday_state": "inherit",
            }
            for key, default in defaults.items():
                value = getattr(inherited, key, None)
                setattr(row, key, default if value is None else value)

        if topic in {"", "verfahren"}:
            workflow = data.get("workflow")
            if workflow not in {"planning", "internal", "external"}:
                raise HTTPException(422, "Urlaubsverfahren prüfen.")
            url = str(data.get("external_url", "")).strip()
            # Reject malformed IPv6 hosts, credentials and control characters
            # before URL values are rendered back into anchor href attributes.
            try:
                parsed = urlparse(url)
                host = parsed.hostname
                invalid_url = (
                    bool(url)
                    and (
                        len(url) > 1000
                        or any(char.isspace() or ord(char) < 32 for char in url)
                        or parsed.scheme not in {"https", "http"}
                        or not host
                        or parsed.username is not None
                        or parsed.password is not None
                    )
                )
            except ValueError:
                invalid_url = True
            if invalid_url:
                raise HTTPException(422, "Gültige Adresse der externen ZE-Software angeben.")
            raw_units = data.getlist("approval_units")
            if any(not str(value).isdigit() for value in raw_units):
                raise HTTPException(422, "Genehmigungsweg prüfen.")
            approval = [int(value) for value in raw_units]
            allowed = set(org.active_path(db, unit))
            if len(approval) != len(set(approval)) or any(
                oid not in allowed for oid in approval
            ):
                raise HTTPException(422, "Genehmigungsweg prüfen.")
            row.workflow = workflow
            row.external_url = url
            row.external_attestation = data.get("external_attestation") == "1"
            row.sync_absence = data.get("sync_absence") == "1"
            row.approval_units = json.dumps(approval)

        if topic in {"", "besetzung"}:
            try:
                minimum = int(data.get("minimum", "0"))
                minimum_capacity = float(data.get("minimum_capacity", "0"))
            except (TypeError, ValueError):
                raise HTTPException(422, "Mindestbesetzung und Kapazität prüfen.")
            mode = data.get("conflict_mode")
            if (
                mode not in {"warning", "block"}
                or not 0 <= minimum <= 10000
                or not math.isfinite(minimum_capacity)
                or not 0 <= minimum_capacity <= 10000
            ):
                raise HTTPException(422, "Besetzungsregeln prüfen.")
            row.minimum = minimum
            row.conflict_mode = mode
            row.advanced = data.get("advanced") == "1"
            row.minimum_capacity = round(minimum_capacity * 100)
            row.notify_only_warnings = data.get("notify_only_warnings") == "1"

        if topic in {"", "feiertage"}:
            state = data.get("holiday_state", "inherit")
            if state not in {"inherit", "none", *STATES}:
                raise HTTPException(422, "Feiertagskalender prüfen.")
            row.holiday_state = state

        if topic in {"", "urlaubskonten"}:
            row.internal_account = data.get("internal_account") == "1"

        if row.workflow == "external" and row.internal_account:
            raise HTTPException(
                422, "Bei externer Kontenverwaltung darf kein internes Urlaubskonto aktiviert werden."
            )
        row.version = (row.version or 0) + 1
        db.add(row)
    org.audit(db, user, unit, "leave_policy", topic=topic or "gesamt", operation=action)
    db.commit()
    flash(request, "Urlaubsregeln gespeichert.")
    fallback = "/urlaub/verwaltung/" + (topic if topic else "verfahren")
    return redirect(_return_to(request, fallback, unit))


@app.get("/urlaub/{rid:int}/verlauf")
def history(
    request: Request,
    rid: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from .leave_models import LeaveAudit

    row = db.get(LeaveRequest, rid)
    if not row or not can_read_history(db, user, row):
        raise HTTPException(403)
    rows = list(
        db.scalars(
            select(LeaveAudit)
            .where(LeaveAudit.request_id == rid)
            .order_by(LeaveAudit.id)
        )
    )
    return render(
        request,
        "leave_history.html",
        user,
        row=row,
        person=db.get(User, row.person_id),
        history=rows,
        actors={a.actor_id: db.get(User, a.actor_id) for a in rows},
    )


@app.get("/urlaub/besetzung")
def summary(
    unit: int,
    start: str,
    end: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not readable(db, user, unit):
        raise HTTPException(403)
    from .calendar_recurrence import window

    a, b = window(start, end)
    days = leave_rules.holiday_days(db, unit, a.date(), b.date())
    return dict(
        summaries=leave_rules.planning_summary(db, unit, a.date(), b.date()),
        holidays=[dict(date=d.isoformat(), label=label) for d, label in days.items()],
    )


@app.get("/urlaub/vorgang/{rid:int}")
def open_request(
    rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.get(LeaveRequest, rid)
    if not row or not can_read_request(db, user, row):
        raise HTTPException(403)
    unit = leave.primary(db, row.person_id)
    for oid in org.active_path(db, unit):
        if readable(db, user, oid):
            return redirect(f"/urlaub?unit={oid}#leave-row-{rid}")
    raise HTTPException(403)


@app.get("/urlaub/{rid:int}/loeschen")
def delete_leave_preview(request: Request, rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _removal_preview(request, db, user, "leave", rid)


@app.get("/urlaub/abwesenheit/{rid:int}/loeschen")
def delete_absence_preview(request: Request, rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _removal_preview(request, db, user, "absence", rid)


def _removal_preview(request, db, user, kind, rid):
    from . import leave_admin
    row = leave_admin.item(db, user, kind, rid)
    uid = row.person_id if kind == "leave" else row.user_id
    response = render(request, "leave_delete.html", user, row=row, person=db.get(User, uid),
                      kind=kind, version=str(row.version) if kind == "leave" else leave_admin.absence_version(row))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/urlaub/{rid:int}/loeschen", dependencies=[Depends(check_csrf)])
async def delete_leave(request: Request, rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return await _remove_absence(request, db, user, "leave", rid)


@app.post("/urlaub/abwesenheit/{rid:int}/loeschen", dependencies=[Depends(check_csrf)])
async def delete_absence(request: Request, rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return await _remove_absence(request, db, user, "absence", rid)


async def _remove_absence(request, db, user, kind, rid):
    from . import leave_admin
    payload = await request.form()
    if payload.get("confirm") != "1":
        raise HTTPException(422, "Die Löschung muss ausdrücklich bestätigt werden.")
    try:
        leave_admin.remove(db, user, kind, rid, payload.get("version"), payload.get("reason", ""))
        db.commit()
    except Exception:
        db.rollback()
        raise
    flash(request, "Abwesenheit aus der aktiven Planung gelöscht. Begründung und Verlauf bleiben erhalten.")
    return redirect("/urlaub/planer")
