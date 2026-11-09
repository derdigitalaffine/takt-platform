"""Administration-controlled AI source collections with live, fail-closed exceptions.

The 'all' rules are dynamic: newly published law texts and newly eligible
manual DMS notes are included without copying their content into another
table. Every access checks the original document state and DMS user ACLs.
"""
import json

from .ai_models import AILawSource, AIDmsSource
from .db import DmsArea, get_settings

MAX_EXCEPTIONS = 10000


def read_ids(raw: str | None) -> set[int] | None:
    """Return None when a rule is malformed; never silently grant bulk access."""
    try:
        values = json.loads(raw or "[]")
        if not isinstance(values, list) or len(values) > MAX_EXCEPTIONS:
            return None
        if any(type(value) is not int or value <= 0 for value in values):
            return None
        return set(values)
    except (ValueError, TypeError, OverflowError):
        return None


def encoded_ids(ids: set[int]) -> str:
    if len(ids) > MAX_EXCEPTIONS or any(type(value) is not int or value <= 0 for value in ids):
        raise ValueError("Ungültige Ausnahmeliste")
    return json.dumps(sorted(ids), separators=(",", ":"))


def law_included(db, law, *, cfg=None) -> bool:
    if law is None or not law.published:
        return False
    cfg = cfg if cfg is not None else get_settings(db)
    if cfg.get("ai_laws_include_all") == "1":
        excluded = read_ids(cfg.get("ai_laws_excluded_ids"))
        return excluded is not None and law.id not in excluded
    return db.get(AILawSource, law.id) is not None


def area_excluded(db, area_id: int, excluded: set[int]) -> bool:
    """Area exceptions cover all descendants and cannot be bypassed by moving."""
    visited = set()
    while area_id and area_id not in visited and len(visited) < 64:
        if area_id in excluded:
            return True
        visited.add(area_id)
        area = db.get(DmsArea, area_id)
        if area is None:
            return True  # Unknown area: fail closed.
        area_id = area.parent_id
    return bool(area_id)  # Cyclic or unresolvable hierarchy: fail closed.


def dms_included(db, record, *, cfg=None) -> bool:
    from . import ai_dms
    if not ai_dms.eligible(record):
        return False
    cfg = cfg if cfg is not None else get_settings(db)
    if cfg.get("ai_dms_include_all") == "1":
        excluded = read_ids(cfg.get("ai_dms_excluded_ids"))
        blocked_areas = read_ids(cfg.get("ai_dms_excluded_areas"))
        return (excluded is not None and blocked_areas is not None
                and record.id not in excluded
                and not area_excluded(db, record.area_id, blocked_areas))
    return db.get(AIDmsSource, record.id) is not None
