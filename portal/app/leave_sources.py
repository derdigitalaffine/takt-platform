"""Read-only staffing projections of existing Fachmodule; no secondary records.

The authoritative sources remain Absence/Vertretung, Krankmelder and seminars.
Only explicitly linked user identities are mapped; name/e-mail guesses are forbidden.
No medical report contents or proof information are returned from these helpers.
"""
from datetime import date, timedelta
from sqlalchemy import select
from .db import KrankReport, Seminar, SeminarEnrollment, get_settings, to_local


def illness_periods(db, person_ids=None):
    """Nonmedical availability intervals from the existing linked Krankmelder."""
    from . import krank

    ids = set(person_ids) if person_ids is not None else None
    q = select(KrankReport).where(KrankReport.user_id.is_not(None))
    if ids is not None:
        if not ids:
            return []
        q = q.where(KrankReport.user_id.in_(ids))
    result = []
    for report in db.scalars(q):
        details = krank.data(report)
        first = details.get("date") if report.kind == "simple" else details.get("from")
        last = details.get("date") if report.kind == "simple" else details.get("to")
        try:
            start = date.fromisoformat(first)
            finish = date.fromisoformat(last)
        except (ValueError, TypeError):
            continue
        if start > finish:
            continue
        result.append(dict(
            kind="illness", id=f"krank:{report.id}", person_id=report.user_id,
            starts_on=start.isoformat(), ends_on=finish.isoformat(),
            start_half="am", end_half="pm",
            title="Kindkrank" if report.kind == "child" else "Krank",
        ))
    return result


def seminar_periods(db, person_ids=None):
    """Exact sessions of confirmed seminar participations from the seminar module.

    Session ownership is checked through SeminarEnrollment.user_id and the
    canonical enrollment_sessions policy; no invitation or waitlist projects
    an absence.
    """
    from . import seminars

    if get_settings(db).get("module_seminars", "1") != "1":
        return []
    ids = set(person_ids) if person_ids is not None else None
    q = select(SeminarEnrollment).where(
        SeminarEnrollment.user_id.is_not(None),
        SeminarEnrollment.status.in_(("confirmed", "attended")),
    )
    if ids is not None:
        if not ids:
            return []
        q = q.where(SeminarEnrollment.user_id.in_(ids))
    result = []
    visited = set()
    for enrollment in db.scalars(q):
        event = db.get(Seminar, enrollment.seminar_id)
        if not event or event.status == "cancelled":
            continue
        for session in seminars.enrollment_sessions(db, event, enrollment):
            if session.cancelled or not session.published:
                continue
            key = (enrollment.user_id, session.id)
            if key in visited:
                continue
            visited.add(key)
            start = to_local(session.starts_at)
            end = to_local(session.ends_at)
            if end <= start:
                continue
            inclusive_end = end - timedelta(microseconds=1)
            result.append(dict(
                kind="seminar", id=f"seminar:{session.id}:{enrollment.user_id}",
                person_id=enrollment.user_id,
                starts_on=start.date().isoformat(),
                ends_on=inclusive_end.date().isoformat(),
                start_half="pm" if start.hour >= 12 else "am",
                end_half="am" if inclusive_end.hour < 12 else "pm",
                title="Seminar / Tagung",
            ))
    return result


def staffing_periods(db, person_ids=None):
    """Staffing availability only; status/reasons never enter its result."""
    return illness_periods(db, person_ids) + seminar_periods(db, person_ids)
