"""Permission-filtered process hub, shared work feed and completion policy for internal cases.

No process data is copied into native tasks. Every internal step remains owned by
AnliegenProcessTask and is rendered exactly once through the shared work feed.
"""
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import anliegen as cases
from . import anliegen_processes as rules
from . import organization
from .anliegen_models import Anliegen, AnliegenEvent
from .anliegen_process_models import (
    AnliegenProcessRun, AnliegenProcessTask, AnliegenProcessRule,
    AnliegenProcessAudit, AnliegenProcessOverride,
)
from .db import Process, User
from .security import decrypt, encrypt

FINAL_STATES = frozenset({"done", "rejected", "cancelled"})
ACTIVE_STATES = frozenset({"requested", "running", "paused", "blocked"})

AUDIT_LABELS = {
    "requested": "Prozessstart angefordert",
    "approved": "Prozessstart freigegeben",
    "task_opened": "Arbeitsschritt zugewiesen",
    "task_completed": "Arbeitsschritt abgeschlossen",
    "finished": "Prozess abgeschlossen",
    "rejected": "Prozess abgelehnt",
    "paused": "Prozess pausiert",
    "resumed": "Prozess fortgesetzt",
    "cancelled": "Prozess abgebrochen",
    "blocked": "Prozess benötigt Klärung",
}


def private_access(db: Session, user: User, case: Anliegen) -> bool:
    """Check object, module and organizational rights before loading internal data."""
    if (not user or not user.active or not user.can("anliegen_process_work")
            or case.confidential or not cases.can_handle(user, case)):
        return False
    if case.org_id is None or user.is_admin or case.assignee_id == user.id:
        return True
    return organization.allows(db, user, case.org_id, "view")


def active_runs(db: Session, case: Anliegen) -> list[AnliegenProcessRun]:
    return list(db.scalars(select(AnliegenProcessRun).where(
        AnliegenProcessRun.anliegen_id == case.id).order_by(
            AnliegenProcessRun.id.desc()).limit(250)))


def completion_state(db: Session, case: Anliegen,
                     runs: list[AnliegenProcessRun] | None = None):
    """Derive a completion decision using immutable per-run rule policies.

    A manual rule never implicitly closes a case. An all-success policy is
    stronger than any-success when both are present. No audit/rule field
    changes state here; the command adapter performs the actual transition.
    """
    runs = active_runs(db, case) if runs is None else runs
    if not runs:
        return {"mode": "manual", "ready": False, "reason": "Noch keine Prozesse"}
    modes = set()
    for run in runs:
        rule = db.get(AnliegenProcessRule, run.rule_id)
        try:
            raw = json.loads(rule.policy_json) if rule else None
            policy = rules.normalize_policy(raw)
        except (ValueError, TypeError):
            return {"mode": "manual", "ready": False,
                    "reason": "Die Abschlussregel muss geprüft werden"}
        modes.add(policy["completion"])
    if "all_success" in modes:
        mode = "all_success"
        ready = all(run.state == "done" for run in runs)
    elif "any_success" in modes:
        mode = "any_success"
        ready = any(run.state == "done" for run in runs)
    else:
        mode, ready = "manual", False
    if mode == "manual":
        reason = "Manueller Abschluss festgelegt"
    elif ready:
        reason = "Abschlussbedingung erfüllt"
    elif any(run.state in ("blocked", "rejected", "cancelled") for run in runs):
        reason = "Mindestens ein Prozess benötigt Klärung"
    else:
        reason = "Wartet auf verknüpfte Prozesse"
    return {"mode": mode, "ready": ready, "reason": reason}


def sync_completion(db: Session, case: Anliegen, actor: User) -> bool:
    """Close only through the existing case state machine, when its rules allow."""
    if (not rules.integration_enabled(db) or case.confidential
            or not cases.can_handle(actor, case)):
        return False
    decision = completion_state(db, case)
    if (not decision["ready"] or "done" not in cases.next_states(case)
            or case.assignee_id is None):
        return False
    cases.update_status(db, case, actor, "done")
    cases.record(db, case, actor, "process_completion",
                 "Anliegen nach freigegebener Prozessabschlussregel erledigt.")
    return True


def require_end_reason(db: Session, case: Anliegen, actor: User, target: str,
                       reason: str = "") -> bool:
    """Manual closure of unfinished or rejected workflow requires private audit."""
    if target not in ("done", "closed") or case.confidential:
        return False
    runs = active_runs(db, case)
    if not runs or all(run.state == "done" for run in runs):
        return False
    if not rules.integration_enabled(db):
        # Turning the feature off freezes execution but does not delete runs.
        # A manual status transition remains available with an audit reason.
        pass
    if not cases.can_handle(actor, case):
        raise HTTPException(403, "Keine Berechtigung für den manuellen Abschluss.")
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 1000:
        raise HTTPException(
            409, "Bitte den vorzeitigen Abschluss der verknüpften Prozesse begründen (10–1000 Zeichen).")
    db.add(AnliegenProcessOverride(
        anliegen_id=case.id, actor_id=actor.id,
        from_status=case.status, to_status=target,
        reason_enc=encrypt(reason.strip())))
    cases.record(db, case, actor, "process_override",
                 "Manueller Abschluss trotz nicht erfolgreich abgeschlossener Prozesse dokumentiert.")
    return True


def _timeline(db: Session, case: Anliegen, runs, *, private: bool,
              tasks_enabled: bool, user: User):
    """Compose existing events/audits/comments with original-file references."""
    result = [
        dict(id=f"case:{evt.id}", when=evt.created_at, kind="anliegen",
             title=evt.kind, detail=evt.note, href=None)
        for evt in db.scalars(select(AnliegenEvent).where(
            AnliegenEvent.anliegen_id == case.id).order_by(
            AnliegenEvent.id.desc()).limit(150))
        if private or evt.kind not in ("process_override", "process_completion")
    ]
    docs = []
    if private:
        run_ids = [run.id for run in runs]
        if run_ids:
            # Whitelist audit kinds and never present stored technical notes as
            # raw HTML or JSON. This prevents accidental leakage of field values.
            for audit in db.scalars(select(AnliegenProcessAudit).where(
                    AnliegenProcessAudit.run_id.in_(run_ids)).order_by(
                    AnliegenProcessAudit.id.desc()).limit(350)):
                title = AUDIT_LABELS.get(audit.kind)
                if title:
                    result.append(dict(
                        id=f"audit:{audit.id}", when=audit.created_at,
                        kind="prozess", title=title,
                        detail=f"Prozesslauf #{audit.run_id}",
                        href=f"#process-run-{audit.run_id}"))
            for override in db.scalars(select(AnliegenProcessOverride).where(
                    AnliegenProcessOverride.anliegen_id == case.id).order_by(
                    AnliegenProcessOverride.id.desc()).limit(80)):
                result.append(dict(
                    id=f"override:{override.id}", when=override.created_at,
                    kind="freigabe", title="Begründete manuelle Abschlussentscheidung",
                    detail=decrypt(override.reason_enc),
                    href=None))
        if case.task_id and tasks_enabled:
            from . import tasks as native
            from .task_models import TaskAttachment, TaskComment
            try:
                native.get(db, user, case.task_id)
            except HTTPException:
                pass
            else:
                for doc in db.scalars(select(TaskAttachment).where(
                        TaskAttachment.task_id == case.task_id,
                        TaskAttachment.removed_at.is_(None)).order_by(
                        TaskAttachment.id.desc()).limit(80)):
                    # Original download endpoint applies native task ACL
                    # and, for DMS references, validates source ACL again.
                    docs.append(dict(id=doc.id, name=doc.name,
                                     href=f"/aufgaben/{case.task_id}/dateien/{doc.id}",
                                     when=doc.created_at))
                for comment in db.scalars(select(TaskComment).where(
                        TaskComment.task_id == case.task_id,
                        TaskComment.removed_at.is_(None)).order_by(
                        TaskComment.id.desc()).limit(80)):
                    result.append(dict(
                        id=f"comment:{comment.id}", when=comment.created_at,
                        kind="notiz", title="Notiz zur verbundenen Aufgabe",
                        detail=comment.body, href=f"/aufgaben/{case.task_id}"))
    result.sort(key=lambda item: (item["when"] or datetime.min, item["id"]),
                reverse=True)
    return result[:250], docs


def summary(db: Session, case: Anliegen, user: User, *,
            tasks_enabled=False, integration_on=None):
    """Render data is prefiltered; templates never decide what may be queried."""
    from . import absence
    from .anliegen_process_engine import validate_internal_version, ProcessEngineError
    from .db import ProcessVersion
    from .anliegen_process_config import can_approve_run
    private = private_access(db, user, case)
    enabled = rules.integration_enabled(db) if integration_on is None else integration_on
    runs = active_runs(db, case)
    users = set(absence.acting_ids(db, user)) if private and enabled else set()
    groups = set(absence.acting_group_ids(db, user)) if private and enabled else set()
    cards = []
    for run in runs:
        rule = db.get(AnliegenProcessRule, run.rule_id)
        proc = db.get(Process, rule.process_id) if rule and private else None
        # Never load internal step definitions for a reporter who lacks private access.
        steps = []
        task_rows = []
        if private:
            version = db.get(ProcessVersion, run.process_version_id)
            try:
                steps = validate_internal_version(version)
            except ProcessEngineError:
                steps = []
            task_rows = list(db.scalars(select(AnliegenProcessTask).where(
                AnliegenProcessTask.run_id == run.id).order_by(
                AnliegenProcessTask.ordinal).limit(240)))
        completed = sum(1 for task in task_rows if task.state in ("done", "skipped"))
        progress = 100 if run.state == "done" else (
            min(99, int(100 * len({t.step_id for t in task_rows
                                 if t.state in ("done", "skipped")}) / len(steps)))
            if steps else 0)
        open_tasks = [task for task in task_rows if task.state == "open"]
        next_task = open_tasks[-1] if open_tasks else None
        due = min((task.due_at for task in open_tasks if task.due_at),
                  default=None)
        permitted = (
            private and enabled and run.state == "running"
        )
        cards.append(dict(
            run=run, rule=rule, process=proc,
            can_view_details=private,
            can_control=private and enabled and user.can("anliegen_process_start"),
            can_approve=(enabled and not case.confidential
                         and can_approve_run(db, user, case)
                         and run.requested_by_id != user.id),
            progress=progress if private else None,
            completed=completed if private else None,
            total=len(steps) if private else None,
            open_count=len(open_tasks) if private else None,
            due=due if private else None,
            next_task=next_task if private else None,
            tasks=[
                dict(task=task, step=steps[task.step_index]
                     if 0 <= task.step_index < len(steps) else {},
                     can_act=bool(permitted and task.state == "open"
                                  and (task.assignee_id in users
                                       or task.group_id is not None
                                       and task.group_id in groups)))
                for task in task_rows
            ],
        ))
    timeline, documents = _timeline(
        db, case, runs, private=private, tasks_enabled=tasks_enabled, user=user)
    aggregate = dict(total=len(runs),
                     running=sum(1 for run in runs if run.state == "running"),
                     waiting=sum(1 for run in runs if run.state == "requested"),
                     blocked=sum(1 for run in runs if run.state in ("blocked", "paused")),
                     done=sum(1 for run in runs if run.state == "done"),
                     active=sum(1 for run in runs if run.state in ACTIVE_STATES),
                     completion=completion_state(db, case, runs))
    aggregate["needs_override"] = bool(runs and any(
        run.state != "done" for run in runs))
    aggregate["can_accept_completion"] = bool(
        private and enabled and aggregate["completion"]["ready"]
        and "done" in cases.next_states(case) and case.assignee_id)
    return dict(cards=cards, timeline=timeline, documents=documents,
                aggregate=aggregate, private=private)


def work_items(db: Session, user: User):
    """One canonical work item per open process step; no Task mirror created."""
    if not (user and user.active and user.can("anliegen_process_work")
            and rules.integration_enabled(db)):
        return []
    from . import absence
    from .anliegen_process_models import AnliegenProcessTask
    from .db import Process
    acting_users = set(absence.acting_ids(db, user))
    acting_groups = set(absence.acting_group_ids(db, user))
    query = (select(AnliegenProcessTask, AnliegenProcessRun, Anliegen)
             .join(AnliegenProcessRun,
                   AnliegenProcessTask.run_id == AnliegenProcessRun.id)
             .join(Anliegen, AnliegenProcessRun.anliegen_id == Anliegen.id)
             .where(AnliegenProcessTask.state == "open",
                    AnliegenProcessRun.state == "running",
                    Anliegen.confidential.is_(False))
             .order_by(AnliegenProcessTask.due_at,
                       AnliegenProcessTask.id).limit(400))
    output = []
    for task, run, case in db.execute(query):
        if (not private_access(db, user, case)
                or not (task.assignee_id in acting_users
                        or task.group_id is not None
                        and task.group_id in acting_groups)):
            continue
        output.append(dict(case=case, run=run, task=task,
                           scope="group" if task.group_id
                           else "personal" if task.assignee_id == user.id
                           else "proxy"))
    return output
