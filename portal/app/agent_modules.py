"""Explicit module adapters. No arbitrary routes, code, publication or deletion.

DMS deliberately uses the newer opt-in AI source policy, not general fulltext.
Only metadata reaches the planner; form answers and process definitions do not.
"""
from itertools import islice

from fastapi import HTTPException
from sqlalchemy import select, or_

from . import ai_dms, calendars, dms, forms as fm, agent_anliegen
from .ai_models import AIDmsSource
from .calendar_models import Calendar, CalendarEvent
from .anliegen_models import AnliegenCategory
from .db import DmsArea, DmsRecord, Form, Process, get_settings

READ = {
    "search_surveys": "surveys",
    "search_anliegen_categories": "anliegen",
    "search_calendars": "calendars", "search_events": "calendars",
    "search_forms": "forms", "search_processes": "processes",
    "search_dms": "dms", "search_dms_areas": "dms",
    "search_my_leave": "leave", "search_leave_requests": "leave",
}
WRITE = {
    "create_survey": "surveys", "survey_state": "surveys", "finalize_poll": "surveys",
    "set_krank_status": "krank", "add_krank_note": "krank", "send_krank_message": "krank",
    "create_leave": "leave", "edit_leave": "leave", "leave_command": "leave",
    "create_form": "forms",
    "configure_anliegen_category": "anliegen",
    "update_event": "calendars", "delete_event": "calendars", "create_event": "calendars", "copy_form": "forms", "move_dms": "dms",
}
LABELS = {
    "search_surveys": "Umfragen und Abstimmungen",
    "search_anliegen_categories": "Anliegen-Kategorien",
    "search_calendars": "Kalendern", "search_events": "Terminen",
    "search_forms": "Formularen", "search_processes": "Prozessen",
    "search_dms": "freigegebenen DMS-Wissensakten", "search_dms_areas": "DMS-Zielbereichen",
    "search_my_leave": "deinen eigenen Urlaubsanträgen", "search_leave_requests": "berechtigten Urlaubsanträgen",
}
KINDS = {"configure_anliegen_category": "anliegen_category", "create_event": "calendar", "copy_form": "form", "move_dms": "dms"}
MODELS = {"configure_anliegen_category": AnliegenCategory, "create_event": Calendar, "copy_form": Form, "move_dms": DmsRecord}


def enabled(user, module):
    from .main import enabled_modules
    mods = enabled_modules()
    if module == "processes":
        return "applications" in mods and user.can("processes")
    if module == "forms":
        return "forms" in mods and user.can("forms")
    if module == "calendars":
        return "calendars" in mods
    if module == "surveys":
        return "polls" in mods and user.active
    if module == "krank":
        return "krank" in mods and user.active
    if module == "leave":
        return "calendars" in mods and user.active
    if module == "dms":
        # Record ACLs and knowledge opt-in are checked with the live DB below.
        return "dms" in mods and user.can("ai_knowledge")
    return False


def search(db, user, spec):
    from .agent import _like, _term, require
    tool = spec["tool"]
    require(user, READ[tool])
    phrase = _term(spec.get("query"))
    pattern = _like(phrase)
    if tool == "search_surveys":
        from .agent_surveys import search as search_surveys
        return search_surveys(db,user,spec)
    if tool == "search_anliegen_categories":
        query = select(AnliegenCategory).where(AnliegenCategory.confidential.is_(False), or_(AnliegenCategory.title.ilike(pattern, escape="\\"), AnliegenCategory.key.ilike(pattern, escape="\\"),
                         AnliegenCategory.description.ilike(pattern, escape="\\"),
                         AnliegenCategory.tags.ilike(pattern, escape="\\")))
        if not user.is_admin:
            query = query.where(AnliegenCategory.enabled.is_(True))
        return [dict(type="anliegen_category", id=c.id, title=c.title, key=c.key, routing=c.routing,
                     assignee_id=c.assignee_id, enabled=c.enabled, description=c.description,
                     tags=[tag for tag in c.tags.split(',') if tag],
                     url="/anliegen/kategorien" if user.is_admin else "/anliegen/neu") for c in db.scalars(query.order_by(AnliegenCategory.position).limit(20))]
    if tool == "search_calendars":
        rows = db.scalars(select(Calendar).where(Calendar.title.ilike(pattern, escape="\\")).order_by(Calendar.id))
        return list(islice((dict(type="calendar", id=r.id, title=r.title, writable=calendars.access(db, user, r, True),
                     url="/kalender?ansicht=termine") for r in rows if calendars.access(db, user, r)), 20))
    if tool == "search_events":
        from .agent_events import search as search_events
        return search_events(db, user, spec)
    if tool == "search_forms":
        rows = db.scalars(select(Form).where(Form.deleted_at.is_(None), Form.archived_at.is_(None),
                          Form.title.ilike(pattern, escape="\\")).order_by(Form.id))
        return list(islice((dict(type="form", id=r.id, title=r.title, active=r.active, kind=r.kind,
                     url=f"/forms/{r.id}") for r in rows if fm.access_level(db, r, user) >= fm.VIEW), 20))
    if tool == "search_processes":
        # Process editor uses the global processes role; there is no owner-only ACL.
        rows = db.scalars(select(Process).where(Process.name.ilike(pattern, escape="\\")).order_by(Process.id).limit(20))
        return [dict(type="process", id=r.id, title=r.name, published=bool(r.current),
                     url=f"/processes/{r.id}") for r in rows]
    if tool in ("search_my_leave", "search_leave_requests"):
        from .agent_leave import search as leave_search
        return leave_search(db, user, spec)
    if not ai_dms.available(db, user):
        return []
    if tool == "search_dms_areas":
        levels = dms.levels(db, user)
        return [dict(type="dms_area", id=r.id, title=r.name) for r in dms.areas(db)
                if levels.get(r.id, 0) >= dms.WRITE and phrase.casefold() in r.name.casefold()][:20]
    if tool == "search_dms":
        query = select(DmsRecord).where(
            or_(DmsRecord.title.ilike(pattern, escape="\\"), DmsRecord.ref_no.ilike(pattern, escape="\\")))
        if get_settings(db).get("ai_dms_include_all") != "1":
            query = query.join(AIDmsSource)
        rows = db.scalars(query.order_by(DmsRecord.id))
        return list(islice((dict(type="dms", id=r.id, title=r.title[:200], area_id=r.area_id,
                     url=f"/dms/r/{r.id}") for r in rows if ai_dms.authorized(db, user, r.id)), 20))
    raise ValueError("Unbekanntes Suchwerkzeug")


def version(row):
    if isinstance(row, AnliegenCategory):
        return agent_anliegen.version(row)
    return row.version if isinstance(row, Calendar) else row.updated_at.isoformat()


def target(db, user, action):
    from .agent import require
    tool = action["tool"]
    require(user, WRITE[tool])
    if tool == "configure_anliegen_category":
        return agent_anliegen.validate(db, user, action)
    row = db.get(MODELS[tool], action["id"])
    if row is None:
        raise HTTPException(404, "Vorgang nicht gefunden.")
    if tool == "copy_form" and (row.deleted_at or row.archived_at or fm.access_level(db, row, user) < fm.VIEW):
        raise HTTPException(403)
    if tool == "move_dms":
        area = db.get(DmsArea, action["area_id"])
        levels = dms.levels(db, user)
        if (not ai_dms.authorized(db, user, row.id) or area is None
                or levels.get(row.area_id, 0) < dms.WRITE or levels.get(area.id, 0) < dms.WRITE):
            raise HTTPException(403)
    return row


def normalize(db, user, raw, findings):
    from . import agent_surveys
    if raw["tool"] in agent_surveys.TOOLS:
        return agent_surveys.normalize(db, user, raw, findings)
    from . import agent_events
    if raw["tool"] in agent_events.TOOLS:
        return agent_events.normalize(db, user, raw, findings)
    from . import agent_krank
    if raw["tool"] in agent_krank.TOOLS:
        return agent_krank.normalize(db, user, raw, findings)
    from . import agent_leave
    if raw["tool"] in agent_leave.TOOLS:
        return agent_leave.normalize(db, user, raw, findings)
    tool = raw["tool"]
    if tool == "create_form":
        from .agent_forms import normalize as normalize_form
        return normalize_form(user, raw)
    if tool == "configure_anliegen_category":
        from .agent import require
        require(user, "anliegen")
        return agent_anliegen.normalize(db, user, raw, findings)
    def found(key, kind):
        value = raw.get(key)
        if type(value) is not int or not any(r.get("type") == kind and r["id"] == value for r in findings):
            raise ValueError("Die Datensatz-ID ist nicht durch eine berechtigte Suche belegt.")
        return value
    action = dict(tool=tool, id=found("id", KINDS[tool]))
    if tool == "move_dms":
        action["area_id"] = found("area_id", "dms_area")
    row = target(db, user, action)
    action["version"] = version(row)
    if tool == "move_dms":
        # The destination name/position is part of the preview too.
        area = db.get(DmsArea, action["area_id"])
        action["area_snapshot"] = [area.name, area.parent_id]
    return action


def preview(db, action):
    from . import agent_surveys
    if action["tool"] in agent_surveys.TOOLS:
        return agent_surveys.preview(db, action)
    from . import agent_events
    if action["tool"] in agent_events.TOOLS:
        return agent_events.preview(db, action)
    from . import agent_krank
    if action["tool"] in agent_krank.TOOLS:
        return agent_krank.preview(db, action)
    from . import agent_leave
    if action["tool"] in agent_leave.TOOLS:
        return agent_leave.preview(db, action)
    if action["tool"] == "create_form":
        from .agent_forms import preview as preview_form
        return preview_form(action)
    if action["tool"] == "configure_anliegen_category":
        return agent_anliegen.preview(db, action)
    row = db.get(MODELS[action["tool"]], action["id"])
    if action["tool"] == "copy_form":
        return f"Formular „{row.title}“ als geschlossenen Entwurf kopieren. Keine Antworten, Einladungen oder öffentlichen Links."
    area = db.get(DmsArea, action["area_id"])
    return f"DMS-Akte #{row.id} „{row.title}“ von „{row.area.name}“ nach „{area.name}“ verschieben. Aufbewahrung nach Zielbereich."


def execute(db, user, action):
    from . import agent_surveys
    if action["tool"] in agent_surveys.TOOLS:
        return agent_surveys.execute(db, user, action)
    from . import agent_events
    if action["tool"] in agent_events.TOOLS:
        return agent_events.execute(db, user, action)
    from . import agent_krank
    if action["tool"] in agent_krank.TOOLS:
        return agent_krank.execute(db, user, action)
    from . import agent_leave
    if action["tool"] in agent_leave.TOOLS:
        return agent_leave.execute(db, user, action)
    if action["tool"] == "create_form":
        from .agent_forms import execute as create_form
        return create_form(db, user, action)
    if action["tool"] == "configure_anliegen_category":
        from .agent import require
        require(user, "anliegen")
        return agent_anliegen.execute(db, user, action)
    row = target(db, user, action)
    if version(row) != action["version"]:
        raise HTTPException(409, "Der Vorgang hat sich geändert. Bitte neu planen.")
    label = preview(db, action)
    if action["tool"] == "copy_form":
        clone = fm.copy_form(db, row, user)
        # Preserve the internal boundary even though the existing copy service defaults to public.
        clone.internal = row.internal
        db.flush()
        target_id = clone.id
        url = f"/forms/{clone.id}"
    else:
        area = db.get(DmsArea, action["area_id"])
        if [area.name, area.parent_id] != action["area_snapshot"]:
            raise HTTPException(409, "Der Zielbereich hat sich geändert. Bitte neu planen.")
        dms.move_record(db, row, area, user)
        target_id = row.id
        url = f"/dms/r/{row.id}"
    return dict(label=label, url=url, target_id=target_id)
