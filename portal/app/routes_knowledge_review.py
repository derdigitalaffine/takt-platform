"""P2 editorial lifecycle: safe amendments, review dates, authorized Markdown preview.

Published content is immutable to readers until a second authorized reviewer
promotes the candidate. No AI or external indexing occurs here.
"""
from datetime import date, timedelta
from difflib import unified_diff

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import knowledge as km, knowledge_approvals as approvals, knowledge_sources as sources
from .knowledge_models import (
    KnowledgeAmendment, KnowledgeAmendmentRevision, KnowledgeArticle,
)
from .db import User, utcnow
from .main import (
    app, check_csrf, current_user, flash, get_db, rate_limit, redirect,
    render,
)
from .routes_knowledge import _article, _reader, _require_text, _space

def _proposal(db, article_id: int) -> KnowledgeAmendment:
    result = db.scalar(select(KnowledgeAmendment).where(
        KnowledgeAmendment.article_id == article_id
    ))
    if result is None or result.status not in {"draft", "review"}:
        raise HTTPException(404, "Für diesen Artikel gibt es keinen offenen Änderungsentwurf.")
    return result


def _can_review(db, user, space, item) -> bool:
    return km.allowed(db, user, space, "publish", item)


def _may_see_proposal(db, user, space, item) -> bool:
    return km.allowed(db, user, space, "edit", item) or _can_review(db, user, space, item)


def _validate_due_on(value: str) -> date | None:
    if not value:
        return None
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, "Prüfdatum muss ein gültiges Datum sein.") from exc
    today = km.review_today()
    if not today <= result <= today + timedelta(days=3650):
        raise HTTPException(422, "Prüfdatum liegt außerhalb des zulässigen Zeitraums.")
    return result


@app.post("/wissen/vorschau", dependencies=[Depends(check_csrf)])
def knowledge_preview(request: Request, body_md: str = Form(""),
                      space_id: int = Form(0), article_id: int = Form(0),
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    _reader(user, db)
    rate_limit(request, "knowledge-preview", limit=40, window=60, key=str(user.id))
    if bool(space_id) == bool(article_id):
        raise HTTPException(422, "Bitte einen Wissensraum oder Artikel angeben.")
    if article_id:
        _article(db, user, article_id, "edit")
    else:
        _space(db, user, space_id, "edit")
    if len(body_md) > 60000:
        raise HTTPException(422, "Text ist zu lang.")
    preview = km.render_markdown(body_md, lambda path: sources.resolve_reference(db, user, path))
    return JSONResponse({"html": str(preview)},
                        headers={"Cache-Control": "no-store"})


@app.post("/wissen/artikel/{article_id:int}/entwurf/start",
          dependencies=[Depends(check_csrf)])
def start_amendment(request: Request, article_id: int,
                    version: int = Form(...),
                    user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    _reader(user, db)
    _, article = _article(db, user, article_id, "edit")
    if article.status != "published":
        raise HTTPException(409, "Nur freigegebene Artikel erhalten separate Änderungsentwürfe.")
    # Serialize proposal creation/reuse with review confirmations and publication.
    current = db.execute(update(KnowledgeArticle).where(
        KnowledgeArticle.id == article_id,
        KnowledgeArticle.version == version,
        KnowledgeArticle.status == "published",
    ).values(version=KnowledgeArticle.version).execution_options(synchronize_session=False))
    if current.rowcount != 1:
        raise HTTPException(409, "Die freigegebene Fassung wurde inzwischen geändert.")
    proposal = db.scalar(select(KnowledgeAmendment).where(
        KnowledgeAmendment.article_id == article.id))
    if proposal is not None and proposal.status in {"draft", "review"}:
        return redirect(f"/wissen/artikel/{article_id}/entwurf")
    if proposal is None:
        proposal = KnowledgeAmendment(
            article_id=article.id, base_version=article.version,
            title=article.title, kind=article.kind, body_md=article.body_md,
            version=1, cycle_start_version=1,
            creator_id=user.id, last_editor_id=user.id, status="draft",
        )
        db.add(proposal)
    else:
        proposal.base_version = article.version
        proposal.cycle_start_version = proposal.version + 1
        proposal.title, proposal.kind, proposal.body_md = (
            article.title, article.kind, article.body_md
        )
        proposal.version += 1
        proposal.creator_id = proposal.last_editor_id = user.id
        proposal.status = "draft"
        proposal.updated_at = utcnow()
    db.flush()
    km.remember_amendment(db, proposal, user.id, "start")
    km.audit(db, user, article.space_id, article.id, "amendment_start",
             f"published_v{article.version}")
    db.commit()
    return redirect(f"/wissen/artikel/{article_id}/entwurf")


@app.get("/wissen/artikel/{article_id:int}/entwurf")
def amendment_page(request: Request, article_id: int,
                   user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    _reader(user, db)
    space, article = _article(db, user, article_id)
    if not _may_see_proposal(db, user, space, article):
        raise HTTPException(403)
    proposal = _proposal(db, article_id)
    rows = list(db.scalars(select(KnowledgeAmendmentRevision).where(
        KnowledgeAmendmentRevision.article_id == article_id
    ).order_by(KnowledgeAmendmentRevision.version.desc()).limit(15)))
    comparison = "\n".join(unified_diff(
        article.body_md.splitlines(), proposal.body_md.splitlines(),
        fromfile="Veröffentlichte Fassung", tofile="Änderungsentwurf",
        lineterm="",
    ))[:15000]
    def resolve_source(path):
        return sources.resolve_reference(db, user, path)

    approvals_received = approvals.current_reviewers(db, space, article, proposal) if proposal.status == "review" else set()
    return render(
        request, "knowledge_amendment.html", user, space=space, item=article,
        proposal=proposal, history=rows, difference=comparison,
        article_html=km.render_markdown(article.body_md, resolve_source),
        proposal_html=km.render_markdown(proposal.body_md, resolve_source),
        kinds=km.KINDS,
        can_edit=km.allowed(db, user, space, "edit", article),
        can_publish=(km.can_approve_amendment(db, user, space, article, proposal)
                     and approvals.can_record(user, proposal, approvals_received)),
        approvals_received=len(approvals_received),
        can_return=_may_see_proposal(db, user, space, article),
    )


@app.post("/wissen/artikel/{article_id:int}/entwurf/save",
          dependencies=[Depends(check_csrf)])
def save_amendment(request: Request, article_id: int, title: str = Form(...),
                   kind: str = Form("article"), body_md: str = Form(""),
                   version: int = Form(...),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    _reader(user, db)
    _, article = _article(db, user, article_id, "edit")
    proposal = _proposal(db, article_id)
    if proposal.status != "draft":
        raise HTTPException(409, "Ein zur Prüfung eingereichter Entwurf ist gesperrt.")
    if proposal.base_version != article.version or article.status != "published":
        raise HTTPException(409, "Der veröffentlichte Stand hat sich geändert.")
    if kind not in km.KINDS:
        raise HTTPException(422, "Unbekannte Wissensart.")
    title, body_md = _require_text(title, body_md)
    # CAS prevents two editing sessions from silently overwriting each other.
    result = db.execute(
        update(KnowledgeAmendment).where(
            KnowledgeAmendment.id == proposal.id, KnowledgeAmendment.version == version,
            KnowledgeAmendment.status == "draft"
        ).values(
            version=version + 1, title=title, kind=kind, body_md=body_md,
            last_editor_id=user.id, updated_at=utcnow(),
        ).execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Der Entwurf wurde inzwischen geändert. Bitte neu laden.")
    db.expire(proposal)
    km.remember_amendment(db, proposal, user.id, "edit")
    km.audit(db, user, article.space_id, article.id,
             "amendment_edit", f"draft_v{proposal.version}")
    db.commit()
    flash(request, "Änderungsentwurf gespeichert. Die veröffentlichte Fassung bleibt unverändert.")
    return redirect(f"/wissen/artikel/{article_id}/entwurf")


def _transition_proposal(db, proposal, version, status, **fields):
    result = db.execute(update(KnowledgeAmendment).where(
        KnowledgeAmendment.id == proposal.id,
        KnowledgeAmendment.version == version,
        KnowledgeAmendment.status == proposal.status,
    ).values(status=status, version=version + 1, updated_at=utcnow(), **fields)
      .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Der Entwurf wurde inzwischen geändert.")
    db.expire(proposal)


@app.post("/wissen/artikel/{article_id:int}/entwurf/status",
          dependencies=[Depends(check_csrf)])
def amendment_status(request: Request, article_id: int,
                     status: str = Form(...), version: int = Form(...),
                     user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    _reader(user, db)
    space, article = _article(db, user, article_id)
    proposal = _proposal(db, article_id)
    if proposal.version != version:
        raise HTTPException(409, "Der Entwurf wurde inzwischen geändert.")
    if proposal.base_version != article.version or article.status != "published":
        raise HTTPException(409, "Die zugrunde liegende freigegebene Fassung ist nicht mehr aktuell.")
    if status == "review" and proposal.status == "draft":
        if not km.allowed(db, user, space, "edit", article):
            raise HTTPException(403)
    elif status == "draft" and proposal.status == "review":
        if not (_may_see_proposal(db, user, space, article)):
            raise HTTPException(403)
    elif status == "published" and proposal.status == "review":
        if not km.can_approve_amendment(db, user, space, article, proposal):
            raise HTTPException(403, "Für die Freigabe ist eine unabhängige, berechtigte Person erforderlich.")
        if not approvals.register(db, user, space, article, proposal):
            db.commit()
            flash(request, "Fachliche Freigabe erfasst. Eine weitere unabhängige Prüfung steht aus.")
            return redirect(f"/wissen/artikel/{article_id}/entwurf")
        if not km.update_article(db, article, proposal.base_version,
                                 title=proposal.title, kind=proposal.kind, body_md=proposal.body_md,
                                 **km.publication_fields()):
            raise HTTPException(409, "Die veröffentlichte Fassung wurde parallel geändert.")
        _transition_proposal(db, proposal, version, "applied")
        km.record_revision(db, article, user.id)
        km.audit(db, user, space.id, article.id, "amendment_publish",
                 f"published_v{article.version}")
        km.remember_amendment(db, proposal, user.id, "publish")
        db.commit()
        flash(request, "Neue Wissensfassung fachlich freigegeben.")
        return redirect(f"/wissen/artikel/{article_id}")
    else:
        raise HTTPException(409, "Dieser Statuswechsel ist nicht zulässig.")
    fields = {"required_approvals": space.required_approvals} if status == "review" else {}
    _transition_proposal(db, proposal, version, status, **fields)
    km.remember_amendment(db, proposal, user.id,
                          "submit" if status == "review" else "return")
    km.audit(db, user, space.id, article.id, "amendment_status", status)
    db.commit()
    flash(request, "Status des Änderungsentwurfs aktualisiert.")
    return redirect(f"/wissen/artikel/{article_id}/entwurf")


@app.post("/wissen/artikel/{article_id:int}/pruefung",
          dependencies=[Depends(check_csrf)])
def knowledge_governance(request: Request, article_id: int,
                         authority: str = Form(...),
                         review_due_on: str = Form(""),
                         version: int = Form(...),
                         user: User = Depends(current_user),
                         db: Session = Depends(get_db)):
    _reader(user, db)
    space, article = _article(db, user, article_id, "publish")
    if article.status != "published":
        raise HTTPException(409, "Nur veröffentlichte Artikel können bestätigt werden.")
    if not km.can_confirm_review(db, user, space, article):
        raise HTTPException(403, "Die eigene Wissensbeschreibung muss unabhängig geprüft werden.")
    if authority not in km.EDITOR_AUTHORITIES:
        raise HTTPException(422, "Verbindliche Anweisungen müssen über den offiziellen Regelwerksprozess freigegeben werden.")
    due = _validate_due_on(review_due_on)
    if not km.update_article(db, article, version, authority=authority,
                             review_due_on=due, last_reviewed_at=utcnow()):
        raise HTTPException(409, "Artikel wurde inzwischen geändert.")
    # A metadata-only review does not change the content underlying a proposal.
    db.execute(update(KnowledgeAmendment).where(
        KnowledgeAmendment.article_id == article_id,
        KnowledgeAmendment.base_version == version,
        KnowledgeAmendment.status.in_(("draft", "review")),
    ).values(base_version=version + 1))
    km.record_revision(db, article, user.id)
    km.audit(db, user, space.id, article.id, "review_confirm", authority)
    db.commit()
    flash(request, "Wissensqualität und nächste Prüfung dokumentiert.")
    return redirect(f"/wissen/artikel/{article_id}")
