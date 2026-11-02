"""Explicit lifecycle operations for individual seminar terms.

Keep term-state changes in one place so the compact planner and the advanced
seminar UI can share the same safety rules, notifications and audit events.
"""
import json

from fastapi import HTTPException
from sqlalchemy import delete as sql_delete, select

from . import seminars as sm, seminar_series as series
from .db import (
    Meeting, Recording, SeminarActivity, SeminarAttendance, SeminarCertificate,
    SeminarEnrollment, SeminarLecturerAccess, SeminarMaterial, SeminarSession,
    utcnow,
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
    """Return human-readable references which make implicit draft deletion unsafe."""
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
        raise HTTPException(409, 'Abgesagten Termin bitte zuerst reaktivieren.')
    if term.published:
        return False
    term.published = True
    term.published_at = term.published_at or utcnow()
    term.revision += 1
    from . import seminar_fixed
    seminar_fixed.enroll_published(db, row, [term], user)
    series.announce(db, row, 'new_terms', f'{term.title or "Termin"} · {sm.local_input(term.starts_at).replace("T", " ")}\nJetzt buchbar.')
    sm.event(db, row, 'session_published', user, str(term.id))
    return True


def unpublish(db, row, term, user=None):
    if row.status != 'published' or not term.published:
        raise HTTPException(409, 'Der Termin ist nicht veröffentlicht.')
    if term.cancelled:
        raise HTTPException(409, 'Abgesagte Termine bitte zuerst reaktivieren.')
    if _records(db, row, term):
        raise HTTPException(409, 'Für diesen Termin bestehen bereits Einladungen oder Anmeldungen. Bitte verschieben, absagen oder endgültig löschen.')
    term.published_at = term.published_at or utcnow()
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
    term.published_at = term.published_at or utcnow()
    term.cancelled = True
    term.reason = reason
    term.revision += 1
    for rec in _records(db, row, term):
        sm.mail(db, row, rec, 'Termin abgesagt', reason, calendar_file=True)
    series.staff_message(db, row, 'Termin abgesagt', reason, [term])
    series.announce(db, row, 'changes', f'Termin abgesagt: {term.title or row.title} · {sm.local_input(term.starts_at).replace("T", " ")}\n{reason}')
    sm.event(db, row, 'session_cancelled', user, f'{term.id}: {reason}')
    return True


def reactivate(db, row, term, user=None):
    if row.status != 'published' or not term.published:
        raise HTTPException(409, 'Nur veröffentlichte Termine können reaktiviert werden.')
    if not term.cancelled:
        raise HTTPException(409, 'Der Termin ist nicht abgesagt.')
    term.cancelled = False
    term.reason = ''
    term.revision += 1
    message = 'Der zuvor abgesagte Termin findet wieder statt. Bitte beachten Sie die aktualisierte Kalenderdatei.'
    for rec in _records(db, row, term):
        sm.mail(db, row, rec, 'Termin reaktiviert', message, calendar_file=True)
    series.staff_message(db, row, 'Termin reaktiviert', message, [term])
    series.announce(db, row, 'changes', f'Termin reaktiviert: {term.title or row.title} · {sm.local_input(term.starts_at).replace("T", " ")}')
    sm.event(db, row, 'session_reactivated', user, str(term.id))
    return True


def delete_term(db, row, term, user=None):
    """Delete a term for real, including data that is scoped exclusively to it.

    A published active term first emits a cancellation calendar update. Series-wide
    enrollments remain intact; only enrollments explicitly scoped to this term are
    removed. Audit events stay on the seminar so the administrative action remains
    traceable even though the term itself is gone.
    """
    term_id = term.id
    meeting = db.get(Meeting, term.meeting_id) if term.meeting_id else None
    meeting_id = meeting.id if meeting else None
    label = f'{term.title or row.title} · {sm.local_input(term.starts_at).replace("T", " ")}'

    if row.status == 'published' and term.published and not term.cancelled:
        # Build cancellation attachments while the term still exists. The queued
        # attachment then removes the old calendar entry even though the DB row is
        # physically deleted immediately afterwards.
        term.cancelled = True
        term.reason = 'Termin gelöscht'
        term.revision += 1
        db.flush()
        message = 'Dieser Termin wurde aus der Seminarreihe gelöscht.'
        for rec in _records(db, row, term):
            sm.mail(db, row, rec, 'Termin gelöscht', message, calendar_file=True)
        series.staff_message(db, row, 'Termin gelöscht', message, [term])
        series.announce(db, row, 'changes', f'Termin gelöscht: {label}')

    # Whole-series enrollments remain, but per-term participation choices must not
    # keep stale IDs after the term disappears.
    key = str(term_id)
    for rec in db.scalars(select(SeminarEnrollment).where(
        SeminarEnrollment.seminar_id == row.id,
        SeminarEnrollment.scope_id != term_id,
    )):
        try:
            modes = json.loads(rec.modes_json or '{}')
        except ValueError:
            modes = {}
        if key in modes:
            modes.pop(key, None)
            rec.modes_json = json.dumps(modes)

    # scope_id fields are intentionally not foreign keys, so these rows must be
    # cleaned explicitly before the session itself is removed.
    db.execute(sql_delete(SeminarAttendance).where(SeminarAttendance.session_id == term_id))
    db.execute(sql_delete(SeminarCertificate).where(SeminarCertificate.scope_id == term_id))
    db.execute(sql_delete(SeminarMaterial).where(SeminarMaterial.scope_id == term_id))
    db.execute(sql_delete(SeminarActivity).where(SeminarActivity.scope_id == term_id))
    db.execute(sql_delete(SeminarLecturerAccess).where(SeminarLecturerAccess.term_id == term_id))
    db.execute(sql_delete(SeminarEnrollment).where(
        SeminarEnrollment.seminar_id == row.id,
        SeminarEnrollment.scope_id == term_id,
    ))
    db.delete(term)
    db.flush()

    # Term-specific video rooms without recordings are disposable. Shared rooms or
    # rooms with recordings stay available because they carry independent history.
    if meeting_id and not db.scalar(select(SeminarSession.id).where(SeminarSession.meeting_id == meeting_id)):
        if not db.scalar(select(Recording.id).where(Recording.meeting_id == meeting_id)):
            db.delete(meeting)

    sm.event(db, row, 'session_deleted', user, str(term_id))
    return True


def delete_draft(db, row, term, user=None):
    """Implicit planner removal stays conservative; explicit delete_term is not."""
    if (row.status == 'published' and term.published) or term.published_at is not None:
        raise HTTPException(409, 'Veröffentlichte Termine bitte über „Termin löschen“ ausdrücklich löschen.')
    refs = _delete_references(db, term)
    if refs:
        raise HTTPException(409, 'Termin kann nicht stillschweigend entfernt werden, weil bereits Daten zugeordnet sind: ' + ', '.join(refs) + '. Bitte „Termin löschen“ verwenden.')
    return delete_term(db, row, term, user)


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
