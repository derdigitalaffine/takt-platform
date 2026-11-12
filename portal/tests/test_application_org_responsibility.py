"""Regression: responsible organizational nodes in applications, cases and steps.

GroupMember and OrgMembership remain separate identity sources. This suite
covers scope boundaries, legacy group routes, UI, conditional rules and tasks.
"""
import json
import secrets

import pytest
from sqlalchemy import delete, select

from app import application_orgs as ao, applications as apps, workflow as wf
from app.db import (ApplicationTask, Form, FormResponse, Group, GroupMember,
                    Organization, User)
from app.org_models import OrgMembership
from conftest import csrf_of, login, settings


@pytest.fixture
def responsibility(db):
    settings(module_applications="1")
    suffix = secrets.token_hex(5)
    admin = db.scalar(select(User).where(User.email == "admin@example.org"))
    a = User(email=f"org-responsible-{suffix}@example.org", name="Zuständige Person",
             password_hash=admin.password_hash, active=True, permissions="video")
    outsider = User(email=f"org-outsider-{suffix}@example.org", name="Unbeteiligte Person",
                    password_hash=admin.password_hash, active=True, permissions="video")
    parent = Organization(name="Zuständigkeit Oberbereich " + suffix, kind="fachbereich", active=True)
    db.add_all([a, outsider, parent])
    db.flush()
    child = Organization(name="Zuständigkeit Sachgebiet " + suffix, kind="sachgebiet",
                         parent_id=parent.id, active=True)
    group_node = Organization(name="Zuständigkeit Gruppe " + suffix, kind="gruppe", active=True)
    db.add_all([child, group_node])
    db.flush()
    group = Group(name="Zuständigkeit Gruppe " + suffix, org_id=group_node.id)
    form = Form(owner_id=admin.id, title="Org-Verantwortung " + suffix, kind="application",
                schema_json=json.dumps([{"id": "ort", "type": "short", "title": "Ortsgemeinde", "required": False}]),
                app_routing_json="[]", app_org_id=child.id)
    db.add_all([group, form])
    db.flush()
    db.add_all([OrgMembership(user_id=a.id, org_id=child.id, is_primary=True,
                              counts_staff=True, capacity_percent=100),
                GroupMember(user_id=a.id, group_id=group.id, manual=True)])
    resp = FormResponse(form_id=form.id, ref_no=f"TEST-{suffix}", status="received",
                        answers_json="{}", responsible_org_id=child.id)
    db.add(resp)
    db.commit()
    yield {"admin": admin.id, "person": a.id, "outsider": outsider.id,
           "parent": parent.id, "child": child.id, "group_node": group_node.id,
           "group": group.id, "form": form.id, "resp": resp.id}
    # The app and test client use independent DB sessions. Remove FK-dependent
    # memberships before their target units; SQLite may not have DB-level
    # ON DELETE CASCADE enabled for every fixture connection.
    db.rollback()
    db.expire_all()
    db.execute(delete(GroupMember).where(GroupMember.group_id == group.id))
    db.execute(delete(OrgMembership).where(OrgMembership.org_id == child.id))
    db.execute(delete(ApplicationTask).where(ApplicationTask.response_id == resp.id))
    db.execute(delete(FormResponse).where(FormResponse.id == resp.id))
    db.execute(delete(Form).where(Form.id == form.id))
    db.execute(delete(Group).where(Group.id == group.id))
    db.flush()
    # Child first, then parent; deleting the group node must not disturb the
    # original administrative root hierarchy or any existing groups.
    for oid in (child.id, group_node.id, parent.id):
        db.execute(delete(Organization).where(Organization.id == oid))
    for uid in (a.id, outsider.id):
        db.execute(delete(User).where(User.id == uid))
    db.commit()


def test_org_assignment_uses_direct_members_not_ancestors_or_random_visitor(db, responsibility):
    ids = responsibility
    member, outsider = db.get(User, ids["person"]), db.get(User, ids["outsider"])
    case = db.get(FormResponse, ids["resp"])
    assert ao.member_ids(db, ids["child"]) == {member.id}
    assert ao.member_ids(db, ids["parent"]) == set()
    assert ao.member_ids(db, ids["group_node"]) == {member.id}
    assert ao.assigned_org_ids(db, [member.id]) == {ids["child"], ids["group_node"]}
    assert ao.assigned_org_ids(db, [outsider.id]) == set()
    assert apps.access(db, member, case) == 2
    assert apps.access(db, outsider, case) == 0
    assert case in db.scalars(apps.inbox_query(db, member)).all()
    assert case not in db.scalars(apps.inbox_query(db, outsider)).all()
    case.responsible_org_id = ids["parent"]
    db.flush()
    assert apps.access(db, member, case) == 0  # parent membership is NOT inferred
    case.responsible_org_id = ids["group_node"]
    db.flush()
    assert apps.access(db, member, case) == 2


def test_org_selection_validation_and_inactive_ancestor(db, responsibility):
    ids = responsibility
    assert ao.validate(db, ids["child"]) == ids["child"]
    with pytest.raises(Exception) as exc:
        ao.validate(db, 999999999)
    assert getattr(exc.value, "status_code", None) == 422
    db.get(Organization, ids["parent"]).active = False
    db.flush()
    assert ao.member_ids(db, ids["child"]) == set()
    with pytest.raises(Exception) as exc:
        ao.validate(db, ids["child"])
    assert getattr(exc.value, "status_code", None) == 422
    db.rollback()
    assert ao.validate(db, ids["child"]) == ids["child"]


def test_existing_group_route_unchanged_and_new_org_rule_is_first_match(db, responsibility):
    ids = responsibility
    f = db.get(Form, ids["form"])
    f.app_org_id = ids["child"]
    f.app_assignee_id = None
    f.app_group_id = ids["group"]
    assert apps.route(f, {}) == (None, ids["group"], "")
    assert apps.route_org(f, {}) == ids["child"]
    f.app_routing_json = json.dumps([
        {"question": "ort", "value": "A", "org_id": ids["group_node"]},
        {"question": "ort", "value": "B", "group_id": ids["group"]}
    ])
    assert apps.route_org(f, {"ort": "A"}) == ids["group_node"]
    assert apps.route(f, {"ort": "B"}) == (None, ids["group"], "")
    assert apps.route_org(f, {"ort": "B"}) is None
    assert apps.route_org(f, {"ort": "C"}) == ids["child"]


def test_form_editor_and_case_detail_use_full_org_tree_and_catalogue_stays_separate(db, responsibility):
    ids = responsibility
    admin = login("admin@example.org", "admin-passwort-123")
    page = admin.get(f'/forms/{ids["form"]}/application')
    assert page.status_code == 200
    assert 'name="app_org_id"' in page.text
    assert 'name="rule_org"' in page.text
    assert db.get(Organization, ids["child"]).name in page.text
    assert db.get(Organization, ids["group_node"]).name in page.text
    form = db.get(Form, ids["form"])
    before_catalog = form.org_id
    token = csrf_of(page.text)
    response = admin.post(f'/forms/{form.id}/application',
        data={"csrf": token, "is_application": "1", "app_org_id": ids["group_node"],
              "org_id": str(before_catalog or ""), "app_assignee_id": "",
              "app_prefix": "ORG", "app_deadline_days": "14"}, follow_redirects=False)
    assert response.status_code == 303
    db.expire(form)
    assert form.app_org_id == ids["group_node"]
    assert form.app_group_id is None
    assert form.org_id == before_catalog
    detail = admin.get(f'/forms/{form.id}/applications/{ids["resp"]}')
    assert detail.status_code == 200
    assert 'name="responsible_org_id"' in detail.text


def test_workflow_org_mode_and_tasks_are_visible_only_to_members(db, responsibility, monkeypatch):
    ids = responsibility
    member, outsider = db.get(User, ids["person"]), db.get(User, ids["outsider"])
    resp = db.get(FormResponse, ids["resp"])
    monkeypatch.setattr(wf, "_notify_task", lambda *a, **kw: 0)
    step = {"id": "review", "name": "Sachbearbeitung", "type": "task",
            "assign": {"mode": "org", "org_id": ids["group_node"]}, "due_days": 3}
    assert wf.clean_definition({"steps": [step]})["steps"][0]["assign"]["org_id"] == ids["group_node"]
    assert wf._resolve(db, resp, step) == (None, None)
    assert wf._resolve_org(db, resp, step) == ids["group_node"]
    task = wf._create_task(db, resp, step)
    db.flush()
    assert task.assignee_id is None and task.group_id is None
    assert task.responsible_org_id == ids["group_node"]
    assert wf.can_work(db, member, task)
    assert not wf.can_work(db, outsider, task)
    assert task in wf.my_tasks(db, member)
    assert task not in wf.my_tasks(db, outsider)
    assert wf.task_count(db, member) >= 1
    assert wf.who(task).find("Gruppe") >= 0
    assert member.email in wf._addresses(db, None, None, ids["group_node"])
    assert outsider.email not in wf._addresses(db, None, None, ids["group_node"])
    # Once a responsible person takes this particular step, the other
    # department members must not be able to complete/approve it.
    task.assignee_id = ids["admin"]
    db.flush()
    assert not wf.can_work(db, member, task)
    assert task not in wf.my_tasks(db, member)
    assert wf.can_work(db, db.get(User, ids["admin"]), task)

