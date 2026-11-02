"""Configurable seminar operations using the existing seat and delivery workflows."""
import json
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from . import seminars as sm, seminar_series as series, seminar_hybrid as hybrid
from .db import SeminarEnrollment, SeminarSubscription, User, to_local, utcnow

DEFAULTS = dict(standing=False, self_checkin=False, guest_materials=False,
                guest_publish=False, teacher_days=30, mail_subject='Einladung: {titel}',
                mail_body='Hallo {name},\n\nwir laden Sie herzlich zu {titel} ein.\n\n{termine}\n\nWeitere Informationen und Anmeldung:\n{link}')
TEMPLATE_FIELDS = ('description', 'channels', 'booking_mode', 'capacity', 'manual_admission',
                   'waitlist', 'offer_hours', 'cancel_hours', 'reminder_days', 'materials_days',
                   'guest_days', 'certificates', 'certificate_scope', 'certificate_auto',
                   'certificate_percent', 'issuer', 'subscriptions', 'digest_mode',
                   'notifications_json', 'operations_json', 'planning_json')


def options(row):
    return {**DEFAULTS, **json.loads(row.operations_json or '{}')}


def standing_bookings(db, row, sub=None):
    """Attempt each published term once, preserving cancellations and manual decisions."""
    if row.status != 'published' or not options(row)['standing']:
        return
    sm.lock(db, row)
    subscriptions = [sub] if sub else list(db.scalars(select(SeminarSubscription).where(
        SeminarSubscription.seminar_id == row.id, SeminarSubscription.standing.is_(True)).order_by(SeminarSubscription.created_at,SeminarSubscription.id)))
    for identity in subscriptions:
        if not identity.standing or not identity.confirmed_at:
            continue
        user = db.get(User, identity.user_id) if identity.user_id else None
        if identity.user_id and (not user or not user.active):
            continue
        if ('internal' if user else 'guest') not in row.channels.split(','):
            continue
        for term in sm.sessions(db, row):
            if term.starts_at <= utcnow():
                continue
            existing = db.scalar(select(SeminarEnrollment.id).where(
                SeminarEnrollment.seminar_id == row.id, SeminarEnrollment.email == identity.email,
                SeminarEnrollment.scope_id.in_([0, term.id])))
            if existing:
                continue
            # A fixed audience must first receive its explicit publication invitation.
            if json.loads(row.fixed_groups_json or '[]'):
                continue
            rec = sm.new_enrollment(db, row, term.id, identity.name, identity.email, user)
            rec.verified_at = identity.confirmed_at
            hybrid.set_modes(db, row, rec, {})
            try:
                sm.request_place(db, row, rec)
            except HTTPException as error:
                if error.status_code != 409:
                    raise
                rec.status = 'invited'
                rec.reason = str(error.detail)[:500]
            if rec.status in {'invited', 'form'}:
                sm.mail(db, row, rec, 'Daueranmeldung: Aktion erforderlich',
                        rec.reason or 'Bitte vervollständigen Sie Ihre Anmeldung.')
            sm.event(db, row, 'standing_booking', detail=f'{identity.id}/{term.id}: {rec.status}')
            db.flush()


def checkin_enabled(row, term):
    return json.loads(term.overrides_json or '{}').get('self_checkin', options(row)['self_checkin'])


def checkin_serializer():
    from itsdangerous import URLSafeTimedSerializer
    from .config import settings
    return URLSafeTimedSerializer(settings.secret_key, salt='seminar-self-checkin-v1')


def checkin_token(row, term):
    return checkin_serializer().dumps([row.id, term.id, term.revision, row.revision])


def checkin_term(db, token):
    from itsdangerous import BadSignature
    from .db import Seminar, SeminarSession
    try:
        sid, tid, revision, row_revision = checkin_serializer().loads(token, max_age=900)
    except (BadSignature, ValueError, TypeError):
        raise HTTPException(410, 'Check-in abgelaufen. Bitte den aktuellen QR-Code verwenden.')
    row, term = db.get(Seminar, sid), db.get(SeminarSession, tid)
    if (not row or not term or term.seminar_id != row.id or term.revision != revision
            or row.status != 'published' or not term.published or term.cancelled
            or row.revision != row_revision or not checkin_enabled(row, term)):
        raise HTTPException(404)
    if not term.starts_at - timedelta(minutes=30) <= utcnow() <= term.ends_at:
        raise HTTPException(409, 'Selbst-Check-in ist nur ab 30 Minuten vor Beginn bis Terminende geöffnet.')
    return row, term


def template_values(row):
    values={key:getattr(row,key) for key in TEMPLATE_FIELDS if key!='planning_json'}
    planning=json.loads(row.planning_json or '{}')
    schedule={key:value for key,value in planning.get('schedule',{}).items() if key in {'kind','time','duration','count','nth','weekday','skip_holidays'}}
    values['planning_json']=json.dumps({'schedule':schedule,'locations':planning.get('locations',[])})
    return values


def render_message(text, row, name, link, terms):
    values = {'name': name, 'titel': row.title, 'link': link,
              'termine': '\n'.join((t.title or row.title)+' · '+to_local(t.starts_at).strftime('%d.%m.%Y %H:%M')+' · '+t.location for t in terms)}
    # Only these literal placeholders are expanded; no format expressions or HTML.
    for key, value in values.items():
        text = text.replace('{'+key+'}', value)
    return text


def mail_content(payload,row,target,link,terms):
    subject=render_message(payload['subject'],row,target['name'],link,terms).replace('\r',' ').replace('\n',' ')[:255]
    body=render_message(payload['body'],row,target['name'],link,terms)
    if '{link}' not in payload['body']:body+='\n\n'+link
    if payload['kind']=='invite' and not target['distribution']:body+='\n\nDie Einladung reserviert keinen Platz. Bitte ausdrücklich anmelden.'
    return subject,body