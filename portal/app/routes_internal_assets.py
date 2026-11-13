"""Interner Gerätepool: keine Veröffentlichung, Zahlung oder externe Buchung."""
from datetime import date, datetime, timedelta, timezone
from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from .db import LOCAL_TZ, User, to_local, utcnow
from .internal_asset_models import (
    InternalAsset, InternalAssetEvent, InternalAssetMaintenance,
    InternalAssetReservation, InternalStorageLocation,
)
from .main import app, check_csrf, current_user, enabled_modules, flash, get_db, redirect, render

CATEGORIES = (
    "Präsentation", "Veranstaltungstechnik", "Mobiliar",
    "Zelte & Pavillons", "Fahrzeuge", "Werkzeuge", "Sonstiges",
)
STATUS_LABELS = {
    "reserved": "Reserviert", "issued": "Ausgegeben",
    "returned": "Zurückgegeben", "cancelled": "Storniert",
}


def _access(user: User, manage: bool = False) -> bool:
    if "internal_assets" not in enabled_modules():
        raise HTTPException(404, "Das Modul Interne Ressourcen ist deaktiviert.")
    if not user.active:
        raise HTTPException(403)
    manager = user.can("internal_assets_manage")
    if manage and not manager:
        raise HTTPException(403, "Nur Gerätepool-Verantwortliche dürfen Bestände und Ausgaben verwalten.")
    if not manager and not user.can("internal_assets_book"):
        raise HTTPException(403, "Für den Gerätepool fehlt die Berechtigung.")
    return manager


def _asset(db: Session, asset_id: int) -> InternalAsset:
    asset = db.get(InternalAsset, asset_id)
    if asset is None:
        raise HTTPException(404, "Der Gegenstand wurde nicht gefunden.")
    return asset


def _time(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(str(raw))
        if value.tzinfo is None:
            value = value.replace(tzinfo=LOCAL_TZ)
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, OverflowError, TypeError):
        raise HTTPException(422, "Ungültiges Datum oder Uhrzeit.")


def _range(start: str, end: str) -> tuple[datetime, datetime]:
    a, b = _time(start), _time(end)
    if a >= b or b - a > timedelta(days=31):
        raise HTTPException(422, "Der Zeitraum muss positiv und höchstens 31 Tage lang sein.")
    if a < utcnow() - timedelta(minutes=2) or a > utcnow() + timedelta(days=730):
        raise HTTPException(422, "Nur zukünftige Buchungen innerhalb der nächsten zwei Jahre sind erlaubt.")
    return a, b


def _peak(db: Session, asset_id: int, start: datetime, end: datetime,
          ignore_maintenance: int | None = None) -> int:
    """Maximale gleichzeitige Nutzung; angrenzende Intervalle überlappen nicht.

    Bereits ausgegebene Gegenstände bleiben bis zur realen Rückgabe gebunden,
    selbst wenn ihr ursprünglich reserviertes Ende überschritten ist.
    """
    events: list[tuple[datetime, int]] = []
    reservations = db.scalars(select(InternalAssetReservation).where(
        InternalAssetReservation.asset_id == asset_id,
        InternalAssetReservation.status.in_(("reserved", "issued")),
    )).all()
    for row in reservations:
        a = start if row.status == "issued" else max(start, row.starts_at)
        b = end if row.status == "issued" else min(end, row.ends_at)
        if a < b:
            events.extend(((a, row.quantity), (b, -row.quantity)))
    maintenance = db.scalars(select(InternalAssetMaintenance).where(
        InternalAssetMaintenance.asset_id == asset_id,
        InternalAssetMaintenance.starts_at < end,
        InternalAssetMaintenance.ends_at > start,
    )).all()
    for row in maintenance:
        if row.id == ignore_maintenance:
            continue
        a, b = max(start, row.starts_at), min(end, row.ends_at)
        if a < b:
            events.extend(((a, row.quantity), (b, -row.quantity)))
    running = peak = 0
    # End first at identical timestamps: end-exclusive reservations.
    for _timepoint, delta in sorted(events, key=lambda e: (e[0], e[1])):
        running += delta
        peak = max(peak, running)
    return peak


def _available(db: Session, asset: InternalAsset, start: datetime, end: datetime) -> int:
    return max(0, asset.quantity - _peak(db, asset.id, start, end)) if asset.active else 0


def _lock_asset(db: Session, asset_id: int) -> None:
    """Write acquisition before stock checks serializes SQLite writers."""
    db.execute(update(InternalAsset).where(InternalAsset.id == asset_id)
               .values(quantity=InternalAsset.quantity))


def _event(db: Session, asset_id: int, user: User, action: str,
           detail: str = "", reservation_id: int | None = None) -> None:
    db.add(InternalAssetEvent(asset_id=asset_id, actor_id=user.id, action=action,
                              detail=detail.strip()[:500], reservation_id=reservation_id))


def _location(db: Session, raw: int) -> InternalStorageLocation | None:
    if not raw:
        return None
    location = db.get(InternalStorageLocation, raw)
    if location is None or not location.active:
        raise HTTPException(422, "Unbekannter oder inaktiver Lagerort.")
    return location


def _number(n: int, name: str, maximum: int = 100000) -> None:
    if not 1 <= n <= maximum:
        raise HTTPException(422, f"{name}: ungültige Anzahl.")


@app.get("/interne-ressourcen")
def internal_home(request: Request, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    manager = _access(user)
    assets = db.scalars(select(InternalAsset).order_by(
        InternalAsset.category, InternalAsset.name)).all()
    q = request.query_params.get("q", "").strip().casefold()[:100]
    category = request.query_params.get("kategorie", "").strip()[:80]
    if category:
        assets = [a for a in assets if a.category == category]
    if q:
        assets = [a for a in assets if q in " ".join((
            a.name, a.category, a.inventory_code, a.location,
            a.storage_location.name if a.storage_location else "",
        )).casefold()]
    history = request.query_params.get("verlauf") == "1"
    bookings_query = select(InternalAssetReservation)
    if not history:
        bookings_query = bookings_query.where(InternalAssetReservation.status.in_(("reserved", "issued")))
    if not manager:
        bookings_query = bookings_query.where(InternalAssetReservation.user_id == user.id)
    bookings = db.scalars(bookings_query.order_by(
        InternalAssetReservation.created_at.desc() if history
        else InternalAssetReservation.starts_at).limit(300)).all()
    maintenance = db.scalars(select(InternalAssetMaintenance).where(
        InternalAssetMaintenance.ends_at > utcnow()
    ).order_by(InternalAssetMaintenance.starts_at).limit(100)).all() if manager else []
    events = db.scalars(select(InternalAssetEvent).order_by(
        InternalAssetEvent.at.desc()).limit(40)).all() if manager else []
    now = utcnow()
    available_now = {
        a.id: _available(db, a, now, now + timedelta(minutes=1)) for a in assets
    }
    locations = db.scalars(select(InternalStorageLocation).where(
        InternalStorageLocation.active.is_(True)).order_by(
        InternalStorageLocation.building, InternalStorageLocation.name)).all()
    return render(request, "resource_internal.html", user, assets=assets,
                  bookings=bookings, manager=manager, locations=locations,
                  maintenance=maintenance, events=events, available_now=available_now,
                  categories=CATEGORIES, status_labels=STATUS_LABELS, q=q,
                  category=category, history=history,
                  today=to_local(now).strftime("%Y-%m-%dT%H:%M"))


@app.get("/interne-ressourcen/verfuegbarkeit")
def internal_availability(asset_id: int, start: str, end: str,
                          user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    _access(user)
    asset = _asset(db, asset_id)
    a, b = _range(start, end)
    return JSONResponse({
        "asset_id": asset.id, "available": _available(db, asset, a, b),
        "total": asset.quantity, "active": asset.active,
    })


@app.post("/interne-ressourcen/lagerorte", dependencies=[Depends(check_csrf)])
def internal_location_create(request: Request, name: str = Form(...),
                             building: str = Form(""), detail: str = Form(""),
                             user: User = Depends(current_user),
                             db: Session = Depends(get_db)):
    _access(user, manage=True)
    if not name.strip() or len(name.strip()) > 160:
        raise HTTPException(422, "Bitte eine gültige Bezeichnung für den Lagerort eingeben.")
    location = InternalStorageLocation(name=name.strip(), building=building.strip()[:160],
                                       detail=detail.strip()[:160])
    db.add(location)
    db.commit()
    flash(request, "Lagerort angelegt.")
    return redirect("/interne-ressourcen#lagerorte")


@app.post("/interne-ressourcen/gegenstaende", dependencies=[Depends(check_csrf)])
def internal_asset_create(request: Request, name: str = Form(...),
                          category: str = Form("Sonstiges"),
                          location_id: int = Form(0), location: str = Form(""),
                          inventory_code: str = Form(""), vehicle_plate: str = Form(""),
                          quantity: int = Form(1), notes: str = Form(""),
                          user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    _access(user, manage=True)
    _number(quantity, "Bestand")
    name = name.strip()
    if not name or len(name) > 200:
        raise HTTPException(422, "Bezeichnung fehlt oder ist zu lang.")
    loc = _location(db, location_id)
    asset = InternalAsset(
        name=name, category=category if category in CATEGORIES else "Sonstiges",
        location_id=loc.id if loc else None, location=location.strip()[:200],
        inventory_code=inventory_code.strip()[:80], vehicle_plate=vehicle_plate.strip()[:30],
        quantity=quantity, notes=notes.strip()[:3000], created_by_id=user.id,
    )
    db.add(asset)
    db.flush()
    _event(db, asset.id, user, "created", f"{name}; Bestand {quantity}")
    db.commit()
    flash(request, "Interner Gegenstand angelegt.")
    return redirect("/interne-ressourcen#katalog")


@app.post("/interne-ressourcen/{asset_id:int}/bearbeiten", dependencies=[Depends(check_csrf)])
def internal_asset_update(request: Request, asset_id: int,
                          name: str = Form(...), category: str = Form("Sonstiges"),
                          quantity: int = Form(...), location_id: int = Form(0),
                          location: str = Form(""), inventory_code: str = Form(""),
                          vehicle_plate: str = Form(""), notes: str = Form(""),
                          active: str = Form(""),
                          user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    _access(user, manage=True)
    _number(quantity, "Bestand")
    name = name.strip()
    if not name or len(name) > 200:
        raise HTTPException(422, "Bitte eine gültige Bezeichnung eingeben.")
    loc = _location(db, location_id)
    _lock_asset(db, asset_id)
    asset = _asset(db, asset_id)
    peak = _peak(db, asset.id, utcnow() - timedelta(days=1), datetime(2100, 1, 1))
    if quantity < peak:
        raise HTTPException(409, f"Mindestens {peak} Stück sind bereits verbindlich reserviert, ausgegeben oder gesperrt.")
    before = asset.quantity
    asset.name, asset.category = name, category if category in CATEGORIES else "Sonstiges"
    asset.quantity, asset.active = quantity, active == "1"
    asset.location_id, asset.location = loc.id if loc else None, location.strip()[:200]
    asset.inventory_code = inventory_code.strip()[:80]
    asset.vehicle_plate = vehicle_plate.strip()[:30]
    asset.notes = notes.strip()[:3000]
    _event(db, asset.id, user, "changed", f"Bestand {before} → {quantity}, aktiv={asset.active}")
    db.commit()
    flash(request, "Gegenstand aktualisiert.")
    return redirect("/interne-ressourcen#katalog")


@app.post("/interne-ressourcen/{asset_id:int}/reservieren", dependencies=[Depends(check_csrf)])
def internal_asset_reserve(request: Request, asset_id: int,
                           start: str = Form(...), end: str = Form(...),
                           quantity: int = Form(1), purpose: str = Form(""),
                           user: User = Depends(current_user),
                           db: Session = Depends(get_db)):
    _access(user)
    starts_at, ends_at = _range(start, end)
    _number(quantity, "Reservierungsmenge")
    _lock_asset(db, asset_id)
    asset = _asset(db, asset_id)
    if not asset.active:
        raise HTTPException(409, "Dieser Gegenstand ist deaktiviert.")
    if _available(db, asset, starts_at, ends_at) < quantity:
        flash(request, "Der gewünschte Bestand ist im Zeitraum nicht verfügbar.", "error")
        return redirect("/interne-ressourcen#katalog")
    booking = InternalAssetReservation(
        asset_id=asset.id, user_id=user.id, starts_at=starts_at,
        ends_at=ends_at, quantity=quantity, purpose=purpose.strip()[:255],
    )
    db.add(booking)
    db.flush()
    _event(db, asset.id, user, "reserved", f"{quantity} × {booking.purpose}", booking.id)
    db.commit()
    flash(request, "Interne Reservierung angelegt.")
    return redirect("/interne-ressourcen#reservierungen")


@app.post("/interne-ressourcen/{asset_id:int}/wartung", dependencies=[Depends(check_csrf)])
def internal_asset_maintenance_create(request: Request, asset_id: int,
                                      start: str = Form(...), end: str = Form(...),
                                      quantity: int = Form(1), reason: str = Form(""),
                                      user: User = Depends(current_user),
                                      db: Session = Depends(get_db)):
    _access(user, manage=True)
    a, b = _range(start, end)
    _number(quantity, "Wartungsmenge")
    _lock_asset(db, asset_id)
    asset = _asset(db, asset_id)
    if _available(db, asset, a, b) < quantity:
        raise HTTPException(409, "Die Sperrmenge überschneidet sich mit bestehenden Buchungen oder Wartungen.")
    hold = InternalAssetMaintenance(asset_id=asset.id, starts_at=a, ends_at=b, quantity=quantity,
                                    reason=reason.strip()[:255], created_by_id=user.id)
    db.add(hold)
    _event(db, asset.id, user, "maintenance", f"{quantity} Stück gesperrt: {hold.reason}")
    db.commit()
    flash(request, "Wartung / Sperrzeit angelegt.")
    return redirect("/interne-ressourcen#wartungen")


@app.post("/interne-ressourcen/wartungen/{maintenance_id:int}/loeschen", dependencies=[Depends(check_csrf)])
def internal_maintenance_delete(request: Request, maintenance_id: int,
                                user: User = Depends(current_user),
                                db: Session = Depends(get_db)):
    _access(user, manage=True)
    hold = db.get(InternalAssetMaintenance, maintenance_id)
    if not hold:
        raise HTTPException(404)
    _lock_asset(db, hold.asset_id)
    _event(db, hold.asset_id, user, "maintenance_cancelled", hold.reason)
    db.delete(hold)
    db.commit()
    flash(request, "Sperrzeit aufgehoben.")
    return redirect("/interne-ressourcen#wartungen")


@app.post("/interne-ressourcen/buchungen/{booking_id:int}/{action}", dependencies=[Depends(check_csrf)])
def internal_asset_transition(request: Request, booking_id: int, action: str,
                              note: str = Form(""), user: User = Depends(current_user),
                              db: Session = Depends(get_db)):
    manager = _access(user)
    booking = db.get(InternalAssetReservation, booking_id)
    if booking is None:
        raise HTTPException(404)
    if action not in ("cancel", "issue", "return"):
        raise HTTPException(404)
    if action != "cancel" and not manager:
        raise HTTPException(403)
    if action == "cancel" and not manager and booking.user_id != user.id:
        raise HTTPException(403)
    _lock_asset(db, booking.asset_id)
    db.refresh(booking)
    transitions = {"cancel": ("reserved", "cancelled"), "issue": ("reserved", "issued"),
                   "return": ("issued", "returned")}
    previous, following = transitions[action]
    if booking.status != previous:
        raise HTTPException(409, "Der Status hat sich geändert. Bitte die Übersicht neu laden.")
    if action == "issue" and not booking.asset.active:
        raise HTTPException(409, "Der Gegenstand ist derzeit deaktiviert.")
    booking.status = following
    if action == "issue":
        booking.issued_at = utcnow()
    elif action == "return":
        booking.returned_at = utcnow()
    _event(db, booking.asset_id, user, following, note.strip()[:500], booking.id)
    db.commit()
    flash(request, {"cancel": "Reservierung storniert.", "issue": "Ausgabe dokumentiert.",
                    "return": "Rückgabe dokumentiert."}[action])
    return redirect("/interne-ressourcen#reservierungen")


@app.get("/interne-ressourcen/plan")
def internal_week_plan(request: Request, start: str = "", category: str = "",
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Öffentliche Belegungsdichte nur für berechtigte interne Nutzer, ohne fremde Personendaten."""
    manager = _access(user)
    try:
        first = date.fromisoformat(start) if start else to_local(utcnow()).date()
    except ValueError:
        first = to_local(utcnow()).date()
    first -= timedelta(days=first.weekday())
    days = [first + timedelta(days=n) for n in range(7)]
    assets = db.scalars(select(InternalAsset).where(
        InternalAsset.active.is_(True)).order_by(
        InternalAsset.category, InternalAsset.name)).all()
    if category:
        assets = [asset for asset in assets if asset.category == category]
    rows = []
    for asset in assets[:250]:
        free = []
        for day in days:
            a = _time(f"{day.isoformat()}T00:00")
            b = _time(f"{(day + timedelta(days=1)).isoformat()}T00:00")
            free.append(max(0, asset.quantity - _peak(db, asset.id, a, b)))
        rows.append((asset, free))
    return render(request, "resource_internal_plan.html", user, manager=manager,
                  days=days, rows=rows, category=category, categories=CATEGORIES,
                  prev=(first - timedelta(days=7)).isoformat(),
                  next=(first + timedelta(days=7)).isoformat())


@app.get("/interne-ressourcen/buchungen/{booking_id:int}/termin.ics")
def internal_booking_ical(booking_id: int, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    """Kalenderexport ohne öffentlich teilbaren Buchungstoken."""
    manager = _access(user)
    booking = db.get(InternalAssetReservation, booking_id)
    if booking is None or (not manager and booking.user_id != user.id):
        raise HTTPException(404)
    if booking.status == "cancelled":
        raise HTTPException(410)
    from icalendar import Calendar, Event
    from fastapi.responses import Response
    cal = Calendar()
    cal.add("prodid", "-//TAKT Interner Geraetepool//DE")
    cal.add("version", "2.0")
    event = Event()
    event.add("uid", f"takt-internal-{booking.id}@local")
    event.add("summary", f"Gerätepool: {booking.asset.name}")
    event.add("description", f"{booking.quantity} Stück; {booking.purpose}")
    event.add("dtstart", booking.starts_at.replace(tzinfo=timezone.utc))
    event.add("dtend", booking.ends_at.replace(tzinfo=timezone.utc))
    event.add("dtstamp", booking.created_at.replace(tzinfo=timezone.utc))
    event.add("location", booking.asset.storage_location.name if booking.asset.storage_location
              else booking.asset.location)
    cal.add_component(event)
    return Response(cal.to_ical(), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="takt-material-{booking.id}.ics"',
                             "Cache-Control": "private, no-store"})


# Alte gespeicherte Links funktionieren weiter, werden aber nur unter dem neuen Modul freigegeben.
@app.get("/resources/intern", include_in_schema=False)
@app.get("/resources/intern/{legacy_path:path}", include_in_schema=False)
def internal_legacy_links(request: Request, legacy_path: str = "",
                          user: User = Depends(current_user)):
    _access(user)
    import re
    from fastapi.responses import RedirectResponse
    allowed = legacy_path in ("", "plan", "verfuegbarkeit") or bool(
        re.fullmatch(r"buchungen/\\d+/termin\\.ics", legacy_path))
    if not allowed:
        raise HTTPException(404)
    new_url = "/interne-ressourcen" + ("/" + legacy_path if legacy_path else "")
    if request.url.query:
        new_url += "?" + request.url.query
    return RedirectResponse(new_url, status_code=308)
