"""Scoped Wissensraum administration and human-facing, ACL-filtered review inbox.

No external calls, scheduled contacts, AI indexing, or global user-directory
access for delegated room administrators.
"""
from datetime import timedelta
from itertools import islice

from fastapi import Depends, Form, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import knowledge as km, knowledge_approvals as approvals
from .db import Group, Organization, User
from .knowledge_models import (
    KnowledgeAmendment, KnowledgeArticle, KnowledgeGrant, KnowledgeSpace,
)
from .org_models import OrgMembership
from .main import app, check_csrf, current_user, flash, get_db, redirect, render
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


@app.post("/wissen/raum/{space_id:int}/freigaben", dependencies=[Depends(check_csrf)])
def knowledge_approval_policy(request: Request, space_id: int,
                              required: int = Form(...),
                              user: User = Depends(current_user),
                              db: Session = Depends(get_db)):
    _reader(user, db)
    if not user.is_admin:
        raise HTTPException(403)
    space = _space(db, user, space_id, "manage")
    if required not in {1, 2}:
        raise HTTPException(422, "Bitte eine oder zwei unabhängige Freigaben wählen.")
    if space.required_approvals != required:
        space.required_approvals = required
        km.audit(db, user, space.id, None, "approval_policy", str(required))
        db.commit()
    flash(request, "Freigaberegel für neue Einreichungen gespeichert.")
    return redirect(f"/wissen/raum/{space.id}/verwaltung")


@app.get("/wissen/pruefungen")
def knowledge_review_queue(request: Request,
                           due_page: int = Query(1, ge=1, le=1_000_000),
                           user: User = Depends(current_user),
                           db: Session = Depends(get_db)):
    """Apply each lane's ACL and review rules before limiting its visible rows."""
    _reader(user, db)
    if not user.can("knowledge_publish"):
        raise HTTPException(403)
    today = km.review_today()
    deadline = today + timedelta(days=30)
    with_space = select(KnowledgeArticle, KnowledgeSpace).join(KnowledgeSpace)
    recent_first = (KnowledgeArticle.updated_at.desc(), KnowledgeArticle.id.desc())

    pending = with_space.where(KnowledgeArticle.status == "review").order_by(*recent_first)
    articles = list(islice(
        ((item, space) for item, space in db.execute(pending.execution_options(yield_per=100))
         if km.can_approve_article(db, user, space, item)
         and approvals.can_record(user, item, approvals.current_reviewers(db, space, item))),
        100,
    ))

    proposed = (with_space.add_columns(KnowledgeAmendment).join(
        KnowledgeAmendment, KnowledgeAmendment.article_id == KnowledgeArticle.id)
        .where(KnowledgeArticle.status == "published", KnowledgeAmendment.status == "review",
               KnowledgeAmendment.base_version == KnowledgeArticle.version)
        .order_by(KnowledgeAmendment.updated_at.desc(), KnowledgeArticle.id.desc()))
    amendments = list(islice(
        ((item, space) for item, space, proposal in db.execute(proposed.execution_options(yield_per=100))
         if km.can_approve_amendment(db, user, space, item, proposal)
         and approvals.can_record(user, proposal, approvals.current_reviewers(db, space, item, proposal))),
        100,
    ))

    page_size = 150
    due = list(islice(km.due_reviews(db, user, deadline),
                      (due_page - 1) * page_size, due_page * page_size + 1))
    return render(request, "knowledge_reviews.html", user,
                  articles=articles, amendments=amendments, due=due[:page_size],
                  due_page=due_page, more_due=len(due) > page_size,
                  today=today, deadline=deadline)


@app.post("/wissen/pruefungen/hinweise", dependencies=[Depends(check_csrf)])
def knowledge_review_reminders(request: Request, enabled: bool = Form(...),
                               user: User = Depends(current_user),
                               db: Session = Depends(get_db)):
    _reader(user, db)
    if not user.can("knowledge_publish"):
        raise HTTPException(403)
    user.knowledge_review_reminders = enabled
    db.commit()
    flash(request, "Einstellung für Prüfhinweise gespeichert.")
    return redirect("/wissen/pruefungen")
