"""Event adapters preserve audience/interval semantics and reject unsafe targets."""
import json
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app import agent, calendars, agent_drafts, agent_events
from app.db import SessionLocal, User
from app.calendar_models import Calendar, CalendarEvent, CalendarGrant, CalendarAudit
from app.ai_models import AgentAudit
from test_agent_modules import isolated, seed, ADMIN, fake
from test_agent import _member
from test_native_tasks import task_people
from test_organization import units
from conftest import login, csrf_of
from test_agent_drafts import final_tokens


def normalize(db, actor, raw, findings):
    return agent.normalize_plan(json.dumps(dict(actions=[raw])), actor, findings, [], db)['actions'][0]


def event(db, actor, cid, **data):
    row=calendars.save_event(db,actor,db.get(Calendar,cid),dict(title='Agent Einzeltermin',start='2026-12-02T09:00:00+01:00',end='2026-12-02T10:00:00+01:00',description='Bestehende Tagesordnung',location='Sitzungsraum',**data))
    db.commit()
    return row


def test_all_day_create_and_update_preserve_inclusive_dates_and_audience(units):
    uid,cid,*_=seed()
    with SessionLocal() as db:
        actor=db.get(User,uid)
        action=normalize(db,actor,dict(tool='create_event',id=cid,title='Ganztägig',start='2026-12-02',end='2026-12-02',all_day=True),[dict(type='calendar',id=cid)])
        assert 'Enddatum einschließlich' in agent.preview(db,[action])[0]
        assert not db.scalar(select(CalendarEvent).where(CalendarEvent.calendar_id==cid))
        rid=agent.execute(db,actor,[action])[0]['target_id'];row=db.get(CalendarEvent,rid)
        assert row.starts_at=='2026-12-02' and row.ends_at=='2026-12-03' and row.all_day
        row.org_id=units[1].id;row.include_children=False;db.commit()
        update=normalize(db,actor,dict(tool='update_event',id=rid,title='Geprüfter Titel'),[dict(type='event',id=rid)])
        assert update['end']=='2026-12-02'
        view=agent_drafts.view(db,actor,dict(actions=[update]),0)
        assert view['fields']['end']=='2026-12-02' and view['fields']['org_id_event']==units[1].id
        agent.execute(db,actor,[update]);db.refresh(row)
        assert row.ends_at=='2026-12-03' and row.org_id==units[1].id and row.include_children is False
        found=agent.search(db,actor,dict(tool='search_events',query=f'#{rid}',start='2026-12-02',end='2026-12-02'))
        assert len(found)==1 and found[0]['editable'] and found[0]['end_exclusive']
        assert not agent.search(db,actor,dict(tool='search_events',query=f'#{rid}',start='2026-12-03'))
        row.org_id=None;db.commit()  # Release the scoped fixture before its RESTRICTed organization is removed.


def test_live_rights_stale_versions_and_series_are_rejected():
    uid,cid,*_=seed(); outsider_id=_member('event-reader@example.org')
    with SessionLocal() as db:
        actor=db.get(User,uid);reader=db.get(User,outsider_id)
        row=event(db,actor,cid)
        db.add(CalendarGrant(calendar_id=cid,user_id=reader.id,can_write=False));db.commit()
        assert not agent.search(db,reader,dict(tool='search_events',query=f'#{row.id}'))[0]['editable']
        with pytest.raises(HTTPException) as exc:
            normalize(db,reader,dict(tool='update_event',id=row.id,title='No'),[dict(type='event',id=row.id)])
        assert exc.value.status_code==403
        with pytest.raises(ValueError):
            normalize(db,actor,dict(tool='delete_event',id=row.id),[])
        change=normalize(db,actor,dict(tool='update_event',id=row.id,location='Anderer Raum'),[dict(type='event',id=row.id)])
        row.version+=1;db.commit()
        with pytest.raises(HTTPException) as exc: agent.execute(db,actor,[change])
        assert exc.value.status_code==409
        db.rollback()
        series=event(db,actor,cid,repeat='weekly',repeat_count='3')
        for tool in ('update_event','delete_event'):
            with pytest.raises(HTTPException) as exc:
                normalize(db,actor,dict(tool=tool,id=series.id),[dict(type='event',id=series.id)])
            assert exc.value.status_code==422
        db.get(Calendar,cid).source='leave';db.commit()
        with pytest.raises(HTTPException):
            normalize(db,actor,dict(tool='delete_event',id=row.id),[dict(type='event',id=row.id)])


def test_delete_is_previewed_confirmed_audited_and_cannot_replay(monkeypatch):
    uid,cid,*_=seed()
    with SessionLocal() as db:
        row=event(db,db.get(User,uid),cid);rid,uid_event=row.id,row.uid
    fake(monkeypatch,[dict(tool='search_events',query=f'#{rid}')],[dict(tool='delete_event',id=rid)])
    c=login(*ADMIN);csrf=csrf_of(c.get('/').text)
    result=c.post('/agent/plan',data=dict(csrf=csrf,prompt='/takt Lösche den Kalendertermin'))
    assert result.status_code==200,result.text
    assert 'endgültig löschen' in result.json()['proposals'][0]
    nonce=result.json()['plan_id']
    assert c.post('/agent/draft/review',data=dict(agent_plan=nonce)).status_code==400
    review=c.post('/agent/draft/review',data=dict(csrf=csrf,agent_plan=nonce))
    assert review.status_code==200
    with SessionLocal() as db: assert db.get(CalendarEvent,rid)
    tokens=final_tokens(review.text)
    assert c.post('/agent/draft/save',data=tokens).status_code==303
    assert c.post('/agent/draft/save',data=tokens).status_code==409
    with SessionLocal() as db:
        assert not db.get(CalendarEvent,rid)
        assert db.scalar(select(CalendarAudit).where(CalendarAudit.event_uid==uid_event,CalendarAudit.action=='delete'))
        assert db.scalar(select(AgentAudit).where(AgentAudit.tool=='delete_event',AgentAudit.target_id==rid))


@pytest.mark.parametrize('day,time', [('2026-03-29','02:30'),('2026-10-25','02:30')])
def test_clock_change_rejects_nonexistent_or_ambiguous_edited_times(day,time):
    with pytest.raises(HTTPException) as exc: agent_events.local_timestamp(day,time,'Europe/Berlin')
    assert exc.value.status_code==422


def test_explicit_clock_change_offset_and_subminute_precision_are_preserved():
    assert agent_events.local_timestamp('2026-10-25','02:30','Europe/Berlin','2026-10-25T02:30:00+01:00').endswith('+01:00')
    assert agent_events.local_timestamp('2026-12-02','09:00','Europe/Berlin','2026-12-02T09:00:30+01:00').endswith('09:00:30+01:00')
    assert agent_events.local_timestamp('2026-03-29','03:30','Europe/Berlin').endswith('+02:00')
    with pytest.raises(HTTPException): agent_events.local_timestamp('2026-12-02','09:00','Invalid/Zone')
