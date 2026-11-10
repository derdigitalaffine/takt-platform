"""Scoped Wissensraum administration and human-facing, ACL-filtered review inbox.

No external calls, scheduled contacts, AI indexing, or global user-directory
access for delegated room administrators.
"""
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import knowledge as km
from .db import LOCAL_TZ, Group, Organization, User
from .knowledge_models import (
    KnowledgeAmendment, KnowledgeAmendmentRevision, KnowledgeArticle, KnowledgeGrant, KnowledgeRevision,
    KnowledgeSpace,
)
from .org_models import OrgMembership
from .main import app, current_user, get_db, render
from .routes_knowledge import _reader, _space


def _matches_name(raw: str) -> str:
    return "%" + raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _people(db: Session, actor: User, space: KnowledgeSpace, query: str) -> list[User]:
    """Bounded directory search. Non-admins see only exact unit members."""
    stmt = select(User).where(User.active.is_(True))
    if not actor.is_admin:
        stmt = stmt.join(OrgMembership, OrgMembership.user_id == User.id).where(
            OrgMembership.org_id == space.org_id
        )
    if query:
        expr = User.name.ilike(_matches_name(query), escape="\\")
        if actor.is_admin:
            expr = or_(expr, User.email.ilike(_matches_name(query), escape="\\"))
        stmt = stmt.where(expr)
    return list(db.scalars(stmt.order_by(User.name, User.id).limit(120)))


def _grants_visible_to(db, actor, space):
    rules = list(db.scalars(select(KnowledgeGrant).where(
        KnowledgeGrant.resource_kind == "space",
        KnowledgeGrant.resource_id == space.id,
    ).order_by(KnowledgeGrant.id)))
    output = []
    for rule in rules:
        if not actor.is_admin:
            if rule.principal_kind != "user":
                continue
            target = db.get(User, rule.principal_id)
            if not km.eligible_subject(db, actor, space, target):
                continue
        if rule.principal_kind == "user":
            subject = db.get(User, rule.principal_id)
            name = subject.name if subject else "Ehemalige Person"
        elif rule.principal_kind == "group":
            group = db.get(Group, rule.principal_id)
            name = group.name if group else "Gelöschte Gruppe"
        else:
            org = db.get(Organization, rule.principal_id)
            name = org.name if org else "Ehemalige Organisationseinheit"
        output.append({"rule": rule, "name": name})
    return output


@app.get("/wissen/raum/{space_id:int}/verwaltung")
def knowledge_management(request: Request, space_id: int, q: str = "",
                         person: int = 0,
                         user: User = Depends(current_user),
                         db: Session = Depends(get_db)):
    _reader(user, db)
    space = _space(db, user, space_id, "manage")
    if not km.can_manage_space(db, user, space):
        raise HTTPException(403)
    q = " ".join(q.split())[:80]
    people = _people(db, user, space, q)
    selected = None
    explanation = []
    if person:
        selected = db.get(User, person)
        if not km.eligible_subject(db, user, space, selected):
            # Do not allow enumeration across organizational boundaries.
            raise HTTPException(403)
        explanation = km.explain_space_access(db, selected, space)
    groups = list(db.scalars(select(Group).order_by(Group.name).limit(200))) if user.is_admin else []
    orgs = list(db.scalars(select(Organization).where(
        Organization.active.is_(True)).order_by(Organization.name).limit(200))) if user.is_admin else []
    return render(request, "knowledge_management.html", user,
                  space=space, people=people, query=q, selected=selected,
                  explanation=explanation, groups=groups, orgs=orgs,
                  rules=_grants_visible_to(db, user, space),
                  capabilities=km.CAP_PERMS, delegated=not user.is_admin)


def _reviewable(db: Session, user: User, item: KnowledgeArticle, space) -> bool:
    return (item.owner_id != user.id and km.allowed(db, user, space, "publish", item))


@app.get("/wissen/pruefungen")
def knowledge_review_queue(request: Request,
                           user: User = Depends(current_user),
                           db: Session = Depends(get_db)):
    """Live restricted inbox – never a cross-tenant report."""
    _reader(user, db)
    if not user.can("knowledge_publish"):
        raise HTTPException(403)
    today = datetime.now(LOCAL_TZ).date()
    deadline = today + timedelta(days=30)
    articles = []
    amendments = []
    due = []
    spaces = {}
    for item in db.scalars(select(KnowledgeArticle).where(
        KnowledgeArticle.status.in_(("published", "review")),
    ).order_by(KnowledgeArticle.updated_at.desc()).limit(3000)):
        space = spaces.get(item.space_id)
        if item.space_id not in spaces:
            space = db.get(KnowledgeSpace, item.space_id)
            spaces[item.space_id] = space
        if not space or not _reviewable(db, user, item, space):
            continue
        if item.status == "review":
            # Don't show an unapprovable draft to one of its content authors.
            author = db.scalar(select(KnowledgeRevision.id).where(
                KnowledgeRevision.article_id == item.id,
                KnowledgeRevision.status == "draft",
                KnowledgeRevision.editor_id == user.id,
            ).limit(1))
            if author is None:
                articles.append((item, space))
        if item.status == "published":
            if item.review_due_on and item.review_due_on <= deadline:
                due.append((item, space))
            proposal = db.scalar(select(KnowledgeAmendment).where(
                KnowledgeAmendment.article_id == item.id,
                KnowledgeAmendment.status == "review",
            ))
            if proposal and user.id not in {proposal.creator_id, proposal.last_editor_id}:
                contributed = db.scalar(select(KnowledgeAmendmentRevision.id).where(
                    KnowledgeAmendmentRevision.article_id == item.id,
                    KnowledgeAmendmentRevision.version >= proposal.cycle_start_version,
                    KnowledgeAmendmentRevision.action.in_(("start", "edit")),
                    KnowledgeAmendmentRevision.actor_id == user.id,
                ).limit(1))
                if contributed is None:
                    amendments.append((item, space))
    due.sort(key=lambda pair: pair[0].review_due_on)
    return render(request, "knowledge_reviews.html", user,
                  articles=articles[:100], amendments=amendments[:100],
                  due=due[:150], today=today, deadline=deadline)
