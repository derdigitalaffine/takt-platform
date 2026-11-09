"""Authorization and lifecycle for TAKT Wissen.

Capability checks are live and deny-first. Global permission alone never
exposes an organization's knowledge; organization membership/explicit grants
are additionally required. Excluded material never enters RAG by default.
"""
from sqlalchemy import select

from .db import Group, GroupMember, Organization, User, get_settings, utcnow
from .knowledge_models import (
    KnowledgeArticle, KnowledgeAudit, KnowledgeGrant, KnowledgeRevision,
    KnowledgeSpace,
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
        body_md=item.body_md, status=item.status, editor_id=editor_id,
    ))


def audit(db, actor, space_id: int | None, article_id: int | None,
          action: str, detail: str = "") -> None:
    db.add(KnowledgeAudit(actor_id=actor.id, space_id=space_id,
                          article_id=article_id, action=action,
                          detail=detail[:255]))


def change_status(db, item: KnowledgeArticle, actor, status: str) -> None:
    if status not in STATUSES:
        raise ValueError("Unbekannter Status")
    item.status = status
    item.version += 1
    item.updated_at = utcnow()
    record_revision(db, item, actor.id)
    audit(db, actor, item.space_id, item.id, "status", status)


def principal_exists(db, kind: str, target_id: int) -> bool:
    model = {"user": User, "group": Group, "org": Organization}.get(kind)
    return bool(model and target_id > 0 and db.get(model, target_id) is not None)
