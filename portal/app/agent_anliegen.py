"""Administrative Anliegen routing proposals, using existing category services."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select
from . import anliegen as service
from .anliegen_models import Anliegen, AnliegenCategory
from .db import User


def version(cat):
    return [cat.title, cat.description, cat.tags, cat.routing, cat.assignee_id, cat.enabled]


def affected(db, cat):
    rows = list(db.execute(select(Anliegen.id, Anliegen.updated_at, Anliegen.assignee_id, Anliegen.status).where(
        Anliegen.category_id == cat.id, Anliegen.confidential.is_(False),
        Anliegen.status.not_in(("done", "closed", "cancelled"))).order_by(Anliegen.id)))
    value = [(r.id, r.updated_at.isoformat(), r.assignee_id, r.status) for r in rows]
    return dict(count=len(rows), fingerprint=hashlib.sha256(json.dumps(value).encode()).hexdigest())


def validate(db, user, action):
    if not user.is_admin:
        raise HTTPException(403, "Nur Administratoren dürfen Anliegen-Routing ändern.")
    cat = db.get(AnliegenCategory, action["id"])
    if not cat or cat.confidential:
        raise HTTPException(403, "Geschützte Kategorien werden ausschließlich manuell verwaltet.")
    person = db.get(User, action["assignee_id"]) if action.get("assignee_id") else None
    if action.get("assignee_id") and (not person or not person.active):
        raise HTTPException(422, "Die Zielperson ist nicht aktiv.")
    return cat


def normalize(db, user, raw, findings):
    tid = raw.get("id")
    if type(tid) is not int or not any(r.get("type") == "anliegen_category" and r["id"] == tid for r in findings):
        raise ValueError("Die Kategorie wurde nicht eindeutig gefunden.")
    title, routing = raw.get("title"), raw.get("routing")
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 120 or routing not in ("lead", "person"):
        raise ValueError("Kategorietitel und Routing prüfen.")
    uid = raw.get("assignee_id") if routing == "person" else None
    # Zero means explicitly unassigned, matching the category settings form.
    if uid == 0:
        uid = None
    if uid is not None and (type(uid) is not int or not any(r.get("type") == "person" and r["id"] == uid for r in findings)):
        raise ValueError("Die verantwortliche Person wurde nicht gefunden.")
    if type(raw.get("enabled")) is not bool or type(raw.get("apply_open", False)) is not bool:
        raise ValueError("Aktivierung und Übernahme auf offene Vorgänge ausdrücklich angeben.")
    action = dict(tool="configure_anliegen_category", id=tid, title=title.strip(), routing=routing,
                  assignee_id=uid, enabled=raw["enabled"], apply_open=raw.get("apply_open", False))
    cat = validate(db, user, action)
    action["version"] = version(cat)
    action["affected"] = affected(db, cat)
    return action


def preview(db, action):
    cat = db.get(AnliegenCategory, action["id"])
    person = db.get(User, action["assignee_id"]) if action.get("assignee_id") else None
    target = "Leitung der primären Organisation" if action["routing"] == "lead" else person.name if person else "Noch keine Person"
    return (f"Anliegen-Kategorie „{cat.title}“ konfigurieren: {action['title']}\n"
            f"Aktiv: {'Ja' if action['enabled'] else 'Nein'} · Routing: {target}\n"
            "Unzugewiesene Anliegen werden gemäß Fachregel neu geprüft.\n"
            f"Bestehende aktive Zuständigkeiten übernehmen: {'Ja' if action['apply_open'] else 'Nein'}. "
            f"Aktive Anliegen dieser Kategorie: {action['affected']['count']}; je Routing-Fachlauf höchstens 300.")


def execute(db, user, action):
    cat = validate(db, user, action)
    if version(cat) != action["version"] or affected(db, cat) != action["affected"]:
        raise HTTPException(409, "Kategorie oder betroffene Anliegen haben sich geändert. Bitte neu planen.")
    label = preview(db, action)
    cat.title = action["title"]
    cat.routing = action["routing"]
    cat.assignee_id = action["assignee_id"]
    cat.enabled = action["enabled"]
    db.flush()
    service.reroute_unassigned(db, cat, user)
    if action["apply_open"]:
        service.reassign_open(db, cat, user)
    return dict(label=label, url="/anliegen/kategorien", target_id=cat.id)
