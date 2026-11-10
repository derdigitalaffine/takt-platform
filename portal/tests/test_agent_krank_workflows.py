"""Local health proposals: no model/history, native confirmation and employer ACLs."""
import json
import re
from datetime import date
import pytest
from fastapi import HTTPException
from sqlalchemy import select, delete, func
from app import ai_provider, agent, agent_krank, krank, main
from app.db import SessionLocal, User, KrankEmployer, KrankReport, KrankAccess, KrankResponsible, get_settings, set_setting
from app.ai_models import AIConversation, AIMessage, AgentAudit
from app.security import hash_password
from test_agent_modules import isolated, ADMIN
from conftest import login, csrf_of, settings


@pytest.fixture
def health(monkeypatch, isolated):
    keys = ('module_krank', 'krank_kinds', 'krank_retention_days')
    with SessionLocal() as db:
        old = {k: get_settings(db).get(k, '') for k in keys}
        person = User(name='Private Health Person', email='agent-health@example.org', permissions='ai_chat,krank', active=True,
                      password_hash=hash_password('health-test-pass123'))
        emp = KrankEmployer(name='Synthetic Health Employer', active=True)
        other = KrankEmployer(name='Synthetic Other Employer', active=True)
        db.add_all([person, emp, other]); db.commit()
        uid, eid, otherid = person.id, emp.id, other.id
        db.add(KrankResponsible(user_id=uid, employer_id=eid)); db.commit()
    settings(module_krank='1', krank_kinds='simple,au,eau,child', krank_retention_days='0')
    monkeypatch.setattr(krank, 'today', lambda: date(2026, 11, 9))
    async def forbidden(*args, **kwargs):
        raise AssertionError('Health data must never reach the LLM')
    monkeypatch.setattr(ai_provider, 'complete', forbidden)
    yield uid, eid, otherid
    with SessionLocal() as db:
        for row in db.scalars(select(KrankReport).where(KrankReport.employer_id.in_([eid, otherid]))):
            krank.delete_files(row.id); db.delete(row)
        db.flush()
        db.execute(delete(KrankResponsible).where(KrankResponsible.user_id == uid))
        db.execute(delete(KrankAccess).where(KrankAccess.user_id == uid))
        db.delete(db.get(User, uid))
        for e in (eid, otherid): db.delete(db.get(KrankEmployer, e))
        for k,v in old.items(): set_setting(db,k,v)
        db.commit()
    main._module_cache['at'] = 0


def prepare(c, prompt):
    csrf = csrf_of(c.get('/').text)
    result = c.post('/agent/plan', data=dict(csrf=csrf, prompt=prompt))
    assert result.status_code == 200, result.text
    return result.json(), csrf


def client():
    return login('agent-health@example.org', 'health-test-pass123')


def report(eid):
    with SessionLocal() as db:
        r, _, _ = krank.create(db, 'eau', dict(first_name='Synthetic', last_name='Employee', **{'from':'2026-11-09','to':'2026-11-10','doctor':'2026-11-09'}), db.get(KrankEmployer,eid), None, None)
        db.commit()
        return r.id, r.ref_no


def test_private_native_prefill_no_provider_no_history_and_one_time_confirmation(health):
    uid,eid,_ = health
    c = client()
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(AIMessage))
    data, csrf = prepare(c, 'Melde eine eAU seit 09.11.2026 bis 10.11.2026 festgestellt am 09.11.2026, Diagnose niemals ins Modell')
    assert data['open_url'].startswith('/krank/eau?agent_health=')
    assert 'Diagnose' not in str(data) and data['plan_id'] == ''
    page = c.get(data['open_url'])
    assert page.status_code == 200 and 'data-agent-health' in page.text
    assert 'name="from" value="2026-11-09"' in page.text
    nonce = data['open_url'].split('agent_health=')[1]
    values = dict(csrf=csrf, agent_health=nonce, first_name='Private',last_name='Person',employer=eid,
                  **{'from':'2026-11-09','to':'2026-11-10','doctor':'2026-11-09'})
    assert c.post('/krank/eau', data={k:v for k,v in values.items() if k != 'csrf'}).status_code == 400
    assert c.post('/krank/eau',data=values).status_code == 422
    with SessionLocal() as db:
        assert not db.scalar(select(KrankReport).where(KrankReport.employer_id == eid))
        assert db.scalar(select(func.count()).select_from(AIMessage)) == before
    saved = c.post('/krank/eau',data=dict(**values,agent_confirm='1'))
    assert saved.status_code == 303 and saved.headers['location'].startswith('/krank/fertig?')
    assert c.post('/krank/eau',data=dict(**values,agent_confirm='1')).status_code == 409
    with SessionLocal() as db:
        row = db.scalar(select(KrankReport).where(KrankReport.employer_id == eid))
        assert row and row.status == 'eau_open' and 'Private' not in row.data_enc
        assert db.scalar(select(KrankAccess).where(KrankAccess.action == 'agent_create', KrankAccess.ref_no == row.ref_no))
        assert db.scalar(select(AgentAudit).where(AgentAudit.tool=='create_krank',AgentAudit.target_id==row.id))


def test_errors_stay_out_of_cookies_and_invalidated_proposals_fail(health):
    c=client(); data,csrf=prepare(c,'Krankmeldung mit AU vom 09.11.2026 bis 10.11.2026')
    nonce=data['open_url'].split('agent_health=')[1]
    failed=c.post('/krank/au',data=dict(csrf=csrf,agent_health=nonce,agent_confirm='1',first_name='NeverInCookie',last_name='Private',**{'from':'2026-11-09','to':'2026-11-10'}))
    assert failed.status_code==303 and 'agent_health=' in failed.headers['location']
    import base64
    cookie=c.cookies.get('jsm_session').split('.')[0]
    content=base64.b64decode(cookie+'='*(-len(cookie)%4)).decode()
    assert 'NeverInCookie' not in content and 'krank_form' not in content
    assert c.get(data['open_url']).status_code==409
    newurl=failed.headers['location']
    assert 'NeverInCookie' in c.get(newurl).text
    csrf=csrf_of(c.get('/').text)
    c.post('/agent/reset',data=dict(csrf=csrf))
    assert c.get(newurl).status_code==409


def test_exact_ref_staff_status_and_message_require_live_employer_rights(health):
    uid,eid,other=health
    rid,ref=report(eid); otherid,otherref=report(other)
    c=client()
    data,csrf=prepare(c,f'Setze Krankmeldung {ref} auf In Bearbeitung')
    assert data['open_url'].startswith(f'/krankmelder/{rid}?agent_plan=')
    nonce=data['plan_id']
    detail=c.get('/agent/draft',params=dict(plan_id=nonce))
    assert detail.status_code==200 and detail.json()['fields']['status']=='progress'
    review=c.post('/agent/draft/review',data=dict(csrf=csrf,agent_plan=nonce,note='Geprüft'))
    assert review.status_code==200
    token=re.search(r'name="review_id" value="([^"]+)"',review.text)[1]
    with SessionLocal() as db:
        assert db.get(KrankReport,rid).status=='eau_open'
        db.execute(delete(KrankResponsible).where(KrankResponsible.user_id==uid)); db.commit()
    assert c.post('/agent/draft/save',data=dict(csrf=csrf,plan_id=nonce,review_id=token)).status_code==404
    assert c.post('/agent/plan',data=dict(csrf=csrf,prompt=f'Setze Krankmeldung {otherref} auf Bearbeitet')).status_code==404
    with SessionLocal() as db:
        db.add(KrankResponsible(user_id=uid,employer_id=eid));db.commit()
    data,csrf=prepare(c,f'Setze Krankmeldung {ref} auf In Bearbeitung')
    assert c.post('/agent/execute',data=dict(csrf=csrf,plan_id=data['plan_id'])).status_code==200
    data,csrf=prepare(c,f'Krankmeldung {ref} Notiz: intern geprüft')
    assert c.post('/agent/execute',data=dict(csrf=csrf,plan_id=data['plan_id'])).status_code==200
    data,csrf=prepare(c,f'Krankmeldung {ref} Nachricht: Bitte Nachweis prüfen')
    assert 'veröffentlichen' in data['proposals'][0]
    assert c.post('/agent/execute',data=dict(csrf=csrf,plan_id=data['plan_id'])).status_code==200
    with SessionLocal() as db:
        row=db.get(KrankReport,rid)
        assert row.status=='progress'
        assert any('intern geprüft' in krank.event_text(e) and not e.public for e in row.events)
        assert any('Bitte Nachweis prüfen' in krank.event_text(e) and e.public for e in row.events)
        assert db.get(KrankReport,otherid).status=='eau_open'


def test_missing_or_ambiguous_kind_dates_and_cross_session_are_safe(health):
    c=client()
    assert prepare(c,'Ich möchte mich krank melden')[0]['open_url']=='/krank'
    assert prepare(c,'Melde mich mit AU oder eAU krank')[0]['open_url']=='/krank'
    assert prepare(c,'Ich melde mich ohne AU bis morgen krank')[0]['open_url']=='/krank'
    data,_=prepare(c,'Melde mich heute ohne AU krank')
    assert data['open_url'].startswith('/krank/simple?')
    assert client().get(data['open_url']).status_code==409
    csrf=csrf_of(c.get('/').text)
    assert c.post('/agent/new',data=dict(csrf=csrf)).status_code==303
    assert c.get(data['open_url']).status_code==409
    assert agent_krank.creation_fields('eAU seit 2026-11-09 bis 2026-11-10, festgestellt am heute')['doctor']=='2026-11-09'
    assert 'doctor' not in agent_krank.creation_fields('eAU seit 2026-11-09 bis 2026-11-10')
    assert agent_krank.creation_fields('seit 2026-11-09 und seit 2026-11-10')=={}
    settings(module_krank='0')
    csrf=csrf_of(c.get('/').text)
    assert c.post('/agent/plan',data=dict(csrf=csrf,prompt='Melde eine eAU')).status_code==403


def test_legacy_health_history_is_not_replayed_to_models():
    messages = [dict(role='user', content='Meine Krankmeldung enthält private Angaben'),
                dict(role='assistant', content='Antwort mit alten privaten Daten'),
                dict(role='user', content='Erstelle eine Aufgabe'), dict(role='assistant', content='Aufgabenentwurf')]
    assert agent_krank.safe_history(messages) == messages[2:]


def test_native_au_upload_and_stale_staff_proposals(health):
    _,eid,_=health
    from test_krank import PDF
    c=client(); data,csrf=prepare(c,'Krankmeldung mit AU vom 09.11.2026 bis 10.11.2026')
    nonce=data['open_url'].split('agent_health=')[1]
    saved=c.post('/krank/au',data=dict(csrf=csrf,agent_health=nonce,agent_confirm='1',first_name='Private',last_name='Employee',employer=eid,
                **{'from':'2026-11-09','to':'2026-11-10'}),files={'file':('Private-Proof.pdf',PDF,'application/pdf')})
    assert saved.status_code==303 and saved.headers['location'].startswith('/krank/fertig?')
    with SessionLocal() as db:
        row=db.scalar(select(KrankReport).where(KrankReport.employer_id==eid))
        rid,ref=row.id,row.ref_no
        assert row.status=='new' and len(row.files)==1
        assert krank.read_file(row.files[0])==PDF and 'Private-Proof' not in row.files[0].name_enc
    data,csrf=prepare(c,f'Setze Krankmeldung {ref} auf In Bearbeitung')
    with SessionLocal() as db:
        row=db.get(KrankReport,rid)
        krank.add_note(db,row,db.scalar(select(User).where(User.email==ADMIN[0])),'Zwischenzeitlich ergänzt')
        db.commit()
    assert c.post('/agent/execute',data=dict(csrf=csrf,plan_id=data['plan_id'])).status_code==409
