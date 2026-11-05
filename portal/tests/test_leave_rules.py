import json
from datetime import date
import pytest
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
