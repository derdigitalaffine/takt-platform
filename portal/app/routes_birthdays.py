"""Authenticated birthday calendar and organization settings (no public directory)."""
from datetime import datetime
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .main import app, current_user, get_db, check_csrf, render, redirect, flash
from .db import User, Organization, to_local, utcnow
from . import birthdays, organization as org


@app.get("/kalender/geburtstage")
def birthday_page(
    request: Request,
    year: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    today = to_local(utcnow()).date()
    if year is None:
        year = today.year
    if not 1970 <= year <= 2200:
        raise HTTPException(422, "Bitte ein gültiges Kalenderjahr wählen.")
    roots = birthdays.managed_roots(db, user)
    return render(
        request, "birthdays.html", user,
        year=year,
        today=today,
        upcoming=birthdays.upcoming(db, user, limit=8, today=today),
        can_configure=bool(roots),
    )


@app.get("/kalender/geburtstage/einstellungen")
def birthday_settings(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    roots = birthdays.managed_roots(db, user)
    if not roots:
        raise HTTPException(403)
    return render(
        request, "birthday_settings.html", user,
        organizations=[
            dict(id=node.id, name=node.name, config=birthdays.rules(db, node.id))
            for node in roots
        ],
    )


@app.post("/kalender/geburtstage/einstellungen", dependencies=[Depends(check_csrf)])
async def birthday_settings_save(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    form = await request.form()
    try:
        oid = int(form.get("org_id", ""))
    except (TypeError, ValueError):
        raise HTTPException(422, "Organisation auswählen.")
    unit = db.get(Organization, oid)
    if (
        unit is None or not unit.active or unit.parent_id is not None
        or not org.allows(db, user, oid, "settings")
    ):
        raise HTTPException(403)
    try:
        birthdays.save_rules(
            db, oid,
            scope=str(form.get("scope", "")),
            leap=str(form.get("leap", "")),
            caldav=form.get("caldav") == "1",
            ics=form.get("ics") == "1",
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    db.commit()
    flash(request, "Geburtstagseinstellungen für " + unit.name + " gespeichert.")
    return redirect("/kalender/geburtstage/einstellungen")
