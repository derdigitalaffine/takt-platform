"""Verwaltung › Körperschaften: Gebietskörperschaften, Zweckverbände und Einrichtungen pflegen."""

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import orgs, organization as structure
from .db import Organization, User
from .org_models import OrgState
from .main import app, check_csrf, flash, get_db, redirect, render, require

orgs_user = require("orgs")


def _org(db, oid: int) -> Organization:
    org = db.get(Organization, oid)
    if org is None:
        raise HTTPException(404, "Diesen Eintrag gibt es nicht.")
    return org


def _parent(db, raw, org: Organization | None) -> tuple[Organization | None, str | None]:
    raw = str(raw or "")
    parent = db.get(Organization, int(raw)) if raw.isdigit() else None
    if raw and parent is None:
        return None, "Übergeordnete Einheit nicht gefunden."
    if parent is not None and org is not None and orgs.would_cycle(org, parent):
        return None, "Ein Eintrag kann nicht unter sich selbst oder einer eigenen Einrichtung hängen."
    return parent, None


@app.get("/admin/orgs")
def orgs_list(request: Request, user: User = Depends(orgs_user), db: Session = Depends(get_db)):
    rows = orgs.tree(db)
    return render(request, "orgs.html", user, rows=rows, kinds=structure.kinds(db), logo_url=orgs.logo_url,
                  usage={o.id: orgs.usage(db, o) for o, _d in rows})


@app.get("/admin/orgs/new")
def org_new(request: Request, parent: int | None = None, user: User = Depends(orgs_user), db: Session = Depends(get_db)):
    p = db.get(Organization, parent) if parent else None
    draft = Organization(kind="einrichtung" if p is not None else "og", parent_id=p.id if p else None, name="", active=True)
    return render(request, "org_edit.html", user, org=draft, new=True, kinds=structure.kinds(db), parents=orgs.options(db, active_only=False),
                  logo_url=orgs.logo_url, usage=None, org_version=db.get(OrgState, 1).version)


@app.get("/admin/orgs/{oid:int}")
def org_edit(request: Request, oid: int, user: User = Depends(orgs_user), db: Session = Depends(get_db)):
    org = _org(db, oid)
    parents = [(i, n) for i, n in orgs.options(db, active_only=False) if i != org.id]
    return render(request, "org_edit.html", user, org=org, new=False, kinds=structure.kinds(db), parents=parents,
                  logo_url=orgs.logo_url, usage=orgs.usage(db, org), org_version=db.get(OrgState, 1).version)


async def _save(request: Request, db, org: Organization | None, actor) -> Organization | None:
    data = await request.form()
    structure.lock(db, data.get("version"))
    values, errors = orgs.clean(data, org, structure.kinds(db))
    target = org or Organization()
    parent, err = _parent(db, data.get("parent_id"), org)
    if err:
        errors.append(err)
    if errors:
        for e in errors:
            flash(request, e, "error")
        return None
    structure.check_structure_change(db, actor, org, parent.id if parent else None, data.get('active') == '1')
    for k, v in values.items():
        setattr(target, k, v)
    target.parent = parent
    target.active = data.get("active") == "1"
    pos = str(data.get("position", "") or "")
    target.position = int(pos) if pos.lstrip("-").isdigit() else (target.position or 0)
    if org is None:
        db.add(target)
    upload = data.get("logo")
    if getattr(upload, "filename", ""):
        msg = orgs.store_logo(target, await upload.read(orgs.MAX_LOGO + 1))
        if msg:
            flash(request, msg, "error")
    elif data.get("logo_remove") == "1":
        orgs.remove_logo(target)
    db.flush()
    structure.audit(db, actor, target.id, "structure_save", name=target.name, parent=target.parent_id)
    return target


@app.post("/admin/orgs/new", dependencies=[Depends(check_csrf)])
async def org_create(request: Request, user: User = Depends(orgs_user), db: Session = Depends(get_db)):
    org = await _save(request, db, None, user)
    if org is None:
        return redirect("/admin/orgs/new")
    db.commit()
    flash(request, f"„{org.name}“ angelegt.")
    return redirect("/admin/orgs#org-" + str(org.id))


@app.post("/admin/orgs/{oid:int}", dependencies=[Depends(check_csrf)])
async def org_update(request: Request, oid: int, user: User = Depends(orgs_user), db: Session = Depends(get_db)):
    org = await _save(request, db, _org(db, oid), user)
    if org is None:
        return redirect(f"/admin/orgs/{oid}")
    db.commit()
    flash(request, f"„{org.name}“ gespeichert.")
    return redirect("/admin/orgs#org-" + str(org.id))


@app.post("/admin/orgs/{oid:int}/delete", dependencies=[Depends(check_csrf)])
async def org_delete(request: Request, oid: int, user: User = Depends(orgs_user), db: Session = Depends(get_db)):
    data = await request.form()
    structure.lock(db, data.get("version"))
    org = _org(db, oid)
    used = {k: v for k, v in orgs.usage(db, org).items() if v}
    if used:
        flash(request, f"„{org.name}“ wird noch verwendet ({', '.join(f'{k}: {v}' for k, v in used.items())}). "
                       "Bitte zuerst umstellen – oder den Eintrag auf inaktiv setzen.", "error")
        return redirect(f"/admin/orgs/{oid}")
    orgs.remove_logo(org)
    db.delete(org)
    db.commit()
    flash(request, f"„{org.name}“ gelöscht.")
    return redirect("/admin/orgs")


@app.get("/org/{oid:int}/logo")
def org_logo(oid: int, db: Session = Depends(get_db)):
    """Wappen öffentlich (Ressourcenseiten, Rechtstexte, Anträge)."""
    org = db.get(Organization, oid)
    if org is None or not org.logo:
        raise HTTPException(404)
    path = orgs.logo_dir() / org.logo
    if not path.is_file():
        raise HTTPException(404)
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(path.suffix, "application/octet-stream")
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "public, max-age=86400",
                                                         "X-Content-Type-Options": "nosniff"})
