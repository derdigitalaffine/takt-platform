"""Versioned, scoped internal process configuration and launch policy.

The global integration switch stays OFF until explicitly enabled by a portal
administrator. ACL checks are intentionally separate from the application-form
process editor; no implicit escalation from a module permission to org scope.
"""
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import anliegen as cases, organization
from . import anliegen_processes as policies
from .anliegen_models import Anliegen, AnliegenCategory
from .anliegen_process_models import (
    AnliegenProcessRule, AnliegenProcessRuleEvent, AnliegenProcessRun,
)
from .anliegen_process_engine import (
    ProcessAccessDenied, ProcessConflict, ProcessEngineError, request_start,
    validate_internal_version,
)
from .db import Organization, Process, ProcessVersion, User, utcnow


def can_configure(db: Session, user: User, org_id: int | None) -> bool:
    if not user or not user.active:
        return False
    if user.is_admin:
        return True
    return bool(org_id is not None and user.can("anliegen_process_configure")
                and (organization.allows(db, user, org_id, "plan")
                     or organization.allows(db, user, org_id, "settings")))


def can_approve_config(db: Session, user: User, org_id: int | None) -> bool:
    if not user or not user.active:
        return False
    if user.is_admin:
        return True
    return bool(org_id is not None and user.can("anliegen_process_approve")
                and organization.allows(db, user, org_id, "approve"))


def can_approve_run(db: Session, user: User, case: Anliegen) -> bool:
    """An approval right and case-handler or explicit org approval authority."""
    return bool(user and user.active and not case.confidential
                and user.can("anliegen_process_approve")
                and (cases.can_handle(user, case)
                     or (case.org_id is not None and
                         organization.allows(db, user, case.org_id, "approve"))))


def require_rule_access(db: Session, actor: User, rule: AnliegenProcessRule,
                        *, approval=False) -> None:
    if not rule or not (
        (can_approve_config(db, actor, rule.org_id) if approval
         else can_configure(db, actor, rule.org_id))
    ):
        raise HTTPException(403, "Keine Berechtigung für diese Prozesskonfiguration.")


def scoped_org(db: Session, actor: User, org_id: int | None, *, approval=False):
    if org_id is None:
        if not actor.is_admin:
            raise HTTPException(403, "Übergreifende Regeln sind der Administration vorbehalten.")
        return None
    org = db.get(Organization, org_id)
    if not org or not org.active:
        raise HTTPException(422, "Organisationseinheit nicht verfügbar.")
    allowed = (can_approve_config(db, actor, org_id) if approval
               else can_configure(db, actor, org_id))
    if not allowed:
        raise HTTPException(403, "Keine Zuständigkeit für diese Organisationseinheit.")
    return org


def process_choices(db: Session, actor: User):
    """Process names are not disclosed to users without editor/owner privileges."""
    if not actor or not actor.active:
        return []
    q = select(Process).where(Process.versions.any())
    if not actor.can("processes"):
        q = q.where(Process.owner_id == actor.id)
    return list(db.scalars(q.order_by(Process.name, Process.id)))


def _event(db: Session, rule: AnliegenProcessRule, actor: User, action: str):
    db.add(AnliegenProcessRuleEvent(rule_id=rule.id, actor_id=actor.id,
                                   kind=action, revision=rule.revision,
                                   process_version_id=rule.process_version_id))


def _latest_version(db: Session, process: Process) -> ProcessVersion:
    if not process:
        raise HTTPException(422, "Prozess nicht gefunden.")
    version = process.current
    try:
        validate_internal_version(version)
    except ProcessEngineError as exc:
        raise HTTPException(422, str(exc)) from exc
    return version


def create_draft(db: Session, actor: User, category_id: int, process_id: int,
                 org_id: int | None, policy: dict) -> AnliegenProcessRule:
    scoped_org(db, actor, org_id)
    category = db.get(AnliegenCategory, category_id)
    if not category or category.confidential:
        raise HTTPException(422, "Die Kategorie ist nicht für Prozesse freigegeben.")
    proc = db.get(Process, process_id)
    if proc not in process_choices(db, actor):
        raise HTTPException(403, "Dieser Prozess darf nicht konfiguriert werden.")
    _latest_version(db, proc)
    try:
        normalized = policies.normalize_policy(policy)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if not normalized["start_modes"]:
        raise HTTPException(422, "Wähle mindestens eine erlaubte Startart.")
    if org_id is not None and "auto" in normalized["start_modes"]:
        # The current engine requires a privileged service actor. Scoped
        # background execution needs a separate service principal in #293.
        raise HTTPException(422, "Automatischer Start ist derzeit nur für globale Regeln zulässig.")
    rev = (db.scalar(select(func.max(AnliegenProcessRule.revision)).where(
        AnliegenProcessRule.category_id == category_id,
        AnliegenProcessRule.process_id == process_id,
        AnliegenProcessRule.org_id.is_(None) if org_id is None
        else AnliegenProcessRule.org_id == org_id)) or 0) + 1
    rule = AnliegenProcessRule(
        category_id=category_id, process_id=process_id, org_id=org_id,
        revision=rev, state="draft",
        policy_json=json.dumps(normalized, ensure_ascii=False),
        created_by_id=actor.id)
    db.add(rule)
    db.flush()
    _event(db, rule, actor, "draft_created")
    return rule


def update_draft(db: Session, rule: AnliegenProcessRule, actor: User, policy: dict):
    require_rule_access(db, actor, rule)
    if rule.state != "draft":
        raise HTTPException(409, "Nur Entwürfe sind änderbar. Bitte eine neue Revision erstellen.")
    try:
        normalized = policies.normalize_policy(policy)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if not normalized["start_modes"]:
        raise HTTPException(422, "Bitte eine Startart wählen.")
    if rule.org_id is not None and "auto" in normalized["start_modes"]:
        raise HTTPException(422, "Automatik für organisationsbezogene Regeln ist noch nicht freigegeben.")
    rule.policy_json = json.dumps(normalized, ensure_ascii=False)
    rule.updated_at = utcnow()
    _event(db, rule, actor, "draft_updated")


def submit_review(db: Session, rule: AnliegenProcessRule, actor: User):
    require_rule_access(db, actor, rule)
    if rule.state != "draft":
        raise HTTPException(409, "Nur Entwürfe können zur Prüfung eingereicht werden.")
    _latest_version(db, db.get(Process, rule.process_id))
    policy = policies.normalize_policy(json.loads(rule.policy_json or "{}"))
    if not policy["start_modes"]:
        raise HTTPException(422, "Mindestens eine Startart ist erforderlich.")
    rule.state = "review"
    rule.updated_at = utcnow()
    _event(db, rule, actor, "review_requested")


def approve(db: Session, rule: AnliegenProcessRule, actor: User):
    require_rule_access(db, actor, rule, approval=True)
    if rule.state != "review":
        raise HTTPException(409, "Nur geprüfte Regeln können aktiviert werden.")
    if rule.created_by_id == actor.id:
        raise HTTPException(403, "Vier-Augen-Prinzip: Eigene Prozessregeln dürfen nicht selbst genehmigt werden.")
    category = db.get(AnliegenCategory, rule.category_id)
    if not category or category.confidential:
        raise HTTPException(422, "Vertrauliche Kategorien sind ausgeschlossen.")
    version = _latest_version(db, db.get(Process, rule.process_id))
    try:
        policy = policies.normalize_policy(json.loads(rule.policy_json or "{}"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Ungültige Prozessregel.") from exc
    if rule.org_id is not None and "auto" in policy["start_modes"]:
        raise HTTPException(422, "Automatik für organisationsbezogene Regeln ist noch nicht freigegeben.")
    if "auto" in policy["start_modes"] and not actor.can("anliegen_manage"):
        raise HTTPException(403, "Automatische Starts benötigen eine berechtigte Verwaltungsidentität.")
    # One active revision per category, process and exact organizational scope.
    active = list(db.scalars(select(AnliegenProcessRule).where(
        AnliegenProcessRule.id != rule.id,
        AnliegenProcessRule.category_id == rule.category_id,
        AnliegenProcessRule.process_id == rule.process_id,
        AnliegenProcessRule.org_id.is_(None) if rule.org_id is None
        else AnliegenProcessRule.org_id == rule.org_id,
        AnliegenProcessRule.state == "active")))
    for old in active:
        old.state, old.updated_at = "retired", utcnow()
        _event(db, old, actor, "superseded")
    rule.process_version_id = version.id
    rule.approved_by_id = actor.id
    rule.state, rule.updated_at = "active", utcnow()
    _event(db, rule, actor, "activated")


def revise(db: Session, rule: AnliegenProcessRule, actor: User) -> AnliegenProcessRule:
    require_rule_access(db, actor, rule)
    if rule.state not in ("review", "active", "retired"):
        raise HTTPException(409, "Die Regel ist bereits als Entwurf bearbeitbar.")
    return create_draft(db, actor, rule.category_id, rule.process_id,
                        rule.org_id, json.loads(rule.policy_json))


def retire(db: Session, rule: AnliegenProcessRule, actor: User):
    require_rule_access(db, actor, rule, approval=True)
    if rule.state != "active":
        raise HTTPException(409, "Nur aktive Regeln können deaktiviert werden.")
    rule.state, rule.updated_at = "retired", utcnow()
    _event(db, rule, actor, "retired")


def applicable(db: Session, category_id: int, org_id: int | None,
               *, origin: str) -> list[AnliegenProcessRule]:
    """Org-specific rules override global rules for the same process."""
    if not policies.integration_enabled(db):
        return []
    q = select(AnliegenProcessRule).where(
        AnliegenProcessRule.category_id == category_id,
        AnliegenProcessRule.state == "active",
        AnliegenProcessRule.approved_by_id.is_not(None),
        AnliegenProcessRule.process_version_id.is_not(None))
    q = q.where(AnliegenProcessRule.org_id.is_(None) if org_id is None else
                or_(AnliegenProcessRule.org_id == org_id,
                    AnliegenProcessRule.org_id.is_(None)))
    selected = {}
    rules = sorted(db.scalars(q), key=lambda v: (
        v.org_id != org_id if org_id is not None else False,
        -v.revision, -v.id))
    for rule in rules:
        if rule.process_id in selected:
            continue
        try:
            policy = policies.normalize_policy(json.loads(rule.policy_json))
        except (TypeError, ValueError):
            continue
        # If an org-scoped active rule overrides a global one, the disabled
        # start mode is deliberately NOT inherited from the global rule.
        selected[rule.process_id] = (rule, policy)
    return [rule for rule, policy in selected.values()
            if origin in policy["start_modes"]]


def allowed_for_submit(db: Session, category_id: int, org_id: int | None, actor: User):
    if not actor or not actor.active or not actor.can("anliegen_submit") or not actor.can("anliegen_process_start"):
        return []
    cat = db.get(AnliegenCategory, category_id)
    if not cat or cat.confidential or not cat.enabled:
        return []
    return applicable(db, category_id, org_id, origin="submit")


def allowed_for_handler(db: Session, case: Anliegen, actor: User):
    if not actor or not actor.active or not actor.can("anliegen_process_start"):
        return []
    if case.confidential or not cases.can_handle(actor, case):
        return []
    return applicable(db, case.category_id, case.org_id, origin="handler")


def launch(db: Session, case: Anliegen, rule_id: int, actor: User,
           *, origin: str, token: str):
    """The only HTTP-facing start adapter, enforcing separate explicit grants."""
    if origin == "submit":
        allowed = allowed_for_submit(db, case.category_id, case.org_id, actor)
        if actor.id != case.reporter_id:
            raise HTTPException(403, "Nur die einreichende Person darf diesen Prozess auswählen.")
    elif origin == "handler":
        allowed = allowed_for_handler(db, case, actor)
    elif origin == "auto":
        allowed = applicable(db, case.category_id, case.org_id, origin="auto")
        rule = db.get(AnliegenProcessRule, rule_id)
        if (not rule or rule not in allowed or rule.approved_by_id != actor.id
                or not actor.active or not actor.can("anliegen_manage")):
            raise HTTPException(403, "Automatischer Start nicht autorisiert.")
    else:
        raise HTTPException(422, "Unbekannte Startart.")
    if not any(rule.id == rule_id for rule in allowed):
        raise HTTPException(403, "Dieser Prozess darf für das Anliegen nicht gestartet werden.")
    if not isinstance(token, str) or not (16 <= len(token) <= 64) or not token.isascii() or any(
            c not in "0123456789abcdef-" for c in token):
        raise HTTPException(422, "Ungültiger Prozessstartschlüssel.")
    key = f"anliegen:{case.id}:rule:{rule_id}:{token}"
    try:
        return request_start(db, case, db.get(AnliegenProcessRule, rule_id),
                             actor, origin=origin, launch_key=key)
    except ProcessAccessDenied as exc:
        raise HTTPException(403, str(exc)) from exc
    except ProcessConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ProcessEngineError as exc:
        raise HTTPException(422, str(exc)) from exc


def start_auto(db: Session, case: Anliegen, actor: User) -> list[AnliegenProcessRun]:
    """Auto starts are scoped and idempotent, using explicit rule approver.

    Deliberately no implicit default enabled. Failing auto start leaves the
    Anliegen intact, reports a generic failure in its existing audit and never
    widens confidentiality.
    """
    started = []
    if case.confidential:
        return started
    for rule in applicable(db, case.category_id, case.org_id, origin="auto"):
        service_actor = db.get(User, rule.approved_by_id)
        if not service_actor or not service_actor.active:
            cases.record(db, case, actor, "process", "Automatischer Start: freigebende Person nicht verfügbar.")
            continue
        try:
            with db.begin_nested():
                run = launch(db, case, rule.id, service_actor, origin="auto",
                             token=uuid4().hex if False else f"{case.id:016x}{rule.id:016x}")
            started.append(run)
        except HTTPException:
            cases.record(db, case, actor, "process", "Automatischer Prozessstart nicht möglich.")
    return started
