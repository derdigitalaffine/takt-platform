"""Compatibility entry points for the unified organization management and public logos."""

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import orgs, organization as structure
from .db import Organization, User
from .main import app, check_csrf, current_user, get_db, redirect, require

orgs_user = require("orgs")


def _org(db, oid: int) -> Organization:
    org = db.get(Organization, oid)
    if org is None:
        raise HTTPException(404, "Diesen Eintrag gibt es nicht.")
    return org


@app.get("/admin/orgs")
def orgs_list(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not structure.has_access(db, user):
        raise HTTPException(403)
    return redirect("/admin/organization")


@app.get("/admin/orgs/new")
def org_new(
    request: Request,
    parent: int | None = None,
    user: User = Depends(orgs_user),
    db: Session = Depends(get_db),
):
    return redirect(
        "/admin/organization?new=1"
        + ("&unit=" + str(parent) if parent else "")
        + "#org-new"
    )


@app.get("/admin/orgs/{oid:int}")
def org_edit(
    request: Request,
    oid: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    structure.require(db, user, oid, "view")
    return redirect(f"/admin/organization?unit={oid}#org-settings")


async def legacy_action(request, user, db, action, oid=None):
    from starlette.datastructures import FormData
    from .routes_organization import handle_action

    data = await request.form()
    data = FormData(
        [(k, v) for k, v in data.multi_items() if k not in {"action", "org_id"}]
        + [("action", action), ("org_id", str(oid) if oid else "")]
    )
    return await handle_action(request, user, db, data)


@app.post("/admin/orgs/new", dependencies=[Depends(check_csrf)])
async def org_create(
    request: Request, user: User = Depends(orgs_user), db: Session = Depends(get_db)
):
    return await legacy_action(request, user, db, "unit_create")


@app.post("/admin/orgs/{oid:int}", dependencies=[Depends(check_csrf)])
async def org_update(
    request: Request,
    oid: int,
    user: User = Depends(orgs_user),
    db: Session = Depends(get_db),
):
    _org(db, oid)
    return await legacy_action(request, user, db, "unit_save", oid)


@app.post("/admin/orgs/{oid:int}/delete", dependencies=[Depends(check_csrf)])
async def org_delete(
    request: Request,
    oid: int,
    user: User = Depends(orgs_user),
    db: Session = Depends(get_db),
):
    _org(db, oid)
    return await legacy_action(request, user, db, "unit_delete", oid)


@app.get("/org/{oid:int}/logo")
def org_logo(oid: int, db: Session = Depends(get_db)):
    """Wappen öffentlich (Ressourcenseiten, Rechtstexte, Anträge)."""
    org = db.get(Organization, oid)
    if org is None or not org.logo:
        raise HTTPException(404)
    path = orgs.logo_dir() / org.logo
    if not path.is_file():
        raise HTTPException(404)
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(
        path.suffix, "application/octet-stream"
    )
    return FileResponse(
        path,
        media_type=mime,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )
