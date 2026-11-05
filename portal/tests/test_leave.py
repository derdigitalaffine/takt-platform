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
        def read_as(actor, unit_id=area.id):
            c = login(actor.email, "task-passwort-123")
            result = c.get(f"/urlaub/data?unit={unit_id}")
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
        own = read_as(person, team.id)
        assert any(row["title"] == "Krank" for row in own["absences"])
    finally:
        db.delete(report)
        db.commit()

def test_illness_source_reduces_staffing_without_duplicate_absence_records(
    db, task_people, units,
):
    """Use canonical Krankmelder data for staffing; never mirror it into Absence."""
    from app import krank
    from app.db import KrankReport

    _, area, _, _ = units
    planner, sick = task_people[:2]
    assigned(db, planner, area)
    assigned(db, sick, area)
    db.add(LeavePolicy(
        org_id=area.id, workflow="planning", minimum=1,
        conflict_mode="block",
    ))
    report = KrankReport(
        ref_no="T-PRIVATE-STAFFING-001", kind="simple", status="new",
        user_id=sick.id,
    )
    krank.set_data(report, {"date": "2026-12-08"})
    db.add(report)
    db.commit()
    try:
        row = leave.save(db, planner, dict(
            starts_on="2026-12-08", ends_on="2026-12-08",
        ))
        db.commit()
        with pytest.raises(HTTPException) as denied:
            leave.command(db, planner, row.id, "bind", row.version)
        assert denied.value.status_code == 409
        # The Krankmelder remains the canonical source: no shadow Absence is made.
        assert not db.scalar(select(Absence.id).where(
            Absence.user_id == sick.id, Absence.starts_on == "2026-12-08",
        ))
    finally:
        db.rollback()
        db.query(LeaveRequest).filter_by(person_id=planner.id).delete()
        db.query(LeavePolicy).filter_by(org_id=area.id).delete()
        db.delete(report)
        db.commit()

def test_leadership_cannot_decide_own_internal_cancellation(db, task_people, units):
    """A deputy is still an employee; cancelling effective leave needs another approver."""
    _, area, _, _ = units
    person = task_people[0]
    assigned(db, person, area)
    grant(db, area, person, "deputy")
    db.add(LeavePolicy(org_id=area.id, workflow="internal"))
    db.commit()
    try:
        row = leave.save(db, person, dict(
            starts_on="2026-12-15", ends_on="2026-12-16",
        ))
        row.status = "binding"
        row.effective_json = json.dumps(leave.interval(row))
        row.cancel_requested = True
        db.commit()
        for action in ("cancel", "reject_cancel"):
            with pytest.raises(HTTPException) as denied:
                leave.command(db, person, row.id, action, row.version)
            assert denied.value.status_code == 403
            db.rollback()
    finally:
        db.rollback()
        db.query(LeaveRequest).filter_by(person_id=person.id).delete()
        db.query(LeavePolicy).filter_by(org_id=area.id).delete()
        db.commit()


def test_settings_tab_ignores_hidden_fields_and_preserves_other_settings(
    db, task_people, units,
):
    """Changing staffing rules must never silently change external procedures."""
    _, area, _, _ = units
    policy = LeavePolicy(
        org_id=area.id, workflow="external",
        external_attestation=True,
        external_url="https://zeit.example.org",
        minimum=3, conflict_mode="warning",
        holiday_state="BE", internal_account=False,
    )
    db.add(policy)
    db.commit()
    try:
        admin = login("admin@example.org", "admin-passwort-123")
        result = admin.post(
            f"/urlaub/regeln/{area.id}",
            data={
                "csrf": csrf_of(admin.get("/").text),
                "policy_version": f"{area.id}:{policy.version}",
                "topic": "besetzung", "action": "save",
                "minimum": "2", "conflict_mode": "block",
                "minimum_capacity": "0",
                # Forged sibling value must be ignored server-side.
                "workflow": "planning",
                "external_url": "https://other.example.org",
            },
            follow_redirects=False,
        )
        assert result.status_code == 303, result.text
        db.refresh(policy)
        assert policy.minimum == 2 and policy.conflict_mode == "block"
        assert policy.workflow == "external"
        assert policy.external_attestation is True
        assert policy.external_url == "https://zeit.example.org"
        assert policy.holiday_state == "BE"
    finally:
        db.rollback()
        db.query(LeavePolicy).filter_by(org_id=area.id).delete()
        db.commit()


def test_first_scoped_settings_save_preserves_inherited_workflow(
    db, task_people, units,
):
    """A child unit editing holidays must not reset its parent's staffing rules."""
    root, area, _, _ = units
    parent = LeavePolicy(
        org_id=root.id, workflow="internal", minimum=4,
        conflict_mode="block", external_attestation=False,
        approval_units=json.dumps([root.id]),
    )
    db.add(parent)
    db.commit()
    try:
        assert db.get(LeavePolicy, area.id) is None
        admin = login("admin@example.org", "admin-passwort-123")
        result = admin.post(
            f"/urlaub/regeln/{area.id}",
            data={
                "csrf": csrf_of(admin.get("/").text),
                "policy_version": f"{root.id}:{parent.version}",
                "topic": "feiertage", "action": "save",
                "holiday_state": "BE",
                # A cross-tab injection must not change the workflow.
                "workflow": "external",
            },
            follow_redirects=False,
        )
        assert result.status_code == 303, result.text
        local = db.get(LeavePolicy, area.id)
        assert local is not None
        assert local.holiday_state == "BE"
        assert local.workflow == "internal"
        assert local.minimum == 4 and local.conflict_mode == "block"
        assert json.loads(local.approval_units) == [root.id]
        assert local.external_attestation is False
        page = admin.get(f"/urlaub/verwaltung/feiertage?unit={area.id}")
        assert page.status_code == 200
        assert 'name="holiday_state"' in page.text
        assert 'name="workflow"' not in page.text
    finally:
        db.rollback()
        db.query(LeavePolicy).filter(
            LeavePolicy.org_id.in_([root.id, area.id])
        ).delete(synchronize_session=False)
        db.commit()


def test_parent_only_approver_sees_assigned_request_not_unrelated_leave(
    db, task_people, units,
):
    """An explicit parent approval is visible even without subtree role grants."""
    root, area, _, _ = units
    employee, reviewer, outsider = task_people[:3]
    assigned(db, employee, area)
    grant(db, root, reviewer, "approver", False)
    grant(db, root, outsider, "viewer", True)
    db.add(LeavePolicy(
        org_id=area.id, workflow="internal",
        approval_units=json.dumps([root.id]),
    ))
    db.commit()
    try:
        request = leave.save(db, employee, dict(
            starts_on="2026-12-17", ends_on="2026-12-18",
        ))
        db.commit()
        leave.command(db, employee, request.id, "request", request.version)
        db.commit()
        assert request.status == "requested"
        assert not __import__("app").organization.allows(
            db, reviewer, area.id, "approve"
        )
        approver = login(reviewer.email, "task-passwort-123")
        result = approver.get(f"/urlaub/genehmigungen?unit={root.id}")
        assert result.status_code == 200, result.text[:600]
        assert f'id="leave-row-{request.id}"' in result.text
        feed = approver.get(f"/urlaub/data?unit={root.id}")
        assert feed.status_code == 200
        assert any(r["id"] == request.id for r in feed.json()["requests"])
        viewer = login(outsider.email, "task-passwort-123")
        assert viewer.get(f"/urlaub/data?unit={root.id}").json()["requests"] == []
    finally:
        db.rollback()
        db.query(LeaveRequest).filter_by(person_id=employee.id).delete()
        db.query(LeavePolicy).filter_by(org_id=area.id).delete()
        db.commit()


def test_own_leave_remains_visible_when_leadership_selects_another_unit(
    db, task_people, units,
):
    _, leadership_unit, _, own_unit = units
    leader = task_people[0]
    assigned(db, leader, own_unit)
    grant(db, leadership_unit, leader, "lead", False)
    try:
        request = leave.save(db, leader, dict(
            starts_on="2026-12-21", ends_on="2026-12-23",
        ))
        db.commit()
        client = login(leader.email, "task-passwort-123")
        page = client.get(f"/urlaub/mein-urlaub?unit={leadership_unit.id}")
        assert page.status_code == 200
        assert f'id="leave-row-{request.id}"' in page.text
        assert f'href="/urlaub/planer?unit={own_unit.id}"' in page.text
    finally:
        db.rollback()
        db.query(LeaveRequest).filter_by(person_id=leader.id).delete()
        db.commit()
