"""Native form drafts. The planner receives schema metadata, never submissions."""

import json
from itertools import islice

from fastapi import HTTPException
from sqlalchemy import exists, select, update

from . import form_ai, forms as fm
from .db import Form, FormBlock, FormResponse

TOOLS = {"create_form", "edit_form"}
CHOICES = fm.CHOICE_TYPES
LAYOUT_WITHOUT_TITLE = {"block", "divider", "pagebreak", "text"}


def require(user):
    from .agent import require as module_access

    module_access(user, "forms")


def version(row):
    return row.updated_at.isoformat()


def has_responses(form_id):
    return exists().where(FormResponse.form_id == form_id)


def editable(row, level, has_answers):
    return (
        level >= fm.EDIT
        and row.kind == "survey"
        and not row.active
        and not row.published_at
        and not row.public_token
        and not has_answers
    )


def search(db, user, phrase, pattern):
    query = select(Form, has_responses(Form.id)).where(
        Form.deleted_at.is_(None), Form.archived_at.is_(None)
    )
    if phrase.lstrip("#").isdigit():
        query = query.where(Form.id == int(phrase.lstrip("#")))
    elif phrase:
        query = query.where(Form.title.ilike(pattern, escape="\\"))

    def visible():
        for row, has_answers in db.execute(
            query.order_by(Form.updated_at.desc(), Form.id)
        ):
            level = fm.access_level(db, row, user)
            if level < fm.VIEW:
                continue
            writable = editable(row, level, has_answers)
            result = dict(
                type="form",
                id=row.id,
                title=row.title,
                active=row.active,
                kind=row.kind,
                editable=writable,
                url=(
                    f"/forms/{row.id}"
                    if level >= fm.EDIT
                    else f"/forms/{row.id}/preview"
                ),
            )
            if writable:
                result["questions"] = [
                    {"title": item["title"][:120], "type": item["type"]}
                    for item in fm.questions(fm.raw_schema(row))[:30]
                ]
            yield result

    return list(islice(visible(), 20))


def target(db, user, action):
    require(user)
    query = select(Form, has_responses(Form.id)).where(
        Form.id == action["id"], Form.deleted_at.is_(None), Form.archived_at.is_(None)
    )
    record = db.execute(query).first()
    if record is None:
        raise HTTPException(404, "Formular nicht gefunden.")
    row, has_answers = record
    level = fm.access_level(db, row, user)
    if level < fm.EDIT:
        raise HTTPException(403, "Die Bearbeitungsfreigabe für das Formular fehlt.")
    if not editable(row, level, has_answers):
        raise HTTPException(
            409,
            "Im Agenten können nur unveröffentlichte Formularentwürfe ohne Antworten bearbeitet werden.",
        )
    if action.get("version", version(row)) != version(row):
        raise HTTPException(409, "Das Formular hat sich geändert. Bitte neu planen.")
    return row


def metadata(title, description):
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 255:
        raise ValueError("Bitte einen Formulartitel mit 3 bis 255 Zeichen angeben.")
    if not isinstance(description, str) or len(description) > 5000:
        raise ValueError(
            "Die Formularbeschreibung darf höchstens 5.000 Zeichen enthalten."
        )
    return " ".join(title.split()), description.replace("\r\n", "\n").strip()


def model_fields(fields, baseline, mode):
    """Adapt concise planner JSON to the existing form assistant contract."""
    if not isinstance(fields, list) or not 1 <= len(fields) <= form_ai.MAX_NEW_ITEMS:
        raise ValueError(
            f"Der Vorschlag benötigt 1 bis {form_ai.MAX_NEW_ITEMS} konkrete Bausteine."
        )
    items = []
    for index, field in enumerate(fields, 1):
        if not isinstance(field, dict) or not isinstance(field.get("type"), str):
            raise ValueError("Jeder Baustein benötigt einen Formulartyp.")
        item = dict(field)
        item.setdefault("id", f"agent_{index}")
        if not isinstance(item["id"], str):
            raise ValueError("Die Bausteine benötigen gültige Kennungen.")
        if item["type"] == "number":
            item.update(type="short", subtype="number")
        elif item["type"] == "yesno":
            item.update(type="radio", options=["Ja", "Nein"])
        if type(item.get("required", False)) is not bool:
            raise ValueError(
                "Pflichtangaben müssen als true oder false angegeben werden."
            )
        items.append(item)
    return form_ai.parse_result(
        json.dumps({"items": items}, ensure_ascii=False), baseline, mode, set()
    )["items"]


def validated_schema(db, raw):
    if not isinstance(raw, list) or not 1 <= len(raw) <= 500:
        raise ValueError("Der Baukasten benötigt 1 bis 500 Bausteine.")
    ids = set()
    for item in raw:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("type"), str)
            or item["type"] not in fm.TYPES
        ):
            raise ValueError("Nicht unterstützter Formularbaustein.")
        qid = item.get("id")
        if not isinstance(qid, str) or not fm.ID_RE.fullmatch(qid) or qid in ids:
            raise ValueError("Die Bausteine benötigen eindeutige Kennungen.")
        ids.add(qid)
        if (
            item["type"] not in LAYOUT_WITHOUT_TITLE
            and not str(item.get("title") or "").strip()
        ):
            raise ValueError("Jede Frage und Überschrift benötigt eine Bezeichnung.")
        if item["type"] == "block":
            block_id = item.get("block_id")
            if type(block_id) is not int or db.get(FormBlock, block_id) is None:
                raise ValueError("Der ausgewählte Datenblock ist nicht verfügbar.")

    items = fm.clean_schema(raw)
    if not fm.questions(items) and not any(item["type"] == "block" for item in items):
        raise ValueError("Der Formularentwurf benötigt mindestens eine Frage.")
    if len(items) != len(raw) or fm.form_validation.schema_errors(items):
        raise ValueError("Bitte die Formularbausteine und Feldregeln prüfen.")
    for source, item in zip(raw, items):
        if item["type"] in CHOICES:
            options = item["options"]
            if len(options) < 2 or len({option["id"] for option in options}) != len(
                options
            ):
                raise ValueError(
                    f"„{item['title']}“ benötigt mindestens zwei eindeutige Antwortoptionen."
                )
        for key in ("show_if", "required_if"):
            if source.get(key) and source[key] != item.get(key):
                raise ValueError(
                    f"Die Bedingung für „{item['title']}“ verweist auf eine ungültige Frage."
                )
    return items


def normalize(user, raw, db=None, findings=()):
    require(user)
    tool = raw.get("tool", "create_form")
    action = dict(tool=tool)
    if tool == "edit_form":
        form_id = raw.get("id")
        if type(form_id) is not int or not any(
            item.get("type") == "form" and item["id"] == form_id for item in findings
        ):
            raise ValueError(
                "Das Formular wurde nicht durch eine berechtigte Suche gefunden."
            )
        row = target(db, user, {"id": form_id})
        action.update(id=row.id, version=version(row))
        baseline = fm.raw_schema(row)
        title, description = metadata(
            raw.get("title", row.title), raw.get("description", row.description or "")
        )
        additions = (
            model_fields(raw["fields"], baseline, "append") if "fields" in raw else []
        )
        if not additions and (title, description) == (row.title, row.description or ""):
            raise ValueError("Bitte die gewünschte Änderung am Formular angeben.")
    else:
        baseline = []
        title, description = metadata(raw.get("title"), raw.get("description", ""))
        additions = model_fields(raw.get("fields"), baseline, "replace")

    action.update(
        title=title,
        description=description,
        fields=validated_schema(db, baseline + additions),
    )
    return action


def validate(db, user, action):
    require(user)
    row = target(db, user, action) if action["tool"] == "edit_form" else None
    metadata(action["title"], action["description"])
    validated_schema(db, action["fields"])
    return row


def edited(db, user, original, data):
    validate(db, user, original)
    title, description = metadata(
        data.get("title", original["title"]),
        data.get("description", original["description"]),
    )
    fields = original["fields"]
    if "items_json" in data:
        payload = data["items_json"]
        if not isinstance(payload, str) or len(payload) > form_ai.MAX_CURRENT_BYTES:
            raise ValueError("Der Formularentwurf ist zu groß oder ungültig.")
        fields = json.loads(payload)
    return dict(
        original,
        title=title,
        description=description,
        fields=validated_schema(db, fields),
    )


def preview(db, action):
    title = action["title"]
    if action["tool"] == "edit_form":
        row = db.get(Form, action["id"])
        lines = [f"Formularentwurf #{row.id} „{row.title}“ bearbeiten → „{title}“"]
        existing = {item["id"]: item for item in fm.raw_schema(row)}
        submitted = {item["id"]: item for item in action["fields"]}
        changes = [
            f"Entfernt · {item['title']}"
            for key, item in existing.items()
            if key not in submitted
        ]
        changes.extend(
            f"Geändert · {existing[key]['title']} → {item['title']}"
            for key, item in submitted.items()
            if key in existing and item != existing[key]
        )
        lines.extend(changes)
    else:
        lines = [f"Internen Formularentwurf erstellen · {title}"]
    lines.append("Geschlossen, ohne Veröffentlichung oder Einladungen.")
    field_titles = {item["id"]: item["title"] for item in action["fields"]}
    if action["description"]:
        lines.append(action["description"])
    for index, item in enumerate(action["fields"], 1):
        kind, _, question = fm.TYPES[item["type"]]
        if item["type"] == "short" and item.get("subtype") != "text":
            kind = fm.SUBTYPES[item["subtype"]]
        required = ""
        if question:
            if item.get("required_if"):
                required = " · bedingt Pflicht"
            else:
                required = " · Pflicht" if item["required"] else " · optional"
        lines.append(f"{index}. {item['title'] or kind} ({kind}{required})")
        if item.get("description"):
            lines.append("   " + item["description"])
        if item.get("options"):
            lines.append(
                "   Auswahl · "
                + ", ".join(option["label"] for option in item["options"])
            )
        bounds = [
            f"{label} {item[key]}"
            for key, label in (("min", "mindestens"), ("max", "höchstens"))
            if item.get(key) not in (None, "")
        ]
        if bounds:
            lines.append("   " + " · ".join(bounds))
        for key, label in (("show_if", "Sichtbar"), ("required_if", "Pflicht")):
            if condition := item.get(key):
                joiner = " und " if condition["mode"] == "all" else " oder "
                rules = [
                    f"„{field_titles.get(rule['q'], rule['q'])}“ {fm.COND_OPS[rule['op']]} {rule['value']}".rstrip()
                    for rule in condition["rules"]
                ]
                lines.append(f"   {label}, wenn " + joiner.join(rules))
    return "\n".join(lines)


def execute(db, user, action):
    row = validate(db, user, action)
    label = preview(db, action)
    values = fm.schema_values(action["title"], action["description"], action["fields"])
    if row is None:
        row = Form(
            owner_id=user.id,
            kind="survey",
            internal=True,
            active=False,
            public_token=None,
            **values,
        )
        db.add(row)
        db.flush()
    else:
        changed = db.execute(
            update(Form)
            .where(
                Form.id == row.id,
                Form.updated_at == row.updated_at,
                Form.active.is_(False),
                Form.published_at.is_(None),
                Form.public_token.is_(None),
                Form.archived_at.is_(None),
                Form.deleted_at.is_(None),
                Form.kind == "survey",
                ~has_responses(row.id),
            )
            .values(**values)
        )
        if changed.rowcount != 1:
            raise HTTPException(
                409, "Das Formular hat sich geändert. Bitte neu planen."
            )
    return dict(label=label, url=f"/forms/{row.id}", target_id=row.id)
