import json
from datetime import date
import pytest
from sqlalchemy import select
from fastapi import HTTPException
from app import leave, leave_rules
from app.db import Absence
from app.leave_models import LeaveRequest, LeavePolicy, LeaveAbsencePeriod
from app.leave_extensions import (
    WorkPattern,
    Closure,
    EmergencyAssignment,
    LeaveAccount,
    LeaveInbox,
)
from test_organization import units, grant
from test_native_tasks import task_people
from test_leave import assigned


def clean(db, uid, unit_ids):
    db.query(LeaveInbox).filter(LeaveInbox.user_id == uid).delete()
    db.query(LeaveRequest).filter(LeaveRequest.person_id == uid).delete()
    db.query(WorkPattern).filter(WorkPattern.person_id == uid).delete()
    db.query(LeaveAccount).filter(LeaveAccount.person_id == uid).delete()
    db.query(Closure).filter(Closure.org_id.in_(unit_ids)).delete()
    db.query(LeavePolicy).filter(LeavePolicy.org_id.in_(unit_ids)).delete()
    db.commit()


def test_multistage_decision_and_half_day_absence(db, task_people, units):
    root, a, _, _ = units
    person, local, central = task_people[:3]
    assigned(db, person, a)
    grant(db, a, local, "approver", False)
    grant(db, root, central, "approver", False)
    db.add(
        LeavePolicy(
            org_id=a.id,
            workflow="internal",
            sync_absence=True,
            approval_units=json.dumps([a.id, root.id]),
        )
    )
    db.commit()
    aid = None
    try:
        row = leave.save(
            db,
            person,
            dict(
                starts_on="2026-12-01",
                ends_on="2026-12-01",
                start_half="pm",
                end_half="pm",
            ),
        )
        db.commit()
        leave.command(db, person, row.id, "request", row.version)
        db.commit()
        leave.command(db, local, row.id, "approve", row.version)
        db.commit()
        assert row.status == "requested" and not row.effective_json
        with pytest.raises(HTTPException) as exc:
            leave.command(db, local, row.id, "approve", row.version)
        assert exc.value.status_code == 403
        db.rollback()
        leave.command(db, central, row.id, "approve", row.version)
        db.commit()
        assert row.status == "binding"
        aid = row.absence_id
        a = db.get(Absence, aid)
        assert a.substitute_id is None
        assert db.get(LeaveAbsencePeriod, aid).start_half == "pm"
        from app import absence

        assert "Nachmittag" in absence.span(a)
        leave.command(db, central, row.id, "cancel", row.version)
        db.commit()
        aid = None
    finally:
        clean(
            db, person.id, [a.org_id if hasattr(a, "org_id") else units[1].id, root.id]
        )
        if aid:
            db.query(LeaveAbsencePeriod).filter_by(absence_id=aid).delete()
            db.query(Absence).filter_by(id=aid).delete()
            db.commit()


def test_optional_account_blocks_overdraw_without_affecting_drafts(
    db, task_people, units
):
    _, unit, _, _ = units
    person = task_people[0]
    assigned(db, person, unit)
    db.add(LeavePolicy(org_id=unit.id, workflow="planning", internal_account=True))
    db.add(LeaveAccount(person_id=person.id, year=2026, entitlement=1, carry=0))
    db.commit()
    try:
        row = leave.save(db, person, dict(starts_on="2026-12-01", ends_on="2026-12-02"))
        db.commit()
        with pytest.raises(HTTPException) as exc:
            leave.command(db, person, row.id, "bind", row.version)
        assert exc.value.status_code == 409
        db.rollback()
        db.refresh(row)
        assert row.status == "planned"
    finally:
        clean(db, person.id, [unit.id])


def test_capacity_does_not_multiply_part_time_twice(db, task_people, units):
    _, unit, _, _ = units
    person, other = task_people[:2]
    assigned(db, person, unit)
    assigned(db, other, unit)
    db.add(
        LeavePolicy(
            org_id=unit.id, advanced=True, minimum_capacity=75, conflict_mode="block"
        )
    )
    db.add(
        WorkPattern(
            person_id=other.id,
            starts_on="2026-01-01",
            ends_on="2026-12-31",
            weekly_json=json.dumps([0.5] * 10 + [0] * 4),
        )
    )
    db.commit()
    try:
        p = leave.period(person.id, dict(starts_on="2026-12-01", ends_on="2026-12-01"))
        result = leave_rules.extra_conflicts(db, p)
        assert len(result) == 2 and all(
            c.available == 0.5 and c.minimum == 0.75 for c in result
        )
    finally:
        db.query(WorkPattern).filter_by(person_id=other.id).delete()
        clean(db, person.id, [unit.id])


def test_closure_markers_and_capacity_exception(db, task_people, units):
    _, unit, _, _ = units
    person = task_people[0]
    assigned(db, person, unit)
    db.add(
        LeavePolicy(
            org_id=unit.id,
            advanced=True,
            minimum=1,
            minimum_capacity=100,
            conflict_mode="block",
        )
    )
    closed = Closure(
        org_id=unit.id,
        title="Betriebsruhe",
        starts_on="2026-12-01",
        ends_on="2026-12-01",
        emergency_minimum=0,
    )
    db.add(closed)
    db.commit()
    try:
        marker = leave_rules.closure_obligations(db, closed, [person])[0]
        assert len(marker["missing"]) == 2
        row = leave.save(
            db, person, dict(starts_on=closed.starts_on, ends_on=closed.ends_on)
        )
        db.commit()
        marker = leave_rules.closure_obligations(db, closed, [person])[0]
        assert marker["planned"] == 2
        assert not leave.conflicts(
            db,
            leave.period(
                person.id, dict(starts_on=closed.starts_on, ends_on=closed.ends_on)
            ),
            row.id,
        )
        leave.command(db, person, row.id, "bind", row.version)
        db.commit()
        assert not leave_rules.closure_obligations(db, closed, [person])[0]["missing"]
        closed.ends_on = "2026-12-02"
        db.commit()
        leave.save(
            db,
            person,
            dict(
                starts_on="2026-12-02",
                ends_on="2026-12-02",
                start_half="am",
                end_half="am",
            ),
        )
        db.commit()
        proposal = leave_rules.closure_obligations(db, closed, [person])[0]["proposal"]
        assert proposal == dict(
            starts_on="2026-12-02", ends_on="2026-12-02", start_half="pm", end_half="pm"
        )
    finally:
        clean(db, person.id, [unit.id])


def test_planning_exception_requires_approver_and_preserves_external_attestation(
    db, task_people, units
):
    _, unit, _, _ = units
    person, approver = task_people[:2]
    assigned(db, person, unit)
    grant(db, unit, approver, "approver", False)
    db.add(
        LeavePolicy(
            org_id=unit.id, workflow="external", minimum=1, conflict_mode="warning"
        )
    )
    db.commit()
    try:
        row = leave.save(db, person, dict(starts_on="2026-12-01", ends_on="2026-12-01"))
        db.commit()
        with pytest.raises(HTTPException):
            leave.command(db, person, row.id, "attest", row.version)
        db.rollback()
        leave.command(db, person, row.id, "request_exception", row.version)
        db.commit()
        leave.command(
            db,
            approver,
            row.id,
            "approve",
            row.version,
            "Vertretung organisatorisch gesichert",
        )
        db.commit()
        assert (
            row.status == "planned"
            and row.warning_approved
            and not row.attested_at
            and not row.effective_json
        )
        leave.command(db, person, row.id, "attest", row.version)
        db.commit()
        assert row.status == "binding" and row.attested_by == person.id
    finally:
        clean(db, person.id, [unit.id])


def test_account_charge_stays_stable_after_work_pattern_changes(db, task_people, units):
    _, unit, _, _ = units
    person = task_people[0]
    assigned(db, person, unit)
    db.add(LeavePolicy(org_id=unit.id, workflow="planning", internal_account=True))
    db.add(LeaveAccount(person_id=person.id, year=2026, entitlement=30, carry=0))
    db.commit()
    try:
        row = leave.save(db, person, dict(starts_on="2026-12-01", ends_on="2026-12-01"))
        db.commit()
        leave.command(db, person, row.id, "bind", row.version)
        db.commit()
        db.add(
            WorkPattern(
                person_id=person.id,
                starts_on="2026-01-01",
                ends_on="2026-12-31",
                weekly_json=json.dumps([0] * 14),
            )
        )
        db.commit()
        assert leave_rules.account_balances(db, person.id)[0]["used"] == 1
        assert "account_charge" not in leave.serialize(row)["effective"]
    finally:
        clean(db, person.id, [unit.id])


def test_full_workday_with_only_one_scheduled_half_uses_one_day():
    from types import SimpleNamespace

    p = leave.period(
        1,
        dict(
            starts_on="2026-12-01", ends_on="2026-12-01", start_half="am", end_half="am"
        ),
    )
    pattern = SimpleNamespace(
        person_id=1,
        starts_on="2026-01-01",
        ends_on="2026-12-31",
        weekly_json=json.dumps([1, 0] * 5 + [0] * 4),
    )
    assert leave_rules.days_used(p, [pattern]) == {2026: 1}
    assert leave_rules.days_used(p, []) == {2026: 0.5}


def test_inactive_emergency_assignment_no_longer_counts(db, task_people, units):
    _, unit, _, _ = units
    person, duty = task_people[:2]
    assigned(db, person, unit)
    assigned(db, duty, unit)
    closed = Closure(
        org_id=unit.id,
        title="Schließzeit",
        starts_on="2026-12-01",
        ends_on="2026-12-01",
        emergency_minimum=1,
    )
    db.add(closed)
    db.flush()
    db.add(EmergencyAssignment(closure_id=closed.id, person_id=duty.id))
    db.commit()
    try:
        assert leave_rules.closure_status(db, closed)["assigned"] == 1
        duty.active = False
        db.commit()
        state = leave_rules.closure_status(db, closed)
        assert state["assigned"] == 0 and len(state["shortages"]) == 2
        p = leave.period(
            person.id, dict(starts_on=closed.starts_on, ends_on=closed.ends_on)
        )
        assert all(
            c.available == 0 and c.mode == "block"
            for c in leave_rules.extra_conflicts(db, p)
        )
        assert len(leave_rules.extra_conflicts(db, p)) == 2
    finally:
        duty.active = True
        clean(db, person.id, [unit.id])


def test_holidays_do_not_charge_leave_and_explicit_day_overrides_them(
    db, task_people, units
):
    from app.db import CustomHoliday
    from app.leave_extensions import WorkDay

    _, unit, _, _ = units
    person = task_people[0]
    assigned(db, person, unit)
    db.add(
        LeavePolicy(
            org_id=unit.id,
            workflow="planning",
            internal_account=True,
            holiday_state="RP",
        )
    )
    db.add(LeaveAccount(person_id=person.id, year=2026, entitlement=30, carry=0))
    price_day = CustomHoliday(day=date(2026, 12, 24), name="Nur Preisaufschlag")
    db.add(price_day)
    db.commit()
    try:
        p = leave.period(person.id, dict(starts_on="2026-12-24", ends_on="2026-12-25"))
        snapshot = leave_rules.work_snapshot(db, p.start, p.end, [person.id])
        assert leave_rules.days_used(p, snapshot) == {2026: 1}
        row = leave.save(db, person, dict(starts_on="2026-12-24", ends_on="2026-12-25"))
        db.commit()
        leave.command(db, person, row.id, "bind", row.version)
        db.commit()
        db.add(WorkDay(person_id=person.id, day="2026-12-25", am=1, pm=0))
        db.commit()
        holiday = leave.period(
            person.id, dict(starts_on="2026-12-25", ends_on="2026-12-25")
        )
        override = leave_rules.work_snapshot(
            db, holiday.start, holiday.end, [person.id]
        )
        assert leave_rules.days_used(holiday, override) == {2026: 1}
        assert leave_rules.account_balances(db, person.id)[0]["used"] == 1
    finally:
        db.delete(price_day)
        db.commit()
        clean(db, person.id, [unit.id])


def test_holiday_policy_inherits_through_local_workflow_override(
    db, task_people, units
):
    root, _, team, _ = units
    person = task_people[0]
    assigned(db, person, team)
    parent = LeavePolicy(org_id=root.id, holiday_state="BE")
    child = LeavePolicy(org_id=team.id, workflow="planning")
    db.add_all([parent, child])
    db.commit()
    try:
        day = date(2027, 3, 8)
        snapshot = leave_rules.work_snapshot(db, day, day, [person.id])
        assert leave_rules.capacity(snapshot, person.id, day, "am") == 0
        parent.holiday_state = "none"
        db.commit()
        assert (
            leave_rules.capacity(
                leave_rules.work_snapshot(db, day, day, [person.id]),
                person.id,
                day,
                "am",
            )
            == 1
        )
    finally:
        clean(db, person.id, [root.id, team.id])


def test_bulk_work_days_preserve_scope_and_roll_back(db, task_people, units):
    from app.leave_extensions import WorkDay
    from conftest import login, csrf_of, settings

    settings(module_calendars="1")
    _, a, _, b = units
    manager, one, two = task_people[:3]
    assigned(db, one, a)
    assigned(db, two, b)
    grant(db, a, manager, "leave_settings")
    c = login(manager.email, "task-passwort-123")
    data = dict(
        csrf=csrf_of(c.get("/").text),
        unit=a.id,
        action="work_day",
        person_ids=[str(one.id), str(two.id)],
        day="2026-12-02",
        am="0",
        pm="0",
    )
    try:
        assert c.post("/urlaub/konfiguration", data=data).status_code == 403
        assert not db.scalar(select(WorkDay.id).where(WorkDay.person_id == one.id))
        grant(db, b, manager, "leave_settings")
        assert c.post("/urlaub/konfiguration", data=data).status_code == 303
        assert db.scalar(select(WorkDay.id).where(WorkDay.person_id == one.id))
        assert db.scalar(select(WorkDay.id).where(WorkDay.person_id == two.id))
        assert c.post("/urlaub/konfiguration", data=data).status_code == 409
    finally:
        db.query(WorkDay).filter(WorkDay.person_id.in_([one.id, two.id])).delete()
        db.commit()
