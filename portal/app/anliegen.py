"""Internal intake workflow, category-based routing, and safe native task linkage."""
from sqlalchemy import select, or_
from fastapi import HTTPException

from .db import GroupMember, Organization, User, utcnow
from .org_models import OrgMembership, OrgRoleGrant
from .anliegen_models import Anliegen, AnliegenCategory, AnliegenEvent

DEFAULT_CATEGORIES = (
    ("office_supply", "Büromaterial", "Verbrauchsmaterial und allgemeine Bestellungen", "fa-paperclip", "person", False),
    ("office_furniture", "Büromöbel", "Möbelbeschaffung und Ausstattung", "fa-chair", "person", False),
    ("defect", "Mangel melden", "Defekte, Schäden und Störungen", "fa-screwdriver-wrench", "person", False),
    ("complaint", "Vertrauliche Beschwerde", "Vertrauliche Meldung an die zuständige Leitung", "fa-shield-halved", "lead", True),
    ("improvement", "Verbesserungsvorschlag", "Ideen und Verbesserungen des Arbeitsalltags", "fa-lightbulb", "person", False),
    ("other", "Sonstiges Anliegen", "Andere interne Anliegen", "fa-inbox", "person", False),
)
STATUSES = {"unassigned": "Zuständigkeit offen", "open": "Offen",
            "in_progress": "In Bearbeitung", "done": "Erledigt", "closed": "Geschlossen"}
NEXT = {"unassigned": {"open", "closed"}, "open": {"in_progress", "done", "closed"},
        "in_progress": {"open", "done", "closed"}, "done": {"in_progress", "closed"},
        "closed": set()}


def seed(db):
    for position, (key, title, desc, icon, route, secret) in enumerate(DEFAULT_CATEGORIES):
        if not db.scalar(select(AnliegenCategory.id).where(AnliegenCategory.key == key)):
            db.add(AnliegenCategory(key=key, title=title, description=desc, icon=icon,
                                   routing=route, confidential=secret, enabled=True,
                                   position=position))


def migrate_confidential_payload(db):
    """Idempotently protect legacy confidential rows during startup.

    No plaintext remains in the historical title/description columns after
    successful migration. A failed encryption aborts startup transaction.
    """
    from .security import encrypt
    for row in db.scalars(select(Anliegen).where(Anliegen.confidential.is_(True))):
        if not row.title_enc:
            row.title_enc = encrypt(row.title or "Vertrauliches Anliegen")
        if not row.description_enc:
            row.description_enc = encrypt(row.description or "")
        row.title = "Vertrauliches Anliegen"
        row.description = ""


def category(db, category_id, *, enabled=False):
    row = db.get(AnliegenCategory, category_id)
    if row is None or (enabled and not row.enabled):
        raise HTTPException(404, "Diese Kategorie ist nicht verfügbar.")
    return row


def can_view(user, row):
    # Confidential cases never become visible through broad management permissions.
    if row.confidential:
        return user.id in (row.reporter_id, row.assignee_id)
    return (user.id in (row.reporter_id, row.assignee_id)
            or user.can("anliegen_manage"))


def can_handle(user, row):
    if row.confidential:
        return row.assignee_id == user.id
    return row.assignee_id == user.id or user.can("anliegen_manage")


def get(db, user, case_id):
    row = db.get(Anliegen, case_id)
    if row is None or not can_view(user, row):
        raise HTTPException(404, "Anliegen nicht gefunden.")
    return row


def visible_query(user):
    # Never leak confidential complaints to global managers.
    member = or_(Anliegen.reporter_id == user.id, Anliegen.assignee_id == user.id)
    return select(Anliegen).where(
        or_(member, Anliegen.confidential.is_(False))
        if user.can("anliegen_manage") else member
    )


def primary_org(db, user_id):
    return db.scalar(select(OrgMembership.org_id).where(
        OrgMembership.user_id == user_id, OrgMembership.is_primary.is_(True)
    ))


def supervisor(db, reporter, org_id):
    """Resolve explicit TAKT org lead grants, escalating to parents only if necessary.

    Multiple equally eligible people are deliberately ambiguous and not routed.
    The author cannot approve their own confidential complaint.
    """
    current, seen = org_id, set()
    while current and current not in seen:
        seen.add(current)
        org = db.get(Organization, current)
        if not org or not org.active:
            return None
        for role in ("lead", "deputy"):
            grants = list(db.scalars(select(OrgRoleGrant).where(
                OrgRoleGrant.org_id == current, OrgRoleGrant.role == role
            )))
            candidates = set()
            for grant in grants:
                if current != org_id and not grant.include_children:
                    continue
                if grant.user_id:
                    candidates.add(grant.user_id)
                if grant.group_id:
                    candidates.update(db.scalars(select(GroupMember.user_id).where(
                        GroupMember.group_id == grant.group_id
                    )))
            active = [uid for uid in candidates if uid != reporter.id
                      and (u := db.get(User, uid)) is not None and u.active]
            if len(active) == 1:
                return active[0]
            if len(active) > 1:
                return None
        current = org.parent_id
    return None


def recipient(db, reporter, cat, org_id):
    if cat.routing == "lead":
        return supervisor(db, reporter, org_id)
    person = db.get(User, cat.assignee_id) if cat.assignee_id else None
    return person.id if person and person.active and person.id != reporter.id else None


def record(db, case, actor, kind, note=""):
    db.add(AnliegenEvent(anliegen_id=case.id, actor_id=actor.id if actor else None,
                        kind=kind, note=note[:500]))
    case.updated_at = utcnow()


def task_for(db, case):
    """A native task is created only for a successfully routed, non-confidential case.

    Complaints must not enter broad tasks_manage feeds. Native tasks are
    optional: internal case management remains functional without that module.
    """
    from .main import enabled_modules
    if case.confidential or not case.assignee_id or case.task_id or "tasks" not in enabled_modules():
        return None
    from .task_models import Task
    from . import tasks
    task = Task(title=case.title[:300],
                description=f"Interner Vorgang ANL-{case.id:06d}\n\n{case.description}",
                creator_id=case.reporter_id,
                assignee_id=case.assignee_id,
                status="open", priority="normal",
                source_type="anliegen", source_id=str(case.id), source_key=f"anliegen:{case.id}")
    db.add(task)
    db.flush()
    case.task_id = task.id
    reporter = db.get(User, case.reporter_id)
    tasks.audit(db, task, reporter, "created", "Aus einem internen Anliegen erstellt.")
    return task


def create(db, user, cat, title, description):
    title, description = title.strip(), description.strip()
    if not 3 <= len(title) <= 200 or not 5 <= len(description) <= 10_000:
        raise HTTPException(422, "Titel (3–200 Zeichen) und Beschreibung (5–10.000 Zeichen) erforderlich.")
    org_id = primary_org(db, user.id)
    assignee_id = recipient(db, user, cat, org_id)
    from .security import encrypt
    confidential = bool(cat.confidential)
    row = Anliegen(category_id=cat.id, reporter_id=user.id, org_id=org_id,
                   assignee_id=assignee_id, confidential=confidential,
                   title="Vertrauliches Anliegen" if confidential else title,
                   description="" if confidential else description,
                   title_enc=encrypt(title) if confidential else None,
                   description_enc=encrypt(description) if confidential else None,
                   status="open" if assignee_id else "unassigned")
    db.add(row)
    db.flush()
    record(db, row, user, "created",
           "Zuständige Person ermittelt." if assignee_id else "Noch keine eindeutige Zuständigkeit.")
    task_for(db, row)
    return row
