"""Explicit admin correction; remove active intervals while retaining audit evidence."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select
from . import leave, organization as org
from .db import Absence, utcnow
from .leave_models import LeaveRequest, LeaveAbsencePeriod, LeaveAdminRemoval


def removed_ids():
    return select(LeaveAdminRemoval.request_id).where(LeaveAdminRemoval.request_id.is_not(None))


def require_admin(actor):
    if not actor.active or not actor.is_admin:
        raise HTTPException(403, "Nur Administratoren dürfen eingetragene Urlaubsabwesenheiten löschen.")


def absence_version(row):
    values = [row.id, row.user_id, row.starts_on, row.ends_on, row.status, row.substitute_id,
              row.note, row.auto_reply, row.decided_at.isoformat() if row.decided_at else None,
              row.created_by, row.created_at.isoformat() if row.created_at else None]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def item(db, actor, kind, rid):
    require_admin(actor)
    if kind == "leave":
        row = db.get(LeaveRequest, rid)
        if row is None or db.scalar(select(LeaveAdminRemoval.id).where(LeaveAdminRemoval.request_id == rid)):
            raise HTTPException(404, "Urlaubseintrag nicht gefunden oder bereits gelöscht.")
        return row
    row = db.get(Absence, rid)
    if not row:
        raise HTTPException(404, "Abwesenheit nicht gefunden.")
    if db.scalar(select(LeaveRequest.id).where(LeaveRequest.absence_id == rid)) is not None:
        raise HTTPException(409, "Diese Abwesenheit gehört zu einem Urlaub. Bitte den Urlaubseintrag löschen.")
    if db.get(LeaveAbsencePeriod, rid):
        raise HTTPException(409, "Verknüpfte Urlaubsabwesenheit bitte über ihren Urlaubsvorgang prüfen.")
    return row


def remove(db, actor, kind, rid, version, reason):
    require_admin(actor)
    if not isinstance(reason, str) or not 5 <= len(reason.strip()) <= 2000:
        raise HTTPException(422, "Bitte die Löschung mit 5 bis 2.000 Zeichen begründen.")
    leave.lock(db)
    row = item(db, actor, kind, rid)
    current = str(row.version) if kind == "leave" else absence_version(row)
    if current != str(version):
        raise HTTPException(409, "Der Eintrag wurde inzwischen geändert. Bitte erneut prüfen.")
    uid = row.person_id if kind == "leave" else row.user_id
    snapshot = dict(kind=kind, id=rid, person_id=uid, starts_on=row.starts_on, ends_on=row.ends_on, status=row.status)
    aid = row.absence_id if kind == "leave" else row.id
    if kind == "leave":
        snapshot.update(effective_json=row.effective_json, version=row.version, org_id=row.org_id,
                        start_half=row.start_half, end_half=row.end_half)
        row.status = "cancelled"
        row.cancel_requested = False
        row.effective_json = ""
        row.absence_id = None
        row.version += 1
        row.updated_at = utcnow()
        leave.audit(db, actor, row, "admin_delete", reason.strip())
        db.flush()
        if aid:
            period = db.get(LeaveAbsencePeriod, aid)
            if period:
                db.delete(period)
                db.flush()
            absence = db.get(Absence, aid)
            if absence:
                # The unique LeaveRequest link owns this mirror; no unrelated manual absence is touched.
                if absence.user_id != uid:
                    raise HTTPException(409, "Die verknüpfte Abwesenheit gehört zu einer anderen Person.")
                db.delete(absence)
    else:
        snapshot["substitute_id"] = row.substitute_id
        db.delete(row)
    db.add(LeaveAdminRemoval(request_id=rid if kind == "leave" else None,
                            absence_id=aid, person_id=uid, actor_id=actor.id,
                            reason=reason.strip(), snapshot_json=json.dumps(snapshot, ensure_ascii=False)))
    if kind == "leave":
        from .leave_rules import notify_request
        notify_request(db, row, actor, "Urlaubsabwesenheit administrativ gelöscht", set(org.active_path(db, row.org_id)))
    db.flush()
    return uid
