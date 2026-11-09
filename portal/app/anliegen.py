"""Internal intake workflow, category-based routing, and safe native task linkage."""
import re
from sqlalchemy import select, or_
from fastapi import HTTPException

from .db import GroupMember, Organization, User, Setting, utcnow
from .org_models import OrgMembership, OrgRoleGrant
from .anliegen_models import Anliegen, AnliegenCategory, AnliegenEvent

DEFAULT_CATEGORIES = (
    ("office_supply", "Büromaterial", "Verbrauchsmaterial und allgemeine Bestellungen", "fa-paperclip", "person", False),
    ("office_furniture", "Büromöbel", "Möbelbeschaffung und Ausstattung", "fa-chair", "person", False),
    ("it_procurement", "IT-Beschaffung", "Hardware, Zubehör, Softwarelizenzen und IT-Ausstattung bestellen", "fa-laptop", "person", False),
    ("defect", "Mangel melden", "Defekte, Schäden und Störungen", "fa-screwdriver-wrench", "person", False),
    ("complaint", "Vertrauliche Beschwerde", "Vertrauliche Meldung an die zuständige Leitung", "fa-shield-halved", "lead", True),
    ("improvement", "Verbesserungsvorschlag", "Ideen und Verbesserungen des Arbeitsalltags", "fa-lightbulb", "person", False),
    ("platform_feedback", "TAKT verbessern", "Fehler, Bedienbarkeit, fehlende Funktionen und Verbesserungsvorschläge zur TAKT-Plattform", "fa-wand-magic-sparkles", "person", False),
    ("other", "Sonstiges Anliegen", "Andere interne Anliegen", "fa-inbox", "person", False),
)
DEFAULT_TAGS = {
    "office_supply": "büromaterial,verbrauchsmaterial,papier,stifte,druckerzubehör",
    "office_furniture": "büromöbel,stuhl,schreibtisch,ausstattung",
    "it_procurement": "it-beschaffung,hardware,software,lizenz,notebook,monitor,zubehör",
    "defect": "mangel,defekt,reparatur,schaden,störung",
    "complaint": "vertraulich,beschwerde,personal,schutz",
    "improvement": "verbesserung,idee,optimierung,arbeitsablauf",
    "platform_feedback": "takt,software,fehler,benutzerführung,feature",
    "other": "sonstiges,anliegen,allgemein",
}
ORDER_KEYS = frozenset({"office_supply", "office_furniture", "it_procurement"})


def normalize_tags(value):
    """Safe, predictable metadata for matching LLM category suggestions."""
    if len(value) > 1000:
        raise HTTPException(422, "Die Schlagwortliste ist zu lang.")
    result, seen = [], set()
    for raw in re.split(r"[,;\\n]+", value):
        tag = " ".join(raw.strip().lstrip("#").split()).casefold()
        if not tag:
            continue
        if len(tag) > 40 or not re.fullmatch(r"[\\w][\\w .-]*", tag):
            raise HTTPException(422, "Schlagwörter dürfen höchstens 40 Zeichen und nur Buchstaben, Zahlen, Leerzeichen, Punkte oder Bindestriche enthalten.")
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    if len(result) > 15:
        raise HTTPException(422, "Maximal 15 Schlagwörter pro Kategorie.")
    return ",".join(result)


def validate_category_fields(title, description, routing, assignee_id, db):
    title, description = title.strip(), description.strip()
    if not 3 <= len(title) <= 120 or len(description) > 255:
        raise HTTPException(422, "Ungültige Kategorienbezeichnung oder Beschreibung.")
    if routing not in ("person", "lead"):
        raise HTTPException(422, "Unbekannte Zuständigkeitsregel.")
    if routing == "person" and assignee_id:
        who = db.get(User, assignee_id)
        if not who or not who.active:
            raise HTTPException(422, "Zuständige Person nicht verfügbar.")
    return title, description

STATUSES = {
    "unassigned": "Zuständigkeit offen",
    "open": "Offen",
    "in_progress": "In Bearbeitung",
    "waiting": "Warten auf Rückmeldung",
    "ordered": "Beim Lieferanten bestellt",
    "partially_delivered": "Teilweise geliefert",
    "delivered": "Geliefert",
    "done": "Erledigt",
    "cancelled": "Abgebrochen",
    "closed": "Geschlossen",
}
NEXT = {
    "unassigned": {"open", "closed"},
    "open": {"in_progress", "waiting", "done", "cancelled", "closed", "ordered"},
    "in_progress": {"open", "waiting", "ordered", "done", "cancelled", "closed"},
    "waiting": {"open", "in_progress", "ordered", "done", "cancelled", "closed"},
    "ordered": {"partially_delivered", "delivered", "waiting", "cancelled"},
    "partially_delivered": {"ordered", "delivered", "waiting", "cancelled"},
    "delivered": {"done", "closed", "in_progress"},
    "done": {"in_progress", "closed"},
    "cancelled": {"open", "closed"},
    "closed": set(),
}
ORDER_STATES = {"ordered", "partially_delivered", "delivered"}


def next_states(case):
    options = NEXT.get(case.status, set())
    if case.category.key not in ORDER_KEYS:
        options = options - ORDER_STATES
    return options


def update_status(db, case, actor, new_status, *, supplier="", order_reference="",
                  expected_delivery_at=None):
    """Centralize transition checks and native task synchronization."""
    if new_status not in next_states(case) or (new_status != "closed" and not case.assignee_id):
        raise HTTPException(422, "Dieser Statuswechsel ist nicht zulässig.")
    if new_status in ORDER_STATES and case.category.key not in ORDER_KEYS:
        raise HTTPException(422, "Lieferstatus nur für Bestellungen verfügbar.")
    if case.category.key in ORDER_KEYS:
        # Allow correcting supplier/reference during later delivery steps.
        case.supplier = supplier.strip()[:160] or case.supplier
        case.order_reference = order_reference.strip()[:120] or case.order_reference
        if expected_delivery_at is not None:
            case.expected_delivery_at = expected_delivery_at
    if new_status == "ordered":
        case.ordered_at = case.ordered_at or utcnow()
    if new_status == "delivered":
        case.delivered_at = utcnow()
    case.status = new_status
    record(db, case, actor, "status", f"Status: {STATUSES[new_status]}")
    if case.task_id:
        from .task_models import Task
        from . import tasks
        task = db.get(Task, case.task_id)
        if task:
            old_task_status = task.status
            task.status = ("done" if new_status in ("done", "closed")
                           else "open" if new_status == "open"
                           else "in_progress")
            if task.status == "done":
                task.completed_at = utcnow()
                task.completed_by = actor.id
            elif old_task_status == "done":
                task.completed_at = None
                task.completed_by = None
            tasks.audit(db, task, actor, "status",
                        f"Status des Anliegens: {STATUSES[new_status]}")
            if task.status != old_task_status:
                db.flush()
                from . import task_rules
                task_rules.emit(db, task, "status_changed",
                                f"anliegen-status:{case.id}:{new_status}:{task.version}")
    return case


def seed(db):
    # One-time backfill: subsequent admin edits (including clearing all tags) win.
    already_seeded = db.get(Setting, "anliegen_category_tags_seeded") is not None
    for position, (key, title, desc, icon, route, secret) in enumerate(DEFAULT_CATEGORIES):
        cat = db.scalar(select(AnliegenCategory).where(AnliegenCategory.key == key))
        if cat is None:
            db.add(AnliegenCategory(key=key, title=title, description=desc, tags=DEFAULT_TAGS.get(key, ""),
                                   icon=icon, routing=route, confidential=secret, enabled=True,
                                   position=position))
        elif not already_seeded and not cat.tags:
            cat.tags = DEFAULT_TAGS.get(key, "")
    if not already_seeded:
        db.add(Setting(key="anliegen_category_tags_seeded", value="1"))


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
    # A department owner can legitimately file and process their own request.
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
    if task.assignee_id != case.reporter_id:
        tasks.ping(db, task, [task.assignee_id], "Neues internes Anliegen")
    from . import task_rules
    task_rules.emit(db, task, "created", f"anliegen-created:{task.id}")
    return task


def create(db, user, cat, title, description):
    title, description = title.strip(), description.strip()
    if not 3 <= len(title) <= 200 or not 5 <= len(description) <= 10_000:
        raise HTTPException(422, "Titel (3–200 Zeichen) und Beschreibung (5–10.000 Zeichen) erforderlich.")
    org_id = primary_org(db, user.id)
    assignee_id = recipient(db, user, cat, org_id)
    from .security import encrypt
    is_private = bool(cat.confidential)
    row = Anliegen(category_id=cat.id, reporter_id=user.id, org_id=org_id,
                   assignee_id=assignee_id, confidential=is_private,
                   title="Vertrauliches Anliegen" if is_private else title,
                   description="" if is_private else description,
                   title_enc=encrypt(title) if is_private else None,
                   description_enc=encrypt(description) if is_private else None,
                   status="open" if assignee_id else "unassigned")
    db.add(row)
    db.flush()
    record(db, row, user, "created",
           "Zuständige Person ermittelt." if assignee_id else "Noch keine eindeutige Zuständigkeit.")
    task_for(db, row)
    return row


def reroute_unassigned(db, category_row, actor=None):
    """Re-evaluate only unresolved cases after an administrator saves a rule.

    Historical assignments never change silently. Confidential cases remain
    private and are not promoted into the general task management module.
    """
    cases = list(db.scalars(select(Anliegen).where(
        Anliegen.category_id == category_row.id,
        Anliegen.status == "unassigned",
        Anliegen.assignee_id.is_(None),
    ).order_by(Anliegen.id).limit(300)))
    count = 0
    if not category_row.enabled:
        return count
    for case in cases:
        reporter = db.get(User, case.reporter_id)
        if not reporter or not reporter.active:
            continue
        receiver = recipient(db, reporter, category_row, case.org_id)
        if not receiver:
            continue
        case.assignee_id = receiver
        case.status = "open"
        record(db, case, actor, "routing", "Zuständigkeit nach Aktualisierung der Kategorie ermittelt.")
        task_for(db, case)
        count += 1
    return count


def routing_preview(db, user, cat):
    """Resolve routing without side effects; used before submission."""
    org_id = primary_org(db, user.id)
    uid = recipient(db, user, cat, org_id)
    person = db.get(User, uid) if uid is not None else None
    if person is not None and person.active:
        return {"ready": True, "recipient": person.name,
                "message": ("Die Leitung Ihrer Organisation" if cat.routing == "lead"
                            else "Die festgelegte zuständige Person")}
    return {"ready": False, "recipient": None,
            "message": ("Keine eindeutige Leitung für Ihre primäre Organisation gefunden."
                        if cat.routing == "lead"
                        else "Noch keine aktive zuständige Person für diese Kategorie hinterlegt.")}


def reassign_open(db, cat, actor):
    """Explicit administrative migration for already assigned, unfinished cases.

    Never silently touch confidential cases, historical completions or other
    categories. Repoint a native task and notify the new owner only on change.
    """
    if cat.confidential or not cat.enabled:
        return 0
    cases = list(db.scalars(select(Anliegen).where(
        Anliegen.category_id == cat.id,
        Anliegen.confidential.is_(False),
        Anliegen.status.not_in(("done", "closed", "cancelled")),
        Anliegen.assignee_id.is_not(None),
    ).order_by(Anliegen.id).limit(300)))
    count = 0
    for case in cases:
        reporter = db.get(User, case.reporter_id)
        if not reporter or not reporter.active:
            continue
        receiver = recipient(db, reporter, cat, case.org_id)
        if not receiver or receiver == case.assignee_id:
            continue
        case.assignee_id = receiver
        record(db, case, actor, "routing", "Bestehende Zuständigkeit nach ausdrücklicher Freigabe angepasst.")
        if case.task_id:
            from .task_models import Task
            from . import tasks
            task = db.get(Task, case.task_id)
            if task:
                task.assignee_id = receiver
                tasks.audit(db, task, actor, "assignment", "Zuständigkeit aus Anliegenverwaltung aktualisiert.")
                tasks.ping(db, task, [receiver], "Internes Anliegen wurde Ihnen zugewiesen")
        else:
            task_for(db, case)
        count += 1
    return count


def sync_from_native_task(db, task, actor, *, assignment=False, status=False):
    """Maintain the single linked Anliegen when a native task is edited directly.

    Confidential concerns have no native task. Do not override procurement
    fulfillment states merely because someone begins work on the task.
    """
    if task.source_type != "anliegen":
        return
    case = db.scalar(select(Anliegen).where(Anliegen.task_id == task.id))
    if case is None or case.confidential:
        return
    if assignment and task.assignee_id and task.assignee_id != case.assignee_id:
        case.assignee_id = task.assignee_id
        record(db, case, actor, "assignment", "Zuständigkeit über die verknüpfte Aufgabe geändert.")
    if status:
        target = {"done": "done", "cancelled": "cancelled",
                  "in_progress": "in_progress", "open": "open"}.get(task.status)
        if target is None:
            return
        if case.status in ORDER_STATES and target in {"open", "in_progress"}:
            return  # Delivery state has more meaning than task activity.
        if case.status != target and target in next_states(case):
            case.status = target
            record(db, case, actor, "status",
                   f"Aus verknüpfter Aufgabe übernommen: {STATUSES[target]}")
