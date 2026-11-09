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
    ("platform_feedback", "TAKT & Software verbessern", "Fehler, Bedienbarkeit und Verbesserungswünsche für TAKT und andere Verwaltungssoftware", "fa-code-branch", "person", False),
    ("other", "Sonstiges Anliegen", "Andere interne Anliegen", "fa-inbox", "person", False),
)
STATUSES = {"unassigned": "Zuständigkeit offen", "open": "Offen",
            "in_progress": "In Bearbeitung", "ordered": "Beim Lieferanten bestellt",
            "partially_delivered": "Teilgeliefert", "delivered": "Geliefert",
            "done": "Erledigt", "closed": "Geschlossen"}
NEXT = {"unassigned": {"open", "closed"}, "open": {"in_progress", "done", "closed"},
        "in_progress": {"open", "done", "closed"}, "done": {"in_progress", "closed"},
        "closed": set()}
PROCUREMENT_NEXT = {
    "open": {"in_progress", "ordered", "closed"},
    "in_progress": {"open", "ordered", "done", "closed"},
    "ordered": {"partially_delivered", "delivered", "in_progress", "closed"},
    "partially_delivered": {"delivered", "in_progress", "closed"},
    "delivered": {"done", "in_progress", "closed"},
}
PROCUREMENT_KEYS = {"office_supply", "office_furniture"}


def choices(case):
    """Allowed next statuses for this category, not a global one-size-fits-all list."""
    if case.category.procurement and not case.confidential:
        return PROCUREMENT_NEXT.get(case.status, NEXT.get(case.status, set()))
    return NEXT.get(case.status, set())


def task_status(status):
    """Map supply-chain stages to the supported native task state machine."""
    if status in ("ordered", "partially_delivered", "delivered"):
        return "in_progress"
    if status in ("done", "closed"):
        return "done"
    return status


def seed(db):
    for position, (key, title, desc, icon, route, secret) in enumerate(DEFAULT_CATEGORIES):
        if not db.scalar(select(AnliegenCategory.id).where(AnliegenCategory.key == key)):
            db.add(AnliegenCategory(key=key, title=title, description=desc, icon=icon,
                                   routing=route, confidential=secret, procurement=key in PROCUREMENT_KEYS, enabled=True,
                                   position=position))


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
    primary = db.scalar(select(OrgMembership.org_id).where(
        OrgMembership.user_id == user_id, OrgMembership.is_primary.is_(True)
    ))
    if primary:
        return primary
    # A single membership is unambiguous even where no primary flag was set.
    memberships = list(db.scalars(select(OrgMembership.org_id).where(
        OrgMembership.user_id == user_id).limit(2)))
    return memberships[0] if len(memberships) == 1 else None


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
    # The material coordinator may raise requests for their own department.
    return person.id if person and person.active else None


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
    if case.assignee_id != case.reporter_id:
        tasks.ping(db, task, [case.assignee_id], "Ein internes Anliegen wurde Ihnen zugewiesen")
    from .main import _badge_cache
    _badge_cache.clear()
    return task


def create(db, user, cat, title, description):
    title, description = title.strip(), description.strip()
    if not 3 <= len(title) <= 200 or not 5 <= len(description) <= 10_000:
        raise HTTPException(422, "Titel (3–200 Zeichen) und Beschreibung (5–10.000 Zeichen) erforderlich.")
    org_id = primary_org(db, user.id)
    assignee_id = recipient(db, user, cat, org_id)
    row = Anliegen(category_id=cat.id, reporter_id=user.id, org_id=org_id,
                   assignee_id=assignee_id, confidential=cat.confidential,
                   title=title, description=description,
                   status="open" if assignee_id else "unassigned")
    db.add(row)
    db.flush()
    record(db, row, user, "created",
           "Zuständige Person ermittelt." if assignee_id else "Noch keine eindeutige Zuständigkeit.")
    task_for(db, row)
    return row



def set_status(db, case, actor, status, *, supplier="", reference=""):
    """Atomic case/task transition with a single validated policy."""
    from .task_models import Task
    from . import tasks
    if status not in choices(case) or (not case.assignee_id and status != "closed"):
        raise HTTPException(422, "Dieser Statuswechsel ist nicht zulässig.")
    if status in {"ordered", "partially_delivered", "delivered"} and not case.category.procurement:
        raise HTTPException(422, "Bestellstatus sind nur für Beschaffungskategorien verfügbar.")
    supplier, reference = supplier.strip(), reference.strip()
    if len(supplier) > 160 or len(reference) > 160:
        raise HTTPException(422, "Lieferant und Bestellreferenz dürfen je höchstens 160 Zeichen enthalten.")
    if case.category.procurement:
        if supplier:
            case.supplier_name = supplier
        if reference:
            case.order_reference = reference
    case.status = status
    record(db, case, actor, "status", f"Status: {STATUSES[status]}")
    if case.task_id:
        task = db.get(Task, case.task_id)
        if task:
            task.status = task_status(status)
            tasks.audit(db, task, actor, "status", "Liefer-/Bearbeitungsstatus aus internen Anliegen aktualisiert.")
    from .main import _badge_cache
    _badge_cache.clear()


def reconcile_category(db, cat, actor, *, reassign: bool = False):
    """Apply current rules to unassigned cases (or explicitly transfer open ones).

    Confidential cases are excluded: retrospective reassignment would disclose
    private complaints to new staff without an explicit per-case decision.
    """
    if cat.confidential:
        raise HTTPException(403, "Vertrauliche Beschwerden dürfen nicht massenhaft umverteilt werden.")
    from .task_models import Task
    from . import tasks
    from .main import _badge_cache
    rows = list(db.scalars(select(Anliegen).where(
        Anliegen.category_id == cat.id, Anliegen.confidential.is_(False),
        Anliegen.status.not_in(("done", "closed")),
    ).order_by(Anliegen.id).limit(1000)))
    counts = {"assigned": 0, "transferred": 0, "unchanged": 0, "unresolved": 0}
    for case in rows:
        if case.assignee_id and not reassign:
            counts["unchanged"] += 1
            continue
        reporter = db.get(User, case.reporter_id)
        if not reporter or not reporter.active:
            counts["unresolved"] += 1
            continue
        target_id = recipient(db, reporter, cat, case.org_id or primary_org(db, reporter.id))
        if target_id is None:
            counts["unresolved"] += 1
            continue
        if case.assignee_id == target_id:
            counts["unchanged"] += 1
            continue
        old_id = case.assignee_id
        case.assignee_id = target_id
        if case.status == "unassigned":
            case.status = "open"
        record(db, case, actor, "assignment", "Automatisch anhand der gespeicherten Kategorie-Regel zugewiesen.")
        if case.task_id:
            task = db.get(Task, case.task_id)
            if task:
                task.assignee_id = target_id
                tasks.audit(db, task, actor, "assigned", "Zuständigkeit aus internen Anliegen aktualisiert.")
                if old_id != target_id:
                    tasks.ping(db, task, [target_id], "Ein internes Anliegen wurde Ihnen neu zugewiesen")
        else:
            task_for(db, case)
        counts["transferred" if old_id else "assigned"] += 1
    _badge_cache.clear()
    return counts
