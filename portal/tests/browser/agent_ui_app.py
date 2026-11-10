"""Deterministic agent browser fixture; real server ACLs and writes, no LLM/network."""
import json
from task_ui_app import app
from app import ai_provider
from app.ai_models import AIProvider, AIDmsSource
from app.calendar_models import Calendar, CalendarEvent
from app.anliegen_models import AnliegenCategory, Anliegen
from app.task_models import Task
from app.security import hash_password
from app.db import SessionLocal, User, Form, DmsArea, DmsRecord, Organization, KrankEmployer, set_setting
from app.org_models import OrgMembership
from app.leave_models import LeavePolicy, LeaveRequest
from app import leave
from sqlalchemy import select

with SessionLocal() as db:
    for module in ('ai', 'calendars', 'forms', 'dms', 'anliegen', 'krank'):
        set_setting(db, 'module_' + module, '1')
    set_setting(db, 'ai_knowledge_enabled', '1')
    user = db.scalar(select(User).where(User.email == 'browser@example.org'))
    user.permissions += ',ai_chat,ai_knowledge,forms'
    db.add(KrankEmployer(name='Agent Health Employer', active=True))
    set_setting(db, 'krank_kinds', 'simple,au,eau,child')
    user.is_admin = True  # Fixture exercises all three adapters in one confirmation.
    cal = Calendar(owner_id=user.id, title='Projektkalender', source='free')
    form = Form(owner_id=user.id, title='Projektformular', internal=True, active=False)
    source = DmsArea(name='Quelle'); dest = DmsArea(name='Projektablage')
    db.add_all([cal, form, source, dest]); db.flush()
    record = DmsRecord(area_id=source.id, title='Projektwissen', note='Freigegeben', kind='manuell')
    db.add(record); db.flush()
    db.add_all([AIDmsSource(record_id=record.id), AIProvider(name='Fixture', base_url='https://llm.invalid', model_id='fixture', active=True)])
    cat = AnliegenCategory(key='browser_agent', title='Agent IT Anliegen', routing='person', assignee_id=user.id, enabled=True)
    colleague = User(name='Alex Agent', email='agent-colleague@example.org', password_hash=hash_password('browser-colleague-password'), permissions='tasks,anliegen_submit', active=True)
    db.add_all([cat, colleague]); db.commit()
    unit = Organization(name='Agent Urlaubsbereich', kind='fachbereich')
    db.add(unit); db.flush()
    db.add(OrgMembership(user_id=user.id, org_id=unit.id, is_primary=True, counts_staff=True))
    db.add(LeavePolicy(org_id=unit.id, workflow='planning', sync_absence=True)); db.commit()
    vacation = leave.save(db, user, dict(starts_on='2030-12-02', ends_on='2030-12-03')); db.commit()
    leave.command(db, user, vacation.id, 'bind', vacation.version); db.commit()
    ids = cal.id, form.id, record.id, dest.id
    cat_id, colleague_id = cat.id, colleague.id


async def complete(provider, messages, **kwargs):
    searching = '"searches"' in messages[0]['content']
    content = messages[-1]['content']
    prompt = content if searching else json.loads(content)['auftrag']
    searches, actions = None, None
    with SessionLocal() as db:
        case = db.scalar(select(Anliegen).where(Anliegen.title == 'Browser Anliegen'))
        task = db.scalar(select(Task).where(Task.title == 'Browser Aufgabe'))
        if 'Geburtstag' in prompt or prompt == 'ja':
            searches = []
            actions = [dict(tool='create_form', title='Geburtstage der Belegschaft', fields=[dict(type='short', title='Name', required=True), dict(type='date', title='Geburtstag', required=False)])]
        elif prompt.startswith('Verschiebe den Kalendertermin'):
            event = db.scalar(select(CalendarEvent).where(CalendarEvent.title == 'Von mir geprüfte Projektbesprechung'))
            searches = [dict(tool='search_events', query='Von mir geprüfte Projektbesprechung')]
            actions = [dict(tool='update_event', id=event.id, start='2026-11-14T14:00:00+01:00', end='2026-11-14T15:00:00+01:00')]
        elif prompt.startswith('Erstelle einen ganztägigen Kalendertermin'):
            searches = [dict(tool='search_calendars', query='Projektkalender')]
            actions = [dict(tool='create_event', id=ids[0], title='Agent Ganztägig', start='2026-12-04', end='2026-12-04', all_day=True)]
        elif prompt.startswith('Lösche den Kalendertermin Agent Ganztägig'):
            event = db.scalar(select(CalendarEvent).where(CalendarEvent.title == 'Agent Ganztägig'))
            searches = [dict(tool='search_events', query='Agent Ganztägig')]
            actions = [dict(tool='delete_event', id=event.id)]
        elif prompt.startswith('Plane meinen Urlaub'):

            searches = []
            actions = [dict(tool='create_leave', starts_on='2030-12-09', ends_on='2030-12-11', start_half='pm', end_half='pm')]
        elif prompt.startswith('Markiere meinen Urlaub'):
            vacation = db.scalar(select(LeaveRequest).where(LeaveRequest.starts_on == '2030-12-09'))
            searches = [dict(tool='search_my_leave', query='2030-12-09')]
            actions = [dict(tool='leave_command', id=vacation.id, command='bind')]
        elif prompt.startswith('Ändere meinen Urlaub'):
            vacation = db.scalar(select(LeaveRequest).where(LeaveRequest.starts_on == '2030-12-09'))
            searches = [dict(tool='search_my_leave', query='2030-12-09')]
            actions = [dict(tool='edit_leave', id=vacation.id, starts_on='2030-12-16', ends_on='2030-12-18')]
        elif prompt.startswith('Internes Anliegen'):

            searches = []
            actions = [dict(tool='create_anliegen', category_id=cat_id, title='Browser Anliegen', description='Zwei Bürostühle für Raum 1 prüfen')]
        elif prompt.startswith('Anliegen bearbeiten'):
            searches = [dict(tool='search_anliegen', query='Browser Anliegen')]
            actions = [dict(tool='set_anliegen_status', id=case.id, status='in_progress')]
        elif prompt.startswith('Anliegen zuweisen'):
            searches = [dict(tool='search_anliegen', query='Browser Anliegen'), dict(tool='search_people', query='Alex Agent')]
            actions = [dict(tool='assign_anliegen', id=case.id, assignee_id=colleague_id)]
        elif prompt.startswith('Routing ändern'):
            searches = [dict(tool='search_anliegen_categories', query='Agent IT Anliegen'), dict(tool='search_people', query='Alex Agent')]
            actions = [dict(tool='configure_anliegen_category', id=cat_id, title='Agent IT Anliegen Team', routing='person', assignee_id=colleague_id, enabled=True, apply_open=False)]
        elif prompt.startswith('Aufgabe vorbereiten'):
            searches = []
            actions = [dict(tool='create_task', title='Browser Aufgabe', description='Unterlagen prüfen')]
        elif prompt.startswith('Aufgabe zuweisen'):
            searches = [dict(tool='search_tasks', query='Browser Aufgabe'), dict(tool='search_people', query='Alex Agent')]
            actions = [dict(tool='assign_task', id=task.id, assignee_id=colleague_id)]
        elif prompt.startswith('Aufgabe priorisieren'):
            searches = [dict(tool='search_tasks', query='Browser Aufgabe')]
            actions = [dict(tool='set_task_priority', id=task.id, priority='high')]
        elif prompt.startswith('Aufgabe starten'):
            searches = [dict(tool='search_tasks', query='Browser Aufgabe')]
            actions = [dict(tool='set_task_status', id=task.id, status='in_progress')]
    if searches is not None:
        return json.dumps(dict(searches=searches) if searching else dict(message='Vorschlag im Fachbereich prüfen.', actions=actions))
    if searching:
        return json.dumps(dict(searches=[dict(tool=t, query='') for t in
            ('search_calendars', 'search_forms', 'search_dms', 'search_dms_areas')]))
    return json.dumps(dict(message='Drei Schritte zur Prüfung. Noch nichts gespeichert.', actions=[
        dict(tool='create_event', id=ids[0], title='Projektbesprechung', description='Tagesordnung prüfen',
             location='Raum 1', start='2026-11-12T09:00:00+01:00', end='2026-11-12T10:00:00+01:00'),
        dict(tool='copy_form', id=ids[1]), dict(tool='move_dms', id=ids[2], area_id=ids[3])]))

ai_provider.complete = complete
