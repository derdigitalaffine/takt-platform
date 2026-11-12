"""Live source references for TAKT Wissen, stored as ordinary Markdown links."""
from dataclasses import dataclass
from hashlib import sha256
import re
from urllib.parse import quote

from fastapi import HTTPException

from . import knowledge as km
from .db import Circulation, DmsRecord, LawText, Process, get_settings


@dataclass(frozen=True)
class SourceType:
    model: type
    module: str
    label: str


TYPES = {
    "rechtstext": SourceType(LawText, "laws", "Rechtstext"),
    "umlauf": SourceType(Circulation, "circulations", "Umlauf"),
    "ablage": SourceType(DmsRecord, "dms", "Ablageeintrag"),
    "prozess": SourceType(Process, "applications", "Bearbeitungsprozess"),
}
REFERENCE = re.compile(r"/wissen/quelle/([a-z]+)/([1-9][0-9]{0,9})/([0-9a-f]{24})")


@dataclass(frozen=True)
class Source:
    label: str
    url: str


def _reference(kind, row):
    # A new row must not inherit links to a deleted row with the same numeric ID.
    identity = f"{kind}:{row.id}:{row.created_at.isoformat()}"
    fingerprint = sha256(identity.encode()).hexdigest()[:24]
    return f"/wissen/quelle/{kind}/{row.id}/{fingerprint}"


def _resolve(db, user, kind, row):
    settings = get_settings(db)
    if settings.get(f"module_{TYPES[kind].module}", "1") != "1":
        return None
    if kind == "rechtstext":
        if row.published or user.can("laws"):
            return Source(row.title, "/recht/" + quote(row.slug, safe=""))
    elif kind == "umlauf":
        from . import circulations
        version = circulations.version(db, row)
        if version and circulations.readable(db, row, version, user):
            return Source(circulations.content(version)["title"], f"/umlaeufe/{row.id}")
    elif kind == "ablage":
        from .routes_dms import _record
        try:
            _record(db, user, row.id)
        except HTTPException as exc:
            if exc.status_code not in {403, 404}:
                raise
        else:
            return Source("Ablageeintrag öffnen", f"/dms/r/{row.id}")
    elif kind == "prozess":
        if settings.get("module_forms", "1") == "1" and user.can("processes"):
            return Source(row.name, f"/processes/{row.id}")
    return None


def resolve_reference(db, user, path):
    match = REFERENCE.fullmatch(path)
    if not match:
        return None
    kind, row_id, _ = match.groups()
    source_type = TYPES.get(kind)
    if source_type is None or int(row_id) > 2_147_483_647:
        return None
    row = db.get(source_type.model, int(row_id))
    if row is None or _reference(kind, row) != path:
        return None
    return _resolve(db, user, kind, row)


def contextual_link(db, user, kind, row):
    if not user or not user.can("knowledge_read") or not km.active(db):
        return None
    if not _resolve(db, user, kind, row):
        return None
    return _reference(kind, row) + "/wissen"


def references_in(tokens):
    for token in tokens:
        for child in token.children or ():
            if child.type == "link_open" and REFERENCE.fullmatch(child.attrGet("href") or ""):
                yield child.attrGet("href")
