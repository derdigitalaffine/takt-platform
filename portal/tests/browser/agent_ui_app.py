"""Deterministic agent browser fixture; real server ACLs and writes, no LLM/network."""
import json
from task_ui_app import app
from app import ai_provider
from app.ai_models import AIProvider, AIDmsSource
from app.calendar_models import Calendar
from app.db import SessionLocal, User, Form, DmsArea, DmsRecord, set_setting
from sqlalchemy import select

with SessionLocal() as db:
    for module in ('ai', 'calendars', 'forms', 'dms'):
        set_setting(db, 'module_' + module, '1')
    set_setting(db, 'ai_knowledge_enabled', '1')
    user = db.scalar(select(User).where(User.email == 'browser@example.org'))
    user.permissions += ',ai_chat,ai_knowledge,forms'
    user.is_admin = True  # Fixture exercises all three adapters in one confirmation.
    cal = Calendar(owner_id=user.id, title='Projektkalender', source='free')
    form = Form(owner_id=user.id, title='Projektformular', internal=True, active=False)
    source = DmsArea(name='Quelle'); dest = DmsArea(name='Projektablage')
    db.add_all([cal, form, source, dest]); db.flush()
    record = DmsRecord(area_id=source.id, title='Projektwissen', note='Freigegeben', kind='manuell')
    db.add(record); db.flush()
    db.add_all([AIDmsSource(record_id=record.id), AIProvider(name='Fixture', base_url='https://llm.invalid', model_id='fixture', active=True)])
    db.commit()
    ids = cal.id, form.id, record.id, dest.id


async def complete(provider, messages, **kwargs):
    if '"searches"' in messages[0]['content']:
        return json.dumps(dict(searches=[dict(tool=t, query='') for t in
            ('search_calendars', 'search_forms', 'search_dms', 'search_dms_areas')]))
    return json.dumps(dict(message='Drei Schritte zur Prüfung. Noch nichts gespeichert.', actions=[
        dict(tool='create_event', id=ids[0], title='Projektbesprechung', description='Tagesordnung prüfen',
             location='Raum 1', start='2026-11-12T09:00:00+01:00', end='2026-11-12T10:00:00+01:00'),
        dict(tool='copy_form', id=ids[1]), dict(tool='move_dms', id=ids[2], area_id=ids[3])]))

ai_provider.complete = complete
