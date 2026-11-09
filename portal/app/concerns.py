"""Routing and native-task integration for internal concerns.

No AI model may assign, approve or create tasks. Rules are deterministic.
Confidential narratives remain in the protected concern table, never in tasks.
"""
from sqlalchemy import select
from fastapi import HTTPException

from . import organization, tasks
from .concern_models import Concern, ConcernCategory
from .db import User, GroupMember
from .org_models import OrgMembership, OrgRoleGrant
from .task_models import Task


def primary_org(db, reporter: User) -> int | None:
    row = db.scalar(select(OrgMembership).where(
        OrgMembership.user_id == reporter.id, OrgMembership.is_primary.is_(True)))
    return row.org_id if row else None


def supervisor(db, reporter: User, org_id: int | None = None) -> User:
    """Find one active leader in the nearest scope, using the existing org grants."""
    org_id = org_id or primary_org(db, reporter)
    if not org_id:
        raise HTTPException(422, "Keine primäre Organisationseinheit vorhanden. Bitte Zuordnung prüfen.")
    path = organization.active_path(db, org_id)
    if not path:
        raise HTTPException(422, "Die primäre Organisationseinheit ist nicht aktiv.")
    for depth, node_id in enumerate(path):
        grants = list(db.scalars(select(OrgRoleGrant).where(
            OrgRoleGrant.org_id == node_id, OrgRoleGrant.role == "lead")))
        possible = set()
        for grant in grants:
            if depth and not grant.include_children:
                continue
            if grant.user_id:
                possible.add(grant.user_id)
            elif grant.group_id:
                possible.update(db.scalars(select(GroupMember.user_id).where(
                    GroupMember.group_id == grant.group_id)))
        possible.discard(reporter.id)
        active = [u for u in db.scalars(select(User).where(
            User.id.in_(possible), User.active.is_(True))) if u.id != reporter.id]
        if len(active) == 1:
            return active[0]
        if len(active) > 1:
            raise HTTPException(422, "Mehrere Leitungspersonen sind eingetragen. "
                                    "Bitte die eindeutige Vorgesetztenzuordnung klären.")
    raise HTTPException(422, "Keine eindeutige vorgesetzte Person für diesen Bereich hinterlegt.")


def destination(db, reporter: User, category: ConcernCategory) -> User:
    if category.routing == "lead":
        return supervisor(db, reporter)
    if category.routing == "person" and category.responsible_id:
        user = db.get(User, category.responsible_id)
        if user and user.active and user.id != reporter.id:
            return user
    raise HTTPException(422, "Für diese Kategorie fehlt eine aktive zuständige Person. "
                            "Bitte die Kategorieverwaltung informieren.")


def current_assignee_id(concern: Concern) -> int | None:
    """Task assignment is authoritative after reassignment by native TAKT workflows."""
    return concern.task.assignee_id if concern.task is not None else None


def can_read(user: User, concern: Concern) -> bool:
    """Always re-check current task assignee; former assignees lose access."""
    return bool(user.is_admin or user.id == concern.reporter_id
                or user.id == current_assignee_id(concern)
                or (not concern.confidential and user.can("concerns_manage")))


def can_work(user: User, concern: Concern) -> bool:
    return bool(user.is_admin or user.id == current_assignee_id(concern))


def create(db, reporter: User, category: ConcernCategory, title: str, description: str) -> Concern:
    if not category.active:
        raise HTTPException(422, "Kategorie wurde deaktiviert.")
    title, description = title.strip(), description.strip()
    if not 5 <= len(title) <= 240 or not 10 <= len(description) <= 12000:
        raise HTTPException(422, "Bitte einen Titel mit 5–240 und eine Beschreibung mit 10–12.000 Zeichen eingeben.")
    assignee = destination(db, reporter, category)
    confidential = bool(category.confidential or category.kind == "complaint")
    concern = Concern(
        category_id=category.id, reporter_id=reporter.id, assignee_id=assignee.id,
        org_id=primary_org(db, reporter), title=title, description=description,
        confidential=confidential,
    )
    db.add(concern)
    db.flush()
    if confidential:
        # Even users with tasks_manage see only a generic shell, and not the reporter identity.
        task_title = f"Vertrauliches internes Anliegen {concern.reference}"
        task_description = f"Vertraulicher Vorgang: [Zum geschützten Anliegen](/anliegen/{concern.id})"
        task_creator_id = assignee.id
    else:
        task_title = f"{category.title}: {title}"
        task_description = f"{description}\n\n[Anliegen {concern.reference} öffnen](/anliegen/{concern.id})"
        task_creator_id = reporter.id
    task = Task(
        title=task_title[:300], description=task_description,
        creator_id=task_creator_id, assignee_id=assignee.id,
        status="open", priority="normal",
        source_type="concern", source_id=str(concern.id),
        source_key=f"concern:{concern.id}",
    )
    db.add(task)
    db.flush()
    concern.task_id = task.id
    # Native task notices include no sensitive description or name.
    tasks.audit(db, task, None if confidential else reporter,
                "created", "Internes Anliegen als Aufgabe angelegt.")
    tasks.ping(db, task, [assignee.id], "Neues internes Anliegen")
    from . import task_rules
    task_rules.emit(db, task, "created", f"created:{task.id}")
    return concern
