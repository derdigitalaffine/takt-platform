"""JSON transfer keeps scheduling data, never live participation or credentials."""
import json
from datetime import timedelta, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app import seminar_transfer as transfer, seminars as sm
from app.db import Seminar, SeminarSession, SeminarEnrollment, Notification
from conftest import login,csrf_of
from test_seminars import people,make,rec


def staff(people):return login(people[0].email,'passwort-test-123')


def test_json_roundtrip_preserves_times_settings_and_scoped_teachers(db,people):
    row,t=make(db,people,booking_mode='both',capacity=7,certificates=True,certificate_scope='term')
    row.lecturers_json=json.dumps([people[2].id]);row.lead_id=people[2].id
    row.operations_json=json.dumps({'standing':True,'self_checkin':True})
    row.notifications_json=json.dumps({'subscriber':False})
    row.planning_json=json.dumps({'schedule':{'kind':'fortnightly','first':'2027-03-15','time':'10:00','duration':30,'count':12},'locations':['Raum A','Raum B']})
    row.registration_until=t.starts_at-timedelta(days=1)
    t.lecturers_json='[]';t.guests_json=json.dumps([{'name':'Extern','email':'extern@example.org','organization':'Institut','lead':True}])
    t.overrides_json=json.dumps({'self_checkin':False,'capacity':3,'planning_customized':True})
    db.commit()
    payload=transfer.export_series(db,row)
    assert payload['seminar']['terms'][0]['starts_at'].endswith('Z') or payload['seminar']['terms'][0]['starts_at'].endswith('+00:00')
    doc=transfer.parse_document(json.dumps(payload).encode())
    copy=transfer.import_series(db,people[0],doc);db.commit();terms=sm.sessions(db,copy,False)
    assert copy.id!=row.id and copy.status=='draft' and not terms[0].published
    assert copy.booking_mode=='both' and copy.capacity==7 and copy.certificate_scope=='term'
    assert copy.registration_until==row.registration_until and terms[0].starts_at==t.starts_at
    assert copy.lecturers_json==row.lecturers_json and copy.lead_id==people[2].id
    assert terms[0].lecturers_json=='[]' and json.loads(terms[0].guests_json)[0]['email']=='extern@example.org'
    assert json.loads(terms[0].overrides_json)=={'capacity':3,'self_checkin':False}
    assert json.loads(copy.operations_json)['standing']
    assert json.loads(copy.notifications_json)=={'subscriber':False}
    assert json.loads(copy.planning_json)['schedule']['kind']=='fortnightly'
    assert json.loads(copy.planning_json)['locations']==['Raum A','Raum B']


def test_export_omits_live_data_and_personal_links(db,people):
    row,t=make(db,people);e=rec(db,row,t,people[1],status='confirmed')
    row.video_room='seminar-private';t.online_url='https://meet.example.org/private?secret=abc'
    row.planning_json=json.dumps({'csrf':'do-not-export','terms':[{'online_url':t.online_url}]})
    row.certificate_options_json=json.dumps({'signature':'private.png','teachers':True});db.commit()
    payload=json.dumps(transfer.export_series(db,row))
    for private in ('token_enc','checkin_hash','seminar-private','secret=abc','do-not-export','private.png',people[1].email):assert private not in payload
    imported=transfer.import_series(db,people[0],transfer.parse_document(payload.encode()));db.commit()
    assert imported.form_id is None and imported.poll_id is None and imported.video_room==''
    assert not db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==imported.id))


def test_routes_permissions_csrf_download_and_import(db,people):
    row,t=make(db,people);c=staff(people)
    exported=c.get(f'/seminare/{row.id}/export.json')
    assert exported.status_code==200 and 'attachment' in exported.headers['content-disposition']
    assert exported.headers['cache-control']=='no-store'
    token=csrf_of(c.get('/seminare/importieren').text)
    before=db.scalar(select(func.count()).select_from(Notification))
    assert c.post('/seminare/importieren',files={'file':('reihe.json',exported.content,'application/json')}).status_code==400
    result=c.post('/seminare/importieren',data={'csrf':token},files={'file':('reihe.json',exported.content,'application/json')})
    assert result.status_code==303
    imported=db.get(Seminar,int(result.headers['location'].split('/')[2]));assert imported.status=='draft'
    assert db.scalar(select(func.count()).select_from(Notification))==before
    other=login(people[3].email,'passwort-test-123')
    assert other.get(f'/seminare/{row.id}/export.json').status_code==404
    assert other.get('/seminare/importieren').status_code==403


@pytest.mark.parametrize('change',[
    lambda p:p.update(version=2),lambda p:p.update(version=True),
    lambda p:p['seminar'].update(owner_id=999),
    lambda p:p['seminar']['settings'].update(capacity=-1),
    lambda p:p['seminar']['settings'].update(manual_admission='false'),
    lambda p:p['seminar']['terms'][0].update(starts_at='2027-03-15T09:00'),
    lambda p:p['seminar']['terms'][0].update(ends_at='2020-01-01T00:00:00Z'),
    lambda p:p['seminar'].update(terms=[p['seminar']['terms'][0]]*101),
])
def test_invalid_or_privileged_json_rejected(db,people,change):
    row,t=make(db,people);payload=transfer.export_series(db,row);change(payload)
    with pytest.raises(HTTPException) as error:transfer.parse_document(json.dumps(payload).encode())
    assert error.value.status_code==422


def test_bad_json_size_and_unresolved_teacher_create_no_draft(db,people):
    row,t=make(db,people);c=staff(people);token=csrf_of(c.get('/seminare/importieren').text)
    before=db.scalar(select(func.count()).select_from(Seminar))
    for content in (b'not JSON',b'{"version":1,"version":2}',b'\xff',b'['*1100):
        assert c.post('/seminare/importieren',data={'csrf':token},files={'file':('bad.json',content)}).status_code==422
    assert c.post('/seminare/importieren',data={'csrf':token},files={'file':('big.json',b' '* (2*1024*1024+1))}).status_code==413
    payload=transfer.export_series(db,row);payload['seminar']['lecturers']=[{'name':'Unbekannt','email':'missing@example.org'}]
    assert c.post('/seminare/importieren',data={'csrf':token},files={'file':('unknown.json',json.dumps(payload).encode())}).status_code==422
    assert db.scalar(select(func.count()).select_from(Seminar))==before
