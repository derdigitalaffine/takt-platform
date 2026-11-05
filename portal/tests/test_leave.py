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
        page = login(person.email, "task-passwort-123").get("/abwesenheiten")
        assert page.status_code == 200 and f"/urlaub/vorgang/{row.id}" in page.text
        assert f"/abwesenheiten/{aid}/loeschen" not in page.text
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


def test_area_viewer_can_read_but_never_plan_or_see_private_history(
    db, task_people, units
):
    _, unit, team, _ = units
    person, viewer = task_people[:2]
    assigned(db, person, team)
    grant(db, unit, viewer, "viewer")
    row = leave.save(db, person, dict(starts_on="2026-12-01", ends_on="2026-12-01"))
    db.commit()
    try:
        c = login(viewer.email, "task-passwort-123")
        page = c.get(f"/urlaub?unit={unit.id}")
        assert page.status_code == 200
        data = c.get(f"/urlaub/data?unit={unit.id}").json()
        # Area viewers may see availability, not colleagues' leave reasons.
        assert data["requests"] == []
        assert data["people"][0]["canSelect"] is False
        token = csrf_of(page.text)
        assert (
            c.post(
                "/urlaub/preview",
                json=dict(
                    person_id=person.id, starts_on="2026-12-01", ends_on="2026-12-01"
                ),
                headers={"X-CSRF-Token": token},
            ).status_code
            == 403
        )
        assert c.get(f"/urlaub/{row.id}/verlauf").status_code == 403
    finally:
        db.query(LeaveRequest).filter_by(person_id=person.id).delete()
        db.commit()


def test_parent_view_uses_each_persons_actual_workflow(db, task_people, units):
    _, unit, team, _ = units
    person = task_people[0]
    assigned(db, person, team)
    grant(db, unit, person, "viewer")
    db.add(LeavePolicy(org_id=team.id, workflow="external"))
    db.commit()
    row = leave.save(db, person, dict(starts_on="2026-12-01", ends_on="2026-12-01"))
    db.commit()
    try:
        c = login(person.email, "task-passwort-123")
        page = c.get(f"/urlaub?unit={unit.id}")
        assert page.status_code == 200
        assert (
            "Externe Genehmigung selbst bestätigen" in page.text
            and 'value="bind"' not in page.text
        )
    finally:
        db.query(LeaveRequest).filter_by(person_id=person.id).delete()
        db.query(LeavePolicy).filter_by(org_id=team.id).delete()
        db.commit()


def test_cancellation_of_edited_binding_leave_reaches_final_approver(
    db, task_people, units
):
    root, unit, _, _ = units
    person, local, central = task_people[:3]
    assigned(db, person, unit)
    grant(db, unit, local, "approver", False)
    grant(db, root, central, "approver", False)
    db.add(
        LeavePolicy(
            org_id=unit.id,
            workflow="internal",
            approval_units=json.dumps([unit.id, root.id]),
        )
    )
    db.commit()
    try:
        row = leave.save(db, person, dict(starts_on="2026-12-01", ends_on="2026-12-01"))
        db.commit()
        for actor, action in (
            (person, "request"),
            (local, "approve"),
            (central, "approve"),
        ):
            leave.command(db, actor, row.id, action, row.version)
            db.commit()
        leave.save(
            db,
            person,
            dict(starts_on="2026-12-02", ends_on="2026-12-02", version=row.version),
            row.id,
        )
        db.commit()
        leave.command(db, person, row.id, "request_cancel", row.version)
        db.commit()
        assert json.loads(row.effective_json)["starts_on"] == "2026-12-01"
        c = login(central.email, "task-passwort-123")
        response = c.get(f"/urlaub/vorgang/{row.id}", follow_redirects=False)
        assert (
            response.status_code == 303
            and f"unit={root.id}" in response.headers["location"]
        )
        assert c.get(f"/urlaub/{row.id}/verlauf").status_code == 200
        with pytest.raises(HTTPException) as exc:
            leave.command(db, local, row.id, "cancel", row.version)
        assert exc.value.status_code == 403
        db.rollback()
        leave.command(db, central, row.id, "cancel", row.version)
        db.commit()
        assert not row.effective_json
    finally:
        db.query(LeaveRequest).filter_by(person_id=person.id).delete()
        db.query(LeavePolicy).filter_by(org_id=unit.id).delete()
        db.commit()


def test_leave_sections_and_settings_are_separate_routes(db, task_people, units):
    _, area, _, _ = units
    person, leader = task_people[:2]
    assigned(db, person, area)
    grant(db, area, leader, "lead", False)
    person_client = login(person.email, "task-passwort-123")
    leader_client = login(leader.email, "task-passwort-123")
    assert person_client.get(f"/urlaub/mein-urlaub?unit={area.id}").status_code == 200
    assert person_client.get(f"/urlaub/verwaltung/feiertage?unit={area.id}").status_code == 403
    assert person_client.get(f"/urlaub/genehmigungen?unit={area.id}").status_code == 403
    assert leader_client.get(f"/urlaub/genehmigungen?unit={area.id}").status_code == 200
    assert leader_client.get(f"/urlaub/verwaltung/besetzung?unit={area.id}").status_code == 403
    admin = login("admin@example.org", "admin-passwort-123")
    for topic in ("verfahren", "besetzung", "arbeitsmodelle", "feiertage", "urlaubskonten"):
        page = admin.get(f"/urlaub/verwaltung/{topic}?unit={area.id}")
        assert page.status_code == 200, (topic, page.text[:300])
    assert admin.get(f"/urlaub/verwaltung/unknown?unit={area.id}").status_code == 404


def test_leader_cannot_approve_own_leave_and_defaults_to_parent(
    db, task_people, units,
):
    root, area, _, _ = units
    person = task_people[0]
    assigned(db, person, area)
    grant(db, area, person, "deputy", False)
    db.add(LeavePolicy(org_id=area.id, workflow="internal"))
    db.commit()
    try:
        row = leave.save(db, person, dict(starts_on="2026-12-09", ends_on="2026-12-10"))
        db.commit()
        leave.command(db, person, row.id, "request", row.version)
        db.commit()
        assert json.loads(row.approval_path) == [root.id]
        with pytest.raises(HTTPException) as exc:
            leave.command(db, person, row.id, "approve", row.version)
        assert exc.value.status_code == 403
        assert row.status == "requested"
    finally:
        db.query(LeaveRequest).filter_by(person_id=person.id).delete()
        db.query(LeavePolicy).filter_by(org_id=area.id).delete()
        db.commit()


def test_existing_krankmeldung_is_private_read_only_projection(
    db, task_people, units,
):
    from app import krank
    from app.db import KrankReport
    _, area, team, _ = units
    person, viewer, leader = task_people[:3]
    assigned(db, person, team)
    grant(db, area, viewer, "viewer")
    grant(db, area, leader, "lead")
    report = KrankReport(
        ref_no="T-PRIVATE-ILLNESS-001", kind="simple", status="new",
        user_id=person.id,
    )
    krank.set_data(report, {"date": "2026-12-07", "first_name": person.name})
    db.add(report)
    db.commit()
    try:
        def read_as(actor):
            c = login(actor.email, "task-passwort-123")
            result = c.get(f"/urlaub/data?unit={area.id}")
            assert result.status_code == 200
            return result.json()
        coworker = read_as(viewer)
        displayed = [row for row in coworker["absences"] if str(row["id"]).startswith("presence:")]
        assert len(displayed) == 1 and displayed[0]["title"] == "Abwesend"
        assert "first_name" not in str(coworker)
        supervisor = read_as(leader)
        displayed = [row for row in supervisor["absences"] if str(row["id"]).startswith("presence:")]
        assert len(displayed) == 1 and displayed[0]["title"] == "Krank"
        assert "first_name" not in str(supervisor)
        own = read_as(person)
        assert any(row["title"] == "Krank" for row in own["absences"])
    finally:
        db.delete(report)
        db.commit()
