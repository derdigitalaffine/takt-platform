"""Manual, organization-scoped TAKT Wissen UI; no implicit AI/RAG ingestion."""
from datetime import datetime, timedelta

from fastapi import Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import knowledge as km
from .db import LOCAL_TZ, Organization, User, utcnow
from .knowledge_models import (KnowledgeAmendment, KnowledgeArticle, KnowledgeGrant,
                               KnowledgeSpace, KnowledgeRevision)
from .main import app, check_csrf, current_user, flash, get_db, redirect, render


def _reader(user, db):
    if not km.active(db):
        raise HTTPException(404)
    if not user.can("knowledge_read"):
        raise HTTPException(403, "Dir fehlt das Recht zum Lesen von Organisationswissen.")


def _space(db, user, space_id: int, cap: str = "read") -> KnowledgeSpace:
    space = db.get(KnowledgeSpace, space_id)
    if space is None:
        raise HTTPException(404)
    if not km.allowed(db, user, space, cap):
        raise HTTPException(403, "Für diesen Wissensraum fehlt die Berechtigung.")
    return space


def _article(db, user, article_id: int, cap: str = "read"):
    item = db.get(KnowledgeArticle, article_id)
    if item is None:
        raise HTTPException(404)
    space = db.get(KnowledgeSpace, item.space_id)
    if not km.allowed(db, user, space, cap, item):
        raise HTTPException(403, "Für diesen Wissensartikel fehlt die Berechtigung.")
    return space, item


def _require_text(title: str, body: str = "") -> tuple[str, str]:
    title = " ".join(title.split())
    if not 1 <= len(title) <= 200 or len(body) > 60000:
        raise HTTPException(422, "Titel (1–200 Zeichen) oder Text (maximal 60.000 Zeichen) ungültig.")
    return title, body


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@app.get("/wissen")
def knowledge_home(request: Request, q: str = "",
                   user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    _reader(user, db)
    q = q.strip()[:120]
    spaces = [s for s in db.scalars(select(KnowledgeSpace).order_by(KnowledgeSpace.title))
              if km.allowed(db, user, s)]
    query = select(KnowledgeArticle).order_by(KnowledgeArticle.updated_at.desc())
    if q:
        from sqlalchemy import or_
        pattern = _like(q)
        query = query.where(or_(
            KnowledgeArticle.title.ilike(pattern, escape="\\"),
            KnowledgeArticle.body_md.ilike(pattern, escape="\\"),
        ))
    articles = []
    for item in db.scalars(query.limit(1000)):
        s = db.get(KnowledgeSpace, item.space_id)
        if km.allowed(db, user, s, article=item):
            articles.append((item, s))
        if len(articles) >= 60:
            break
    orgs = [o for o in db.scalars(select(Organization).where(
        Organization.active.is_(True)).order_by(Organization.name))
        if km.can_create_space(db, user, o.id)]
    return render(request, "knowledge_home.html", user,
                  spaces=spaces, articles=articles, q=q, orgs=orgs,
                  can_create=bool(orgs or user.is_admin),
                  kinds=km.KINDS, statuses=km.STATUSES)


@app.post("/wissen/raum/neu", dependencies=[Depends(check_csrf)])
def knowledge_create_space(request: Request, title: str = Form(...),
                           description: str = Form(""), org_id: int = Form(0),
                           user: User = Depends(current_user),
                           db: Session = Depends(get_db)):
    _reader(user, db)
    org = org_id or None
    if not km.can_create_space(db, user, org):
        raise HTTPException(403)
    title, description = _require_text(title, description)
    space = KnowledgeSpace(title=title, description=description, org_id=org, owner_id=user.id)
    db.add(space)
    db.flush()
    km.audit(db, user, space.id, None, "space_create")
    db.commit()
    return redirect(f"/wissen/raum/{space.id}")


@app.get("/wissen/raum/{space_id:int}")
def knowledge_space(request: Request, space_id: int,
                    user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    _reader(user, db)
    space = _space(db, user, space_id)
    entries = [item for item in db.scalars(select(KnowledgeArticle).where(
        KnowledgeArticle.space_id == space_id).order_by(KnowledgeArticle.updated_at.desc()))
        if km.allowed(db, user, space, article=item)]
    return render(request, "knowledge_space.html", user, space=space,
                  entries=entries, kinds=km.KINDS, statuses=km.STATUSES,
                  can_edit=km.allowed(db, user, space, "edit"),
                  can_manage=user.is_admin, grants=list(db.scalars(select(KnowledgeGrant).where(
                      KnowledgeGrant.resource_kind == "space", KnowledgeGrant.resource_id == space.id
                  ))) if user.is_admin else [])


@app.post("/wissen/raum/{space_id:int}/artikel", dependencies=[Depends(check_csrf)])
def knowledge_create_article(request: Request, space_id: int,
                             title: str = Form(...), kind: str = Form("article"),
                             body_md: str = Form(""),
                             user: User = Depends(current_user),
                             db: Session = Depends(get_db)):
    _reader(user, db)
    _space(db, user, space_id, "edit")
    if kind not in km.KINDS:
        raise HTTPException(422, "Unbekannte Wissensart.")
    title, body_md = _require_text(title, body_md)
    item = KnowledgeArticle(space_id=space_id, title=title, kind=kind,
                            body_md=body_md, owner_id=user.id, status="draft",
                            scope="inherit", version=1)
    db.add(item)
    db.flush()
    km.record_revision(db, item, user.id)
    km.audit(db, user, space_id, item.id, "article_create")
    db.commit()
    return redirect(f"/wissen/artikel/{item.id}")


@app.get("/wissen/artikel/{article_id:int}")
def knowledge_article(request: Request, article_id: int,
                      user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    _reader(user, db)
    space, item = _article(db, user, article_id)
    history = list(db.scalars(select(KnowledgeRevision).where(
        KnowledgeRevision.article_id == item.id).order_by(
        KnowledgeRevision.version.desc()).limit(30)))
    grants = list(db.scalars(select(KnowledgeGrant).where(
        KnowledgeGrant.resource_kind == "article", KnowledgeGrant.resource_id == item.id
    ))) if user.is_admin else []
    can_edit = km.allowed(db, user, space, "edit", item)
    can_publish = km.allowed(db, user, space, "publish", item)
    # Editors/reviewers only: the existence of pending drafts is itself sensitive.
    proposal = db.scalar(select(KnowledgeAmendment).where(
        KnowledgeAmendment.article_id == item.id
    )) if (item.status == "published" and (can_edit or can_publish)) else None
    if proposal and proposal.status == "applied":
        proposal = None
    today = datetime.now(LOCAL_TZ).date()
    return render(request, "knowledge_article.html", user, space=space,
                  item=item, history=history, grants=grants, proposal=proposal,
                  kinds=km.KINDS, statuses=km.STATUSES, authorities=km.AUTHORITIES,
                  can_edit=can_edit, can_publish=can_publish,
                  today=today, can_manage=user.is_admin)


@app.post("/wissen/artikel/{article_id:int}/save", dependencies=[Depends(check_csrf)])
def knowledge_save_article(request: Request, article_id: int,
                           title: str = Form(...), kind: str = Form("article"),
                           body_md: str = Form(""), version: int = Form(...),
                           user: User = Depends(current_user),
                           db: Session = Depends(get_db)):
    _reader(user, db)
    space, item = _article(db, user, article_id, "edit")
    if item.version != version:
        raise HTTPException(409, "Der Artikel wurde inzwischen geändert. Bitte neu laden.")
    if item.status != "draft":
        raise HTTPException(409, "Zur Überarbeitung zuerst in den Entwurfsstatus zurücksetzen.")
    if kind not in km.KINDS:
        raise HTTPException(422)
    title, body_md = _require_text(title, body_md)
    item.title, item.kind, item.body_md = title, kind, body_md
    item.version += 1
    item.updated_at = utcnow()
    km.record_revision(db, item, user.id)
    km.audit(db, user, space.id, item.id, "article_edit", f"v{item.version}")
    db.commit()
    flash(request, "Entwurf gespeichert.")
    return redirect(f"/wissen/artikel/{article_id}")


@app.post("/wissen/artikel/{article_id:int}/status", dependencies=[Depends(check_csrf)])
def knowledge_article_status(request: Request, article_id: int,
                             status: str = Form(...), version: int = Form(...),
                             user: User = Depends(current_user),
                             db: Session = Depends(get_db)):
    _reader(user, db)
    space, item = _article(db, user, article_id)
    if item.version != version:
        raise HTTPException(409, "Der Artikel wurde inzwischen geändert.")
    if status == "review" and item.status == "draft":
        cap = "edit"
    elif status == "draft" and item.status == "review":
        cap = "edit"
    elif status == "published" and item.status == "review":
        cap = "publish"
        content_author = db.scalar(select(KnowledgeRevision.id).where(
            KnowledgeRevision.article_id == item.id,
            KnowledgeRevision.status == "draft",
            KnowledgeRevision.editor_id == user.id,
        ).limit(1))
        if item.owner_id == user.id or content_author is not None:
            raise HTTPException(403, "Vier-Augen-Freigabe: Wer die aktuelle Fassung bearbeitet hat, darf sie nicht selbst freigeben.")
    else:
        raise HTTPException(409, "Dieser Statuswechsel ist nicht zulässig.")
    if not km.allowed(db, user, space, cap, item):
        raise HTTPException(403)
    if status == "published":
        item.authority = "verified"
        item.published_at = utcnow()
        item.last_reviewed_at = utcnow()
        item.review_due_on = datetime.now(LOCAL_TZ).date() + timedelta(days=365)
    km.change_status(db, item, user, status)
    db.commit()
    flash(request, "Wissensstatus aktualisiert.")
    return redirect(f"/wissen/artikel/{article_id}")


@app.post("/wissen/{resource_kind}/{resource_id:int}/rechte",
          dependencies=[Depends(check_csrf)])
def knowledge_permissions(request: Request, resource_kind: str, resource_id: int,
                          principal_kind: str = Form(...), principal_id: int = Form(...),
                          capability: str = Form(...), effect: str = Form(...),
                          include_children: str = Form(""),
                          user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    _reader(user, db)
    # First version deliberately confines ACL editing to global administrators.
    # Broader delegated administration needs a separate authorization review.
    if not user.is_admin:
        raise HTTPException(403)
    if resource_kind == "space":
        space = db.get(KnowledgeSpace, resource_id)
        item = None
        dest = f"/wissen/raum/{resource_id}"
    elif resource_kind == "article":
        item = db.get(KnowledgeArticle, resource_id)
        space = db.get(KnowledgeSpace, item.space_id) if item else None
        dest = f"/wissen/artikel/{resource_id}"
    else:
        raise HTTPException(404)
    if space is None or not km.principal_exists(db, principal_kind, principal_id):
        raise HTTPException(422, "Bereich oder Empfänger nicht gefunden.")
    if capability not in km.CAP_PERMS or effect not in {"allow", "deny", "remove"}:
        raise HTTPException(422, "Ungültige Berechtigungsregel.")
    existing = db.scalar(select(KnowledgeGrant).where(
        KnowledgeGrant.resource_kind == resource_kind,
        KnowledgeGrant.resource_id == resource_id,
        KnowledgeGrant.principal_kind == principal_kind,
        KnowledgeGrant.principal_id == principal_id,
        KnowledgeGrant.capability == capability,
    ))
    if effect == "remove":
        if existing:
            db.delete(existing)
    else:
        if existing is None:
            existing = KnowledgeGrant(resource_kind=resource_kind, resource_id=resource_id,
                                      principal_kind=principal_kind, principal_id=principal_id,
                                      capability=capability, effect=effect)
            db.add(existing)
        existing.effect = effect
        existing.include_children = principal_kind == "org" and include_children == "1"
    km.audit(db, user, space.id, item.id if item else None,
             "acl_change", f"{resource_kind}:{principal_kind}:{principal_id}:{capability}:{effect}")
    db.commit()
    flash(request, "Berechtigungsregel gespeichert.")
    return redirect(dest)


@app.post("/wissen/artikel/{article_id:int}/schutz",
          dependencies=[Depends(check_csrf)])
def knowledge_article_scope(request: Request, article_id: int,
                            scope: str = Form(...),
                            user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    _reader(user, db)
    if not user.is_admin:
        raise HTTPException(403)
    space, item = _article(db, user, article_id)
    if scope not in {"inherit", "restricted"}:
        raise HTTPException(422)
    if item.scope != scope:
        item.scope = scope
        km.audit(db, user, space.id, item.id, "scope_change", scope)
        db.commit()
    return redirect(f"/wissen/artikel/{article_id}")
