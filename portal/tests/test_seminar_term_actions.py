import json
import re
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import seminar_terms, seminars as sm
from app.db import SeminarEvent, SeminarSession, utcnow
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


def test_term_unpublish_publish_and_cancel_preserve_history(db, people):
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


def test_only_never_published_unreferenced_drafts_are_deleted(db, people):
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
    db.add(referenced);db.flush()
    sm.new_enrollment(db, row, referenced.id, people[1].name, people[1].email, people[1], status='cancelled')
    db.flush()
    with pytest.raises(HTTPException) as exc:
        seminar_terms.delete_draft(db, row, referenced, people[0])
    assert exc.value.status_code == 409


def test_planner_exposes_term_actions_and_action_endpoint(db, people):
    row, term = make(db, people)
    # Simulate legacy data which was visible before published_at was consistently set.
    term.published_at = None
    db.commit()
    c = login(people[0].email, 'passwort-test-123')
    page = c.get(f'/seminare/{row.id}/planen')
    assert page.status_code == 200
    assert 'Sichtbarkeit &amp; Zugang' in page.text
    assert 'Änderungen speichern' in page.text
    assert '/static/seminar_planner_actions.js' in page.text
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


def test_published_planner_rejects_publish_action_for_whole_series(db, people):
    row, _term = make(db, people)
    loaded = state(db, row)
    loaded['action'] = 'publish'
    with pytest.raises(HTTPException) as exc:
        save(db, people[0], loaded, row)
    assert exc.value.status_code == 409
