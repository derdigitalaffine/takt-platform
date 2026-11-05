"""Organization-scoped leave commands. Caller commits or rolls back the whole transaction."""

import json
from dataclasses import asdict
from datetime import date, timedelta
from fastapi import HTTPException
from sqlalchemy import select, update
from .db import User, Organization, Absence, utcnow
from .org_models import OrgMembership, OrgState
from .leave_models import LeavePolicy, LeaveRequest, LeaveAudit, LeaveAbsencePeriod
from . import organization as org, staffing


def primary(db, person_id):
    row = db.scalar(
        select(OrgMembership).where(
            OrgMembership.user_id == person_id, OrgMembership.is_primary.is_(True)
        )
    )
    if not row or not org.active_path(db, row.org_id):
        raise HTTPException(422, "Eine aktive Hauptzuordnung ist erforderlich.")
    return row.org_id


def policy(db, unit):
    for oid in org.active_path(db, unit):
        row = db.get(LeavePolicy, oid)
        if row:
            return row
    return LeavePolicy(
        org_id=unit,
        workflow="planning",
        sync_absence=False,
        minimum=0,
        conflict_mode="warning",
        external_url="",
    )


def can_plan(db, actor, person_id):
    person = db.get(User, person_id)
    if not actor.active or not person or not person.active:
        return False
    try:
        unit = primary(db, person_id)
    except HTTPException:
        return False
    return actor.id == person_id or org.allows(db, actor, unit, "plan")


def period(person_id, data, max_days=400):
    try:
        p = staffing.Period(
            person_id,
            date.fromisoformat(data["starts_on"]),
            date.fromisoformat(data["ends_on"]),
            data.get("start_half", "am"),
            data.get("end_half", "pm"),
        )
        if (p.end - p.start).days > max_days:
            raise ValueError()
        return p
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "Gültigen Zeitraum mit höchstens 401 Tagen wählen.")


def interval(row):
    return dict(
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        start_half=row.start_half,
        end_half=row.end_half,
    )


def serialize(row):
    return dict(
        id=row.id,
        person_id=row.person_id,
        org_id=row.org_id,
        **interval(row),
        status=row.status,
        version=row.version,
        effective=(
            {
                key: value
                for key, value in json.loads(row.effective_json).items()
                if key in ("starts_on", "ends_on", "start_half", "end_half")
            }
            if row.effective_json
            else None
        ),
        external_attested=bool(row.attested_at),
        cancel_requested=row.cancel_requested
    )


def conflicts(db, p, keep=None):
    nodes = {n.id: n for n in db.scalars(select(Organization))}
    parents = {oid: n.parent_id for oid, n in nodes.items()}
    memberships = [
        (m.user_id, m.org_id, m.counts_staff)
        for m in db.scalars(
            select(OrgMembership)
            .join(User, User.id == OrgMembership.user_id)
            .where(User.active.is_(True))
        )
        if org.active_path(db, m.org_id, nodes)
    ]
    rules = [
        staffing.Rule(r.org_id, r.minimum, r.conflict_mode)
        for r in db.scalars(select(LeavePolicy))
        if r.minimum and org.active_path(db, r.org_id, nodes)
    ]
    effective = []
    tentative = []
    mirrors = set()
    for row in db.scalars(select(LeaveRequest)):
        if row.absence_id:
            mirrors.add(row.absence_id)
        if row.id == keep:
            continue
        if row.effective_json:
            effective.append(period(row.person_id, json.loads(row.effective_json)))
        if row.status in ("planned", "requested"):
            tentative.append(period(row.person_id, interval(row)))
    for a in db.scalars(select(Absence).where(Absence.status == "confirmed")):
        if a.id not in mirrors:
            effective.append(
                period(a.user_id, dict(starts_on=a.starts_on, ends_on=a.ends_on))
            )
    working = {uid: set() for uid, _, _ in memberships}
    for offset in range((p.end - p.start).days + 1):
        day = p.start + timedelta(days=offset)
        if day.weekday() < 5:
            for slots in working.values():
                slots.update(((day, "am"), (day, "pm")))
    result = staffing.check_headcount(
        candidate=p,
        memberships=memberships,
        parents=parents,
        rules=rules,
        unavailable=effective,
        tentative=tentative,
        working=working,
    )
    from .leave_rules import extra_conflicts, capacity
    from .leave_extensions import WorkPattern

    patterns = list(db.scalars(select(WorkPattern)))
    advanced = {r.org_id for r in db.scalars(select(LeavePolicy)) if r.advanced}
    if advanced:
        result = [c for c in result if c.org_id not in advanced]
        scheduled = {uid: set() for uid, _, _ in memberships}
        for offset in range((p.end - p.start).days + 1):
            day = p.start + timedelta(days=offset)
            for uid in scheduled:
                for half in ("am", "pm"):
                    if capacity(patterns, uid, day, half) > 0:
                        scheduled[uid].add((day, half))
        result += staffing.check_headcount(
            candidate=p,
            memberships=memberships,
            parents=parents,
            rules=[r for r in rules if r.org_id in advanced],
            unavailable=effective,
            tentative=tentative,
            working=scheduled,
        )

    from .leave_extensions import Closure

    closures = list(db.scalars(select(Closure)))
    result = [
        c
        for c in result
        if not any(
            cl.org_id in org.active_path(db, c.org_id, nodes)
            and cl.starts_on <= c.day.isoformat() <= cl.ends_on
            for cl in closures
        )
    ]
    return result + extra_conflicts(db, p, keep)


def audit(db, actor, row, action, detail=""):
    db.add(
        LeaveAudit(request_id=row.id, actor_id=actor.id, action=action, detail=detail)
    )


def lock(db):
    # Shares the organizational mutation lock: moves and memberships cannot race binding.
    db.execute(
        update(OrgState).where(OrgState.id == 1).values(version=OrgState.version + 1)
    )
    db.expire_all()


def save(db, actor, data, request_id=None):
    lock(db)
    row = db.get(LeaveRequest, request_id) if request_id else None
    if request_id and not row:
        raise HTTPException(404)
    try:
        uid = row.person_id if row else int(data.get("person_id") or actor.id)
    except (TypeError, ValueError):
        raise HTTPException(422, "Gültige Person wählen.")
    if not can_plan(db, actor, uid):
        raise HTTPException(403)
    if row and str(row.version) != str(data.get("version")):
        raise HTTPException(
            409, "Der Urlaub wurde inzwischen geändert. Bitte neu laden."
        )
    p = period(uid, data)
    unit = primary(db, uid)
    if row is None:
        row = LeaveRequest(person_id=uid, org_id=unit, created_by=actor.id)
        db.add(row)
    row.starts_on = p.start.isoformat()
    row.ends_on = p.end.isoformat()
    row.start_half = p.start_half
    row.end_half = p.end_half
    row.org_id = unit
    row.status = "planned"
    row.attested_at = None
    row.attested_by = None
    row.warning_approved = False
    row.approval_path = "[]"
    row.approval_step = 0
    row.requested_workflow = ""
    row.cancel_requested = False
    row.version = (row.version or 0) + 1
    row.updated_at = utcnow()
    db.flush()
    audit(db, actor, row, "plan", json.dumps(interval(row)))
    return row


def decision_unit(row):
    path = json.loads(row.approval_path or "[]") or [row.org_id]
    return path[min(row.approval_step or 0, len(path) - 1)]


def cancellation_unit(db, row):
    return (json.loads(policy(db, row.org_id).approval_units or "[]") or [row.org_id])[
        -1
    ]


def command(db, actor, request_id, action, version, reason=""):
    lock(db)
    row = db.get(LeaveRequest, request_id)
    if not row:
        raise HTTPException(404)
    if str(row.version) != str(version):
        raise HTTPException(
            409, "Der Urlaub wurde inzwischen geändert. Bitte neu laden."
        )
    unit = primary(db, row.person_id)
    if unit != row.org_id:
        raise HTTPException(
            409,
            "Die Hauptzuordnung wurde geändert. Den Zeitraum als Entwurf neu prüfen.",
        )
    cfg = policy(db, unit)
    if (
        action in ("approve", "reject")
        and row.requested_workflow
        and row.requested_workflow != cfg.workflow
    ):
        raise HTTPException(
            409, "Der Urlaubsablauf wurde geändert. Den Antrag als Entwurf neu prüfen."
        )
    path = json.loads(row.approval_path or "[]") or [unit]
    decision_unit = path[min(row.approval_step or 0, len(path) - 1)]
    if action in ("cancel", "request_cancel", "reject_cancel"):
        decision_unit = cancellation_unit(db, row)
    if action == "reject_cancel":
        if not row.cancel_requested or not org.allows(
            db, actor, decision_unit, "approve"
        ):
            raise HTTPException(403)
        row.cancel_requested = False
    elif action in ("approve", "reject"):
        if (
            not org.allows(db, actor, decision_unit, "approve")
            or row.status != "requested"
        ):
            raise HTTPException(403)
    elif not can_plan(db, actor, row.person_id) and not (
        action == "cancel" and org.allows(db, actor, decision_unit, "approve")
    ):
        raise HTTPException(403)
    if action in ("request", "request_exception"):
        if (
            action == "request" and cfg.workflow != "internal"
        ) or row.status != "planned":
            raise HTTPException(422, "Dieser Ablauf benötigt keinen internen Antrag.")
        row.status = "requested"
        row.requested_workflow = cfg.workflow
        path = json.loads(cfg.approval_units or "[]") or [unit]
        if any(node not in org.active_path(db, unit) for node in path):
            raise HTTPException(
                422,
                "Genehmigungsweg muss der Hauptzuordnung und ihren Vorfahren folgen.",
            )
        row.approval_path = json.dumps(path)
        row.approval_step = 0
    elif action == "request_cancel":
        if row.cancel_requested:
            raise HTTPException(409, "Die Stornierung ist bereits angefragt.")
        if not row.effective_json or cfg.workflow != "internal":
            raise HTTPException(
                422, "Für diesen Urlaub ist keine Stornoanfrage erforderlich."
            )
        row.cancel_requested = True
    elif action == "reject_cancel":
        pass
    elif action == "reject":
        row.status = "rejected"
    elif action == "cancel":
        if (
            cfg.workflow == "internal"
            and row.effective_json
            and not org.allows(db, actor, decision_unit, "approve")
        ):
            raise HTTPException(
                403, "Verbindlichen Urlaub muss die zuständige Genehmigung aufheben."
            )
        row.status = "cancelled"
        row.cancel_requested = False
        row.effective_json = ""
        if row.absence_id:
            a = db.get(Absence, row.absence_id)
            row.absence_id = None
            db.flush()
            db.delete(a)
    elif action == "approve" and (row.approval_step or 0) + 1 < len(path):
        row.approval_step = (row.approval_step or 0) + 1
    elif action == "approve" and cfg.workflow != "internal":
        if not reason.strip():
            raise HTTPException(422, "Eine Ausnahme muss begründet werden.")
        if any(
            c.mode == "block" and not c.forecast
            for c in conflicts(db, period(row.person_id, interval(row)), row.id)
        ):
            raise HTTPException(
                409, "Verbindliche Sperren können nicht übergangen werden."
            )
        row.warning_approved = True
        row.status = "planned"
    elif action in ("bind", "attest", "approve"):
        if action == "bind" and cfg.workflow != "planning":
            raise HTTPException(
                422, "Genehmigung oder externe Selbstauskunft erforderlich."
            )
        if action == "attest" and (
            cfg.workflow != "external" or actor.id != row.person_id
        ):
            raise HTTPException(
                403,
                "Externe Genehmigung kann nur die betroffene Person selbst bestätigen.",
            )
        if row.status not in ("planned", "requested"):
            raise HTTPException(422, "Zuerst einen Entwurf erstellen.")
        p = period(row.person_id, interval(row))
        for existing in db.scalars(
            select(LeaveRequest).where(
                LeaveRequest.person_id == row.person_id, LeaveRequest.id != row.id
            )
        ):
            if existing.effective_json:
                other = period(row.person_id, json.loads(existing.effective_json))
                if (p.start, p.start_half == "pm") <= (
                    other.end,
                    other.end_half == "pm",
                ) and (other.start, other.start_half == "pm") <= (
                    p.end,
                    p.end_half == "pm",
                ):
                    raise HTTPException(
                        409,
                        "Dieser Zeitraum überschneidet sich mit bereits verbindlichem Urlaub.",
                    )
        issues = [c for c in conflicts(db, p, row.id) if not c.forecast]
        if any(c.mode == "block" for c in issues):
            raise HTTPException(409, "Verbindliche Mindestbesetzung unterschritten.")
        if (
            issues
            and not row.warning_approved
            and not cfg.notify_only_warnings
            and (
                not org.allows(db, actor, decision_unit, "approve")
                or not reason.strip()
            )
        ):
            raise HTTPException(
                409,
                "Warnungen benötigen eine Begründung durch berechtigte Genehmigende.",
            )
        # Manual absences remain authoritative; never overwrite their dates or delegation.
        mirrors = set(
            db.scalars(
                select(LeaveRequest.absence_id).where(
                    LeaveRequest.absence_id.is_not(None)
                )
            )
        )
        for a in db.scalars(
            select(Absence).where(
                Absence.user_id == row.person_id,
                Absence.status == "confirmed",
                Absence.starts_on <= row.ends_on,
                Absence.ends_on >= row.starts_on,
            )
        ):
            if a.id not in mirrors:
                raise HTTPException(
                    409,
                    "Der Zeitraum überschneidet sich mit einer manuell erfassten Abwesenheit.",
                )
        if cfg.internal_account:
            from .leave_rules import account_check

            account_check(db, row.person_id, p, row.id)
        row.status = "binding"
        effective = interval(row)
        if cfg.internal_account:
            from .leave_rules import days_used
            from .leave_extensions import WorkPattern

            effective["account_charge"] = days_used(
                p, list(db.scalars(select(WorkPattern)))
            )
        row.effective_json = json.dumps(effective)
        if action == "attest":
            row.attested_by = actor.id
            row.attested_at = utcnow()
        if cfg.sync_absence or row.absence_id:
            a = (
                db.get(Absence, row.absence_id)
                if row.absence_id
                else Absence(
                    user_id=row.person_id,
                    created_by=actor.id,
                    status="confirmed",
                    substitute_id=None,
                )
            )
            a.starts_on = row.starts_on
            a.ends_on = row.ends_on
            if not row.absence_id:
                db.add(a)
                db.flush()
                row.absence_id = a.id
            scope = db.get(LeaveAbsencePeriod, a.id) or LeaveAbsencePeriod(
                absence_id=a.id
            )
            scope.start_half = row.start_half
            scope.end_half = row.end_half
            db.add(scope)
    else:
        raise HTTPException(422, "Aktion unbekannt.")
    row.version += 1
    row.updated_at = utcnow()
    audit(db, actor, row, action, reason.strip()[:2000])
    from .leave_rules import notify_request

    affected = {
        unit
        for m in db.scalars(
            select(OrgMembership).where(
                OrgMembership.user_id == row.person_id,
                OrgMembership.counts_staff.is_(True),
            )
        )
        for unit in org.active_path(db, m.org_id)
    }
    notify_request(
        db,
        row,
        actor,
        "Urlaub: "
        + {
            "request": "Antrag eingegangen",
            "request_exception": "Ausnahmeentscheidung erforderlich",
            "request_cancel": "Stornierung angefragt",
            "reject_cancel": "Stornierung abgelehnt",
            "approve": "Genehmigung bearbeitet",
            "reject": "Antrag abgelehnt",
            "bind": "Verbindlich eingeplant",
            "attest": "Externe Selbstauskunft erfasst",
            "cancel": "Urlaub storniert",
        }.get(action, action),
        affected,
    )
    return row
