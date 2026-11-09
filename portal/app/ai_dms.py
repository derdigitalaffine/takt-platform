"""Read-only, explicitly approved DMS source adapter for TAKT AI.

Safety boundaries:
- Only *manual* records without applicant/person/booking/case links qualify.
- An admin explicitly approves each record for AI-use.
- Only its title + manually written note are consulted; never attachments,
  indexed form answers, archived cases or other citizen information.
- Before every retrieval and again on history/export, recompute the user's
  current inherited DMS-area read permissions. An index is never an ACL.
"""
from sqlalchemy import select, or_

from . import dms
from .ai_models import AIDmsSource
from .db import DmsRecord, get_settings
from .ai_knowledge import terms, _score, revision
from . import ai_source_policy


def dms_revision(record: DmsRecord) -> str:
    """Pin the precise manual DMS note, title and area as source provenance."""
    return revision(record.id, record.area_id, record.title, record.note,
                    record.kind, record.archived_at)


def eligible(record: DmsRecord | None) -> bool:
    return bool(
        record is not None
        and record.kind == "manuell"
        and record.response_id is None
        and record.person_id is None
        and record.booking_id is None
        and not record.applicant
        and not record.applicant_email
        and record.archived_at is None
        and (record.note or "").strip()
    )


def available(db, user) -> bool:
    cfg = get_settings(db)
    return bool(
        cfg.get("module_ai") == "1"
        and cfg.get("ai_knowledge_enabled") == "1"
        and dms.enabled(db)
        and user.can("ai_knowledge")
    )


def authorized(db, user, record_id: int) -> bool:
    """Fail closed on any revocation, deletion, archive, move or module switch."""
    if not available(db, user):
        return False
    record = db.get(DmsRecord, record_id)
    if not ai_source_policy.dms_included(db, record):
        return False
    return dms.levels(db, user).get(record.area_id, 0) >= dms.READ


def retrieve(db, user, question: str, limit: int = 2) -> list[dict]:
    if not available(db, user):
        return []
    words = terms(question)
    if not words:
        return []
    permitted = dms.levels(db, user)
    if not permitted:
        return []
    readable_areas = [area_id for area_id, level in permitted.items() if level >= dms.READ]
    if not readable_areas:
        return []
    query = select(DmsRecord).where(
        DmsRecord.area_id.in_(readable_areas),
        DmsRecord.kind == "manuell",
        DmsRecord.archived_at.is_(None),
        DmsRecord.response_id.is_(None),
        DmsRecord.person_id.is_(None),
        DmsRecord.booking_id.is_(None),
        DmsRecord.note != "",
        or_(DmsRecord.applicant.is_(None), DmsRecord.applicant == ""),
        or_(DmsRecord.applicant_email.is_(None), DmsRecord.applicant_email == ""),
        or_(*[
            or_(DmsRecord.title.ilike(f"%{word}%"),
                DmsRecord.note.ilike(f"%{word}%"))
            for word in words
        ]),
    )
    cfg = get_settings(db)
    if cfg.get("ai_dms_include_all") != "1":
        query = query.join(AIDmsSource, AIDmsSource.record_id == DmsRecord.id)
    rows = db.scalars(query.order_by(DmsRecord.id.desc()).limit(1500))
    found = []
    for record in rows:
        if not ai_source_policy.dms_included(db, record, cfg=cfg):
            continue
        score = _score(record.title or "", record.note or "", words)
        if score:
            found.append((score, record))
    found.sort(key=lambda pair: pair[0], reverse=True)
    out = []
    for _score_value, record in found[:max(0, min(limit, 3))]:
        # Re-validate the source against the current permissions before use.
        if not authorized(db, user, record.id):
            continue
        out.append({"title": record.title[:200],
                    "url": f"/dms/r/{record.id}",
                    "text": (record.note or "")[:1800],
                    "kind": "dms", "revision": dms_revision(record)})
    return out
