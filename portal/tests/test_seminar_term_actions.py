import json
import re
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import seminar_terms, seminars as sm
from app.db import Notification, SeminarEnrollment, SeminarEvent, SeminarSession, utcnow
from app.routes_seminar_planning import save, state
from conftest import client, login
from test_seminars import make, people, rec


def test_published_series_visibility_can_change_without_republishing(db, people):
    row, _term = make(db, people)
    loaded = state(db, row)
    loaded.update(action='save', channels=['internal'])
    save(db, people[0], loaded, row)
    db.commit()
    db.refresh(row)
    assert row.status == 'published'
    assert row.channels == 'internal'
    assert client().get(f'/seminare/{row.id}').status_code == 404

    loaded = state(db, row)
    loaded.update(action='save', channels=['internal', 'guest', 'public'])
    save(db, people[0], loaded, row)
    db.commit()
    db.refresh(row)
    assert row.status == 'published'
    assert row.channels == 'internal,guest,public'
    assert client().get(f'/seminare/{row.id}').status_code == 200
    events = list(db.scalars(select(SeminarEvent).where(
        SeminarEvent.seminar_id == row.id,
        SeminarEvent.kind == 'visibility_changed',
    )))
    assert len(events) == 2


def test_term_unpublish_publish_cancel_and_reactivate_preserve_history(db, people):
    row, term = make(db, people)
    term.published_at = utcnow()
    db.commit()
    published_at = term.published_at

    assert seminar_terms.unpublish(db, row, term, people[0]) is True
    assert term.published is False and term.published_at == published_at
    with pytest.raises(HTTPException) as exc:
        seminar_terms.delete_draft(db, row, term, people[0])
    assert exc.value.status_code == 409

    assert seminar_terms.publish(db, row, term, people[0]) is True
    attendee = rec(db, row, term, people[1])
    db.flush()
    with pytest.raises(HTTPException) as exc:
        seminar_terms.unpublish(db, row, term, people[0])
    assert exc.value.status_code == 409

    assert seminar_terms.cancel(db, row, term, 'Dozent verhindert', people[0]) is True
    assert term.cancelled is True and term.reason == 'Dozent verhindert'
    assert 'STATUS:CANCELLED' in sm.calendar_text(db, row, attendee)

    assert seminar_terms.reactivate(db, row, term, people[0]) is True
    assert term.cancelled is False and term.reason == ''
    assert term.published_at == published_at
    assert 'STATUS:CANCELLED' not in sm.calendar_text(db, row, attendee)


def test_reactivation_uses_change_notification_channel(db, people):
    row, term = make(db, people)
    attendee = rec(db, row, term, people[1], status='confirmed')
    row.notifications_json = json.dumps({'registration': False, 'changes': True})
    term.cancelled = True
    term.reason = 'Fällt aus'
    term.published_at = utcnow()
    db.flush()

    assert seminar_terms.reactivate(db, row, term, people[0]) is True
    assert db.scalar(select(Notification.id).where(Notification.to_addr == attendee.email)) is not None


def test_only_never_published_unreferenced_drafts_are_implicitly_deleted(db, people):
    row, base = make(db, people)
    draft = SeminarSession(
        seminar_id=row.id,
        starts_at=base.starts_at + timedelta(days=7),
        ends_at=base.ends_at + timedelta(days=7),
        published=False,
    )
    db.add(draft);db.flush();draft_id=draft.id
    assert seminar_terms.delete_draft(db, row, draft, people[0]) is True
    assert db.get(SeminarSession, draft_id) is None

    referenced = SeminarSession(
        seminar_id=row.id,
        starts_at=base.starts_at + timedelta(days=14),
        ends_at=base.ends_at + timedelta(days=14),
        published=False,
    )
    db.add(referenced);db.flush();referenced_id=referenced.id
    enrollment = sm.new_enrollment(db, row, referenced.id, people[1].name, people[1].email, people[1], status='cancelled')
    db.flush();enrollment_id=enrollment.id
    with pytest.raises(HTTPException) as exc:
        seminar_terms.delete_draft(db, row, referenced, people[0])
    assert exc.value.status_code == 409

    assert seminar_terms.delete_term(db, row, referenced, people[0]) is True
    assert db.get(SeminarSession, referenced_id) is None
    assert db.get(SeminarEnrollment, enrollment_id) is None


def test_explicit_delete_removes_published_term_and_scoped_booking(db, people):
    row, term = make(db, people)
    term.published_at = utcnow()
    attendee = rec(db, row, term, people[1], status='confirmed')
    db.commit()
    term_id = term.id
    attendee_id = attendee.id

    assert seminar_terms.delete_term(db, row, term, people[0]) is True
    db.flush()
    assert db.get(SeminarSession, term_id) is None
    assert db.get(SeminarEnrollment, attendee_id) is None
    assert db.scalar(select(SeminarEvent.id).where(
        SeminarEvent.seminar_id == row.id,
        SeminarEvent.kind == 'session_deleted',
    )) is not None


def test_cancelled_term_survives_later_planner_saves(db, people):
    row, term = make(db, people)
    term.cancelled = True
    term.reason = 'Fällt aus'
    term.published_at = utcnow()
    db.commit()
    loaded = state(db, row)
    assert loaded['terms'][0]['include'] is False
    loaded.update(action='save', channels=['internal'])
    save(db, people[0], loaded, row)
    db.commit()
    db.expire_all()
    term = db.get(SeminarSession, term.id)
    assert term is not None and term.cancelled is True and term.reason == 'Fällt aus'


def test_planner_exposes_term_actions_and_action_endpoint(db, people):
    row, term = make(db, people)
    # Simulate legacy data which was visible before published_at was consistently set.
    term.published_at = None
    db.commit()
    c = login(people[0].email, 'passwort-test-123')
    page = c.get(f'/seminare/{row.id}/planen')
    assert page.status_code == 200
    assert 'Sichtbarkeit & Zugang' in page.text
    assert 'Änderungen speichern' in page.text
    assert '/static/seminar_planner_actions.js' in page.text
    actions = c.get('/static/seminar_planner_actions.js')
    assert actions.status_code == 200
    assert 'Reaktivieren' in actions.text
    assert 'Termin löschen' in actions.text
    config = json.loads(re.search(r'<script[^>]*id="sp-data"[^>]*>(.*?)</script>', page.text, re.S).group(1))
    initial = config['initial']
    current = next(item for item in initial['terms'] if item['id'] == term.id)
    response = c.post(
        f'/seminare/{row.id}/terms/{term.id}/action',
        json={
            'csrf': config['csrf'],
            'row_revision': initial['revision'],
            'term_revision': current['revision'],
            'action': 'unpublish',
        },
        headers={'Accept': 'application/json'},
    )
    assert response.status_code == 200
    db.expire_all()
    term = db.get(SeminarSession, term.id)
    assert term.published is False
    assert term.published_at is not None


def test_planner_action_endpoint_reactivates_and_deletes(db, people):
    row, term = make(db, people)
    term.published_at = utcnow()
    assert seminar_terms.cancel(db, row, term, 'Fällt aus', people[0]) is True
    db.commit()
    term_id = term.id

    c = login(people[0].email, 'passwort-test-123')
    page = c.get(f'/seminare/{row.id}/planen')
    config = json.loads(re.search(r'<script[^>]*id="sp-data"[^>]*>(.*?)</script>', page.text, re.S).group(1))
    current = next(item for item in config['initial']['terms'] if item['id'] == term_id)
    response = c.post(
        f'/seminare/{row.id}/terms/{term_id}/action',
        json={
            'csrf': config['csrf'],
            'row_revision': config['initial']['revision'],
            'term_revision': current['revision'],
            'action': 'reactivate',
        },
        headers={'Accept': 'application/json'},
    )
    assert response.status_code == 200
    db.expire_all()
    assert db.get(SeminarSession, term_id).cancelled is False

    page = c.get(f'/seminare/{row.id}/planen')
    config = json.loads(re.search(r'<script[^>]*id="sp-data"[^>]*>(.*?)</script>', page.text, re.S).group(1))
    current = next(item for item in config['initial']['terms'] if item['id'] == term_id)
    response = c.post(
        f'/seminare/{row.id}/terms/{term_id}/action',
        json={
            'csrf': config['csrf'],
            'row_revision': config['initial']['revision'],
            'term_revision': current['revision'],
            'action': 'delete',
        },
        headers={'Accept': 'application/json'},
    )
    assert response.status_code == 200
    db.expire_all()
    assert db.get(SeminarSession, term_id) is None


def test_published_planner_rejects_publish_action_for_whole_series(db, people):
    row, _term = make(db, people)
    loaded = state(db, row)
    loaded['action'] = 'publish'
    with pytest.raises(HTTPException) as exc:
        save(db, people[0], loaded, row)
    assert exc.value.status_code == 409
