"""Scoped configuration commands for work patterns, closure staffing and accounts."""

import json, math
from datetime import date
from fastapi import Depends, Request, HTTPException, Form
from sqlalchemy import select
from sqlalchemy.orm import Session
from .main import app, current_user, get_db, check_csrf, redirect, flash
from .db import User
from .leave_extensions import (
    WorkPattern,
    WorkDay,
    Closure,
    EmergencyAssignment,
    LeaveAccount,
    LeaveInbox,
    LeavePreference,
)
from .leave_models import LeaveRequest
from . import leave, leave_rules, organization as org


def number(raw):
    try:
        return int(raw)
    except (ValueError, TypeError):
        raise HTTPException(422, "Gültige Auswahl erforderlich.")


@app.post("/urlaub/hinweise/{notice_id:int}/lesen", dependencies=[Depends(check_csrf)])
def dismiss_leave_notice(notice_id: int, back: str = Form(""),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Only the addressee can acknowledge a notification from their task list."""
    notice = db.get(LeaveInbox, notice_id)
    if notice is None or notice.user_id != user.id:
        raise HTTPException(404)
    notice.read = True
    db.commit()
    return redirect('/urlaub/mein-urlaub' if back == 'leave' else '/tasks')


@app.post("/urlaub/konfiguration", dependencies=[Depends(check_csrf)])
async def configure(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    data = await request.form()
    unit = number(data.get("unit"))
    action = data.get("action")
    leave.lock(db)
    if action == "global_holidays":
        from .db import set_setting
        from .holidays import STATES

        if not user.is_admin:
            raise HTTPException(403)
        state = data.get("holiday_state")
        if state not in {*STATES, "none"}:
            raise HTTPException(422)
        set_setting(db, "leave_holiday_state", state)
        org.audit(db, user, None, "leave_holidays", state=state)
    elif action == "notifications":
        mode = data.get("email_mode")
        if mode not in ("none", "immediate", "daily"):
            raise HTTPException(422)
        row = db.get(LeavePreference, user.id) or LeavePreference(user_id=user.id)
        row.email_mode = mode
        db.add(row)
    elif action == "notice_read":
        row = db.get(LeaveInbox, number(data.get("notice_id")))
        if not row or row.user_id != user.id:
            raise HTTPException(404)
        row.read = True
    elif action == "emergency":
        closed = db.get(Closure, number(data.get("closure_id")))
        if not closed:
            raise HTTPException(404)
        uid = number(data.get("person_id") or user.id)
        is_manager = (org.allows(db, user, closed.org_id, "leave_settings") or org.allows(db, user, closed.org_id, "plan"))
        if not is_manager and not (closed.enrollment in ("self", "both") and uid == user.id):
            raise HTTPException(403)
        if closed.org_id not in org.active_path(db, leave.primary(db, uid)):
            raise HTTPException(403)
        person = db.get(User, uid)
        if not person or not person.active:
            raise HTTPException(
                422, "Eine aktive Person für die Notbesetzung auswählen."
            )
        key = (closed.id, uid)
        row = db.get(EmergencyAssignment, key)
        if data.get("remove") == "1":
            if row:
                db.delete(row)
        elif not row:
            for req in db.scalars(
                select(LeaveRequest).where(LeaveRequest.person_id == uid)
            ):
                if req.effective_json:
                    effective = json.loads(req.effective_json)
                    if (
                        effective["starts_on"] <= closed.ends_on
                        and effective["ends_on"] >= closed.starts_on
                    ):
                        raise HTTPException(
                            409,
                            "Verbindlicher Urlaub überschneidet sich mit der Notbesetzung.",
                        )
            from .db import Absence

            if db.scalar(
                select(Absence.id).where(
                    Absence.user_id == uid,
                    Absence.status == "confirmed",
                    Absence.starts_on <= closed.ends_on,
                    Absence.ends_on >= closed.starts_on,
                )
            ):
                raise HTTPException(
                    409,
                    "Eine wirksame Abwesenheit überschneidet sich mit der Notbesetzung.",
                )
            db.add(EmergencyAssignment(closure_id=closed.id, person_id=uid))
        org.audit(db, user, closed.org_id, "leave_emergency")
    elif action == "closure_update":
        closed = db.get(Closure, number(data.get("closure_id")))
        if not closed:
            raise HTTPException(404)
        if not org.allows(db, user, closed.org_id, "leave_settings"):
            raise HTTPException(403)
        signature = f"{closed.starts_on}:{closed.ends_on}:{closed.title}:{closed.emergency_minimum}:{closed.enrollment}"
        if signature != data.get("closure_version"):
            raise HTTPException(
                409, "Die Schließzeit wurde inzwischen geändert. Bitte neu laden."
            )
        if data.get("remove") == "1":
            db.delete(closed)
        else:
            p = leave.period(user.id, data)
            title = str(data.get("title", "")).strip()
            minimum = number(data.get("minimum"))
            enrollment = data.get("enrollment")
            if (
                not title
                or len(title) > 200
                or not 0 <= minimum <= 10000
                or enrollment not in ("lead", "self", "both")
            ):
                raise HTTPException(422)
            from .db import Absence

            ids = list(
                db.scalars(
                    select(EmergencyAssignment.person_id).where(
                        EmergencyAssignment.closure_id == closed.id
                    )
                )
            )
            if db.scalar(
                select(Absence.id).where(
                    Absence.user_id.in_(ids),
                    Absence.status == "confirmed",
                    Absence.starts_on <= p.end.isoformat(),
                    Absence.ends_on >= p.start.isoformat(),
                )
            ):
                raise HTTPException(
                    409,
                    "Die Notbesetzung überschneidet sich mit einer Abwesenheit. Zuerst Einteilung ändern.",
                )
            for req in db.scalars(
                select(LeaveRequest).where(LeaveRequest.person_id.in_(ids))
            ):
                if req.effective_json:
                    interval = json.loads(req.effective_json)
                    if (
                        interval["starts_on"] <= p.end.isoformat()
                        and interval["ends_on"] >= p.start.isoformat()
                    ):
                        raise HTTPException(
                            409,
                            "Die Notbesetzung überschneidet sich mit verbindlichem Urlaub.",
                        )
            closed.title = title
            closed.starts_on = p.start.isoformat()
            closed.ends_on = p.end.isoformat()
            closed.emergency_minimum = minimum
            closed.enrollment = enrollment
        org.audit(db, user, closed.org_id, "leave_closure_update")
    elif action == "work_remove":
        row = db.get(WorkPattern, number(data.get("work_id")))
        if not row:
            raise HTTPException(404)
        if not org.allows(db, user, leave.primary(db, row.person_id), "leave_settings"):
            raise HTTPException(403)
        db.delete(row)
        org.audit(db, user, leave.primary(db, row.person_id), "leave_work_remove")
    else:
        if not org.allows(db, user, unit, "leave_settings"):
            raise HTTPException(403)
        if action == "closure":
            p = leave.period(user.id, data)
            title = str(data.get("title", "")).strip()
            minimum = number(data.get("minimum", "0"))
            enrollment = data.get("enrollment", "lead")
            if (
                not title
                or len(title) > 200
                or not 0 <= minimum <= 10000
                or enrollment not in ("lead", "self", "both")
            ):
                raise HTTPException(422)
            db.add(
                Closure(
                    org_id=unit,
                    title=title,
                    starts_on=p.start.isoformat(),
                    ends_on=p.end.isoformat(),
                    emergency_minimum=minimum,
                    enrollment=enrollment,
                )
            )
        elif action == "work_day_remove":
            row = db.get(WorkDay, number(data.get("work_day_id")))
            if not row:
                raise HTTPException(404)
            if not org.allows(
                db, user, leave.primary(db, row.person_id), "leave_settings"
            ):
                raise HTTPException(403)
            db.delete(row)
        elif action in ("work", "account", "work_day"):
            selected = list(
                dict.fromkeys(data.getlist("person_ids") or [data.get("person_id", "")])
            )
            if not 1 <= len(selected) <= 500:
                raise HTTPException(422, "Zwischen einer und 500 Personen auswählen.")
            for raw in selected:
                uid = number(raw)
                person = db.get(User, uid)
                if not person or not person.active:
                    raise HTTPException(422, "Eine aktive Person auswählen.")
                if not org.allows(db, user, leave.primary(db, uid), "leave_settings"):
                    raise HTTPException(403)
                if action == "work_day":
                    try:
                        day = date.fromisoformat(data.get("day", ""))
                    except (ValueError, TypeError):
                        raise HTTPException(422, "Gültigen Arbeitstag auswählen.")
                    if not 1970 <= day.year <= 2200:
                        raise HTTPException(422)
                    values = leave_rules.validate_pattern(
                        [data.get("am", "0"), data.get("pm", "0")] + [0] * 12
                    )
                    if db.scalar(
                        select(WorkDay.id).where(
                            WorkDay.person_id == uid, WorkDay.day == day.isoformat()
                        )
                    ):
                        raise HTTPException(
                            409,
                            "Für diesen Tag ist bereits eine Abweichung erfasst. Diese vor einer Änderung entfernen.",
                        )
                    db.add(
                        WorkDay(
                            person_id=uid,
                            day=day.isoformat(),
                            am=values[0],
                            pm=values[1],
                        )
                    )
                elif action == "work":
                    p = leave.period(uid, data, max_days=36500)
                    weekly = leave_rules.validate_pattern(
                        [data.get("slot_" + str(i), "0") for i in range(14)]
                    )
                    if db.scalar(
                        select(WorkPattern.id).where(
                            WorkPattern.person_id == uid,
                            WorkPattern.starts_on <= p.end.isoformat(),
                            WorkPattern.ends_on >= p.start.isoformat(),
                        )
                    ):
                        raise HTTPException(
                            409,
                            "Für diesen Zeitraum ist bereits ein Arbeitsmodell vorhanden.",
                        )
                    db.add(
                        WorkPattern(
                            person_id=uid,
                            starts_on=p.start.isoformat(),
                            ends_on=p.end.isoformat(),
                            weekly_json=json.dumps(weekly),
                        )
                    )
                else:
                    try:
                        year = int(data.get("year"))
                        entitlement = float(data.get("entitlement", "0"))
                        carry = float(data.get("carry", "0"))
                    except (TypeError, ValueError):
                        raise HTTPException(422)
                    if not 2000 <= year <= 2200 or any(
                        not math.isfinite(v)
                        or not 0 <= v <= 10000
                        or v * 2 != int(v * 2)
                        for v in (entitlement, carry)
                    ):
                        raise HTTPException(
                            422,
                            "Anspruch und Übertrag in ganzen oder halben Tagen angeben.",
                        )
                    row = db.get(LeaveAccount, (uid, year)) or LeaveAccount(
                        person_id=uid, year=year
                    )
                    used = next(
                        (
                            a["used"]
                            for a in leave_rules.account_balances(db, uid)
                            if a["year"] == year
                        ),
                        0,
                    )
                    if entitlement + carry < used:
                        raise HTTPException(
                            409,
                            "Anspruch und Übertrag dürfen bereits verbrauchten Urlaub nicht unterschreiten.",
                        )
                    row.entitlement = entitlement
                    row.carry = carry
                    db.add(row)
        else:
            raise HTTPException(422)
        org.audit(db, user, unit, "leave_" + action)
    db.commit()
    flash(request, "Planungseinstellungen gespeichert.")
    from .routes_leave import _return_to
    return redirect(_return_to(request, "/urlaub/verwaltung", unit))
