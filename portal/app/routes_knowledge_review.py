"""P2 editorial lifecycle: safe amendments, review dates, authorized Markdown preview.

Published content is immutable to readers until a second authorized reviewer
promotes the candidate. No AI or external indexing occurs here.
"""
from datetime import date, datetime, timedelta
from difflib import unified_diff

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import knowledge as km
from .knowledge_models import (
    KnowledgeAmendment, KnowledgeAmendmentRevision, KnowledgeArticle,
    KnowledgeRevision,
)
from .db import LOCAL_TZ, User, utcnow
from .main import (
    app, check_csrf, current_user, flash, get_db, rate_limit, redirect,
    render, templates,
)
from .routes_knowledge import _article, _reader, _require_text, _space

templates.env.filters["knowledge_markdown"] = km.render_markdown


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


def _today() -> date:
    return datetime.now(LOCAL_TZ).date()


def _validate_due_on(value: str) -> date | None:
    if not value:
        return None
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, "Prüfdatum muss ein gültiges Datum sein.") from exc
    if result < _today() - timedelta(days=3650) or result > _today() + timedelta(days=3650):
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
    return JSONResponse({"html": str(km.render_markdown(body_md))},
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
    if version != article.version:
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
    return render(
        request, "knowledge_amendment.html", user, space=space, item=article,
        proposal=proposal, history=rows, difference=comparison,
        kinds=km.KINDS,
        can_edit=km.allowed(db, user, space, "edit", article),
        can_publish=_can_review(db, user, space, article)
        and user.id not in {proposal.creator_id, proposal.last_editor_id},
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
        if not _can_review(db, user, space, article):
            raise HTTPException(403)
        content_author = db.scalar(select(KnowledgeAmendmentRevision.id).where(
            KnowledgeAmendmentRevision.article_id == article_id,
            KnowledgeAmendmentRevision.version >= proposal.cycle_start_version,
            KnowledgeAmendmentRevision.action.in_(("start", "edit")),
            KnowledgeAmendmentRevision.actor_id == user.id,
        ).limit(1))
        if (user.id in {proposal.creator_id, proposal.last_editor_id}
                or content_author is not None):
            raise HTTPException(403, "Vier-Augen-Freigabe: Wer die aktuelle Fassung bearbeitet hat, darf sie nicht selbst freigeben.")
        result = db.execute(update(KnowledgeArticle).where(
            KnowledgeArticle.id == article.id, KnowledgeArticle.version == proposal.base_version,
            KnowledgeArticle.status == "published",
        ).values(
            title=proposal.title, kind=proposal.kind, body_md=proposal.body_md,
            authority="verified", version=article.version + 1,
            published_at=utcnow(), last_reviewed_at=utcnow(),
            review_due_on=_today() + timedelta(days=365),
            updated_at=utcnow(),
        ).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Die veröffentlichte Fassung wurde parallel geändert.")
        db.expire(article)
        km.record_revision(db, article, user.id)
        km.audit(db, user, space.id, article.id, "amendment_publish",
                 f"published_v{article.version}")
        proposal.status = "applied"
        proposal.version += 1
        proposal.updated_at = utcnow()
        km.remember_amendment(db, proposal, user.id, "publish")
        db.commit()
        flash(request, "Neue Wissensfassung fachlich freigegeben.")
        return redirect(f"/wissen/artikel/{article_id}")
    else:
        raise HTTPException(409, "Dieser Statuswechsel ist nicht zulässig.")
    proposal.status = status
    proposal.version += 1
    proposal.updated_at = utcnow()
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
    if article.owner_id == user.id:
        raise HTTPException(403, "Die eigene Wissensbeschreibung muss unabhängig geprüft werden.")
    if authority not in km.EDITOR_AUTHORITIES:
        raise HTTPException(422, "Verbindliche Anweisungen müssen über den offiziellen Regelwerksprozess freigegeben werden.")
    due = _validate_due_on(review_due_on)
    result = db.execute(update(KnowledgeArticle).where(
        KnowledgeArticle.id == article_id, KnowledgeArticle.version == version,
        KnowledgeArticle.status == "published",
    ).values(
        authority=authority, review_due_on=due, last_reviewed_at=utcnow(),
        version=version + 1, updated_at=utcnow(),
    ).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Artikel wurde inzwischen geändert.")
    db.expire(article)
    km.record_revision(db, article, user.id)
    km.audit(db, user, space.id, article.id, "review_confirm", authority)
    db.commit()
    flash(request, "Wissensqualität und nächste Prüfung dokumentiert.")
    return redirect(f"/wissen/artikel/{article_id}")
