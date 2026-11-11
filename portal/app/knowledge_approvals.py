"""Independent approval decisions tied to a single submission."""
from fastapi import HTTPException
from sqlalchemy import select, update

from . import knowledge as km
from .db import User
from .knowledge_models import KnowledgeAmendment, KnowledgeApproval, KnowledgeArticle


def current_reviewers(db, space, article, proposal=None):
    submission = proposal if proposal is not None else article
    if submission.required_approvals == 1:
        return set()
    reviewers = db.scalars(select(User).join(KnowledgeApproval, KnowledgeApproval.reviewer_id == User.id).where(
        KnowledgeApproval.article_id == article.id,
        KnowledgeApproval.amendment.is_(proposal is not None),
        KnowledgeApproval.version == submission.version,
    ))
    if proposal is None:
        return {u.id for u in reviewers if km.can_approve_article(db, u, space, article)}
    return {u.id for u in reviewers if km.can_approve_amendment(db, u, space, article, proposal)}


def can_record(user, submission, reviewers):
    return user.id not in reviewers or len(reviewers) >= submission.required_approvals


def register(db, user, space, article, proposal=None):
    """Called after checking the actor's ACL and independence. Returns readiness to publish."""
    submission = proposal if proposal is not None else article
    if submission.required_approvals == 1:
        return True

    # Serialize votes against publication, review confirmation and return to draft.
    lock = db.execute(update(KnowledgeArticle).where(
        KnowledgeArticle.id == article.id,
        KnowledgeArticle.version == article.version,
        KnowledgeArticle.status == article.status,
    ).values(version=KnowledgeArticle.version).execution_options(synchronize_session=False))
    if lock.rowcount != 1:
        raise HTTPException(409, "Die Artikelfassung wurde inzwischen geändert.")
    if proposal is not None:
        lock = db.execute(update(KnowledgeAmendment).where(
            KnowledgeAmendment.id == proposal.id,
            KnowledgeAmendment.version == proposal.version,
            KnowledgeAmendment.status == "review",
        ).values(version=KnowledgeAmendment.version).execution_options(synchronize_session=False))
        if lock.rowcount != 1:
            raise HTTPException(409, "Der Änderungsentwurf wurde inzwischen geändert.")

    reviewers = current_reviewers(db, space, article, proposal)
    if user.id in reviewers:
        if len(reviewers) >= submission.required_approvals:
            return True
        raise HTTPException(409, "Du hast diese Fassung bereits fachlich freigegeben.")
    db.add(KnowledgeApproval(article_id=article.id, amendment=proposal is not None,
                             version=submission.version, reviewer_id=user.id))
    km.audit(db, user, space.id, article.id, "amendment_approval" if proposal else "article_approval",
             f"v{submission.version}")
    return len(reviewers) + 1 >= submission.required_approvals
