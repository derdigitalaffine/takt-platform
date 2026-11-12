"""Operate existing application cases through the same services as the case page."""

import hashlib
import json
from datetime import date, datetime, time, timezone
from itertools import islice

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from . import application_orgs as ao, applications as apps, workflow as wf
from .db import (
    ApplicationEvent,
    Form,
    FormResponse,
    Group,
    Organization,
    LOCAL_TZ,
    User,
    to_local,
    utcnow,
)

TOOLS = {"application_command", "application_step"}
CASE_COMMANDS = {"status", "note", "message", "assign", "due", "take"}
STEP_COMMANDS = {"claim", "done", "approved", "rejected"}
STEP_LABELS = {
    "claim": "Schritt übernehmen",
    "done": "Schritt erledigen",
    "approved": "Schritt genehmigen",
    "rejected": "Schritt ablehnen oder zurückgeben",
}


def path(row):
    return f"/forms/{row.form_id}/applications/{row.id}"


def revision(db, row):
    if row is None:
        return None
    latest_event = db.scalar(
        select(func.max(ApplicationEvent.id)).where(
            ApplicationEvent.response_id == row.id
        )
    )
    values = [
        row.form_id,
        row.form.title,
        row.form.archived_at,
        row.form.deleted_at,
        row.ref_no,
        row.status,
        row.status_at,
        row.closed_at,
        row.assignee_id,
        row.group_id,
        row.responsible_org_id,
        row.due_at,
        row.process_version_id,
        latest_event,
        [
            (t.id, t.state, t.assignee_id, t.group_id, t.responsible_org_id, t.completed_by_id, t.due_at)
            for t in row.tasks
        ],
    ]
    return hashlib.sha256(json.dumps(values, default=str).encode()).hexdigest()


def visible(db, user, row):
    return bool(
        row
        and row.ref_no
        and apps.is_application(row.form)
        and not row.form.deleted_at
        and not row.form.archived_at
        and apps.access(db, user, row)
    )


def allowed_step(db, user, row, task, level):
    if (
        row.closed_at
        or task is None
        or task.state != "open"
        or wf.step_of(task) is None
    ):
        return []
    operations = []
    can_work = wf.can_work(db, user, task)
    if task.assignee_id != user.id and (can_work or level >= 2):
        operations.append("claim")
    if can_work and task.kind == "task":
        operations.append("done")
    if can_work and task.kind == "approval" and not wf.four_eyes_block(task, user):
        operations.extend(("approved", "rejected"))
    return operations


def search(db, user, spec, phrase, pattern):
    query = apps.inbox_query(db, user).where(
        Form.archived_at.is_(None), Form.deleted_at.is_(None)
    )
    if phrase:
        query = query.where(
            or_(
                FormResponse.ref_no.ilike(pattern, escape="\\"),
                Form.title.ilike(pattern, escape="\\"),
                FormResponse.name.ilike(pattern, escape="\\"),
            )
        )
    status = spec.get("status", "")
    if status in apps.STATUSES:
        query = query.where(FormResponse.status == status)
    elif status == "open":
        query = query.where(FormResponse.closed_at.is_(None))
    elif status == "overdue":
        query = query.where(
            FormResponse.closed_at.is_(None), FormResponse.due_at < utcnow()
        )
    if spec.get("scope") == "mine":
        query = query.where(
            or_(
                FormResponse.assignee_id.in_(apps._user_ids(db, user)),
                FormResponse.group_id.in_(apps._group_ids(db, user)),
                FormResponse.responsible_org_id.in_(
                    ao.assigned_org_ids(db, apps._user_ids(db, user)) or [-1]),
            )
        )

    def results():
        for row in db.scalars(
            query.order_by(FormResponse.created_at.desc(), FormResponse.id.desc())
        ):
            level = apps.access(db, user, row)
            if not level:
                continue
            due = to_local(row.due_at).date().isoformat() if row.due_at else ""
            task = wf.open_task(row)
            result = dict(
                type="application",
                id=row.id,
                ref=row.ref_no,
                title=row.form.title,
                status=row.status,
                status_label=apps.status_label(row.status),
                due=due,
                editable=level >= 2,
                url=path(row),
            )
            if task:
                result["step"] = dict(
                    id=task.id,
                    title=task.name,
                    kind=task.kind,
                    state=task.state,
                    operations=allowed_step(db, user, row, task, level),
                )
            yield result

    return list(islice(results(), 20))


def validate(db, user, action):
    from .agent import require

    require(user, "applications")
    row = db.get(FormResponse, action["id"])
    if not visible(db, user, row):
        raise HTTPException(404, "Antrag nicht gefunden.")
    if action.get("form_id", row.form_id) != row.form_id or (
        "version" in action and action["version"] != revision(db, row)
    ):
        raise HTTPException(409, "Der Antrag hat sich geändert. Bitte neu planen.")
    level = apps.access(db, user, row)
    operation = action["operation"]
    task = wf.open_task(row)
    if action["tool"] == "application_step":
        if task is None or task.id != action.get("task_id"):
            raise HTTPException(
                409, "Der vorgeschlagene Arbeitsschritt ist nicht mehr aktuell."
            )
        if operation not in allowed_step(db, user, row, task, level):
            raise HTTPException(403, "Dieser Arbeitsschritt ist nicht freigegeben.")
        return row, task
    if level < 2:
        raise HTTPException(403, "Sie dürfen diesen Antrag nur ansehen.")
    if operation == "status":
        status = action.get("status")
        if (
            not isinstance(status, str)
            or status not in apps.STATUSES
            or status == row.status
        ):
            raise ValueError("Bitte einen anderen gültigen Antragsstatus wählen.")
        if task and status in apps.CLOSED:
            raise HTTPException(
                409,
                "Bitte den aktiven Arbeitsschritt bearbeiten, bevor der Vorgang geschlossen wird.",
            )
    if operation == "take" and (row.closed_at or row.assignee_id == user.id):
        raise HTTPException(409, "Dieser Antrag kann derzeit nicht übernommen werden.")
    if action.get("inform") and not apps.mail_ready(db):
        raise HTTPException(409, "Der E-Mail-Versand ist nicht eingerichtet.")
    if operation == "message" or action.get("inform"):
        recipient = apps.applicant_email(row.form, row)
        if not recipient:
            raise HTTPException(
                409, "Für diesen Antrag ist keine Empfängeradresse vorhanden."
            )
        recipient_key = hashlib.sha256(recipient.encode()).hexdigest()
        if action.get("recipient_key", recipient_key) != recipient_key:
            raise HTTPException(
                409, "Die Empfängeradresse hat sich geändert. Bitte neu planen."
            )
    if operation == "assign":
        for model, key in ((User, "user_id"), (Group, "group_id"), (Organization, "org_id")):
            if (record_id := action.get(key)) is not None:
                item = db.get(model, record_id)
                if item is None or (model is User and not item.active) or (
                    model is Organization and not ao.validate(db, record_id)
                ):
                    raise HTTPException(
                        409, "Die gewählte Zuständigkeit ist nicht verfügbar."
                    )
                if action.get(key + "_name", item.name) != item.name:
                    raise HTTPException(
                        409,
                        "Die gewählte Zuständigkeit hat sich geändert. Bitte neu planen.",
                    )
    return row, task


def resolve_name(db, model, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Bitte die Person oder Gruppe eindeutig benennen.")
    query = select(model).where(func.lower(model.name) == value.strip().lower())
    if model is User:
        query = query.where(User.active.is_(True))
    matches = db.scalars(query.limit(2)).all()
    if len(matches) != 1:
        raise ValueError(
            "Die Person oder Gruppe konnte nicht eindeutig gefunden werden."
        )
    return matches[0].id


def bounded_text(value, limit, *, required=False):
    if (
        not isinstance(value, str)
        or len(value) > limit
        or (required and not value.strip())
    ):
        raise ValueError(
            "Bitte den erforderlichen Text in der vorgesehenen Länge angeben."
        )
    return value.replace("\r\n", "\n").strip()


def due_date(value):
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise ValueError("Bitte die Frist als Datum angeben.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError("Bitte die Frist im Format JJJJ-MM-TT angeben.") from None


def normalize(db, user, raw, findings):
    tool, case_id, operation = raw["tool"], raw.get("id"), raw.get("operation")
    if type(case_id) is not int or not any(
        r["type"] == "application" and r["id"] == case_id for r in findings
    ):
        raise ValueError("Bitte zuerst den konkreten Antrag suchen.")
    operations = STEP_COMMANDS if tool == "application_step" else CASE_COMMANDS
    if not isinstance(operation, str) or operation not in operations:
        raise ValueError("Diese Antragsbearbeitung ist nicht unterstützt.")
    action = dict(tool=tool, id=case_id, operation=operation)
    if tool == "application_step":
        step_id = raw.get("task_id")
        if type(step_id) is not int or not any(
            r["type"] == "application"
            and r["id"] == case_id
            and r.get("step", {}).get("id") == step_id
            for r in findings
        ):
            raise ValueError("Bitte den konkret gefundenen Arbeitsschritt verwenden.")
        action.update(
            task_id=step_id, comment=bounded_text(raw.get("comment", ""), 10000)
        )
    elif operation in ("status", "note", "message"):
        action["text"] = bounded_text(
            raw.get("text", ""), 20000, required=operation != "status"
        )
        if operation == "status":
            action["status"] = raw.get("status")
            action["inform"] = raw.get("inform") is True
    elif operation == "due":
        if "due" not in raw:
            raise ValueError(
                "Bitte das Fristdatum oder ausdrücklich keine Frist angeben."
            )
        action["due"] = due_date(raw["due"])

    row, _ = validate(db, user, action)
    if operation == "assign":
        if not raw.get("person") and not raw.get("group") and not raw.get("organization"):
            raise ValueError("Bitte eine Person, Gruppe oder Organisationseinheit für die Zuweisung angeben.")
        action["user_id"] = (
            resolve_name(db, User, raw["person"]) if raw.get("person") else None
        )
        action["group_id"] = (
            resolve_name(db, Group, raw["group"]) if raw.get("group") else None
        )
        action["org_id"] = (
            resolve_name(db, Organization, raw["organization"])
            if raw.get("organization") else None
        )
        if action["org_id"] is not None:
            ao.validate(db, action["org_id"])
    action.update(form_id=row.form_id, version=revision(db, row))
    return snapshot(db, user, action)


def snapshot(db, user, action):
    row, _ = validate(db, user, action)
    if action["operation"] == "message" or action.get("inform"):
        action["recipient_key"] = hashlib.sha256(
            apps.applicant_email(row.form, row).encode()
        ).hexdigest()
    if action["operation"] == "assign":
        for model, key in ((User, "user_id"), (Group, "group_id"), (Organization, "org_id")):
            action[key + "_name"] = (
                db.get(model, action.get(key)).name if action.get(key) else ""
            )
        group = db.get(Group, action.get("group_id")) if action.get("group_id") else None
        action["responsible_org_id"] = action.get("org_id") or (group.org_id if group else None)
    return action


def editor_fields(db, action):
    if action["tool"] != "application_step" or action["operation"] != "done":
        return []
    task = wf.open_task(db.get(FormResponse, action["id"]))
    return [
        "check",
        *[f"f_{field['key']}" for field in (wf.step_of(task) or {}).get("fields", [])],
    ]


def edited(db, user, original, data):
    _, task = validate(db, user, original)
    action = dict(original)
    operation = action["operation"]
    if action["tool"] == "application_step":
        action["comment"] = bounded_text(
            data.get("comment", action["comment"]),
            10000,
            required=operation == "rejected",
        )
        if operation == "done":
            step = wf.step_of(task) or {}
            submitted = set(data.getlist("check"))
            checks = [
                label for label in step.get("checklist", []) if label in submitted
            ]
            values = {
                field["key"]: bounded_text(data.get(f"f_{field['key']}", ""), 5000)
                for field in step.get("fields", [])
            }
            _, error = wf.completion_fields(step, checks, values)
            if error:
                raise ValueError(error)
            action.update(checks=checks, values=values)
    elif operation in ("status", "note", "message"):
        action["text"] = bounded_text(
            data.get("text", action["text"]), 20000, required=operation != "status"
        )
        if operation == "status":
            action["status"] = data.get("status", action["status"])
            action["inform"] = data.get("inform") == "1"
    elif operation == "due":
        action["due"] = due_date(data.get("due", action["due"]))
    elif operation == "assign":
        for key in ("user_id", "group_id", "responsible_org_id"):
            if key in data:
                value = data[key]
                if not isinstance(value, str) or (
                    value and (not value.isascii() or not value.isdigit())
                ):
                    raise ValueError("Bitte eine gültige Zuständigkeit wählen.")
                if key == "responsible_org_id":
                    action["org_id"] = ao.validate(db, int(value) if value else None)
                    action["group_id"] = None
                    action.pop("group_id_name", None)
                    action.pop("org_id_name", None)
                else:
                    action[key] = int(value) if value else None
                    action.pop(key + "_name", None)
    action["reviewed"] = True
    return snapshot(db, user, action)


def preview(db, action):
    row = db.get(FormResponse, action["id"])
    lines = [f"{row.ref_no} · {row.form.title}"]
    operation = action["operation"]
    if action["tool"] == "application_step":
        task = wf.open_task(row)
        lines.append(f"{STEP_LABELS[operation]} · {task.name}")
        if operation == "done":
            for check in action.get("checks", []):
                lines.append(f"Bestätigter Prüfpunkt · {check}")
            values = action.get("values", {})
            for field in (wf.step_of(task) or {}).get("fields", []):
                if field["key"] in values:
                    lines.append(f"{field['label']} · {values[field['key']] or 'leer'}")
        if operation == "rejected":
            step = wf.step_of(task) or {}
            if step.get("on_reject", "end") == "end":
                lines.append(
                    "Der Prozess endet. Die Begründung wird der antragstellenden Person mitgeteilt."
                )
            else:
                lines.append(
                    "Der Prozess kehrt zum vorgesehenen früheren Schritt zurück."
                )
        if action["comment"]:
            lines.append(action["comment"])
    elif operation == "status":
        lines.append(
            f"Status ändern · {apps.status_label(row.status)} → {apps.status_label(action['status'])}"
        )
        lines.append("Der Status und die Mitteilung erscheinen auf der Statusseite.")
        if action["inform"]:
            lines.append(
                "Zusätzlich wird eine E-Mail an die antragstellende Person ausgelöst."
            )
    elif operation == "message":
        lines.append(
            "Nachricht an die antragstellende Person per E-Mail und auf der Statusseite"
        )
    elif operation == "note":
        lines.append("Interne Notiz für die Sachbearbeitung")
    elif operation == "due":
        lines.append(
            f"Frist setzen · {action['due']}" if action["due"] else "Frist entfernen"
        )
    elif operation == "take":
        lines.append("Vorgang selbst übernehmen")
        if row.status == "received":
            lines.append("Der Status wechselt zu „In Bearbeitung“.")
    elif operation == "assign":
        names = [
            action.get(key) for key in ("user_id_name", "group_id_name", "org_id_name") if action.get(key)
        ]
        lines.append(
            "Zuständigkeit ändern · "
            + (" und ".join(names) if names else "keine Person oder Organisationseinheit")
        )
        lines.append("Neu Zuständige erhalten einen Hinweis.")
    if action.get("text"):
        lines.append(action["text"])
    return "\n".join(lines)


def execute(db, user, action):
    from .agent import require

    require(user, "applications")
    if not action.get("reviewed"):
        raise HTTPException(
            409, "Bitte zuerst die ausgefüllte Fachmaske prüfen und bestätigen."
        )
    connection = db.connection()
    # Serialize the check and write with other case changes in SQLite.
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    db.flush()
    db.expire_all()
    row, task = validate(db, user, action)
    label = preview(db, action)
    operation = action["operation"]
    if action["tool"] == "application_step":
        if operation == "claim":
            wf.claim(db, task, user)
        else:
            error = wf.complete(
                db,
                task,
                user,
                operation,
                action["comment"],
                action.get("checks", []),
                action.get("values", {}),
            )
            if error:
                raise HTTPException(422, error)
    elif operation == "status":
        apps.set_status(
            db, row, action["status"], action["text"], user, action["inform"]
        )
    elif operation == "note":
        apps.note(row, action["text"], user)
    elif operation == "message":
        apps.message(db, row, action["text"], user)
    elif operation == "due":
        due = (
            datetime.combine(date.fromisoformat(action["due"]), time(23, 59), LOCAL_TZ)
            if action["due"]
            else None
        )
        apps.set_due(
            row,
            due.astimezone(timezone.utc).replace(tzinfo=None) if due else None,
            user,
        )
    elif operation == "assign":
        apps.assign(db, row, action["user_id"], action.get("group_id"), user,
                    org_id=action.get("org_id"))
    elif operation == "take":
        apps.assign(db, row, user.id, row.group_id, user, org_id=row.responsible_org_id)
        if row.status == "received":
            apps.set_status(db, row, "in_progress", "", user, inform=False)
    return dict(label=label, url=path(row), target_id=row.id)
