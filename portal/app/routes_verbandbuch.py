"""TAKT Digitales Verbandbuch – ausschließlich interne, modulgeschützte Fachrouten."""
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import Organization, User, LOCAL_TZ, utcnow
from .organization import active_path
from .main import app, check_csrf, current_user, flash, get_db, redirect, render
from . import verbandbuch as aid
from .verbandbuch_models import (
    FirstAidAudit, FirstAidCase, FirstAidCorrection, FirstAidGrant, FirstAidSite,
)


def _private(response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _can_visit(user: User) -> bool:
    return user.is_admin or bool(user.perms & {"verbandbuch_capture", "verbandbuch_review"})


def _open(user: User) -> None:
    if not _can_visit(user):
        raise HTTPException(403, "Für das Verbandbuch fehlt eine Fachberechtigung.")


def _site(db: Session, site_id: int) -> FirstAidSite:
    site = db.get(FirstAidSite, site_id)
    if site is None or not site.active or not active_path(db, site.org_id):
        raise HTTPException(404, "Standort nicht verfügbar.")
    return site


def _case(db: Session, case_id: str) -> FirstAidCase:
    case = db.get(FirstAidCase, case_id)
    if case is None:
        raise HTTPException(404)
    return case


@app.get("/verbandbuch")
def verbandbuch_home(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _open(user)
    capture = aid.sites_for(db, user, "capture")
    review = aid.sites_for(db, user, "review")
    # Eigene Belege nur bei weiterhin bestehender Standort-Erfassungsberechtigung.
    # Entzug, Deaktivierung oder Organisationssperre wirkt unmittelbar.
    my_rows = db.scalars(select(FirstAidCase).where(
        FirstAidCase.created_by_id == user.id,
        FirstAidCase.site_id.in_([site.id for site in capture]),
    ).order_by(FirstAidCase.created_at.desc()).limit(40)).all()
    cases = db.scalars(select(FirstAidCase).where(
        FirstAidCase.site_id.in_([s.id for s in review])
    ).order_by(FirstAidCase.created_at.desc()).limit(80)).all() if review else []
    sites = {s.id: s for s in db.scalars(select(FirstAidSite)).all()}
    return _private(render(request, "verbandbuch_home.html", user, capture=capture, review=review,
                           cases=cases, my_rows=my_rows, sites=sites, ready=aid.ready(),
                           approved=aid.approved()))


@app.get("/verbandbuch/neu")
def verbandbuch_new(
    request: Request, s: str = "",
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    _open(user)
    available = aid.sites_for(db, user, "capture")
    chosen = None
    if s:
        chosen = aid.qr_site(db, s)
        if chosen.id not in {x.id for x in available}:
            raise HTTPException(403, "Dieser Standort ist für Ihr Konto nicht freigegeben.")
    return _private(render(request, "verbandbuch_form.html", user, sites=available,
                           selected_id=chosen.id if chosen else (available[0].id if len(available) == 1 else None),
                           values={}, errors=[], now=datetime.now(LOCAL_TZ).strftime("%Y-%m-%dT%H:%M"),
                           approved=aid.approved(), ready=aid.ready()))


@app.post("/verbandbuch/neu", dependencies=[Depends(check_csrf)])
async def verbandbuch_save(
    request: Request,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    _open(user)
    raw = await request.form()
    try:
        site_id = int(raw.get("site_id") or 0)
    except (ValueError, TypeError):
        raise HTTPException(422, "Standort auswählen.") from None
    _site(db, site_id)
    if not aid.may(db, user, site_id, "capture"):
        raise HTTPException(403, "Keine Erfassungsberechtigung für diesen Standort.")
    if not aid.ready():
        raise HTTPException(503, "Fachschlüssel fehlt. Keine Daten wurden gespeichert.")
    if not aid.approved():
        raise HTTPException(423, "Vor Erfassung echter Gesundheitsdaten ist die Betriebs- und Datenschutzfreigabe erforderlich.")
    payload, errors = aid.validate(raw)
    if errors:
        result = render(request, "verbandbuch_form.html", user, sites=aid.sites_for(db, user, "capture"),
                        selected_id=site_id, values=payload, errors=errors,
                        now=datetime.now(LOCAL_TZ).strftime("%Y-%m-%dT%H:%M"),
                        approved=True, ready=True)
        result.status_code = 422
        return _private(result)
    now = utcnow()
    entry = FirstAidCase(site_id=site_id, created_by_id=user.id,
                         payload_enc=aid.seal(payload), created_at=now,
                         retention_due_at=aid.retention_date(now))
    db.add(entry)
    db.flush()
    aid.log_access(db, user.id, "capture", entry.id)
    db.commit()
    flash(request, "Die Erste-Hilfe-Leistung wurde geschützt dokumentiert.")
    return redirect("/verbandbuch/beleg/" + entry.id)


@app.get("/verbandbuch/beleg/{case_id}")
def verbandbuch_receipt(
    request: Request, case_id: str,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    entry = _case(db, case_id)
    if not user.active or not aid.may(db, user, entry.site_id, "review") and not (
        entry.created_by_id == user.id and aid.may(db, user, entry.site_id, "capture")
    ):
        raise HTTPException(404)
    site = db.get(FirstAidSite, entry.site_id)
    return _private(render(request, "verbandbuch_receipt.html", user,
                           entry=entry, site=site,
                           review=aid.may(db, user, entry.site_id, "review")))


@app.get("/verbandbuch/fall/{case_id}")
def verbandbuch_detail(
    request: Request, case_id: str,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    entry = aid.record_for_review(db, user, case_id)
    data, versions = aid.snapshot(db, entry)
    aid.log_access(db, user.id, "read", entry.id)
    db.commit()
    return _private(render(request, "verbandbuch_detail.html", user,
                           entry=entry, site=db.get(FirstAidSite, entry.site_id),
                           values=data, versions=versions, labels=aid.FIELD_LABELS, errors=[]))


@app.get("/verbandbuch/fall/{case_id}/druck")
def verbandbuch_print(
    request: Request, case_id: str,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    entry = aid.record_for_review(db, user, case_id)
    data, versions = aid.snapshot(db, entry)
    aid.log_access(db, user.id, "print", entry.id)
    db.commit()
    return _private(render(request, "verbandbuch_detail.html", user,
                           entry=entry, site=db.get(FirstAidSite, entry.site_id),
                           values=data, versions=versions, labels=aid.FIELD_LABELS, errors=[], printing=True))


@app.post("/verbandbuch/fall/{case_id}/korrektur", dependencies=[Depends(check_csrf)])
async def verbandbuch_correct(
    request: Request, case_id: str,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    entry = aid.record_for_review(db, user, case_id)
    raw = await request.form()
    values, errors = aid.validate(raw)
    reason = str(raw.get("reason") or "").strip()
    if not reason or len(reason) > 600:
        errors.append("Für jede Berichtigung ist eine Begründung (max. 600 Zeichen) erforderlich.")
    current, versions = aid.snapshot(db, entry)
    if values == current:
        errors.append("Es wurden keine Angaben geändert.")
    if errors:
        response = render(request, "verbandbuch_detail.html", user,
                          entry=entry, site=db.get(FirstAidSite, entry.site_id),
                          values=values, versions=versions, labels=aid.FIELD_LABELS, errors=errors)
        response.status_code = 422
        return _private(response)
    revision = versions[0].revision + 1 if versions else 1
    db.add(FirstAidCorrection(case_id=entry.id, revision=revision,
                              payload_enc=aid.seal(values), reason_enc=aid.seal(reason),
                              changed_by_id=user.id))
    aid.log_access(db, user.id, "correct", entry.id)
    db.commit()
    flash(request, "Berichtigung als neue, unveränderliche Version gespeichert.")
    return redirect("/verbandbuch/fall/" + entry.id)


@app.post("/verbandbuch/fall/{case_id}/sperren", dependencies=[Depends(check_csrf)])
async def verbandbuch_hold(
    request: Request, case_id: str,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    entry = aid.record_for_review(db, user, case_id)
    raw = await request.form()
    reason = str(raw.get("reason") or "").strip()
    if not 10 <= len(reason) <= 600:
        raise HTTPException(422, "Die Aufbewahrungssperre benötigt eine nachvollziehbare Begründung.")
    entry.legal_hold = True
    entry.legal_hold_reason_enc = aid.seal(reason)
    aid.log_access(db, user.id, "legal_hold", entry.id)
    db.commit()
    flash(request, "Löschsperre gesetzt. Aufhebung nur nach gesonderter fachlicher Freigabe.")
    return redirect("/verbandbuch/fall/" + entry.id)


@app.get("/verbandbuch/standorte")
def verbandbuch_sites(
    request: Request,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    if not user.is_admin:
        raise HTTPException(403)
    sites = db.scalars(select(FirstAidSite).order_by(FirstAidSite.title)).all()
    orgs = db.scalars(select(Organization).where(Organization.active.is_(True)).order_by(Organization.name)).all()
    users = db.scalars(select(User).where(User.active.is_(True)).order_by(User.name)).all()
    grants = db.scalars(select(FirstAidGrant).order_by(FirstAidGrant.site_id, FirstAidGrant.role)).all()
    return _private(render(request, "verbandbuch_sites.html", user, sites=sites, orgs=orgs, users=users,
                           grants=grants, qr_base=settings.portal_base_url, make_qr=aid.qr_token,
                           ready=aid.ready(), approved=aid.approved(), key_source=aid.key_source()))


@app.post("/verbandbuch/schluessel/erzeugen", dependencies=[Depends(check_csrf)])
def verbandbuch_generate_key(
    request: Request,
    user: User = Depends(current_user),
):
    if not user.is_admin:
        raise HTTPException(403)
    aid.generate_key_once()
    flash(request, "Fachschlüssel sicher auf dem Server erstellt. Jetzt unbedingt ein geschütztes Backup einrichten. Die Datenschutzfreigabe bleibt unverändert gesperrt.")
    return redirect("/verbandbuch/standorte")


@app.post("/verbandbuch/standorte", dependencies=[Depends(check_csrf)])
async def verbandbuch_site_create(
    request: Request,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    if not user.is_admin:
        raise HTTPException(403)
    form = await request.form()
    title = str(form.get("title") or "").strip()
    try:
        org_id = int(form.get("org_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(422, "Arbeitgeber / Organisation auswählen.") from None
    org = db.get(Organization, org_id)
    if not 2 <= len(title) <= 160 or not org or not active_path(db, org.id):
        raise HTTPException(422, "Bitte einen gültigen Standort und eine aktive Organisation wählen.")
    db.add(FirstAidSite(org_id=org_id, title=title))
    aid.log_access(db, user.id, "site_create")
    db.commit()
    flash(request, "Standort angelegt. Jetzt Fachberechtigungen zuweisen und QR-Code erzeugen.")
    return redirect("/verbandbuch/standorte")


@app.post("/verbandbuch/standorte/{site_id}/status", dependencies=[Depends(check_csrf)])
async def verbandbuch_site_status(request: Request, site_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.is_admin:
        raise HTTPException(403)
    site = db.get(FirstAidSite, site_id)
    if site is None:
        raise HTTPException(404)
    form = await request.form()
    if str(form.get("active") or "") not in {"0", "1"}:
        raise HTTPException(422)
    site.active = str(form.get("active")) == "1"
    aid.log_access(db, user.id, "site_activate" if site.active else "site_deactivate")
    db.commit()
    flash(request, "Standort aktiviert." if site.active else "Standort und QR-Zugang deaktiviert.")
    return redirect("/verbandbuch/standorte")


@app.post("/verbandbuch/standorte/{site_id}/berechtigungen", dependencies=[Depends(check_csrf)])
async def verbandbuch_grant(
    request: Request, site_id: int,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    if not user.is_admin:
        raise HTTPException(403)
    _site(db, site_id)
    form = await request.form()
    role = str(form.get("role") or "")
    try:
        target_id = int(form.get("user_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(422, "Person auswählen.") from None
    target = db.get(User, target_id)
    if role not in ("capture", "review") or not target or not target.active:
        raise HTTPException(422, "Gültige Person und Fachrolle auswählen.")
    needed = "verbandbuch_capture" if role == "capture" else "verbandbuch_review"
    if needed not in target.perms:
        raise HTTPException(422, "Der Person fehlt das entsprechende Fachrecht in der TAKT-Benutzerverwaltung.")
    if role == "review" and target.id == user.id:
        raise HTTPException(403, "Selbstfreigabe zur Einsicht in Gesundheitsdaten ist nicht zulässig.")
    existing = db.scalar(select(FirstAidGrant).where(
        FirstAidGrant.site_id == site_id, FirstAidGrant.user_id == target_id, FirstAidGrant.role == role))
    if existing is None:
        db.add(FirstAidGrant(site_id=site_id, user_id=target_id, role=role, created_by_id=user.id))
        aid.log_access(db, user.id, "grant")
        db.commit()
    flash(request, "Standortberechtigung gespeichert. Zusätzlich muss das Fachrecht im Benutzerprofil vergeben sein.")
    return redirect("/verbandbuch/standorte")


@app.post("/verbandbuch/standorte/{site_id}/berechtigungen/{grant_id}/entziehen", dependencies=[Depends(check_csrf)])
def verbandbuch_revoke(
    request: Request, site_id: int, grant_id: int,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    if not user.is_admin:
        raise HTTPException(403)
    grant = db.get(FirstAidGrant, grant_id)
    if grant is None or grant.site_id != site_id:
        raise HTTPException(404)
    db.delete(grant)
    aid.log_access(db, user.id, "revoke")
    db.commit()
    flash(request, "Fachberechtigung entzogen.")
    return redirect("/verbandbuch/standorte")
