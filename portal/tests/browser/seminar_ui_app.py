"""Isolated seminar fixtures; no worker and no actual mail delivery."""
import json, os
from datetime import timedelta
from pathlib import Path
os.environ.update(PORTAL_BASE_URL='http://127.0.0.1:8766',MEET_BASE_URL='http://127.0.0.1:8080',PORTAL_SECRET_KEY='seminar-browser-secret-with-more-than-32-characters',JWT_APP_SECRET='seminar-browser-jwt-with-more-than-32-characters',TZ='Europe/Berlin')
from app import main, seminars as sm, seminar_operations as ops, seminar_hybrid as hybrid
from app.db import SessionLocal, User, Seminar, SeminarSession, init_db, set_setting, utcnow
from app.security import hash_password
init_db()
with SessionLocal() as db:
    set_setting(db,'module_seminars','1');set_setting(db,'smtp_host','localhost');set_setting(db,'mail_from','test@example.org')
    planner=User(name='Mara Planung',email='planner@example.org',password_hash=hash_password('browser-test-password'),permissions='seminars,video')
    member=User(name='Alex Teilnahme',email='member@example.org',password_hash=hash_password('browser-test-password'))
    db.add_all([planner,member]);db.flush()
    row=Seminar(owner_id=planner.id,title='Wissenshäppchen',description='Gemeinsam lernen – alle 14 Tage an wechselnden Orten.',status='published',channels='internal,guest',booking_mode='individual',certificates=True,certificate_scope='term',operations_json=json.dumps({**ops.DEFAULTS,'standing':True,'self_checkin':True,'guest_materials':True}))
    db.add(row);db.flush()
    today=SeminarSession(seminar_id=row.id,title='Digitale Zusammenarbeit',starts_at=utcnow()-timedelta(minutes=5),ends_at=utcnow()+timedelta(minutes=25),location='Rathaus · Besprechungsraum 1',guests_json=json.dumps([{'name':'Kim Extern','email':'external@example.org'}]))
    future=SeminarSession(seminar_id=row.id,title='Wissen sicher teilen',starts_at=utcnow()+timedelta(days=14),ends_at=utcnow()+timedelta(days=14,minutes=30),location='Rathaus · Besprechungsraum 2')
    single=Seminar(owner_id=planner.id,title='Einzelworkshop Datenschutz',status='published',channels='internal',capacity=12,booking_mode='individual')
    db.add_all([today,future,single]);db.flush()
    db.add(SeminarSession(seminar_id=single.id,title='Datenschutz im Alltag',starts_at=utcnow()+timedelta(days=20),ends_at=utcnow()+timedelta(days=20,hours=2),location='Schulungsraum'))
    sm.new_enrollment(db,row,today.id,member.name,member.email,member,status='confirmed')
    guest_url=hybrid.invite_teacher(db,row,today,'external@example.org');db.commit()
    Path(os.environ['DATA_DIR'],'browser-fixture.json').write_text(json.dumps(dict(sid=row.id,tid=today.id,future=future.id,single=single.id,teacher=guest_url[guest_url.index('/seminare/'):])) )
app=main.app
