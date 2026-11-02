"""Explicit lifecycle operations for individual seminar terms.

Keep term-state changes in one place so the compact planner and the advanced
seminar UI can share the same safety rules, notifications and audit events.
"""
from fastapi import HTTPException
from sqlalchemy import select

from . import seminars as sm, seminar_series as series
from .db import (
    Meeting, SeminarActivity, SeminarAttendance, SeminarEnrollment,
    SeminarLecturerAccess, SeminarMaterial, SeminarSession, utcnow,
)

ACTIVE_RECORDS = {'confirmed', 'offered', 'waitlist', 'pending', 'invited', 'form', 'unverified'}


def _records(db, row, term, active_only=True):
    q = select(SeminarEnrollment).where(
        SeminarEnrollment.seminar_id == row.id,
        SeminarEnrollment.scope_id.in_([0, term.id]),
    )
    if active_only:
        q = q.where(SeminarEnrollment.status.in_(ACTIVE_RECORDS))
    return list(db.scalars(q))


def _delete_references(db, term):
    """Return human-readable references which make hard deletion unsafe."""
    refs = []
    if db.scalar(select(SeminarEnrollment.id).where(SeminarEnrollment.scope_id == term.id)):
        refs.append('Teilnahmen')
    if db.scalar(select(SeminarAttendance.id).where(SeminarAttendance.session_id == term.id)):
        refs.append('Anwesenheiten')
    if db.scalar(select(SeminarMaterial.id).where(SeminarMaterial.scope_id == term.id)):
        refs.append('Unterlagen')
    if db.scalar(select(SeminarActivity.id).where(SeminarActivity.scope_id == term.id)):
        refs.append('Aktivitäten')
    if db.scalar(select(SeminarLecturerAccess.id).where(SeminarLecturerAccess.term_id == term.id)):
        refs.append('Dozentenzugänge')
    return refs


def publish(db, row, term, user=None):
    if row.status != 'published':
        raise HTTPException(409, 'Die Seminarreihe muss zuerst veröffentlicht werden.')
    if term.cancelled:
        raise HTTPException(409, 'Abgesagten Termin nicht veröffentlichen.')
    if term.published:
        return False
    term.published = True
    term.published_at = term.published_at or utcnow()
    term.revision += 1
    series.announce(db, row, 'new_terms', f'{term.title or "Termin"} · {sm.local_input(term.starts_at).replace("T", " ")}\nJetzt buchbar.')
    sm.event(db, row, 'session_published', user, str(term.id))
    return True


def unpublish(db, row, term, user=None):
    if row.status != 'published' or not term.published:
        raise HTTPException(409, 'Der Termin ist nicht veröffentlicht.')
    if term.cancelled:
        raise HTTPException(409, 'Abgesagte Termine können nicht zurückgezogen werden.')
    if _records(db, row, term):
        raise HTTPException(409, 'Für diesen Termin bestehen bereits Einladungen oder Anmeldungen. Bitte verschieben oder absagen.')
    term.published = False
    # published_at bleibt absichtlich erhalten: der Termin war bereits öffentlich.
    term.revision += 1
    series.announce(db, row, 'changes', f'Termin zurückgezogen: {term.title or row.title} · {sm.local_input(term.starts_at).replace("T", " ")}')
    sm.event(db, row, 'session_unpublished', user, str(term.id))
    return True


def cancel(db, row, term, reason, user=None):
    reason = str(reason or '').strip()[:500]
    if not reason:
        raise HTTPException(422, 'Bitte einen Absagegrund angeben.')
    if row.status != 'published' or not term.published:
        raise HTTPException(409, 'Unveröffentlichten Termin bitte löschen oder unveröffentlicht lassen.')
    if term.cancelled:
        raise HTTPException(409, 'Der Termin ist bereits abgesagt.')
    term.cancelled = True
    term.reason = reason
    term.revision += 1
    for rec in _records(db, row, term):
        sm.mail(db, row, rec, 'Termin abgesagt', reason, calendar_file=True)
    series.staff_message(db, row, 'Termin abgesagt', reason, [term])
    series.announce(db, row, 'changes', f'Termin abgesagt: {term.title or row.title} · {sm.local_input(term.starts_at).replace("T", " ")}\n{reason}')
    sm.event(db, row, 'session_cancelled', user, f'{term.id}: {reason}')
    return True


def delete_draft(db, row, term, user=None):
    if term.published_at is not None:
        raise HTTPException(409, 'Ein bereits veröffentlichter Termin bleibt aus Nachweisgründen erhalten. Bitte Veröffentlichung zurücknehmen oder absagen.')
    refs = _delete_references(db, term)
    if refs:
        raise HTTPException(409, 'Termin kann nicht gelöscht werden, weil bereits Daten zugeordnet sind: ' + ', '.join(refs) + '.')
    meeting = db.get(Meeting, term.meeting_id) if term.meeting_id else None
    meeting_id = meeting.id if meeting else None
    term_id = term.id
    db.delete(term)
    db.flush()
    if meeting_id and not db.scalar(select(SeminarSession.id).where(SeminarSession.meeting_id == meeting_id)):
        db.delete(meeting)
    sm.event(db, row, 'session_deleted', user, str(term_id))
    return True


def notify_changed(db, row, terms, message='Bitte beachten Sie den aktualisierten Termin und Ihre Kalenderdatei.'):
    """Notify participant and staff audiences affected by explicit term changes."""
    terms = list(dict.fromkeys(terms))
    if not terms or row.status != 'published':
        return
    ids = {term.id for term in terms}
    records = db.scalars(select(SeminarEnrollment).where(
        SeminarEnrollment.seminar_id == row.id,
        SeminarEnrollment.status.in_(ACTIVE_RECORDS),
    ))
    for rec in records:
        if not rec.scope_id or rec.scope_id in ids:
            sm.mail(db, row, rec, 'Termin geändert', message, calendar_file=True)
    series.staff_message(db, row, 'Termin geändert', message, terms)
    series.announce(db, row, 'changes', 'Terminänderung: ' + ', '.join(
        (term.title or row.title) + ' · ' + sm.local_input(term.starts_at).replace('T', ' ') for term in terms
    ))
