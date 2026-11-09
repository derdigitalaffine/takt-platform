import json
import pytest
from sqlalchemy import select
from app import agent
from app.db import SessionLocal, User
from app.task_models import Task, TaskCheck
from fastapi import HTTPException
from test_agent_modules import isolated, ADMIN


def test_task_planning_preserves_schedule_checklist_and_preview():
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        raw = dict(tool='create_task', title='Unterlagen prüfen', description='Originalangaben', due_date='2026-12-04', due_time='10:30', starts_at='2026-12-03T09:00', checklist='Belege sammeln\nZahlen prüfen', tags='Haushalt')
        action = agent.normalize_plan(json.dumps(dict(actions=[raw])), actor, [], [], db)['actions'][0]
        preview = agent.preview(db, [action])[0]
        assert '2026-12-04' in preview and '10:30' in preview and 'Zahlen prüfen' in preview
        assert db.scalar(select(Task).where(Task.title == raw['title'])) is None
        result = agent.execute(db, actor, [action])
        tid = result[0]['target_id']
        assert [r.title for r in db.scalars(select(TaskCheck).where(TaskCheck.task_id == tid).order_by(TaskCheck.position))] == ['Belege sammeln', 'Zahlen prüfen']
        assert db.get(Task, tid).due_has_time


@pytest.mark.parametrize('fields', [dict(priority='höchste'), dict(due_time='09:00'), dict(due_date='2026-99-99'), dict(starts_at='2026-12-10T09:00', due_date='2026-12-01')])
def test_invalid_task_plans_fail_before_confirmation(fields):
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        with pytest.raises((ValueError, HTTPException)):
            agent.normalize_plan(json.dumps(dict(actions=[dict(tool='create_task', title='Nicht speichern', **fields)])), actor, [], [], db)


def test_precision_hints_use_live_category_ids_and_no_duplicate_task():
    from app.agent_precision import context, intake_category
    cats = [dict(id=914, key='office_supply'), dict(id=821, key='office_furniture')]
    assert intake_category('Bitte Toner bestellen', cats)['id'] == 914
    assert intake_category('Toner und Bürostühle bestellen', cats) is None
    assert 'niemals zusätzlich' in context('Bitte Toner bestellen', cats)
