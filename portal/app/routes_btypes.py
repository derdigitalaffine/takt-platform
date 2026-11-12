"""Terminbuchung im erweiterten Umfang: Terminarten, zuständige Mitarbeitende, Sprechzeiten und Ausnahmen
verwalten (Stufe „Bearbeiten“ der Buchungsseite). Logik in btypes.py."""

from datetime import date, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import bookings as bk, btypes, shares as sh
from .db import BookingClosure, BookingHours, BookingType, Organization, User, to_local, utcnow
from .main import app, check_csrf, current_user, flash, get_db, redirect, render
from .routes_bookings import _bpage, _int


def _users(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.active.is_(True)).order_by(User.name)))


@app.get("/bookings/{page_id}/arten")
def btypes_page(request: Request, page_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.EDIT)
    providers = btypes.all_providers(page, db)
    organizations = list(db.scalars(select(Organization).where(
        Organization.active.is_(True)).order_by(Organization.name)))
    from . import booking_integration
    oid = booking_integration.creator_org_id(db, page)
    unit = db.get(Organization, oid) if oid else None
    calendar_module_enabled = booking_integration.calendars_enabled(db)
    org_closing_entries = []
    if oid and calendar_module_enabled:
        from . import organization as org
        from .leave_extensions import Closure
        path = org.active_path(db, oid)
        if path:
            now = to_local(utcnow()).date()
            org_closing_entries = list(db.scalars(select(Closure).where(
                Closure.org_id.in_(path),
                Closure.starts_on <= (now + timedelta(days=366)).isoformat(),
                Closure.ends_on >= now.isoformat(),
            ).order_by(Closure.starts_on).limit(20)))
    return render(request, "booking_types.html", user, page=page, users=_users(db),
                  providers=providers, organizations=organizations, routing=btypes.routing,
                  org_closures=booking_integration.options(page).get("org_closures", True) is not False,
                  creator_org_name=unit.name if unit else "",
                  calendar_module_enabled=calendar_module_enabled,
                  org_closing_entries=org_closing_entries,
                  plan=btypes.weekly_plan(page), weekdays=btypes.WEEKDAYS, durations=btypes.DURATIONS,
                  phone_modes=btypes.PHONE_MODES, summary=btypes.summary, field_kinds=btypes.FIELD_KINDS,
                  fields=btypes.fields, max_fields=btypes.MAX_FIELDS, can_video=user.can("video"),
                  previews={t.id: btypes.slots(db, page, t)[:3] for t in page.types}, label=bk.label)


@app.post("/bookings/{page_id}/arten", dependencies=[Depends(check_csrf)])
async def btypes_save(request: Request, page_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Terminart anlegen (type_id leer) oder ändern."""
    page, _level = _bpage(db, page_id, user, sh.EDIT)
    data = await request.form()
    tid = str(data.get("type_id", ""))
    bt = next((t for t in page.types if str(t.id) == tid), None) if tid else None
    if tid and bt is None:
        raise HTTPException(404)
    name = " ".join(str(data.get("name", "")).split())[:160]
    if not name:
        flash(request, "Bitte einen Namen für die Terminart angeben.", "error")
        return redirect(f"/bookings/{page.id}/arten")
    if bt is None:
        bt = BookingType(page_id=page.id, position=len(page.types))
        db.add(bt)
    bt.name = name
    bt.description = str(data.get("description", "")).replace("\r\n", "\n").strip()[:3000]
    bt.docs_hint = str(data.get("docs_hint", "")).replace("\r\n", "\n").strip()[:2000]
    bt.duration_minutes = _int(data.get("duration_minutes"), 5, 480, 30)
    bt.buffer_minutes = _int(data.get("buffer_minutes"), 0, 240, 0)
    bt.min_notice_hours = _int(data.get("min_notice_hours"), 0, 24 * 60, 24)
    bt.location = " ".join(str(data.get("location", "")).split())[:255]
    bt.online = data.get("online") == "1" and user.can("video")
    bt.approval = data.get("approval") == "1"
    bt.choose_provider = data.get("choose_provider") == "1"
    bt.active = data.get("active", "1") == "1"
    bt.phone_mode = data.get("phone_mode") if data.get("phone_mode") in btypes.PHONE_MODES else "optional"
    bt.privacy_mode = data.get("privacy_mode") if data.get("privacy_mode") in ("inherit", "restricted", "busy") else "inherit"
    bt.fields_json = btypes.clean_fields(data.getlist("f_label"), data.getlist("f_kind"), data.getlist("f_options"),
                                         set(data.getlist("f_required")), data.getlist("f_help"))
    ids = {int(x) for x in data.getlist("providers") if str(x).isdigit()}
    bt.providers = list(db.scalars(select(User).where(User.id.in_(ids), User.active.is_(True)))) if ids else []
    mode = str(data.get("routing_mode", "manual"))
    if mode not in ("manual", "organization", "mixed"):
        mode = "manual"
    org_id = int(data.get("routing_org_id")) if str(data.get("routing_org_id", "")).isdigit() else None
    if mode in ("organization", "mixed"):
        org = db.get(Organization, org_id) if org_id else None
        if not org or not org.active:
            db.rollback()
            flash(request, "Bitte eine aktive Organisationseinheit für die Terminverteilung auswählen.", "error")
            return redirect(f"/bookings/{page.id}/arten")
    else:
        org_id = None
    import json
    bt.routing_json = json.dumps({"mode": mode, "org_id": org_id,
                                  "include_children": data.get("routing_children") == "1"},
                                 ensure_ascii=False)
    db.flush()
    eligible = btypes.providers_for(db, bt)
    db.commit()
    missing = [p.name for p in eligible if not any(h.user_id == p.id for h in page.hours)]
    flash(request, f"Terminart „{bt.name}“ gespeichert." + (
        f" Noch ohne Sprechzeiten: {', '.join(missing)} – bitte unten eintragen." if missing else "")
        + ("" if eligible else " Ohne geeignete zuständige Person wird sie nicht angeboten."))
    return redirect(f"/bookings/{page.id}/arten#art-{bt.id}")


@app.post("/bookings/{page_id}/arten/{type_id}/loeschen", dependencies=[Depends(check_csrf)])
def btypes_delete(request: Request, page_id: int, type_id: int, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    page, _level = _bpage(db, page_id, user, sh.EDIT)
    bt = db.get(BookingType, type_id)
    if bt is None or bt.page_id != page.id:
        raise HTTPException(404)
    if any(b.type_id == bt.id and b.status in ("booked", "requested") for b in page.bookings):
        bt.active = False
        flash(request, f"„{bt.name}“ hat noch Termine und wurde deshalb nur abgeschaltet.")
    else:
        db.delete(bt)
        flash(request, f"Terminart „{bt.name}“ gelöscht.")
    db.commit()
    return redirect(f"/bookings/{page.id}/arten")


@app.post("/bookings/{page_id}/sprechzeiten", dependencies=[Depends(check_csrf)])
async def btypes_hours_add(request: Request, page_id: int, user: User = Depends(current_user),
                           db: Session = Depends(get_db)):
    page, _level = _bpage(db, page_id, user, sh.EDIT)
    data = await request.form()
    uid = int(data["user_id"]) if str(data.get("user_id", "")).isdigit() else None
    start, end = btypes.valid_time(str(data.get("start", ""))), btypes.valid_time(str(data.get("end", "")))
    days = [int(d) for d in data.getlist("weekday") if str(d).isdigit() and 0 <= int(d) <= 6]
    if uid is None or not db.get(User, uid) or not start or not end or end <= start or not days:
        flash(request, "Bitte Person, Wochentag(e) sowie Beginn und Ende (HH:MM, Ende nach Beginn) angeben.", "error")
        return redirect(f"/bookings/{page.id}/arten#sprechzeiten")
    added = 0
    for d in days:
        if any(h.user_id == uid and h.weekday == d and h.start < end and start < h.end for h in page.hours):
            continue
        page.hours.append(BookingHours(page_id=page.id, user_id=uid, weekday=d, start=start, end=end))
        added += 1
    db.commit()
    flash(request, f"{added} Sprechzeit(en) eingetragen." if added else "Überschneidet sich mit vorhandenen Sprechzeiten.",
          "ok" if added else "error")
    return redirect(f"/bookings/{page.id}/arten#sprechzeiten")


@app.post("/bookings/{page_id}/sprechzeiten/{hid}/loeschen", dependencies=[Depends(check_csrf)])
def btypes_hours_delete(request: Request, page_id: int, hid: int, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    page, _level = _bpage(db, page_id, user, sh.EDIT)
    h = db.get(BookingHours, hid)
    if h is None or h.page_id != page.id:
        raise HTTPException(404)
    db.delete(h)
    db.commit()
    return redirect(f"/bookings/{page.id}/arten#sprechzeiten")


@app.post("/bookings/{page_id}/ausnahmen/schliesszeiten", dependencies=[Depends(check_csrf)])
async def booking_org_closures_toggle(
    request: Request, page_id: int, user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Save a single page-level opt-out without resetting its other settings."""
    page, _level = _bpage(db, page_id, user, sh.EDIT)
    data = await request.form()
    import json
    from . import booking_integration
    settings = booking_integration.options(page)
    settings["org_closures"] = data.get("org_closures") == "1"
    page.integration_json = json.dumps(settings, ensure_ascii=False)
    db.commit()
    flash(request, "Schließtag-Einstellung übernommen. Bestehende Termine bleiben unverändert.")
    return redirect(f"/bookings/{page.id}/arten#ausnahmen")


@app.post("/bookings/{page_id}/ausnahmen", dependencies=[Depends(check_csrf)])
async def btypes_closure_add(request: Request, page_id: int, user: User = Depends(current_user),
                             db: Session = Depends(get_db)):
    page, _level = _bpage(db, page_id, user, sh.EDIT)
    data = await request.form()

    def day(v):
        try:
            return date.fromisoformat(str(v or "")).isoformat()
        except ValueError:
            return None
    d0, d1 = day(data.get("date_from")), day(data.get("date_to")) or day(data.get("date_from"))
    uid = int(data["user_id"]) if str(data.get("user_id", "")).isdigit() else None
    if not d0 or not d1 or d1 < d0:
        flash(request, "Bitte einen gültigen Zeitraum angeben.", "error")
        return redirect(f"/bookings/{page.id}/arten#ausnahmen")
    page.closures.append(BookingClosure(page_id=page.id, user_id=uid, date_from=d0, date_to=d1,
                                        note=" ".join(str(data.get("note", "")).split())[:200]))
    db.commit()
    flash(request, "Ausnahme eingetragen – an diesen Tagen werden keine Termine angeboten.")
    return redirect(f"/bookings/{page.id}/arten#ausnahmen")


@app.post("/bookings/{page_id}/ausnahmen/{cid}/loeschen", dependencies=[Depends(check_csrf)])
def btypes_closure_delete(request: Request, page_id: int, cid: int, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    page, _level = _bpage(db, page_id, user, sh.EDIT)
    c = db.get(BookingClosure, cid)
    if c is None or c.page_id != page.id:
        raise HTTPException(404)
    db.delete(c)
    db.commit()
    return redirect(f"/bookings/{page.id}/arten#ausnahmen")
