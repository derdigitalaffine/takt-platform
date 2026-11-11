"""Seiten der Terminbuchung: Buchungsseiten verwalten, Zeitbereiche im Kalender, öffentliches Buchen."""

from datetime import timedelta
from urllib.parse import quote, urlencode

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from . import access, bookings as bk, shares as sh, shortlinks as sl, worker
from .db import Booking, BookingInvite, BookingPage, BookingWindow, Group, Organization, User, to_local, utcnow
from .main import (
    app, check_csrf, current_user, home_for, flash, get_db, rate_limit, redirect, render, require, session_user,
)
from .planning import DURATIONS, EMAIL_RE
from .security import new_link_token, room_slug

booking_user = require("bookings")
SLOT_CHOICES = [10, 15, 20, 30, 45, 60, 90, 120]
PAUSE_CHOICES = [0, 5, 10, 15, 30]


def _bpage(db: Session, page_id: int, user: User, need: int) -> tuple[BookingPage, int]:
    """Buchungsseite mit Zugriffsprüfung. need: sh.VIEW, sh.INVITE, sh.EDIT oder sh.OWNER."""
    page = db.get(BookingPage, page_id)
    level = sh.access_level(db, "booking", page, user)
    if level == 0:
        raise HTTPException(404, "Buchungsseite nicht gefunden.")
    if level < need:
        raise HTTPException(403, "Für diese Aktion reicht Ihre Freigabe für die Buchungsseite nicht aus.")
    return page, level


def _int(value, lo: int, hi: int, default: int) -> int:
    try:
        return min(max(int(value), lo), hi)
    except (TypeError, ValueError):
        return default


def _apply(page: BookingPage, data) -> None:
    flag = lambda key: data.get(key) == "1"  # noqa: E731
    page.title = " ".join(str(data.get("title", "")).split())[:255] or page.title or "Terminbuchung"
    page.description = str(data.get("description", "")).replace("\r\n", "\n").strip()[:5000]
    page.location = " ".join(str(data.get("location", "")).split())[:255]
    page.slot_minutes = _int(data.get("slot_minutes"), 5, 480, 30)
    page.pause_minutes = _int(data.get("pause_minutes"), 0, 240, 0)
    page.capacity = _int(data.get("capacity"), 1, 500, 1)
    page.min_notice_hours = _int(data.get("min_notice_hours"), 0, 24 * 60, 12)
    page.cancel_hours = _int(data.get("cancel_hours"), 0, 24 * 60, 24)
    page.max_per_person = _int(data.get("max_per_person"), 1, 50, 1)
    page.reminder_hours = _int(data.get("reminder_hours"), 0, 24 * 14, 24)
    page.invite_only, page.ask_phone = flag("invite_only"), flag("ask_phone")
    page.listed = flag("listed") and not page.invite_only
    if "extended_form" in data:   # Schalter nur auf der Einstellungsseite (nicht beim Kopieren o. Ä.)
        page.extended = flag("extended")
        page.days_ahead = _int(data.get("days_ahead"), 1, 730, 60)
        page.step_minutes = _int(data.get("step_minutes"), 5, 60, 15)
        page.holidays_closed = flag("holidays_closed")
    page.online, page.notify_owner = flag("online"), flag("notify_owner")
    page.confirm_text = str(data.get("confirm_text", "")).replace("\r\n", "\n").strip()[:2000]
    if "integration_form" in data:
        import json
        from . import booking_integration
        opts = booking_integration.options(page)
        opts.update({
            "calendar_conflicts": flag("calendar_conflicts"),
            "org_closures": flag("org_closures"),
            "conflict_sources": [key for key in ("personal", "meetings")
                                 if flag("conflict_" + key)],
            "staff_calendar_attachment": flag("staff_calendar_attachment"),
            "mail_digest": flag("mail_digest"),
            "calendar_privacy": data.get("calendar_privacy") if data.get("calendar_privacy")
                                in ("staff", "assigned", "busy") else "staff",
            "external_calendar": data.get("external_calendar") if data.get("external_calendar")
                                 in ("busy", "type") else "busy",
        })
        page.integration_json = json.dumps(opts, ensure_ascii=False)



def _settings_ctx(page: BookingPage | None, user: User, db: Session) -> dict:
    from . import booking_integration
    integration = booking_integration.options(page) if page else {
        "calendar_conflicts": True, "conflict_sources": ["personal", "meetings"],
        "staff_calendar_attachment": False, "mail_digest": False, "org_closures": True}
    target = page or BookingPage(owner_id=user.id, title="", public_token="")
    creator_unit_id = booking_integration.creator_org_id(db, target)
    unit = db.get(Organization, creator_unit_id) if creator_unit_id else None
    return {"page": page, "slot_choices": SLOT_CHOICES, "pause_choices": PAUSE_CHOICES, "durations": DURATIONS,
            "can_video": user.can("video"), "integration": integration,
            "creator_org_name": unit.name if unit else "",
            "calendar_module_enabled": booking_integration.calendars_enabled(db)}


# --- Verwaltung --------------------------------------------------------------------------

@app.get("/bookings")
def bookings_list(request: Request, all: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    show_all = user.is_admin and all == "1"
    shared = [] if show_all else sh.shared_with(db, "booking", user)
    if not user.can("bookings") and not shared:
        raise HTTPException(403, "Für den Bereich „Terminbuchung“ fehlt die Berechtigung. "
                                 "Bitte wenden Sie sich an die Verwaltung des Portals.")
    q = select(BookingPage).options(joinedload(BookingPage.owner)).order_by(BookingPage.updated_at.desc())
    if not show_all:
        q = q.where(BookingPage.owner_id == user.id)
    pages = db.scalars(q).unique().all() if user.can("bookings") else []
    now = utcnow()
    upcoming = dict(db.execute(select(Booking.page_id, func.count(Booking.id))
                               .where(Booking.status == "booked", Booking.starts_at >= now)
                               .group_by(Booking.page_id)).all())
    free = {p.id: sum(s["free"] for s in bk.free_slots(db, p)) for p in list(pages) + [p for p, _ in shared]}
    return render(request, "bookings.html", user, pages=pages, upcoming=upcoming, free=free, show_all=show_all,
                  shared=shared, levels=sh.LEVELS["booking"])


@app.get("/bookings/new")
def booking_new(request: Request, user: User = Depends(booking_user), db: Session = Depends(get_db)):
    return render(request, "booking_settings.html", user, **_settings_ctx(None, user, db))


@app.post("/bookings/new", dependencies=[Depends(check_csrf)])
async def booking_create(request: Request, user: User = Depends(booking_user), db: Session = Depends(get_db)):
    data = await request.form()
    page = BookingPage(owner_id=user.id, title="", public_token=new_link_token())
    _apply(page, data)
    # Fix the creator's organization to the booking page at creation.
    # Closing days must not silently change when the owner is reassigned.
    from . import booking_integration
    import json
    opts = booking_integration.options(page)
    opts["creator_org_id"] = booking_integration.creator_org_id(db, page)
    page.integration_json = json.dumps(opts, ensure_ascii=False)
    if page.online and not user.can("video"):
        page.online = False
    db.add(page)
    db.commit()
    flash(request, "Buchungsseite angelegt. Ziehen Sie jetzt im Kalender die Zeitbereiche auf, in denen gebucht "
                   "werden kann.")
    return redirect(f"/bookings/{page.id}")


@app.get("/bookings/{page_id}")
def booking_detail(request: Request, page_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.VIEW)
    now = utcnow()
    active = bk.active_bookings(page)
    users = db.scalars(select(User).where(User.active.is_(True)).order_by(User.name)).all()
    groups = db.scalars(select(Group).order_by(Group.name)).all()
    free_slots = bk.free_slots(db, page)
    first = min([s["start"] for s in free_slots] or
                [w.starts_at for w in page.windows if w.ends_at >= now], default=now)
    link = bk.public_link(page)
    qp = request.query_params
    filt = {"status": qp.get("status") if qp.get("status") in bk.STATUS_FILTERS else "upcoming",
            "date_from": qp.get("from", "")[:10], "date_to": qp.get("to", "")[:10], "q": qp.get("q", "")[:100],
            "sort": qp.get("sort") if qp.get("sort") in bk.SORTS else "start"}
    query = urlencode({"status": filt["status"], "from": filt["date_from"], "to": filt["date_to"], "q": filt["q"],
                       "sort": filt["sort"]})
    return render(request, "booking.html", user, page=page, upcoming=[b for b in active if b.ends_at >= now],
                  listed=bk.filter_bookings(page, **filt), filt=filt, export_query=query,
                  status_filters=bk.STATUS_FILTERS, sorts=bk.SORTS, feed_url=bk.feed_link(page), now=now,
                  past=[b for b in active if b.ends_at < now],
                  cancelled=[b for b in page.bookings if b.status == "cancelled"],
                  free_count=sum(s["free"] for s in free_slots),
                  slot_count=len(free_slots) if page.extended else len(bk.slots(page)),
                  free_days=bk.group_by_day(free_slots), label=bk.label, public_url=link, users=users, groups=groups,
                  booked_emails=bk.booked_emails(page), invite_link=bk.invite_link, errors=sl.QR_ERRORS,
                  events=bk.calendar_events(page), initial_date=to_local(first).date().isoformat(),
                  manage_link=bk.manage_link, answers=bk.answers,
                  shortlink_url="/shortlinks?new=" + quote(link) + "&title=" + quote(page.title)
                  + "&next=" + quote(f"/bookings/{page.id}") + "#neu", level=level, share_levels=sh.LEVELS["booking"])


@app.get("/bookings/{page_id}/settings")
def booking_settings(request: Request, page_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "booking_settings.html", user, **_settings_ctx(_bpage(db, page_id, user, sh.EDIT)[0], user, db))


@app.post("/bookings/{page_id}/settings", dependencies=[Depends(check_csrf)])
async def booking_settings_save(request: Request, page_id: int, user: User = Depends(current_user),
                                db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.EDIT)
    data = await request.form()
    before = (page.slot_minutes, page.pause_minutes)
    _apply(page, data)
    if page.online and not user.can("video"):
        page.online = False
    db.commit()
    msg = "Einstellungen gespeichert."
    if before != (page.slot_minutes, page.pause_minutes) and bk.active_bookings(page):
        msg += " Bestehende Buchungen behalten ihre Zeiten; neue Zeitfenster richten sich nach der neuen Dauer."
    flash(request, msg)
    if page.extended and not page.types:
        return redirect(f"/bookings/{page.id}/arten")
    return redirect(f"/bookings/{page.id}")


@app.get("/bookings/{page_id}/events.json")
def booking_events(page_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return JSONResponse(bk.calendar_events(_bpage(db, page_id, user, sh.VIEW)[0]))


def _window_change_payload(db: Session, page: BookingPage, message: str) -> dict:
    """Aktuelle Kalenderdaten und kleine Vorschau ohne erneutes Laden der gesamten Seite."""
    free = bk.bookable(page, db=db)
    days = bk.group_by_day(free)
    return {
        "ok": True, "message": message, "events": bk.calendar_events(page),
        "availability": {
            "free_count": sum(s["free"] for s in free),
            "slot_count": len(bk.slots(page)),
            "window_count": len(page.windows),
            "days": [
                {"label": f'{day["weekday_long"]}, {day["full"]}',
                 "count": len(day["slots"]),
                 "slots": [{"time": slot["time"], "free": slot["free"]}
                           for slot in day["slots"][:8]]}
                for day in days[:7]
            ],
        },
    }


@app.post("/bookings/{page_id}/windows", dependencies=[Depends(check_csrf)])
async def booking_window_add(request: Request, page_id: int, user: User = Depends(current_user),
                             db: Session = Depends(get_db)):
    """Zeitbereich anlegen – aus dem Kalender (start/end, JSON-Antwort) oder aus dem Formular (mit Wiederholung)."""
    page, level = _bpage(db, page_id, user, sh.EDIT)
    data = await request.form()
    ajax = request.headers.get("x-requested-with") == "fetch"
    if data.get("date"):
        day, start_t, end_t = str(data.get("date")), str(data.get("from", "")), str(data.get("to", ""))
        start, end = bk.parse_local(f"{day}T{start_t}"), bk.parse_local(f"{day}T{end_t}")
    else:
        start, end = bk.parse_local(str(data.get("start", ""))), bk.parse_local(str(data.get("end", "")))
    error = "" if start and end and bk.horizon_ok(start) else "Bitte gültige Zeiten angeben."
    weeks = _int(data.get("repeat_weeks"), 0, 52, 0)
    created = 0
    if not error:
        for n in range(weeks + 1):
            # Wochenweise in Ortszeit wiederholen (Sommer-/Winterzeit bleibt korrekt)
            s_local, e_local = to_local(start) + timedelta(weeks=n), to_local(end) + timedelta(weeks=n)
            error = bk.add_window(db, page, bk.to_utc(s_local.replace(tzinfo=None)), bk.to_utc(e_local.replace(tzinfo=None)))
            if error:
                break
            created += 1
    if error:
        # Eine Wiederholung ist eine Transaktion: nie nur einzelne Wochen übernehmen.
        db.rollback()
    else:
        db.commit()
    if ajax:
        if error:
            return JSONResponse({"ok": False, "error": error}, status_code=422)
        return JSONResponse(_window_change_payload(db, page, f"{created} Zeitbereich(e) hinzugefügt."))
    if error:
        flash(request, error, "error")
    else:
        flash(request, f"{created} Zeitbereich(e) hinzugefügt.")
    return redirect(f"/bookings/{page.id}#kalender")


@app.post("/bookings/{page_id}/windows/{wid}/delete", dependencies=[Depends(check_csrf)])
def booking_window_delete(request: Request, page_id: int, wid: int, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.EDIT)
    w = db.get(BookingWindow, wid)
    if w is None or w.page_id != page.id:
        raise HTTPException(404)
    affected = [b for b in bk.active_bookings(page) if w.starts_at <= b.starts_at < w.ends_at]
    db.delete(w)
    db.commit()
    db.refresh(page)
    msg = "Zeitbereich entfernt." + (f" {len(affected)} Buchung(en) darin bleiben bestehen – sagen Sie sie bei "
                                     "Bedarf unten ab." if affected else "")
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse(_window_change_payload(db, page, msg))
    flash(request, msg)
    return redirect(f"/bookings/{page.id}#kalender")


@app.post("/bookings/{page_id}/windows/clear", dependencies=[Depends(check_csrf)])
def booking_windows_clear(request: Request, page_id: int, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.EDIT)
    now = utcnow()
    removed = 0
    for w in list(page.windows):
        if w.starts_at >= now:
            page.windows.remove(w)
            db.delete(w)
            removed += 1
    db.commit()
    msg = f"{removed} künftige Zeitbereiche entfernt. Bestehende Buchungen bleiben erhalten."
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse(_window_change_payload(db, page, msg))
    flash(request, msg)
    return redirect(f"/bookings/{page.id}#kalender")


@app.post("/bookings/{page_id}/entries/{bid}", dependencies=[Depends(check_csrf)])
def booking_entry_action(request: Request, page_id: int, bid: int, action: str = Form(...), reason: str = Form(""),
                         slot: str = Form(""), user: User = Depends(current_user), db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.EDIT)
    b = db.get(Booking, bid)
    if b is None or b.page_id != page.id:
        raise HTTPException(404)
    if action == "confirm":
        bk.confirm(db, b)
        flash(request, f"Termin von {b.name} bestätigt – die Bestätigung mit Kalendereintrag geht per Mail raus.")
    elif action == "cancel":
        declined = b.status == "requested"
        bk.cancel(db, b, "owner", " ".join(reason.split()))
        flash(request, f"Anfrage von {b.name} abgelehnt." if declined else f"Termin von {b.name} abgesagt. {b.name} wird per Mail informiert.")
    elif action == "move":
        start = bk.parse_local(slot)
        error = bk.move(db, b, start) if start else "Bitte einen Termin wählen."
        if error:
            db.rollback()
            flash(request, error, "error")
            return redirect(f"/bookings/{page.id}#buchungen")
        flash(request, f"Termin von {b.name} verschoben auf {bk.label(b.starts_at, b.ends_at)}.")
    db.commit()
    access.sync(db)
    worker.wake()
    return redirect(f"/bookings/{page.id}#buchungen")


@app.post("/bookings/{page_id}/invite", dependencies=[Depends(check_csrf)])
async def booking_invite(request: Request, page_id: int, user: User = Depends(current_user),
                         db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.INVITE)
    data = await request.form()
    guests, bad = bk.parse_guests(str(data.get("guests", "")))
    if bad:
        flash(request, "Nicht erkannt (bitte „Name <E-Mail>“ oder nur die Adresse je Zeile): " + "; ".join(bad[:5]),
              "error")
        return redirect(f"/bookings/{page.id}#einladungen")
    added, skipped = bk.invite(db, page, user, [int(v) for v in data.getlist("users") if str(v).isdigit()],
                               [int(v) for v in data.getlist("groups") if str(v).isdigit()], guests)
    db.commit()
    worker.wake()
    if added or skipped:
        flash(request, f"{added} Person(en) eingeladen" + (f", {skipped} waren schon eingeladen" if skipped else "") + ".")
    else:
        flash(request, "Bitte Personen, Gruppen oder Adressen angeben.", "error")
    return redirect(f"/bookings/{page.id}#einladungen")


@app.post("/bookings/{page_id}/invites/remind", dependencies=[Depends(check_csrf)])
def booking_invites_remind(request: Request, page_id: int, user: User = Depends(current_user),
                           db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.INVITE)
    count = bk.remind_invites(db, page, user)
    db.commit()
    worker.wake()
    flash(request, f"Erinnerung an {count} Person(en) ohne Termin wird verschickt." if count else
          "Alle Eingeladenen haben schon gebucht (oder Mailversand nicht eingerichtet).")
    return redirect(f"/bookings/{page.id}#einladungen")


@app.post("/bookings/{page_id}/invites/{iid}/delete", dependencies=[Depends(check_csrf)])
def booking_invite_delete(request: Request, page_id: int, iid: int, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.INVITE)
    inv = db.get(BookingInvite, iid)
    if inv is None or inv.page_id != page.id:
        raise HTTPException(404)
    db.delete(inv)
    db.commit()
    flash(request, f"Einladung für {inv.email} entfernt. Bestehende Buchungen bleiben.")
    return redirect(f"/bookings/{page.id}#einladungen")


@app.post("/bookings/{page_id}/state", dependencies=[Depends(check_csrf)])
def booking_state(request: Request, page_id: int, action: str = Form(...), user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.INVITE if action == "renew" else sh.EDIT)
    if action == "pause":
        page.active = False
        flash(request, "Buchungen pausiert. Bestehende Termine bleiben, neue Buchungen sind nicht möglich.")
    elif action == "resume":
        page.active = True
        flash(request, "Buchungen wieder möglich.")
    elif action == "renew":
        page.public_token = new_link_token()
        flash(request, "Neuer Link erzeugt. Der bisherige funktioniert nicht mehr (auch Einladungslinks).")
    db.commit()
    return redirect(f"/bookings/{page.id}")


@app.post("/bookings/{page_id}/delete", dependencies=[Depends(check_csrf)])
def booking_delete(request: Request, page_id: int, notify_guests: str = Form(""), user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.EDIT)
    future = [b for b in bk.active_bookings(page) if b.starts_at >= utcnow()]
    for b in future:
        if notify_guests == "1":
            bk.cancel(db, b, "owner", "Die Terminbuchung wurde beendet.")
        elif b.meeting_id:  # Videokonferenz still entfernen
            from .db import Meeting
            meeting = db.get(Meeting, b.meeting_id)
            if meeting is not None:
                for rec in meeting.recordings:
                    rec.meeting_id = None
                db.delete(meeting)
    db.flush()
    db.delete(page)
    db.commit()
    access.sync(db)
    worker.wake()
    flash(request, f"Buchungsseite „{page.title}“ gelöscht." + (f" {len(future)} Gäste werden über die Absage "
                                                                  "informiert." if future and notify_guests == "1" else ""))
    return redirect("/bookings" if user.can("bookings") else home_for(user))


@app.post("/bookings/{page_id}/copy", dependencies=[Depends(check_csrf)])
def booking_copy(request: Request, page_id: int, user: User = Depends(booking_user), db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.VIEW)
    clone = BookingPage(owner_id=user.id, public_token=new_link_token(), title=(page.title + " (Kopie)")[:255])
    for col in ("description", "location", "slot_minutes", "pause_minutes", "capacity", "min_notice_hours",
                "cancel_hours", "max_per_person", "invite_only", "listed", "ask_phone", "online", "notify_owner", "integration_json",
                "reminder_hours", "confirm_text"):
        setattr(clone, col, getattr(page, col))
    db.add(clone)
    db.commit()
    flash(request, "Kopie angelegt – ohne Zeitbereiche, Buchungen und Einladungen.")
    return redirect(f"/bookings/{clone.id}")


EXPORTS = {"csv": ("text/csv; charset=utf-8", "csv"), "json": ("application/json; charset=utf-8", "json"),
           "md": ("text/markdown; charset=utf-8", "md"), "ics": ("text/calendar; charset=utf-8", "ics")}


@app.get("/bookings/{page_id}/export.{fmt}")
def booking_export(request: Request, page_id: int, fmt: str, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    """Terminliste exportieren – mit denselben Filtern wie in der Übersicht."""
    page, level = _bpage(db, page_id, user, sh.VIEW)
    if fmt not in EXPORTS:
        raise HTTPException(404)
    qp = request.query_params
    items = bk.filter_bookings(page, qp.get("status") if qp.get("status") in bk.STATUS_FILTERS else "all",
                               qp.get("from", "")[:10], qp.get("to", "")[:10], qp.get("q", "")[:100],
                               qp.get("sort") if qp.get("sort") in bk.SORTS else "start")
    content = {"csv": bk.to_csv, "json": bk.to_json, "md": bk.to_markdown, "ics": bk.to_ics}[fmt](page, items)
    media, ext = EXPORTS[fmt]
    name = f"{room_slug(page.title) or 'buchungen'}-{to_local(utcnow()):%Y-%m-%d}.{ext}"
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/bookings/{page_id}/feed", dependencies=[Depends(check_csrf)])
def booking_feed(request: Request, page_id: int, action: str = Form(...), user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.EDIT)
    if action in ("enable", "renew"):
        page.feed_token = new_link_token()
        flash(request, "Kalender-Abo eingerichtet." if action == "enable" else
              "Neuer Abo-Link erzeugt. Der bisherige funktioniert nicht mehr.")
    else:
        page.feed_token = None
        flash(request, "Kalender-Abo abgeschaltet.")
    db.commit()
    return redirect(f"/bookings/{page.id}#export")


@app.post("/bookings/{page_id}/shares", dependencies=[Depends(check_csrf)])
async def booking_share_add(request: Request, page_id: int, user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    """Im Portal für Personen oder Gruppen freigeben (nur Besitzer:in bzw. Admin)."""
    page, _ = _bpage(db, page_id, user, sh.OWNER)
    added, level = sh.add(db, "booking", page, await request.form())
    db.commit()
    flash(request, f"Freigabe für {added} Eintrag/Einträge gespeichert: {sh.LEVELS['booking'][level][0]}." if added
          else "Bitte Personen oder Gruppen auswählen.", "ok" if added else "error")
    return redirect(f"/bookings/{page.id}#freigaben")


@app.post("/bookings/{page_id}/shares/{share_id}", dependencies=[Depends(check_csrf)])
def booking_share_update(request: Request, page_id: int, share_id: int, action: str = Form("save"),
                         level: int = Form(1), user: User = Depends(current_user), db: Session = Depends(get_db)):
    page, _ = _bpage(db, page_id, user, sh.OWNER)
    message = sh.update(db, "booking", page, share_id, action, level)
    if message is None:
        raise HTTPException(404)
    db.commit()
    flash(request, message)
    return redirect(f"/bookings/{page.id}#freigaben")


@app.get("/b/feed/{token}.ics")
def booking_feed_ics(token: str, db: Session = Depends(get_db)):
    """Abonnierbarer Kalender der anbietenden Person (geheimer Link): gebuchte Termine ab 30 Tagen zurück."""
    page = db.scalar(select(BookingPage).where(BookingPage.feed_token == token)) if len(token) > 10 else None
    if page is None:
        raise HTTPException(404)
    since = utcnow() - timedelta(days=30)
    items = [b for b in page.bookings if b.status == "booked" and b.starts_at >= since]
    return Response(bk.to_ics(page, items), media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "private, max-age=300"})


@app.get("/bookings/{page_id}/qr.{fmt}")
def booking_qr(page_id: int, fmt: str, size: int = 10, dark: str = "#000000", light: str = "#ffffff",
               error: str = "m", border: int = 2, download: str = "", user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    page, level = _bpage(db, page_id, user, sh.INVITE)
    opts = sl.qr_options(fmt, size, dark, light, error, border)
    data, media = sl.qr_image(bk.public_link(page), opts)
    headers = {"Cache-Control": "private, max-age=60"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="qr-terminbuchung-{page.id}.{opts["fmt"]}"'
    return Response(data, media_type=media, headers=headers)


# --- Öffentlich: buchen, verschieben, absagen ------------------------------------------------

def _page(db: Session, token: str) -> BookingPage | None:
    return db.scalar(select(BookingPage).where(BookingPage.public_token == token)) if len(token) > 10 else None


def _invite(db: Session, page: BookingPage, token: str) -> BookingInvite | None:
    inv = db.scalar(select(BookingInvite).where(BookingInvite.token == token)) if len(token or "") > 10 else None
    return inv if inv and inv.page_id == page.id else None


def _public(request: Request, db: Session, page: BookingPage | None, **ctx):
    status = ctx.pop("status", 200)
    if page is None:
        status = 404
    response = render(request, "booking_public.html", None, page=page, **ctx)
    response.status_code = status
    return response


@app.get("/b")
def booking_directory(request: Request, db: Session = Depends(get_db)):
    """Öffentliches Verzeichnis „Termine buchen“: alle freigegebenen Buchungsseiten mit nächstem freien Termin."""
    pages = db.scalars(select(BookingPage).where(BookingPage.listed.is_(True), BookingPage.active.is_(True),
                                                 BookingPage.invite_only.is_(False))
                       .order_by(BookingPage.title)).all()
    rows = []
    for page in pages:
        free = bk.free_slots(db, page)
        rows.append({"page": page, "next": bk.label(free[0]["start"]) if free else "", "count": len(free)})
    response = render(request, "booking_directory.html", None, rows=rows)
    if "jsm_session" not in request.cookies:
        request.session.clear()
    return response


@app.get("/b/m/{token}")
def booking_manage(request: Request, token: str, db: Session = Depends(get_db)):
    b = db.scalar(select(Booking).where(Booking.token == token)) if len(token) > 10 else None
    if b is None:
        return _public(request, db, None, mode="missing")
    page = b.page
    return _public(request, db, page, mode="manage", booking=b, label=bk.label, can_cancel=bk.can_cancel(b),
                   days=bk.group_by_day(bk.slots_for(db, b)) if page.active and bk.can_cancel(b) else [],
                   join=bk.join_link(db, b), fresh=request.query_params.get("neu") == "1")


@app.post("/b/m/{token}", dependencies=[Depends(check_csrf)])
def booking_manage_action(request: Request, token: str, action: str = Form(...), slot: str = Form(""),
                          reason: str = Form(""), db: Session = Depends(get_db)):
    rate_limit(request, "booking", limit=30)
    b = db.scalar(select(Booking).where(Booking.token == token)) if len(token) > 10 else None
    if b is None:
        return _public(request, db, None, mode="missing")
    if not bk.can_cancel(b):
        flash(request, "Der Termin kann online nicht mehr geändert werden. Bitte melden Sie sich direkt.", "error")
        return redirect(f"/b/m/{token}")
    if action == "cancel":
        bk.cancel(db, b, "guest", " ".join(reason.split()))
        flash(request, "Ihr Termin ist abgesagt. Sie erhalten eine Bestätigung per E-Mail.")
    elif action == "move":
        start = bk.parse_local(slot)
        error = bk.move(db, b, start) if start and b.page.active else "Bitte einen freien Termin wählen."
        if error:
            db.rollback()
            flash(request, error, "error")
            return redirect(f"/b/m/{token}")
        flash(request, f"Ihr Termin ist verschoben auf {bk.label(b.starts_at, b.ends_at)}. Sie erhalten einen neuen "
                       "Kalendereintrag per E-Mail.")
    db.commit()
    access.sync(db)
    worker.wake()
    return redirect(f"/b/m/{token}")


def _booking_public_steps(request: Request, db: Session, page: BookingPage, invite: BookingInvite | None,
                          member: User | None, types: list, bt=None, person: int | None = None):
    """Serverseitige, direkt verlinkbare Schritte: Terminart, Tag/Uhrzeit, Kontaktdaten.

    Es werden nur öffentliche Auswahlwerte über GET transportiert. Kontaktdaten werden
    erst mit dem abschließenden POST übermittelt und niemals in der URL gespeichert.
    """
    q = request.query_params
    base = f"/b/{page.public_token}"
    params = {}
    if invite is not None:
        params["i"] = invite.token
    if bt is not None:
        params["art"] = str(bt.id)
    if person is not None:
        params["person"] = str(person)

    def link(**changes):
        args = {**params, **changes}
        args = {k: v for k, v in args.items() if v is not None and v != ""}
        return base + ("?" + urlencode(args) if args else "")

    if bt is None and page.extended:
        from . import btypes
        return _public(request, db, page, mode="types", types=types,
                       summary=btypes.summary, invite=invite, start_url=link())

    from . import btypes
    available = (btypes.slots(db, page, bt, person) if bt is not None else bk.bookable(page, db=db))
    days = bk.group_by_day(available)
    slot_value = q.get("slot", "")[:100]
    chosen = next(((day, slot) for day in days for slot in day["slots"]
                   if slot["iso"] + "+00:00" == slot_value), None)
    is_details = q.get("step") == "details" and chosen is not None
    show_invalid = q.get("step") == "details" and chosen is None

    # Pro Seite höchstens sieben Tage anzeigen, aber nur einen Tag mit Uhrzeiten.
    requested_day = q.get("day", "")[:10]
    if chosen:
        requested_day = chosen[0]["key"]
    index = next((n for n, day in enumerate(days) if day["key"] == requested_day), None)
    offset = (index // 7) * 7 if index is not None else (_int(q.get("offset"), 0, max(0, len(days) - 1), 0) // 7) * 7
    chunk = days[offset:offset + 7]
    day = (days[index] if index is not None else chunk[0] if chunk else None)
    back_day = day["key"] if day else ""
    return _public(
        request, db, page, mode="book", step="details" if is_details else "times",
        invite=invite, member=member, bt=bt, person=person, types=types,
        assignable=btypes.providers_for(db, bt) if bt is not None else [],
        fields=btypes.fields(bt) if bt is not None else [],
        days=days, day_nav=chunk, active_day=day, day_offset=offset,
        prev_days=link(step="times", offset=max(0, offset - 7)) if offset > 0 else "",
        next_days=link(step="times", offset=offset + 7) if offset + 7 < len(days) else "",
        times_url=link(step="times", day=back_day),
        types_url=link(art=None, person=None) if page.extended else "",
        chosen_day=chosen[0] if chosen else None, chosen_slot=chosen[1] if chosen else None,
        selected=slot_value, invalid_slot=show_invalid,
        summary=btypes.summary if bt is not None else None,
        public_link=link,
    )


@app.get("/b/{token}")
def booking_public(request: Request, token: str, i: str = "", db: Session = Depends(get_db)):
    page = _page(db, token)
    if page is None:
        return _public(request, db, None, mode="missing")
    inv = _invite(db, page, i)
    if not page.active:
        return _public(request, db, page, mode="paused")
    if page.invite_only and inv is None:
        return _public(request, db, page, mode="invite_only")
    if inv is not None:
        existing = next((b for b in bk.active_bookings(page) if b.email == inv.email and b.starts_at >= utcnow()), None)
        if existing is not None and page.max_per_person <= 1:
            return redirect(f"/b/m/{existing.token}")
    member = session_user(request, db)
    if page.extended:
        from . import btypes
        types = btypes.active_types(page, db)
        art = request.query_params.get("art", "")
        bt = next((t for t in types if str(t.id) == art), None) if art else (types[0] if len(types) == 1 else None)
        person = request.query_params.get("person", "")
        pid = int(person) if person.isdigit() and bt and bt.choose_provider and any(
            p.id == int(person) for p in btypes.providers_for(db, bt)) else None
        return _booking_public_steps(request, db, page, inv, member, types, bt, pid)
    return _booking_public_steps(request, db, page, inv, member, [], None)


@app.post("/b/{token}", dependencies=[Depends(check_csrf)])
async def booking_public_book(request: Request, token: str, db: Session = Depends(get_db)):
    rate_limit(request, "booking", limit=30)
    page = _page(db, token)
    if page is None:
        return _public(request, db, None, mode="missing")
    data = await request.form()
    inv = _invite(db, page, str(data.get("i", "")))
    back = f"/b/{token}" + (f"?i={inv.token}" if inv else "")
    if data.get("website"):
        return redirect(back)
    if not page.active or (page.invite_only and inv is None):
        return redirect(back)
    name = " ".join(str(data.get("name", "")).split())[:120]
    email = (inv.email if inv else str(data.get("email", ""))).strip().lower()[:255]
    phone = " ".join(str(data.get("phone", "")).split())[:60]
    note = str(data.get("note", "")).replace("\r\n", "\n").strip()[:2000]
    start = bk.parse_local(str(data.get("slot", "")))
    bt, pid = None, None
    if page.extended:
        from . import btypes
        bt = next((t for t in btypes.active_types(page, db) if str(t.id) == str(data.get("art", ""))), None)
        person = str(data.get("person", ""))
        pid = int(person) if bt and bt.choose_provider and person.isdigit() else None
        back += ("&" if "?" in back else "?") + f"art={bt.id if bt else ''}" + (f"&person={pid}" if pid else "")
    need_phone = (bt.phone_mode == "required") if bt else page.ask_phone
    error = ""
    if page.extended and bt is None:
        error = "Bitte wählen Sie eine Terminart."
    elif not start:
        error = "Bitte wählen Sie einen Termin."
    elif not name:
        error = "Bitte geben Sie Ihren Namen an."
    elif not EMAIL_RE.match(email):
        error = "Bitte geben Sie eine gültige E-Mail-Adresse an – dorthin geht die Bestätigung."
    elif need_phone and not phone:
        error = "Bitte geben Sie eine Telefonnummer an."
    answers = ""
    if not error and bt is not None:
        import json as _json
        rows, error = btypes.read_answers(bt, data)
        answers = _json.dumps(rows, ensure_ascii=False) if rows else ""
    if not error:
        b, error = bk.book(db, page, start, name, email, phone, note, session_user(request, db), inv, bt=bt,
                           provider_id=pid, answers=answers)
    if error:
        db.rollback()
        flash(request, error, "error")
        # Bei Eingabefehlern zurück zu den Kontaktdaten, bei nicht mehr freien
        # Slots zur Tagesauswahl. Die Buchungsdaten selbst landen nie im URL.
        recover_step = "times" if not start or "nicht mehr frei" in error or "Termin" in error and "frei" in error else "details"
        return redirect(back + ("&" if "?" in back else "?") + "step=" + recover_step
                        + "&slot=" + quote(str(data.get("slot", ""))))
    db.commit()
    access.sync(db)
    worker.wake()
    return redirect(f"/b/m/{b.token}?neu=1")

