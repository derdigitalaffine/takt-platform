"""Operational workflows preserve booking, identity and publication boundaries."""
import json
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from starlette.datastructures import FormData
from app import seminars as sm, seminar_series as series, seminar_operations as ops, seminar_hybrid as hybrid
from app.db import (Seminar, SeminarSession, SeminarEnrollment, SeminarAttendance, SeminarMaterial,
                    SeminarFavorite, SeminarTemplate, SeminarMailDraft, SeminarSubscription, Notification, utcnow)
from conftest import login, client, csrf_of
from test_seminars import people, make, rec


def configure(db,row,**values):
    row.operations_json=json.dumps({**ops.DEFAULTS,**values});db.commit()


def staff(people):return login(people[0].email,'passwort-test-123')


def test_standing_enrolls_new_terms_once_preserves_cancellation_and_capacity(db,people):
    row,t=make(db,people,capacity=1)
    configure(db,row,standing=True)
    sub=series.subscribe(db,row,people[1],'','');sub.standing=True
    other=rec(db,row,t,people[2]);sm.request_place(db,row,other)
    ops.standing_bookings(db,row,sub);db.commit()
    first=db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==row.id,SeminarEnrollment.user_id==people[1].id))
    assert first.status=='waitlist'
    sm.cancel(db,row,first,True)
    t2=SeminarSession(seminar_id=row.id,title='Neuer Termin',starts_at=t.starts_at+timedelta(days=14),ends_at=t.ends_at+timedelta(days=14),published=False);db.add(t2);db.commit()
    ops.standing_bookings(db,row);db.commit()
    assert db.scalar(select(func.count()).select_from(SeminarEnrollment).where(SeminarEnrollment.seminar_id==row.id))==2
    t2.published=True;db.commit();ops.standing_bookings(db,row);db.commit();ops.standing_bookings(db,row);db.commit()
    assert first.status=='cancelled'
    future=db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.scope_id==t2.id,SeminarEnrollment.user_id==people[1].id))
    assert future.status=='confirmed'
    sub.standing=False;db.commit();assert future.status=='confirmed'


def test_standing_requires_consent_and_can_end_when_disabled(db,people):
    row,t=make(db,people);configure(db,row,standing=True)
    c=login(people[1].email,'passwort-test-123');token=csrf_of(c.get(f'/seminare/{row.id}').text)
    r=c.post(f'/seminare/{row.id}/subscribe',data={'csrf':token});path=r.headers['location']
    assert not db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==row.id))
    token=csrf_of(c.get(path).text)
    assert c.post(path,data={'csrf':token,'action':'standing','enabled':'1'}).status_code==303
    sub=db.scalar(select(SeminarSubscription).where(SeminarSubscription.seminar_id==row.id))
    db.refresh(sub);assert sub.standing
    configure(db,row,standing=False)
    assert c.post(path,data={'csrf':token,'action':'standing','enabled':'0'}).status_code==303
    db.refresh(sub);assert not sub.standing


def test_standing_required_form_stays_actionable(db,people):
    from app.db import Form
    row,t=make(db,people);form=Form(owner_id=people[0].id,title='Anmeldung');db.add(form);db.flush();row.form_id=form.id
    configure(db,row,standing=True)
    sub=series.subscribe(db,row,people[1],'','');sub.standing=True;ops.standing_bookings(db,row,sub);db.commit()
    result=db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==row.id))
    assert result.status=='form'
    row.form_id=None;db.delete(form);db.commit()


def test_self_checkin_requires_booking_time_explicit_post_and_preserves_staff_correction(db,people):
    row,t=make(db,people);t.starts_at=utcnow()-timedelta(minutes=10);t.ends_at=utcnow()+timedelta(minutes=30)
    configure(db,row,self_checkin=True)
    e=rec(db,row,t,people[1],status='confirmed');db.commit()
    path='/seminare/checkin/'+ops.checkin_token(row,t)
    outsider=login(people[3].email,'passwort-test-123');assert outsider.get(path).status_code==403
    c=login(people[1].email,'passwort-test-123');page=c.get(path);assert page.status_code==200
    assert not db.scalar(select(SeminarAttendance).where(SeminarAttendance.enrollment_id==e.id))
    assert c.post(path,data={}).status_code==400
    token=csrf_of(page.text);assert c.post(path,data={'csrf':token}).status_code==303
    a=db.scalar(select(SeminarAttendance).where(SeminarAttendance.enrollment_id==e.id));assert a.present and a.source=='self' and a.recorded_by==people[1].id
    c.post(path,data={'csrf':token});assert db.scalar(select(func.count()).select_from(SeminarAttendance).where(SeminarAttendance.enrollment_id==e.id))==1
    a.source='staff';a.present=False;db.commit()
    assert c.post(path,data={'csrf':token}).status_code==409;db.refresh(a);assert not a.present
    t.revision+=1;db.commit();assert c.get(path).status_code==404


def test_self_checkin_expired_and_closed(db,people,monkeypatch):
    row,t=make(db,people);configure(db,row,self_checkin=True)
    c=staff(people);path='/seminare/checkin/'+ops.checkin_token(row,t)
    assert c.get(path).status_code==409
    import itsdangerous.timed
    now=itsdangerous.timed.time.time()
    monkeypatch.setattr(itsdangerous.timed.time,'time',lambda:now+901)
    assert c.get(path).status_code==410


def test_scoped_conduct_and_manual_attendance(db,people):
    row,t=make(db,people);t.starts_at=utcnow()-timedelta(minutes=1);t.ends_at=utcnow()+timedelta(hours=1);db.commit()
    e=rec(db,row,t,people[1],status='confirmed');db.commit()
    c=staff(people);path=f'/seminare/{row.id}/durchfuehrung/{t.id}';page=c.get(path)
    assert page.status_code==200 and 'Noch nicht erfasst' in page.text
    assert c.post(path,data={'csrf':csrf_of(page.text),'enrollment':e.id,'present':'1'}).status_code==303
    assert 'Durch Betreuung erfasst' in c.get(path).text
    outsider=login(people[3].email,'passwort-test-123');assert outsider.get(path).status_code==404


def test_mail_preview_distribution_safety_dedup_and_replay(db,people):
    row,t=make(db,people);c=staff(people);page=c.get(f'/seminare/{row.id}/mail');assert page.status_code==200
    token=csrf_of(page.text)
    r=c.post(f'/seminare/{row.id}/mail/preview',data={'csrf':token,'kind':'invite','scope_id':t.id,
        'subject':'Einladung {titel}','body':'Hallo {name}\n{link}', 'users':str(people[1].id),
        'addresses':people[1].email+'\nGast;external-test@example.org','distributors':'Haus;alle@example.org'})
    assert r.status_code==200 and '3 Empfänger' in r.text
    assert not db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==row.id))
    draft=db.scalar(select(SeminarMailDraft).where(SeminarMailDraft.seminar_id==row.id))
    send=f'/seminare/{row.id}/mail/{draft.id}/send'
    assert c.post(send,data={'csrf':token}).status_code==303
    records=list(db.scalars(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==row.id)))
    assert len(records)==2 and all(r.status=='invited' for r in records)
    mail=db.scalar(select(Notification).where(Notification.to_addr=='alle@example.org',Notification.kind=='seminar'))
    assert '/seminare/p/' not in mail.body and f'/seminare/{row.id}' in mail.body
    assert c.post(send,data={'csrf':token}).status_code==409


def test_general_notice_never_creates_enrollment_and_stale_preview_rejected(db,people):
    row,t=make(db,people);c=staff(people);token=csrf_of(c.get(f'/seminare/{row.id}/mail').text)
    payload={'csrf':token,'kind':'notice','scope_id':0,'subject':'Hinweis','body':'{titel} {link}','addresses':'notice-test@example.org'}
    assert c.post(f'/seminare/{row.id}/mail/preview',data=payload).status_code==200
    draft=db.scalar(select(SeminarMailDraft).where(SeminarMailDraft.seminar_id==row.id));row.revision+=1;db.commit()
    assert c.post(f'/seminare/{row.id}/mail/{draft.id}/send',data={'csrf':token}).status_code==409
    assert c.post(f'/seminare/{row.id}/mail/preview',data=payload).status_code==200
    latest=db.scalar(select(SeminarMailDraft).where(SeminarMailDraft.seminar_id==row.id).order_by(SeminarMailDraft.id.desc()))
    assert c.post(f'/seminare/{row.id}/mail/{latest.id}/send',data={'csrf':token}).status_code==303
    assert not db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==row.id))


def test_templates_copy_settings_without_people_terms_or_access(db,people):
    row,t=make(db,people);configure(db,row,standing=True,mail_subject='Info {titel}')
    c=staff(people);token=csrf_of(c.get(f'/seminare/{row.id}/organisation').text)
    assert c.post(f'/seminare/{row.id}/template',data={'csrf':token,'name':'Eigene Vorlage'}).status_code==303
    template=db.scalar(select(SeminarTemplate).where(SeminarTemplate.owner_id==people[0].id))
    outsider=login(people[3].email,'passwort-test-123');other_csrf=csrf_of(outsider.get('/').text)
    assert outsider.post('/seminare/vorlagen/new',data={'csrf':other_csrf,'template':template.id}).status_code==403
    r=c.post('/seminare/vorlagen/new',data={'csrf':token,'template':template.id});assert r.status_code==303
    new_id=int(r.headers['location'].split('/')[2]);copied=db.get(Seminar,new_id)
    assert copied.status=='draft' and ops.options(copied)['standing']
    assert not sm.sessions(db,copied,False) and copied.lecturers_json=='[]'
    configure(db,copied,standing=False);db.refresh(row);assert ops.options(row)['standing']
    assert c.get('/seminare/vorlagen').status_code==200
    r=c.post('/seminare/vorlagen/new',data={'csrf':token,'template':'wissenshaeppchen'})
    preset=db.get(Seminar,int(r.headers['location'].split('/')[2]))
    assert preset.certificate_scope=='term' and json.loads(preset.planning_json)['schedule']['kind']=='fortnightly'


def test_favorites_are_private_and_do_not_book_or_subscribe(db,people):
    row,t=make(db,people);c=login(people[1].email,'passwort-test-123');token=csrf_of(c.get('/seminare').text)
    path=f'/seminare/{row.id}/favorite';assert c.post(path,data={'csrf':token,'enabled':'1'}).status_code==303
    c.post(path,data={'csrf':token,'enabled':'1'})
    assert db.scalar(select(func.count()).select_from(SeminarFavorite).where(SeminarFavorite.seminar_id==row.id))==1
    assert row.title in c.get('/seminare?tab=favorites').text
    outsider=login(people[3].email,'passwort-test-123');assert row.title not in outsider.get('/seminare?tab=favorites').text
    assert not db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==row.id))


def test_guest_materials_review_scope_schedule_and_revocation(db,people):
    row,t=make(db,people);t.guests_json=json.dumps([{'name':'Extern','email':'teacher@example.org'}]);db.commit()
    configure(db,row,guest_materials=True)
    url=hybrid.invite_teacher(db,row,t,'teacher@example.org');db.commit();path=url[url.index('/seminare/'):]
    c=client();page=c.get(path);assert page.status_code==200 and 'Unterlage hochladen' in page.text
    token=csrf_of(page.text)
    r=c.post(path+'/materials',data={'csrf':token,'title':'Präsentation','mode':'scheduled','release_at':'2027-03-15T12:00'},files={'file':('slides.pptx',b'presentation','application/octet-stream')})
    assert r.status_code==303
    m=db.scalar(select(SeminarMaterial).where(SeminarMaterial.seminar_id==row.id));assert not m.published and m.manual_release and m.release_at
    assert c.get(path+f'/materials/{m.id}').status_code==200
    other=SeminarMaterial(seminar_id=row.id,scope_id=t.id,title='Intern',item_json='{}');db.add(other);db.commit()
    assert c.get(path+f'/materials/{other.id}').status_code==404
    configure(db,row,guest_materials=True,guest_publish=True)
    assert c.post(path+f'/materials/{m.id}',data={'csrf':token,'mode':'immediate'}).status_code==303
    db.refresh(m);assert m.published and not m.release_at
    planner=staff(people);staff_token=csrf_of(planner.get(f'/seminare/{row.id}/organisation').text)
    assert planner.post(f'/seminare/{row.id}/teacher-access/{t.id}',data={'csrf':staff_token,'email':'teacher@example.org','action':'revoke'}).status_code==303
    assert c.get(path).status_code==404
    db.refresh(m);assert m.author_access_id is None


def test_organisation_stale_write_and_guest_disabled(db,people):
    row,t=make(db,people);c=staff(people);page=c.get(f'/seminare/{row.id}/organisation');token=csrf_of(page.text)
    data={'csrf':token,'revision':row.revision,'standing':'1','self_checkin':'1','teacher_days':30}
    assert c.post(f'/seminare/{row.id}/organisation',data=data).status_code==303
    assert c.post(f'/seminare/{row.id}/organisation',data=data).status_code==409
    db.refresh(row);assert ops.options(row)['standing']


def test_standing_available_without_newsletter(db,people):
    row,t=make(db,people,subscriptions=False);configure(db,row,standing=True)
    c=login(people[1].email,'passwort-test-123');page=c.get(f'/seminare/{row.id}')
    assert 'Daueranmeldung verwalten' in page.text
    r=c.post(f'/seminare/{row.id}/subscribe',data={'csrf':csrf_of(page.text)})
    path=r.headers['location'];page=c.get(path)
    assert 'Ausdrücklich dauerhaft anmelden' in page.text
    assert c.post(path,data={'csrf':csrf_of(page.text),'action':'standing','enabled':'1'}).status_code==303
    sub=db.scalar(select(SeminarSubscription).where(SeminarSubscription.seminar_id==row.id))
    assert sub.standing and not sub.active


def test_existing_database_migration_is_additive_and_repeatable(tmp_path,monkeypatch):
    import app.db as model
    from sqlalchemy import create_engine, text, inspect
    from sqlalchemy.orm import sessionmaker
    engine=create_engine('sqlite:///'+str(tmp_path/'old.db'))
    monkeypatch.setattr(model,'engine',engine)
    monkeypatch.setattr(model,'SessionLocal',sessionmaker(bind=engine,expire_on_commit=False))
    model.init_db()
    with model.SessionLocal() as session:
        owner=model.User(name='Bestand',email='bestand@example.org',password_hash='test-only')
        session.add(owner);session.flush()
        row=model.Seminar(owner_id=owner.id,title='Bestehende Reihe');session.add(row);session.commit();sid=row.id
    with engine.begin() as connection:
        for table,column in [('seminars','operations_json'),('seminar_subscriptions','standing'),('seminar_attendance','source')]:
            connection.execute(text(f'ALTER TABLE {table} DROP COLUMN {column}'))
        connection.execute(text('DROP TABLE seminar_materials'))
        connection.execute(text("CREATE TABLE seminar_materials (id INTEGER PRIMARY KEY,seminar_id INTEGER NOT NULL REFERENCES seminars(id) ON DELETE CASCADE,scope_id INTEGER NOT NULL,title VARCHAR(255) NOT NULL,item_json TEXT NOT NULL,release_at DATETIME,manual_release BOOLEAN NOT NULL,published BOOLEAN NOT NULL,position INTEGER NOT NULL)"))
        for table in ('seminar_favorites','seminar_templates','seminar_mail_drafts'):
            connection.execute(text(f'DROP TABLE {table}'))
    model.init_db();model.init_db()
    assert 'operations_json' in {col['name'] for col in inspect(engine).get_columns('seminars')}
    assert 'standing' in {col['name'] for col in inspect(engine).get_columns('seminar_subscriptions')}
    assert all(inspect(engine).has_table(table) for table in ('seminar_favorites','seminar_templates','seminar_mail_drafts'))
    with model.SessionLocal() as session:
        restored=session.get(model.Seminar,sid)
        assert restored.title=='Bestehende Reihe' and ops.options(restored)==ops.DEFAULTS
    engine.dispose()


def test_mail_failure_rolls_back_entire_draft(db,people,monkeypatch):
    from app import notify
    row,t=make(db,people);c=staff(people);token=csrf_of(c.get(f'/seminare/{row.id}/mail').text)
    c.post(f'/seminare/{row.id}/mail/preview',data={'csrf':token,'kind':'invite','scope_id':t.id,'subject':'Einladung','body':'{link}','addresses':'one-fail@example.org\ntwo-fail@example.org'})
    draft=db.scalar(select(SeminarMailDraft).where(SeminarMailDraft.seminar_id==row.id))
    original=notify.enqueue
    def fail_second(connection,address,*args,**kwargs):
        return False if address=='two-fail@example.org' else original(connection,address,*args,**kwargs)
    monkeypatch.setattr(notify,'enqueue',fail_second)
    assert c.post(f'/seminare/{row.id}/mail/{draft.id}/send',data={'csrf':token}).status_code==409
    db.expire_all();assert draft.sent_at is None
    assert not db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==row.id))
    assert not db.scalar(select(Notification).where(Notification.to_addr=='one-fail@example.org'))


def test_guest_upload_rechecks_assignment_after_lock(db,people,monkeypatch):
    row,t=make(db,people);t.guests_json=json.dumps([{'name':'Extern','email':'race@example.org'}]);db.commit()
    configure(db,row,guest_materials=True)
    url=hybrid.invite_teacher(db,row,t,'race@example.org');db.commit();path=url[url.index('/seminare/'):]
    c=client();token=csrf_of(c.get(path).text)
    original=sm.lock
    def revoke_assignment(connection,seminar,*args):
        original(connection,seminar,*args)
        term=connection.get(SeminarSession,t.id);term.guests_json='[]';connection.flush()
    monkeypatch.setattr(sm,'lock',revoke_assignment)
    result=c.post(path+'/materials',data={'csrf':token,'title':'Unterlage','mode':'immediate'},files={'file':('test.txt',b'test')})
    assert result.status_code==404
    assert not db.scalar(select(SeminarMaterial).where(SeminarMaterial.seminar_id==row.id))
