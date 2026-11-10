"""Only an explicit /takt enables portal tools, including API and no-JS paths."""
import json
from sqlalchemy import select
from app import agent, ai_provider
from app.db import SessionLocal
from app.ai_models import AIProvider, AIMessage
from test_agent_modules import isolated, ADMIN, fake
from conftest import login, csrf_of


def test_action_language_and_short_replies_are_chat_even_with_legacy_toggle(monkeypatch):
    calls=[]
    async def complete(provider,messages,**kw):
        calls.append(messages)
        return 'Für eine Portalaktion beginne deine Nachricht mit /takt.'
    def forbidden(*a,**kw):raise AssertionError('Chat must not invoke any portal tool or normalizer')
    monkeypatch.setattr(ai_provider,'complete',complete)
    monkeypatch.setattr(agent,'search',forbidden)
    monkeypatch.setattr(agent,'normalize_plan',forbidden)
    c=login(*ADMIN);csrf=csrf_of(c.get('/').text)
    for prompt in ('Erstelle eine Aufgabe für die Inventur','Öffne die Aufgaben','ja','Bitte /takt erstelle eine Aufgabe','/taktisch ist kein Befehl'):
        r=c.post('/agent/plan',data=dict(csrf=csrf,prompt=prompt,use_agent='1'))
        assert r.status_code==200,r.text
        data=r.json()
        assert data['mode']=='chat' and data['proposals']==[] and data['results']==[] and data['plan_id']=='' and data['open_url']==''
    assert len(calls)==5 and all('reiner Chat ohne Portalwerkzeuge' in x[0]['content'] for x in calls)


def test_empty_explicit_command_is_help_not_model_or_mutation(monkeypatch):
    async def forbidden(*a,**kw):raise AssertionError('No model call for command help')
    monkeypatch.setattr(ai_provider,'complete',forbidden)
    c=login(*ADMIN);csrf=csrf_of(c.get('/').text)
    r=c.post('/agent/plan',data=dict(csrf=csrf,prompt=' /takt  '))
    assert r.status_code==200 and 'hinter /takt' in r.json()['message'] and r.json()['plan_id']==''


def test_explicit_command_keeps_checked_preview_and_persists_mode(monkeypatch):
    c=login(*ADMIN);csrf=csrf_of(c.get('/').text)
    new=c.post('/agent/new',data=dict(csrf=csrf));cid=int(new.headers['location'].split('chat=')[1])
    fake(monkeypatch,[],[dict(tool='create_task',title='Explizite Inventur',description='Geprüfter Vorschlag')])
    r=c.post('/agent/plan',data=dict(csrf=csrf,chat_id=cid,prompt='/TAKT\nErstelle eine Aufgabe für die Inventur'))
    assert r.status_code==200,r.text
    assert r.json()['mode']=='operate' and r.json()['open_url'].startswith('/aufgaben/neu?agent_plan=')
    with SessionLocal() as db:
        from app.task_models import Task
        assert not db.scalar(select(Task).where(Task.title=='Explizite Inventur'))
        assert db.scalar(select(AIMessage).where(AIMessage.conversation_id==cid,AIMessage.role=='user')).content.startswith('/takt ')
    async def chat(*a,**kw):return 'Ja ist hier eine Chatnachricht.'
    monkeypatch.setattr(ai_provider,'complete',chat)
    plain=c.post('/agent/plan',data=dict(csrf=csrf,chat_id=cid,prompt='ja'))
    assert plain.json()['mode']=='chat'
    assert c.post('/agent/execute',data=dict(csrf=csrf,plan_id=r.json()['plan_id'])).status_code==409


def test_no_js_command_has_safe_native_handoff_and_stream_route_never_executes(monkeypatch):
    c=login(*ADMIN);csrf=csrf_of(c.get('/').text)
    new=c.post('/agent/new',data=dict(csrf=csrf));cid=int(new.headers['location'].split('chat=')[1])
    fake(monkeypatch,[],[dict(tool='create_task',title='Ohne JavaScript',description='Native Übergabe')])
    r=c.post(f'/agent/{cid}/message',data=dict(csrf=csrf,message='/takt Erstelle eine Aufgabe'))
    assert r.status_code==200 and 'Vorschlag im Fachbereich prüfen' in r.text and 'Ohne JavaScript' in r.text
    assert c.post(f'/agent/{cid}/message/updates',data=dict(csrf=csrf,message='/takt Erstelle eine Aufgabe')).status_code==409
    with SessionLocal() as db:pid=db.scalar(select(AIProvider.id).where(AIProvider.active.is_(True)))
    for path in ('/agent/temporary/message','/agent/temporary/updates'):
        assert c.post(path,data=dict(csrf=csrf,provider_id=pid,message='/takt Erstelle eine Aufgabe')).status_code==422
    r=c.post('/agent/plan',data=dict(csrf=csrf,prompt='/takt Erstelle eine Aufgabe'),files={'image':('sample.png',b'not-an-image','image/png')})
    assert r.status_code==422
