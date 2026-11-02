"""Versioned, portable seminar planning data; imports always create a new draft."""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, StrictBool, ValidationError
from sqlalchemy import select
from . import seminars as sm, seminar_operations as ops, seminar_series as series
from .db import Seminar, SeminarSession, User

Short = Annotated[str, Field(max_length=255)]
Count = Annotated[int, Field(strict=True, ge=0, le=10000)]


class Document(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Teacher(Document):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    email: Short = ''
    organization: Short = ''
    lead: StrictBool = False


class Operations(Document):
    standing: StrictBool = False
    self_checkin: StrictBool = False
    guest_materials: StrictBool = False
    guest_publish: StrictBool = False
    teacher_days: Annotated[int, Field(strict=True, ge=1, le=365)] = 30
    mail_subject: Annotated[str, Field(min_length=1, max_length=200)] = ops.DEFAULTS['mail_subject']
    mail_body: Annotated[str, Field(min_length=1, max_length=10000)] = ops.DEFAULTS['mail_body']


class Settings(Document):
    booking_mode: Literal['individual','series','both'] = 'individual'
    channels: Annotated[list[Literal['internal','guest','public']], Field(min_length=1,max_length=3)] = ['internal']
    capacity: Count = 0
    manual_admission: StrictBool = False
    waitlist: StrictBool = True
    offer_hours: Annotated[int, Field(strict=True,ge=1,le=720)] = 48
    cancel_hours: Annotated[int, Field(strict=True,ge=0,le=8760)] = 24
    reminder_days: Annotated[list[Annotated[int, Field(strict=True,ge=1,le=365)]], Field(max_length=365)] = [7,1]
    registration_until: AwareDatetime | None = None
    materials_days: Annotated[int, Field(strict=True,ge=0,le=3650)] = 0
    guest_days: Annotated[int, Field(strict=True,ge=0,le=3650)] = 0
    contact_email: Short = ''
    contact_visible: StrictBool = False
    certificates: StrictBool = False
    certificate_scope: Literal['enrollment','term','series','both'] = 'enrollment'
    certificate_auto: StrictBool = False
    certificate_percent: Annotated[int, Field(strict=True,ge=0,le=100)] = 80
    certificate_teachers: StrictBool = False
    issuer: Short = ''
    form_once: StrictBool = False
    subscriptions: StrictBool = True
    digest_mode: Literal['daily','immediate'] = 'daily'
    notifications: dict[str,StrictBool] = {}
    operations: Operations = Field(default_factory=Operations)


class Overrides(Document):
    capacity: Count | None = None
    cancel_hours: Annotated[int, Field(strict=True,ge=0,le=8760)] | None = None
    manual_admission: StrictBool | None = None
    registration_until: AwareDatetime | None = None
    self_checkin: StrictBool | None = None


class Term(Document):
    title: Short = ''
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    location: Annotated[str, Field(max_length=500)] = ''
    delivery_mode: Literal['onsite','online','hybrid'] = 'onsite'
    online_capacity: Count = 0
    lecturers: Annotated[list[Teacher], Field(max_length=100)] = []
    guests: Annotated[list[Teacher], Field(max_length=30)] = []
    lecturer_description: Annotated[str, Field(max_length=10000)] = ''
    show_contact: StrictBool = False
    participants_visible: StrictBool = False
    cancelled: StrictBool = False
    reason: Annotated[str, Field(max_length=500)] = ''
    overrides: Overrides = Field(default_factory=Overrides)


class Schedule(Document):
    kind: Literal['once','weekly','fortnightly','monthly','monthly_weekday','dates'] = 'once'
    first: date | None = None
    time: Annotated[str, Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')] = '09:00'
    duration: Annotated[int, Field(strict=True,ge=1,le=10080)] = 60
    count: Annotated[int, Field(strict=True,ge=1,le=100)] = 6
    until: date | None = None
    end_mode: Literal['count','until'] = 'count'
    nth: Annotated[int, Field(strict=True,ge=-1,le=5)] = 1
    weekday: Annotated[int, Field(strict=True,ge=0,le=6)] = 0
    dates: Annotated[list[date], Field(max_length=100)] = []
    skip_holidays: StrictBool = False


class Series(Document):
    title: Annotated[str, Field(min_length=1,max_length=255)]
    description: Annotated[str, Field(max_length=100000)] = ''
    settings: Settings = Field(default_factory=Settings)
    schedule: Schedule | None = None
    locations: Annotated[list[Annotated[str, Field(max_length=500)]], Field(max_length=20)] = []
    lecturers: Annotated[list[Teacher], Field(max_length=100)] = []
    guests: Annotated[list[Teacher], Field(max_length=30)] = []
    terms: Annotated[list[Term], Field(max_length=100)] = []


class Transfer(Document):
    format: Literal['takt.seminar-series']
    version: Annotated[int, Field(strict=True,ge=1,le=1)]
    seminar: Series


def utc(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def internal_teachers(db,ids,lead=None):
    result=[]
    for uid in ids:
        user=db.get(User,uid)
        if user:result.append(dict(name=user.name,email=user.email,lead=uid==lead))
    return result


def guests(raw):
    return [{key:value for key,value in item.items() if key in Teacher.model_fields} for item in json.loads(raw or '[]')]


def export_series(db,row):
    config={key:getattr(row,key) for key in Settings.model_fields if key not in {
        'channels','reminder_days','registration_until','notifications','operations','certificate_teachers'}}
    config.update(channels=row.channels.split(','),reminder_days=[int(v) for v in row.reminder_days.split(',') if v],
        registration_until=utc(row.registration_until),notifications=json.loads(row.notifications_json),
        operations=ops.options(row),certificate_teachers=bool(json.loads(row.certificate_options_json).get('teachers')))
    terms=[]
    for term in sm.sessions(db,row,False):
        overrides={key:value for key,value in json.loads(term.overrides_json).items() if key in Overrides.model_fields}
        if overrides.get('registration_until'):overrides['registration_until']=utc(datetime.fromisoformat(overrides['registration_until']))
        terms.append(dict(title=term.title,starts_at=utc(term.starts_at),ends_at=utc(term.ends_at),location=term.location,
            delivery_mode=term.delivery_mode,online_capacity=term.online_capacity,
            lecturers=internal_teachers(db,series.lecturer_ids(row,term),term.lead_id),guests=guests(term.guests_json),
            lecturer_description=term.lecturer_description,show_contact=term.show_contact,
            participants_visible=term.participants_visible,cancelled=term.cancelled,reason=term.reason,overrides=overrides))
    planning=json.loads(row.planning_json or '{}')
    schedule={key:value for key,value in (planning.get('schedule') or {}).items() if key in Schedule.model_fields and value!=''}
    payload=dict(format='takt.seminar-series',version=1,seminar=dict(title=row.title,description=row.description,
        settings=config,schedule=schedule or None,locations=planning.get('locations',[]),lecturers=internal_teachers(db,json.loads(row.lecturers_json),row.lead_id),guests=guests(row.guests_json),terms=terms))
    # Export and import share the same schema, including timezone-aware timestamps.
    return Transfer.model_validate(payload).model_dump(mode='json')


def parse_document(body):
    try:
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise ValueError('Doppelter Schlüssel: '+key)
                result[key]=value
            return result
        value=json.loads(body.decode('utf-8-sig'),object_pairs_hook=unique)
        document=Transfer.model_validate(value)
    except (UnicodeError,ValueError,RecursionError,ValidationError) as error:
        # Do not echo uploaded data or potentially sensitive fields in error messages.
        raise HTTPException(422,'Ungültige Seminar-JSON-Datei. Format, Version und Feldtypen prüfen.') from error
    if not document.seminar.title.strip():raise HTTPException(422,'Titel erforderlich.')
    for term in document.seminar.terms:
        if term.ends_at<=term.starts_at or term.ends_at-term.starts_at>timedelta(days=7):raise HTTPException(422,'Terminende muss nach Beginn liegen, Dauer maximal sieben Tage.')
    return document


def import_series(db,user,document):
    source=document.seminar;config=source.settings
    if set(config.notifications)-series.EVENTS.keys():raise HTTPException(422,'Unbekannte Benachrichtigungsoption.')
    if any(c in config.operations.mail_subject for c in '\r\n'):raise HTTPException(422,'Mailbetreff darf keine Zeilenumbrüche enthalten.')
    def validate_email(email):
        if email and not sm.re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',email):raise HTTPException(422,'Ungültige E-Mail-Adresse in der Importdatei.')
    validate_email(config.contact_email)
    def resolve(teachers,external):
        ids=[];lead=None
        for teacher in [*teachers,*external]:validate_email(teacher.email)
        for teacher in teachers:
            member=db.scalar(select(User).where(User.email==teacher.email.strip().lower(),User.active.is_(True)))
            if not member:raise HTTPException(422,'Interner Dozent ist hier nicht als aktiver Benutzer vorhanden: '+teacher.email)
            if member.id in ids:raise HTTPException(422,'Interner Dozent mehrfach zugeordnet.')
            ids.append(member.id)
            if teacher.lead:
                if lead:raise HTTPException(422,'Nur einen Hauptdozenten auswählen.')
                lead=member.id
        if bool(lead)+sum(t.lead for t in external)>1:raise HTTPException(422,'Nur einen Hauptdozenten auswählen.')
        return ids,lead
    # Validate every identity before creating any persistent data.
    ids,lead=resolve(source.lecturers,source.guests)
    resolved=[resolve(t.lecturers,t.guests) for t in source.terms]
    values=config.model_dump(exclude={'channels','reminder_days','registration_until','notifications','operations','certificate_teachers'})
    row=Seminar(owner_id=user.id,title=source.title,description=source.description,**values,
        channels=','.join(dict.fromkeys(config.channels)),reminder_days=','.join(str(v) for v in sorted(set(config.reminder_days),reverse=True)),
        registration_until=naive(config.registration_until),notifications_json=json.dumps(config.notifications),
        operations_json=config.operations.model_dump_json(),certificate_options_json=json.dumps({'teachers':config.certificate_teachers}),
        lecturers_json=json.dumps(ids),lead_id=lead,guests_json=json.dumps([t.model_dump() for t in source.guests]),advanced=bool(ids))
    row.planning_json=json.dumps(dict(schedule=source.schedule.model_dump(mode='json',exclude_none=True) if source.schedule else {},locations=source.locations))
    db.add(row);db.flush()
    for term,(ids,lead) in zip(source.terms,resolved):
        overrides=term.overrides.model_dump(mode='json',exclude_none=True)
        if term.overrides.registration_until:overrides['registration_until']=naive(term.overrides.registration_until).isoformat()
        db.add(SeminarSession(seminar_id=row.id,title=term.title,starts_at=naive(term.starts_at),ends_at=naive(term.ends_at),
            location=term.location,delivery_mode=term.delivery_mode,online_capacity=term.online_capacity,
            published=False,cancelled=term.cancelled,reason=term.reason,lecturers_json=json.dumps(ids),lead_id=lead,
            guests_json=json.dumps([t.model_dump() for t in term.guests]),lecturer_description=term.lecturer_description,
            show_contact=term.show_contact,participants_visible=term.participants_visible,overrides_json=json.dumps(overrides)))
    sm.event(db,row,'json_import',user,f'{len(source.terms)} Termine als Entwurf importiert.')
    db.flush();return row


def naive(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value else None
