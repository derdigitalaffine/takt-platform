"""Session-bound handoff to real TAKT forms, with review after human edits.

Only known fields and destinations are accepted. Opening a form never writes.
Each saved step rotates the plan nonce, so old tabs cannot replay a step.
"""
import secrets
from datetime import datetime
from urllib.parse import urlencode

from fastapi import HTTPException

from . import agent, tasks, anliegen
from .db import DmsArea, LOCAL_TZ


def destination(action):
    tool = action["tool"]
    if tool == "configure_anliegen_category":
        return "/anliegen/kategorien"
    if tool == "create_task":
        return "/aufgaben/neu"
    if tool == "create_anliegen":
        return "/anliegen/neu"
    if tool in ("assign_task", "set_task_priority"):
        return f"/aufgaben/{action['id']}/bearbeiten"
    if tool == "set_task_status":
        return f"/aufgaben/{action['id']}"
    if tool in ("assign_anliegen", "set_anliegen_status"):
        return f"/anliegen/{action['id']}"
    if tool == "create_event":
        return "/kalender?ansicht=termine"
    if tool == "copy_form":
        return f"/forms/{action['id']}"
    if tool == "move_dms":
        return f"/dms/r/{action['id']}"
    raise HTTPException(422, "Für dieses Werkzeug gibt es keine Fachmaske.")


def url(plan, step=0):
    base = destination(plan["actions"][step])
    return base + ("&" if "?" in base else "?") + urlencode({"agent_plan": plan["nonce"], "agent_step": step})


def load(request, user, nonce, step):
    from .main import stash_get
    plan = stash_get(request, "takt-agent-plan")
    if (not plan or not nonce or not secrets.compare_digest(nonce, plan.get("nonce", ""))
            or plan.get("user_id") != user.id or type(step) is not int
            or not 0 <= step < len(plan.get("actions", []))):
        raise HTTPException(409, "Dieser Vorschlag ist abgelaufen. Bitte im Agenten neu planen.")
    return plan, plan["actions"][step]


def validate(db, user, action):
    if action["tool"] in agent.modules.WRITE:
        row = agent.modules.target(db, user, action)
        current = agent.modules.version(row)
        if action["tool"] == "move_dms":
            area = db.get(DmsArea, action["area_id"])
            if [area.name, area.parent_id] != action["area_snapshot"]:
                raise HTTPException(409, "Der Zielbereich hat sich geändert.")
        if action["tool"] == "configure_anliegen_category" and agent.modules.agent_anliegen.affected(db, row) != action["affected"]:
            raise HTTPException(409, "Betroffene Anliegen haben sich geändert.")
    elif not action["tool"].startswith("create_"):
        is_case = "anliegen" in action["tool"]
        row = anliegen.get(db, user, action["id"]) if is_case else tasks.get(db, user, action["id"])
        current = row.updated_at.isoformat() if is_case else row.version
        agent.validate_action(db, user, action, row)
    else:
        agent.validate_action(db, user, action)
        return
    if current != action["version"]:
        raise HTTPException(409, "Der Vorgang hat sich geändert. Bitte neu planen.")


def view(db, user, plan, step):
    action = plan["actions"][step]
    validate(db, user, action)
    fields = {k: v for k, v in action.items() if k not in ("version", "routing_snapshot", "area_snapshot", "affected", "tool", "id")}
    tool = action["tool"]
    if tool == "create_anliegen":
        fields["description_final"] = fields["description"]
    if tool == "create_event":
        fields["calendar_id"] = action["id"]
        for key in ("start", "end"):
            local = datetime.fromisoformat(action[key]).astimezone(LOCAL_TZ)
            fields[key] = local.date().isoformat()
            fields[key + "_time"] = local.strftime("%H:%M")
        fields["kind"] = "event"
        fields["repeat"] = "none"
        fields["all_day"] = False
    return dict(tool=tool, fields=fields, id=action.get("id"), step=step,
                total=len(plan["actions"]), preview=agent.preview(db, [action])[0],
                path=destination(action).split("?")[0],
                event_times={k: action[k] for k in ("start", "end")} if tool == "create_event" else {})


def edited(db, user, original, data):
    """The human edits a native form; normalization still checks the real services."""
    validate(db, user, original)
    raw = dict(original)
    tool = raw["tool"]
    allowed = {
        "create_task": ("title", "description", "priority", "assignee_id"),
        "create_anliegen": ("title", "description", "category_id"),
        "assign_task": ("assignee_id",), "set_task_priority": ("priority",),
        "set_task_status": (), "assign_anliegen": ("assignee_id",),
        "set_anliegen_status": ("status", "supplier", "order_reference", "expected_delivery"),
        "create_event": ("title", "description", "location", "calendar_id"),
        "copy_form": (), "move_dms": ("area_id",),
        "configure_anliegen_category": ("title", "routing", "assignee_id"),
    }[tool]
    for key in allowed:
        if key in data:
            value = str(data[key])
            if key.endswith("_id"):
                try:
                    value = int(value or "0") if tool == "configure_anliegen_category" else int(value)
                except ValueError:
                    raise HTTPException(422, "Bitte ein gültiges Ziel auswählen.")
            raw[key] = value
    if tool == "configure_anliegen_category":
        raw["enabled"] = data.get("enabled") == "1"
        raw["apply_open"] = data.get("apply_open") == "1"
    if tool == "create_anliegen":
        raw["description"] = str(data.get("description_final", data.get("description", raw["description"])))
    if tool == "create_event":
        raw["id"] = raw.pop("calendar_id", raw["id"])
        for key in ("start", "end"):
            try:
                from zoneinfo import ZoneInfo
                zone = ZoneInfo(str(data.get("agent_timezone") or "Europe/Berlin"))
                raw[key] = datetime.fromisoformat(str(data[key]) + "T" + str(data[key + "_time"])).replace(tzinfo=zone).isoformat()
            except (KeyError, TypeError, ValueError):
                raise HTTPException(422, "Beginn und Ende prüfen.")
    # These IDs come from a human form submission, not from the LLM. The exact
    # module ACL is still checked by normalize/validate, including the new target.
    findings = []
    if "id" in raw:
        kind = agent.modules.KINDS.get(tool, "anliegen" if "anliegen" in tool else "task")
        findings.append(dict(type=kind, id=raw["id"]))
    if "assignee_id" in raw:
        findings.append(dict(type="person", id=raw["assignee_id"]))
    if "area_id" in raw:
        findings.append(dict(type="dms_area", id=raw["area_id"]))
    import json
    try:
        normalized = agent.normalize_plan(json.dumps(dict(actions=[raw])), user, findings, agent.categories_for(db, user), db)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return normalized["actions"][0]
