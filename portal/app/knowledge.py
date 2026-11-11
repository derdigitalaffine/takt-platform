"""Authorization and lifecycle for TAKT Wissen.

Capability checks are live and deny-first. Global permission alone never
exposes an organization's knowledge; organization membership/explicit grants
are additionally required. Excluded material never enters RAG by default.
"""
from datetime import datetime, timedelta

from sqlalchemy import select, update
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markupsafe import Markup

from .db import LOCAL_TZ, Group, GroupMember, Organization, User, get_settings, utcnow
from .org_models import OrgMembership
from .knowledge_models import (
    KnowledgeArticle, KnowledgeAudit, KnowledgeGrant, KnowledgeRevision,
    KnowledgeSpace, KnowledgeAmendmentRevision,
)
from . import organization

CAP_PERMS = {
    "read": "knowledge_read",
    "edit": "knowledge_edit",
    "publish": "knowledge_publish",
    "manage": "knowledge_manage",
    "ai": "knowledge_ai",
}
KINDS = {
    "article": "Wissensartikel",
    "process": "Prozessbeschreibung",
    "checklist": "Checkliste",
    "faq": "Fragen & Antworten",
    "experience": "Erfahrungswissen",
}
STATUSES = {"draft": "Entwurf", "review": "In Prüfung", "published": "Freigegeben"}
AUTHORITIES = {
    "unconfirmed": "Unbestätigte Information",
    "experience": "Erfahrungswissen",
    "verified": "Fachlich geprüft",
    "official": "Offiziell freigegeben",
    "binding": "Verbindliche Regelung",
}
# In P2 official/binding classification is only possible through the existing
# separate legal-text and circulation workflows; ordinary knowledge cannot
# proclaim itself a binding administrative rule.
EDITOR_AUTHORITIES = {"unconfirmed", "experience", "verified"}
_MD = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


def parse_markdown(raw: str | None):
    return _MD.parse(raw or "")


def render_markdown(raw: str | None, resolve_source=None) -> Markup:
    """Render Markdown and replace reserved reference labels using live ACLs."""
    from .knowledge_sources import REFERENCE

    tokens = parse_markdown(raw)
    sources = {}
    for token in tokens:
        if not token.children:
            continue
        rewritten = []
        children = iter(token.children)
        for child in children:
            href = child.attrGet("href") if child.type == "link_open" else None
            if not href or not REFERENCE.fullmatch(href):
                rewritten.append(child)
                continue
            if href not in sources:
                sources[href] = resolve_source(href) if resolve_source else None
            source = sources[href]
            for close in children:
                if close.type == "link_close":
                    break
            if source is None:
                rewritten.append(Token("text", "", 0, content="Quelle nicht verfügbar"))
                continue
            child.attrs.pop("title", None)
            rewritten.extend((child, Token("text", "", 0, content=source.label), close))
        token.children = rewritten
    return Markup(_MD.renderer.render(tokens, _MD.options, {}))


def remember_amendment(db, proposal, actor_id: int, action: str) -> None:
    """Keep a cycle-safe immutable trace of content edits versus workflow acts."""
    db.add(KnowledgeAmendmentRevision(
        article_id=proposal.article_id, version=proposal.version,
        base_version=proposal.base_version, title=proposal.title,
        kind=proposal.kind, body_md=proposal.body_md,
        status=proposal.status, action=action, actor_id=actor_id,
    ))



def active(db) -> bool:
    return get_settings(db).get("module_knowledge") == "1"


def _org_scope(db, user, org_id: int, *, include_children: bool) -> bool:
    """Membership/role scope, deliberately NOT global org-management permission."""
    ctx = organization.context(db, user)
    nodes = ctx["nodes"]
    root_path = organization.active_path(db, org_id, nodes)
    if not root_path:
        return False
    for assigned in ctx["own"]:
        path = organization.active_path(db, assigned, nodes)
        if path and (assigned == org_id or include_children and org_id in path):
            return True
    for grant in ctx["grants"]:
        if "view" not in organization.ROLES.get(grant.role, ("", set(), ""))[1]:
            continue
        assigned_path = organization.active_path(db, grant.org_id, nodes)
        if not assigned_path:
            continue
        # The user's role itself may apply to descendants.
        if (grant.org_id == org_id
                or grant.include_children and grant.org_id in root_path
                or include_children and org_id in assigned_path):
            return True
    return False


def _principal_matches(db, user, grant: KnowledgeGrant) -> bool:
    if grant.principal_kind == "user":
        return grant.principal_id == user.id
    if grant.principal_kind == "group":
        return db.scalar(select(GroupMember.user_id).where(
            GroupMember.user_id == user.id,
            GroupMember.group_id == grant.principal_id,
        ).limit(1)) is not None
    if grant.principal_kind == "org":
        return _org_scope(db, user, grant.principal_id,
                          include_children=grant.include_children)
    return False


def _grants(db, resource_kind: str, resource_id: int) -> list[KnowledgeGrant]:
    return list(db.scalars(select(KnowledgeGrant).where(
        KnowledgeGrant.resource_kind == resource_kind,
        KnowledgeGrant.resource_id == resource_id,
    )))


def _raw_allowed(db, user, space, cap: str, article=None) -> bool:
    """Direct ACL computation; deny always beats default and allow."""
    if cap not in CAP_PERMS or not user or not user.active or not active(db):
        return False
    if article is not None and article.space_id != space.id:
        return False
    if not user.can(CAP_PERMS[cap]):
        return False
    if user.is_admin:
        return True
    matched_space = [g for g in _grants(db, "space", space.id)
                     if _principal_matches(db, user, g)]
    matched_article = [g for g in _grants(db, "article", article.id)
                       if _principal_matches(db, user, g)] if article else []
    matched = matched_space + matched_article
    if any(g.effect == "deny" and g.capability in ({cap, "read"} if cap != "read" else {"read"})
           for g in matched):
        return False
    explicit_space = any(g.effect == "allow" and g.capability == cap for g in matched_space)
    explicit_article = any(g.effect == "allow" and g.capability == cap for g in matched_article)
    owner = space.owner_id == user.id or bool(article and article.owner_id == user.id)
    if article and article.scope == "restricted":
        return bool(explicit_article or article.owner_id == user.id)
    default = (cap in {"read", "edit", "publish"} and space.org_id is not None
               and _org_scope(db, user, space.org_id, include_children=False))
    return bool(owner or explicit_space or explicit_article or default)


def allowed(db, user, space, cap: str = "read", article=None) -> bool:
    if space is None:
        return False
    if not _raw_allowed(db, user, space, cap, article):
        return False
    # Non-read permissions also require at least the ability to read the object.
    if cap != "read" and not _raw_allowed(db, user, space, "read", article):
        return False
    if article is not None and article.status != "published" and cap == "read":
        # Mere read grants never disclose unpublished material.
        return bool(article.owner_id == user.id and user.can("knowledge_edit")
                    or _raw_allowed(db, user, space, "edit", article)
                    or _raw_allowed(db, user, space, "publish", article)
                    or _raw_allowed(db, user, space, "manage", article))
    return True


def can_create_space(db, user, org_id: int | None) -> bool:
    if not active(db) or not user or not user.active or not user.can("knowledge_manage") or not user.can("knowledge_read"):
        return False
    if user.is_admin:
        return org_id is None or bool(db.get(Organization, org_id))
    return (org_id is not None and db.get(Organization, org_id) is not None
            and _org_scope(db, user, org_id, include_children=False))


def record_revision(db, item: KnowledgeArticle, editor_id: int) -> None:
    db.add(KnowledgeRevision(
        article_id=item.id, version=item.version, title=item.title,
        body_md=item.body_md, status=item.status,
        authority=item.authority, review_due_on=item.review_due_on,
        editor_id=editor_id,
    ))


def audit(db, actor, space_id: int | None, article_id: int | None,
          action: str, detail: str = "") -> None:
    db.add(KnowledgeAudit(actor_id=actor.id, space_id=space_id,
                          article_id=article_id, action=action,
                          detail=detail[:255]))


def review_today():
    return datetime.now(LOCAL_TZ).date()


def publication_fields():
    now = utcnow()
    return dict(authority="verified", published_at=now, last_reviewed_at=now,
                review_due_on=review_today() + timedelta(days=365))


def can_approve_article(db, user, space, item):
    if (item.status != "review" or item.owner_id == user.id
            or not allowed(db, user, space, "publish", item)):
        return False
    return db.scalar(select(KnowledgeRevision.id).where(
        KnowledgeRevision.article_id == item.id,
        KnowledgeRevision.status == "draft",
        KnowledgeRevision.editor_id == user.id,
    ).limit(1)) is None


def can_approve_amendment(db, user, space, item, proposal):
    if (item.status != "published" or proposal.status != "review"
            or proposal.base_version != item.version
            or user.id in {proposal.creator_id, proposal.last_editor_id}
            or not allowed(db, user, space, "publish", item)):
        return False
    return db.scalar(select(KnowledgeAmendmentRevision.id).where(
        KnowledgeAmendmentRevision.article_id == item.id,
        KnowledgeAmendmentRevision.version >= proposal.cycle_start_version,
        KnowledgeAmendmentRevision.action.in_(("start", "edit")),
        KnowledgeAmendmentRevision.actor_id == user.id,
    ).limit(1)) is None


def can_confirm_review(db, user, space, item):
    return (item.status == "published" and item.owner_id != user.id
            and allowed(db, user, space, "publish", item))


def due_reviews(db, user, through):
    """Yield eligible published reviews in deadline order, including overdue items."""
    stmt = (select(KnowledgeArticle, KnowledgeSpace).join(KnowledgeSpace)
            .where(KnowledgeArticle.status == "published",
                   KnowledgeArticle.review_due_on <= through,
                   KnowledgeArticle.owner_id.is_distinct_from(user.id))
            .order_by(KnowledgeArticle.review_due_on, KnowledgeArticle.id))
    for item, space in db.execute(stmt.execution_options(yield_per=100)):
        if can_confirm_review(db, user, space, item):
            yield item, space


def has_due_review_reminder(db, user) -> bool:
    if (not user.knowledge_review_reminders or not user.can("knowledge_read")
            or not user.can("knowledge_publish") or not active(db)):
        return False
    return next(due_reviews(db, user, review_today()), None) is not None


def update_article(db, item, version, **fields):
    result = db.execute(update(KnowledgeArticle).where(
        KnowledgeArticle.id == item.id,
        KnowledgeArticle.version == version,
        KnowledgeArticle.status == item.status,
    ).values(version=version + 1, updated_at=utcnow(), **fields)
      .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        return False
    db.expire(item)
    return True


def principal_exists(db, kind: str, target_id: int) -> bool:
    model = {"user": User, "group": Group, "org": Organization}.get(kind)
    return bool(model and target_id > 0 and db.get(model, target_id) is not None)


def can_manage_space(db, user, space: KnowledgeSpace | None) -> bool:
    """Explicit, current, scoped management; portal-wide right alone is not enough."""
    return bool(space is not None and allowed(db, user, space, "manage"))


def eligible_subject(db, actor, space: KnowledgeSpace, target: User | None) -> bool:
    """Delegated managers may grant within the room's EXACT organization only.

    Explicitly do not infer other users' memberships from broad user-directory,
    inherited leadership, or shared groups.
    """
    if not target or not target.active or not actor or not can_manage_space(db, actor, space):
        return False
    if actor.is_admin:
        return True
    if space.org_id is None:
        return False
    return db.scalar(select(OrgMembership.id).where(
        OrgMembership.user_id == target.id,
        OrgMembership.org_id == space.org_id,
    ).limit(1)) is not None


def explain_space_access(db, target: User, space: KnowledgeSpace) -> list[dict]:
    """Trace rights for a manager's authorized subject; final verdict from allowed().

    Explanations never override runtime authorization.
    """
    rules = [g for g in _grants(db, "space", space.id)
             if _principal_matches(db, target, g)]
    own = space.owner_id == target.id
    org_member = bool(space.org_id and _org_scope(
        db, target, space.org_id, include_children=False
    ))
    descriptions = {
        "read": "Lesen", "edit": "Bearbeiten", "publish": "Freigeben",
        "manage": "Verwalten", "ai": "KI-Verarbeitung",
    }
    outcomes = []
    for capability, label in descriptions.items():
        permit = allowed(db, target, space, capability)
        matching_denies = [g for g in rules if g.effect == "deny"
                           and g.capability in {"read", capability}]
        matching_allows = [g for g in rules if g.effect == "allow"
                           and g.capability == capability]
        if not active(db):
            reason = "Modul ist ausgeschaltet."
        elif not target.active:
            reason = "Benutzerkonto ist deaktiviert."
        elif not target.can(CAP_PERMS[capability]):
            reason = "Globale TAKT-Berechtigung fehlt."
        elif target.is_admin:
            reason = "TAKT-Administration (plattformweite Ausnahme)."
        elif matching_denies:
            reason = "Explizite Sperre hat Vorrang vor Vererbung und Freigabe."
        elif capability != "read" and not _raw_allowed(db, target, space, "read"):
            reason = "Das notwendige Leserecht fehlt."
        elif matching_allows:
            reason = "Ausdrückliche Freigabe im Wissensraum."
        elif own:
            reason = "Eigentümer des Wissensraums."
        elif org_member and capability in {"read", "edit", "publish"}:
            reason = "Aktive Organisationszuordnung bzw. vererbte Organisationsrolle."
        else:
            reason = "Keine passende Berechtigung im Wissensraum."
        outcomes.append({"capability": capability, "label": label,
                         "allowed": permit, "reason": reason})
    return outcomes
