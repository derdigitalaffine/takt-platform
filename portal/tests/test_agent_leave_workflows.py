"""Agent leave commands exercise real organizational, transactional and HTTP boundaries."""
import json
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func, delete
from app import agent, agent_leave, leave
from app.db import User, Absence
from app.ai_models import AgentAudit
from app.leave_models import LeaveRequest, LeavePolicy, LeaveAudit
from app.org_models import OrgState
from test_agent_modules import isolated, fake
from test_native_tasks import task_people
from test_organization import units, grant
from test_leave import assigned
from conftest import login, csrf_of


@pytest.fixture
def people(db, task_people, units, isolated):
    _, unit, _, _ = units
    owner, approver, outsider = task_people[:3]
    for p in (owner, approver, outsider):
        p.permissions += ',ai_chat'
    db.commit()
    assigned(db, owner, unit)
    grant(db, unit, approver, 'lead')
    cfg = LeavePolicy(org_id=unit.id, workflow='internal', sync_absence=True)
    db.add(cfg); db.commit()
    yield owner, approver, outsider, cfg
    db.rollback()
    ids = list(db.scalars(select(LeaveRequest.id).where(LeaveRequest.person_id == owner.id)))
    aids = list(db.scalars(select(LeaveRequest.absence_id).where(LeaveRequest.id.in_(ids), LeaveRequest.absence_id.is_not(None))))
    db.execute(delete(LeaveAudit).where(LeaveAudit.request_id.in_(ids)))
    db.execute(delete(LeaveRequest).where(LeaveRequest.id.in_(ids)))
    for aid in aids:
        a = db.get(Absence, aid)
        if a: db.delete(a)
    db.delete(cfg); db.commit()


def normalized(db, actor, raw, row=None):
    findings = [dict(type='leave', id=row.id)] if row else []
    return agent.normalize_plan(json.dumps(dict(actions=[raw])), actor, findings, [], db)['actions'][0]


def make(db, owner):
    row = leave.save(db, owner, dict(starts_on='2026-12-07', ends_on='2026-12-09'))
    db.commit()
    return row


def test_full_internal_workflow_and_preview_have_no_effects(db, people):
    owner, approver, _, _ = people
    state = db.get(OrgState, 1).version
    before = db.scalar(select(func.count()).select_from(LeaveAudit))
    create = normalized(db, owner, dict(tool='create_leave', starts_on='2026-12-07', ends_on='2026-12-09'))
    assert db.scalar(select(LeaveRequest).where(LeaveRequest.person_id == owner.id)) is None
    rid = agent.execute(db, owner, [create])[0]['target_id']
    row = db.get(LeaveRequest, rid)
    assert row.status == 'planned'
    before = db.scalar(select(func.count()).select_from(LeaveAudit))
    state = db.get(OrgState, 1).version
    action = normalized(db, owner, dict(tool='leave_command', id=rid, command='request'), row)
    assert db.get(LeaveRequest, rid).status == 'planned'
    assert db.get(OrgState, 1).version == state
    assert db.scalar(select(func.count()).select_from(LeaveAudit)) == before
    assert db.get(LeaveRequest, rid).absence_id is None
    agent.execute(db, owner, [action]); db.refresh(row)
    assert row.status == 'requested'
    found = agent.search(db, approver, dict(tool='search_leave_requests', scope='decisions', query=''))
    assert rid in [r['id'] for r in found] and 'approve' in found[0]['operations']
    approval = normalized(db, approver, dict(tool='leave_command', id=rid, command='approve'), row)
    assert db.get(LeaveRequest, rid).status == 'requested' and db.get(LeaveRequest, rid).absence_id is None
    agent.execute(db, approver, [approval]); db.refresh(row)
    assert row.status == 'binding' and db.get(Absence, row.absence_id)
    aid = row.absence_id
    edit = normalized(db, owner, dict(tool='edit_leave', id=rid, starts_on='2026-12-14', ends_on='2026-12-16'), row)
    agent.execute(db, owner, [edit]); db.refresh(row)
    assert row.status == 'planned' and row.starts_on == '2026-12-14'
    assert db.get(Absence, aid).starts_on == '2026-12-07'
    assert db.scalar(select(AgentAudit).where(AgentAudit.tool == 'edit_leave', AgentAudit.target_id == rid))


def test_acl_self_approval_stale_policy_and_forged_ids(db, people):
    owner, approver, outsider, cfg = people
    row = make(db, owner)
    with pytest.raises(ValueError):
        normalized(db, owner, dict(tool='leave_command', id=row.id, command='request'))
    assert not agent.search(db, outsider, dict(tool='search_leave_requests', scope='manageable', query=''))
    with pytest.raises(HTTPException):
        normalized(db, outsider, dict(tool='leave_command', id=row.id, command='request'), row)
    action = normalized(db, owner, dict(tool='leave_command', id=row.id, command='request'), row)
    cfg.workflow = 'external'; db.commit()
    with pytest.raises(HTTPException) as exc:
        agent.execute(db, owner, [action])
    assert exc.value.status_code == 409
    db.rollback(); cfg.workflow = 'internal'; db.commit()
    leave.command(db, owner, row.id, 'request', row.version); db.commit()
    with pytest.raises(HTTPException) as exc:
        normalized(db, owner, dict(tool='leave_command', id=row.id, command='approve'), row)
    assert exc.value.status_code == 403
    approval = normalized(db, approver, dict(tool='leave_command', id=row.id, command='approve'), row)
    row.version += 1; db.commit()
    with pytest.raises(HTTPException) as exc:
        agent.execute(db, approver, [approval])
    assert exc.value.status_code == 409


def test_native_review_edits_confirmation_replay_and_csrf(db, people, monkeypatch):
    owner, _, _, _ = people
    raw = dict(tool='create_leave', starts_on='2026-12-07', ends_on='2026-12-09', start_half='pm')
    fake(monkeypatch, [], [raw])
    c = login(owner.email, 'task-passwort-123')
    csrf = csrf_of(c.get('/').text)
    assert c.post('/agent/plan', data=dict(prompt='/takt Plane meinen Urlaub')).status_code == 400
    r = c.post('/agent/plan', data=dict(csrf=csrf, prompt='/takt Plane meinen Urlaub'))
    assert r.status_code == 200, r.text
    data = r.json(); nonce = data['plan_id']
    assert data['open_url'].startswith('/urlaub/planer?unit=')
    assert c.get(data['open_url']).status_code == 200
    assert c.get('/agent/draft', params=dict(plan_id=nonce)).json()['fields']['start_half'] == 'pm'
    assert not db.scalar(select(LeaveRequest).where(LeaveRequest.person_id == owner.id))
    review = c.post('/agent/draft/review', data=dict(csrf=csrf, agent_plan=nonce, starts_on='2026-12-14', ends_on='2026-12-16', start_half='am', end_half='pm'))
    assert review.status_code == 200, review.text
    assert '2026-12-14' in review.text
    import re
    review_id = re.search(r'name="review_id" value="([^"]+)"', review.text)[1]
    save = dict(csrf=csrf, plan_id=nonce, review_id=review_id)
    assert c.post('/agent/draft/save', data=save, follow_redirects=False).status_code == 303
    assert c.post('/agent/draft/save', data=save).status_code == 409
    db.expire_all()
    row = db.scalar(select(LeaveRequest).where(LeaveRequest.person_id == owner.id))
    assert row.starts_on == '2026-12-14' and row.status == 'planned'


@pytest.mark.parametrize('fields', [dict(starts_on='2026-12-09',ends_on='2026-12-07'), dict(starts_on='2026-12-07',ends_on='2026-12-09',start_half='invalid')])
def test_invalid_period_never_gets_a_proposal(db, people, fields):
    with pytest.raises(HTTPException):
        normalized(db, people[0], dict(tool='create_leave', **fields))


def test_binding_conflicts_cancellation_and_notifications_are_not_bypassed(db, people):
    from app.leave_extensions import LeaveInbox
    owner, approver, _, cfg = people
    row = make(db, owner)
    leave.command(db, owner, row.id, 'request', row.version); db.commit()
    cfg.minimum = 2; cfg.conflict_mode = 'block'; db.commit()
    before = db.scalar(select(func.count()).select_from(LeaveInbox))
    with pytest.raises(HTTPException) as exc:
        normalized(db, approver, dict(tool='leave_command', id=row.id, command='approve'), row)
    assert exc.value.status_code == 409
    assert db.get(LeaveRequest, row.id).status == 'requested'
    assert db.scalar(select(func.count()).select_from(LeaveInbox)) == before
    cfg.minimum = 0; db.commit()
    approval = normalized(db, approver, dict(tool='leave_command', id=row.id, command='approve'), row)
    assert db.scalar(select(func.count()).select_from(LeaveInbox)) == before
    agent.execute(db, approver, [approval]); db.refresh(row)
    with pytest.raises(HTTPException) as exc:
        normalized(db, owner, dict(tool='leave_command', id=row.id, command='cancel'), row)
    assert exc.value.status_code == 403
    cancellation = normalized(db, owner, dict(tool='leave_command', id=row.id, command='request_cancel'), row)
    agent.execute(db, owner, [cancellation]); db.refresh(row)
    cancel = normalized(db, approver, dict(tool='leave_command', id=row.id, command='cancel', reason='Geprüft'), row)
    aid = row.absence_id
    assert db.get(Absence, aid) and db.get(LeaveRequest, row.id).cancel_requested
    agent.execute(db, approver, [cancel]); db.refresh(row)
    assert row.status == 'cancelled' and not db.get(Absence, aid)


def test_parent_approver_without_child_scope_uses_readable_native_unit(db, people, units):
    import json
    owner, approver, _, cfg = people
    parent = units[0]
    grant(db, parent, approver, 'approver', children=False)
    cfg.approval_units = json.dumps([parent.id]); db.commit()
    row = make(db, owner)
    leave.command(db, owner, row.id, 'request', row.version); db.commit()
    # Drop the child's leader grant; parent decision access alone must suffice.
    from app.org_models import OrgRoleGrant
    db.execute(delete(OrgRoleGrant).where(OrgRoleGrant.user_id == approver.id, OrgRoleGrant.org_id == row.org_id)); db.commit()
    found = agent.search(db, approver, dict(tool='search_leave_requests', scope='decisions', query=''))
    assert row.id in [r['id'] for r in found]
    action = normalized(db, approver, dict(tool='leave_command', id=row.id, command='approve'), row)
    assert action['display_unit'] == parent.id
    from app import agent_drafts
    url = agent_drafts.destination(action)
    db.commit()  # End the isolated preview transaction before another HTTP session writes.
    c = login(approver.email, 'task-passwort-123')
    html = c.get(url)
    assert html.status_code == 200 and f'id="leave-row-{row.id}"' in html.text
