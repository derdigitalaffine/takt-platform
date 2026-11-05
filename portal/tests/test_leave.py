"""Commands exercise transaction and scope boundaries, not just date formatting."""

import json
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app import leave
from app.db import Absence
from app.leave_models import LeavePolicy, LeaveRequest
from test_organization import units, grant
from test_native_tasks import task_people
from conftest import login, csrf_of


def assigned(db, person, unit):
    from app.org_models import OrgMembership

    db.add(
        OrgMembership(
            user_id=person.id, org_id=unit.id, is_primary=True, counts_staff=True
        )
    )
    db.commit()


def test_binding_sync_and_proposed_change_keep_effective_absence(
    db, task_people, units
):
    _, a, _, _ = units
    person = task_people[0]
    assigned(db, person, a)
    db.add(LeavePolicy(org_id=a.id, workflow="planning", sync_absence=True))
    db.commit()
    try:
        row = leave.save(db, person, dict(starts_on="2026-12-01", ends_on="2026-12-03"))
        db.commit()
        leave.command(db, person, row.id, "bind", row.version)
        db.commit()
        aid = row.absence_id
        assert db.get(Absence, aid).substitute_id is None
        leave.save(
            db,
            person,
            dict(starts_on="2026-12-07", ends_on="2026-12-09", version=row.version),
            row.id,
        )
        db.commit()
        assert db.get(Absence, aid).starts_on == "2026-12-01"
        assert json.loads(row.effective_json)["starts_on"] == "2026-12-01"
        leave.command(db, person, row.id, "bind", row.version)
        db.commit()
        assert row.absence_id == aid and db.get(Absence, aid).starts_on == "2026-12-07"
        leave.command(db, person, row.id, "cancel", row.version)
        db.commit()
        assert not db.get(Absence, aid)
    finally:
        db.query(LeaveRequest).filter_by(person_id=person.id).delete()
        db.query(LeavePolicy).filter_by(org_id=a.id).delete()
        db.commit()


def test_external_attestation_cannot_be_delegated_and_stale_version(
    db, task_people, units
):
    _, a, _, _ = units
    person, planner = task_people[:2]
    assigned(db, person, a)
    grant(db, a, planner, "planner")
    db.add(LeavePolicy(org_id=a.id, workflow="external"))
    db.commit()
    try:
        row = leave.save(
            db,
            planner,
            dict(person_id=person.id, starts_on="2026-12-01", ends_on="2026-12-01"),
        )
        db.commit()
        rid, version = row.id, row.version
        with pytest.raises(HTTPException) as exc:
            leave.command(db, planner, rid, "attest", version)
        assert exc.value.status_code == 403
        db.rollback()
        leave.command(db, person, rid, "attest", version)
        db.commit()
        assert row.attested_by == person.id
        with pytest.raises(HTTPException) as exc:
            leave.command(db, person, rid, "cancel", version)
        assert exc.value.status_code == 409
        db.rollback()
    finally:
        db.query(LeaveRequest).filter_by(person_id=person.id).delete()
        db.query(LeavePolicy).filter_by(org_id=a.id).delete()
        db.commit()


def test_leave_routes_require_scope_and_hide_internal_audit(db, task_people, units):
    _, a, _, b = units
    person, other = task_people[:2]
    assigned(db, person, a)
    assigned(db, other, b)
    c = login(person.email, "task-passwort-123")
    assert c.get("/urlaub?unit=" + str(a.id)).status_code == 200
    assert c.get("/urlaub/data?unit=" + str(b.id)).status_code == 403
    response = c.post(
        "/urlaub",
        data={
            "csrf": csrf_of(c.get("/").text),
            "person_id": other.id,
            "starts_on": "2026-12-01",
            "ends_on": "2026-12-02",
        },
    )
    assert response.status_code == 403


from test_calendars import calendar_enabled


def test_two_binding_requests_cannot_overlap_for_same_person(db, task_people, units):
    _, unit, _, _ = units
    person = task_people[0]
    assigned(db, person, unit)
    try:
        first = leave.save(
            db, person, dict(starts_on="2026-12-01", ends_on="2026-12-01")
        )
        db.commit()
        leave.command(db, person, first.id, "bind", first.version)
        db.commit()
        second = leave.save(
            db, person, dict(starts_on="2026-12-01", ends_on="2026-12-01")
        )
        db.commit()
        with pytest.raises(HTTPException) as exc:
            leave.command(db, person, second.id, "bind", second.version)
        assert exc.value.status_code == 409
        db.rollback()
        db.refresh(second)
        assert not second.effective_json
    finally:
        db.query(LeaveRequest).filter_by(person_id=person.id).delete()
        db.commit()


def test_simultaneous_binding_serializes_staffing_decision(db, task_people, units):
    from concurrent.futures import ThreadPoolExecutor
    from app.db import SessionLocal, User
    from app.leave_extensions import LeaveInbox

    _, unit, _, _ = units
    first, second = task_people[:2]
    assigned(db, first, unit)
    assigned(db, second, unit)
    db.add(
        LeavePolicy(
            org_id=unit.id, workflow="planning", minimum=1, conflict_mode="block"
        )
    )
    db.commit()
    rows = [
        leave.save(db, p, dict(starts_on="2026-12-01", ends_on="2026-12-01"))
        for p in (first, second)
    ]
    db.commit()
    inputs = [(r.id, r.person_id, r.version) for r in rows]

    def bind(values):
        rid, uid, version = values
        with SessionLocal() as session:
            try:
                leave.command(session, session.get(User, uid), rid, "bind", version)
                session.commit()
                return 200
            except HTTPException as exc:
                session.rollback()
                return exc.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(bind, inputs)) == [200, 409]
    finally:
        db.rollback()
        db.query(LeaveRequest).filter(
            LeaveRequest.person_id.in_([first.id, second.id])
        ).delete()
        db.query(LeavePolicy).filter_by(org_id=unit.id).delete()
        db.commit()
