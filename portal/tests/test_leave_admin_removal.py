"""Admin removal frees active intervals, mirrors and account charges; evidence remains."""
import json
import pytest
from fastapi import HTTPException
from sqlalchemy import select, delete
from app import leave, leave_admin
from app.db import Absence, User
from app.leave_models import LeavePolicy, LeaveRequest, LeaveAbsencePeriod, LeaveAudit, LeaveAdminRemoval
from app.leave_extensions import LeaveInbox
from conftest import login, csrf_of, settings
from test_native_tasks import task_people
from test_organization import units
from test_leave import assigned

ADMIN = ("admin@example.org", "admin-passwort-123")


@pytest.fixture
def entered(db, task_people, units):
    _, unit, _, _ = units
    person, other = task_people[:2]
    assigned(db, person, unit)
    settings(module_calendars="1")
    db.add(LeavePolicy(org_id=unit.id, workflow="planning", sync_absence=True)); db.commit()
    row = leave.save(db, person, dict(starts_on="2026-12-01", ends_on="2026-12-03")); db.commit()
    leave.command(db, person, row.id, "bind", row.version); db.commit()
    rid = row.id
    yield person, other, rid, unit.id
    db.rollback()
    db.execute(delete(LeaveAdminRemoval).where(LeaveAdminRemoval.person_id == person.id))
    remaining = db.get(LeaveRequest, rid)
    if remaining and remaining.absence_id:
        aid = remaining.absence_id; remaining.absence_id = None; db.flush()
        db.execute(delete(LeaveAbsencePeriod).where(LeaveAbsencePeriod.absence_id == aid))
        db.execute(delete(Absence).where(Absence.id == aid))
    db.execute(delete(LeaveInbox).where(LeaveInbox.request_id == rid))
    db.execute(delete(LeaveAudit).where(LeaveAudit.request_id == rid))
    db.execute(delete(LeaveRequest).where(LeaveRequest.id == rid))
    db.execute(delete(LeavePolicy).where(LeavePolicy.org_id == unit.id)); db.commit()


def test_admin_remove_preview_confirmation_audit_and_replay(db, entered):
    person, other, rid, unit = entered
    row = db.get(LeaveRequest, rid); version = row.version; aid = row.absence_id
    row.effective_json = json.dumps({**json.loads(row.effective_json), "account_charge": 3}); db.commit()
    c = login(*ADMIN)
    preview = c.get(f"/urlaub/{rid}/loeschen")
    assert preview.status_code == 200 and person.name in preview.text
    csrf = csrf_of(preview.text)
    data = dict(csrf=csrf, version=version, reason="Fehlerhafte Eintragung korrigieren")
    assert c.post(f"/urlaub/{rid}/loeschen", data=data).status_code == 422
    assert c.post(f"/urlaub/{rid}/loeschen", data={**data, "confirm": "1", "csrf": "invalid"}).status_code == 400
    response = c.post(f"/urlaub/{rid}/loeschen", data={**data, "confirm": "1"})
    assert response.status_code == 303, response.text
    db.expire_all(); row = db.get(LeaveRequest, rid)
    assert row.status == "cancelled" and not row.effective_json and row.absence_id is None
    assert db.get(Absence, aid) is None and db.get(LeaveAbsencePeriod, aid) is None
    audit = db.scalar(select(LeaveAdminRemoval).where(LeaveAdminRemoval.request_id == rid))
    assert audit.reason == data["reason"] and json.loads(audit.snapshot_json)["effective_json"]
    assert db.scalar(select(LeaveAudit).where(LeaveAudit.request_id == rid, LeaveAudit.action == "admin_delete"))
    assert c.get(f"/urlaub/{rid}/verlauf").status_code == 200
    feed = c.get(f"/urlaub/data?unit={unit}")
    assert feed.status_code == 200
    assert all(r["id"] != rid for r in feed.json()["requests"])
    assert c.post(f"/urlaub/{rid}/loeschen", data={**data, "confirm": "1"}).status_code == 404
    with pytest.raises(HTTPException):
        leave.command(db, person, rid, "bind", row.version)
    db.rollback()


def test_non_admin_and_stale_admin_remove_fail_closed(db, entered):
    person, other, rid, unit = entered
    c = login(person.email, "task-passwort-123")
    assert c.get(f"/urlaub/{rid}/loeschen").status_code == 403
    token = csrf_of(c.get("/").text)
    assert c.post(f"/urlaub/{rid}/loeschen", data=dict(csrf=token, version=1, confirm="1", reason="Nicht erlaubt")).status_code == 403
    admin = login(*ADMIN); token = csrf_of(admin.get("/").text)
    row = db.get(LeaveRequest, rid); aid = row.absence_id
    response = admin.post(f"/urlaub/{rid}/loeschen", data=dict(csrf=token, version=row.version-1, confirm="1", reason="Alte Vorschau"))
    assert response.status_code == 409
    db.expire_all()
    assert db.get(LeaveRequest, rid).effective_json and db.get(Absence, aid)
    assert db.scalar(select(LeaveAdminRemoval).where(LeaveAdminRemoval.request_id == rid)) is None


def test_manual_absence_removal_does_not_remove_linked_leave_or_other_periods(db, entered):
    person, other, rid, unit = entered
    manual = Absence(user_id=person.id, starts_on="2026-12-10", ends_on="2026-12-11", status="confirmed", substitute_id=other.id)
    db.add(manual); db.commit(); aid = manual.id
    c = login(*ADMIN)
    preview = c.get(f"/urlaub/abwesenheit/{aid}/loeschen")
    assert preview.status_code == 200
    import re
    version = re.search(r'name="version" value="([^"]+)"', preview.text).group(1)
    response = c.post(f"/urlaub/abwesenheit/{aid}/loeschen", data=dict(csrf=csrf_of(preview.text), version=version, reason="Doppelte Abwesenheit", confirm="1"))
    assert response.status_code == 303
    db.expire_all()
    assert db.get(Absence, aid) is None
    leave_row = db.get(LeaveRequest, rid)
    assert leave_row.effective_json and db.get(Absence, leave_row.absence_id)
    assert c.get(f"/urlaub/abwesenheit/{leave_row.absence_id}/loeschen").status_code == 409


def test_admin_can_correct_leave_after_primary_assignment_changed(db, entered):
    from app.org_models import OrgMembership
    person, _, rid, unit = entered
    db.execute(delete(OrgMembership).where(OrgMembership.user_id == person.id)); db.commit()
    admin = db.scalar(select(User).where(User.email == ADMIN[0]))
    row = db.get(LeaveRequest, rid)
    leave_admin.remove(db, admin, "leave", rid, row.version, "Fehler nach Organisationswechsel")
    db.commit()
    assert not db.get(LeaveRequest, rid).effective_json


def test_old_manual_absence_preview_cannot_delete_a_recreated_record(db, entered):
    from datetime import timedelta
    person, _, _, _ = entered
    actor = db.scalar(select(User).where(User.email == ADMIN[0]))
    old = Absence(user_id=person.id, starts_on="2026-12-15", ends_on="2026-12-16", status="confirmed")
    db.add(old); db.commit()
    aid, created = old.id, old.created_at
    stale = leave_admin.absence_version(old)
    db.delete(old); db.commit()
    new = Absence(id=aid, user_id=person.id, starts_on="2026-12-15", ends_on="2026-12-16", status="confirmed", created_at=created + timedelta(seconds=1))
    db.add(new); db.commit()
    try:
        with pytest.raises(HTTPException) as exc:
            leave_admin.remove(db, actor, "absence", aid, stale, "Vorschau eines alten Eintrags")
        assert exc.value.status_code == 409
        db.rollback()
        assert db.get(Absence, aid)
    finally:
        db.delete(db.get(Absence, aid)); db.commit()
