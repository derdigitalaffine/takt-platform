"""First complete server-rendered entry points for the leave domain."""

import json
from datetime import date
from dataclasses import asdict
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from .main import app, current_user, get_db, check_csrf, render, redirect, flash
from .db import User, Organization
from .org_models import OrgMembership
from .leave_models import LeaveRequest, LeavePolicy
from . import leave, leave_rules, organization as org
from .leave_extensions import (
    Closure,
    EmergencyAssignment,
    LeaveInbox,
    LeaveAccount,
    WorkPattern,
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


@app.get("/urlaub")
def page(
    request: Request,
    unit: int | None = None,
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
        unit = own or (units[0].id if units else None)
    people = visible_people(db, user, unit) if unit else []
    ids = [p.id for p in people]
    rows = list(
        db.scalars(
            select(LeaveRequest)
            .where(LeaveRequest.person_id.in_(ids))
            .order_by(LeaveRequest.starts_on, LeaveRequest.id)
        )
    )
    rows = [r for r in rows if can_read_request(db, user, r)]
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
        current_year=date.today().year,
        people=people,
        rows=rows,
        closures=[
            c
            for c in db.scalars(select(Closure))
            if unit and c.org_id in org.active_path(db, unit)
        ],
        closure_managers={
            c.id: org.allows(db, user, c.org_id, "leave_settings")
            for c in db.scalars(select(Closure))
        },
        closure_obligations={
            c.id: leave_rules.closure_obligations(db, c, people)
            for c in db.scalars(select(Closure))
            if unit and c.org_id in org.active_path(db, unit)
        },
        emergency={
            c.closure_id: set(
                db.scalars(
                    select(EmergencyAssignment.person_id).where(
                        EmergencyAssignment.closure_id == c.closure_id
                    )
                )
            )
            for c in db.scalars(select(EmergencyAssignment))
        },
        email_mode=(
            db.get(LeavePreference, user.id).email_mode
            if db.get(LeavePreference, user.id)
            else "none"
        ),
        notices=list(
            db.scalars(
                select(LeaveInbox)
                .where(LeaveInbox.user_id == user.id, LeaveInbox.read.is_(False))
                .order_by(LeaveInbox.id.desc())
                .limit(50)
            )
        ),
        accounts=(
            leave_rules.account_balances(db, user.id)
            if unit and leave.policy(db, unit).internal_account
            else []
        ),
        work_patterns=(
            list(db.scalars(select(WorkPattern).where(WorkPattern.person_id.in_(ids))))
            if unit and org.allows(db, user, unit, "leave_settings")
            else []
        ),
        local_policy=db.get(LeavePolicy, unit) if unit else None,
        policy=leave.policy(db, unit) if unit else None,
        can_settings=bool(unit and org.allows(db, user, unit, "leave_settings")),
        planners={p.id: leave.can_plan(db, user, p.id) for p in people},
        approvers={
            r.id: org.allows(db, user, leave.decision_unit(r), "approve") for r in rows
        },
        history_rights={
            r.id: user.id == r.person_id
            or org.allows(db, user, leave.decision_unit(r), "approve")
            for r in rows
        },
        cancel_approvers={
            r.id: org.allows(db, user, leave.cancellation_unit(db, r), "approve")
            for r in rows
        },
    )


@app.get("/urlaub/data")
def data(unit: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    people = visible_people(db, user, unit)
    ids = [p.id for p in people]
    from .db import Absence

    mirrors = set(
        db.scalars(
            select(LeaveRequest.absence_id).where(LeaveRequest.absence_id.is_not(None))
        )
    )
    absence_rows = [
        a
        for a in db.scalars(
            select(Absence).where(
                Absence.user_id.in_(ids), Absence.status == "confirmed"
            )
        )
        if a.id not in mirrors
    ]
    return dict(
        absences=[
            dict(
                id=a.id,
                person_id=a.user_id,
                starts_on=a.starts_on,
                ends_on=a.ends_on,
                start_half="am",
                end_half="pm",
            )
            for a in absence_rows
        ],
        people=[
            dict(id=p.id, name=p.name, canSelect=leave.can_plan(db, user, p.id))
            for p in people
        ],
        requests=[
            leave.serialize(r)
            for r in db.scalars(
                select(LeaveRequest).where(LeaveRequest.person_id.in_(ids))
            )
            if can_read_request(db, user, r)
        ],
    )


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
    return redirect("/urlaub?unit=" + str(row.org_id))


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
    return redirect("/urlaub?unit=" + str(row.org_id))


@app.post("/urlaub/regeln/{unit:int}", dependencies=[Depends(check_csrf)])
async def settings_save(
    request: Request,
    unit: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from urllib.parse import urlparse

    if not org.allows(db, user, unit, "leave_settings"):
        raise HTTPException(403)
    data = await request.form()
    leave.lock(db)
    current = leave.policy(db, unit)
    if data.get("policy_version") != f"{current.org_id}:{current.version or 0}":
        raise HTTPException(
            409, "Die Urlaubsregeln wurden inzwischen geändert. Bitte neu laden."
        )
    if data.get("action") == "inherit":
        row = db.get(LeavePolicy, unit)
        if row:
            db.delete(row)
    else:
        workflow = data.get("workflow")
        mode = data.get("conflict_mode")
        url = str(data.get("external_url", "")).strip()
        try:
            minimum = int(data.get("minimum", "0"))
        except (TypeError, ValueError):
            raise HTTPException(422, "Mindestbesetzung prüfen.")
        if (
            workflow not in ("planning", "internal", "external")
            or mode not in ("warning", "block")
            or not 0 <= minimum <= 10000
        ):
            raise HTTPException(422, "Regeln prüfen.")
        if url and (
            urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc
        ):
            raise HTTPException(422, "Gültige Adresse des externen Systems angeben.")
        row = db.get(LeavePolicy, unit) or LeavePolicy(org_id=unit)
        row.version = (row.version or 0) + 1
        row.workflow = workflow
        row.minimum = minimum
        row.conflict_mode = mode
        row.external_url = url[:1000]
        row.sync_absence = data.get("sync_absence") == "1"
        row.notify_only_warnings = data.get("notify_only_warnings") == "1"
        import json, math

        try:
            minimum_capacity = float(data.get("minimum_capacity", "0"))
        except ValueError:
            raise HTTPException(422)
        if not math.isfinite(minimum_capacity) or not 0 <= minimum_capacity <= 10000:
            raise HTTPException(422)
        path = [
            int(raw) for raw in data.getlist("approval_units") if str(raw).isdigit()
        ]
        if any(oid not in org.active_path(db, unit) for oid in path) or len(
            path
        ) != len(set(path)):
            raise HTTPException(422, "Genehmigungsweg prüfen.")
        row.advanced = data.get("advanced") == "1"
        row.minimum_capacity = round(minimum_capacity * 100)
        row.internal_account = data.get("internal_account") == "1"
        row.approval_units = json.dumps(path)
        if row.workflow == "external" and row.internal_account:
            raise HTTPException(
                422,
                "Bei externer Kontenverwaltung darf kein internes Urlaubskonto aktiviert werden.",
            )
        db.add(row)
    org.audit(db, user, unit, "leave_policy")
    db.commit()
    flash(request, "Urlaubsregeln gespeichert.")
    return redirect("/urlaub?unit=" + str(unit))


@app.get("/urlaub/{rid:int}/verlauf")
def history(
    request: Request,
    rid: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from .leave_models import LeaveAudit

    row = db.get(LeaveRequest, rid)
    if not row or not (
        user.id == row.person_id
        or org.allows(db, user, leave.decision_unit(row), "approve")
    ):
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
    return leave_rules.planning_summary(db, unit, a.date(), b.date())
