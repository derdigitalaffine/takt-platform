"""Interne Material- und Geräteplanung mit Bestandsprüfung und Aus-/Rückgabe."""
from datetime import datetime, timezone
from fastapi import Depends, Form, HTTPException, Request
from sqlalchemy import select, func, or_, and_, update
from sqlalchemy.orm import Session
from .db import User, utcnow
from .internal_asset_models import InternalAsset, InternalAssetReservation
from .main import app, check_csrf, current_user, enabled_modules, flash, get_db, redirect, render

CATEGORIES = ("Präsentation", "Veranstaltungstechnik", "Mobiliar", "Zelte & Pavillons", "Fahrzeuge", "Werkzeuge", "Sonstiges")

def _access(user):
    if "resources" not in enabled_modules():
        raise HTTPException(404)
    if not user.active or not user.can("resources"):
        raise HTTPException(403, "Für den internen Gerätepool ist das Ressourcenrecht erforderlich.")

def _asset(db, asset_id):
    asset = db.get(InternalAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Gegenstand nicht gefunden.")
    return asset

def _date(raw):
    try:
        value = datetime.fromisoformat(str(raw))
        if value.tzinfo is None:
            from .db import LOCAL_TZ
            value = value.replace(tzinfo=LOCAL_TZ)
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(422, "Ungültiger Zeitraum.")

def _reserved(db, asset_id, start, end, exclude=None):
    query = select(func.coalesce(func.sum(InternalAssetReservation.quantity), 0)).where(
        InternalAssetReservation.asset_id == asset_id,
        or_(InternalAssetReservation.status == "issued", and_(
            InternalAssetReservation.status == "reserved",
            InternalAssetReservation.starts_at < end,
            InternalAssetReservation.ends_at > start)))
    if exclude:
        query = query.where(InternalAssetReservation.id != exclude)
    return int(db.scalar(query) or 0)

@app.get("/resources/intern")
def internal_assets_home(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _access(user)
    assets = db.scalars(select(InternalAsset).order_by(InternalAsset.category, InternalAsset.name)).all()
    bookings = db.scalars(select(InternalAssetReservation).where(
        InternalAssetReservation.status.in_(("reserved", "issued"))).order_by(InternalAssetReservation.starts_at).limit(300)).all()
    return render(request, "resource_internal.html", user, assets=assets, bookings=bookings,
                  categories=CATEGORIES, now=utcnow())

@app.post("/resources/intern/gegenstaende", dependencies=[Depends(check_csrf)])
def internal_asset_create(request: Request, name: str = Form(...), category: str = Form("Sonstiges"),
                          location: str = Form(""), inventory_code: str = Form(""), quantity: int = Form(1),
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    _access(user)
    if not name.strip() or len(name.strip()) > 200 or not 1 <= quantity <= 100000:
        raise HTTPException(422, "Name oder Bestand ungültig.")
    db.add(InternalAsset(name=name.strip(), category=category if category in CATEGORIES else "Sonstiges",
                         location=location.strip()[:200], inventory_code=inventory_code.strip()[:80],
                         quantity=quantity, created_by_id=user.id))
    db.commit()
    flash(request, "Interne Ressource angelegt.")
    return redirect("/resources/intern")

@app.post("/resources/intern/{asset_id:int}/reservieren", dependencies=[Depends(check_csrf)])
def internal_asset_reserve(request: Request, asset_id: int, start: str = Form(...), end: str = Form(...),
                           quantity: int = Form(1), purpose: str = Form(""), user: User = Depends(current_user),
                           db: Session = Depends(get_db)):
    _access(user)
    asset = _asset(db, asset_id)
    starts_at, ends_at = _date(start), _date(end)
    if not asset.active or starts_at >= ends_at or starts_at < utcnow() or not 1 <= quantity <= asset.quantity:
        raise HTTPException(422, "Zeitraum oder Menge ungültig.")
    # Eine tatsächliche UPDATE-Schreibsperre serialisiert die Bestandsprüfung unter SQLite.
    # Damit können parallele Requests nicht beide denselben Restbestand reservieren.
    db.execute(update(InternalAsset).where(InternalAsset.id == asset_id).values(quantity=InternalAsset.quantity))
    if _reserved(db, asset_id, starts_at, ends_at) + quantity > asset.quantity:
        flash(request, "Nicht genug Bestand im gewählten Zeitraum verfügbar.", "error")
        return redirect("/resources/intern")
    db.add(InternalAssetReservation(asset_id=asset.id, user_id=user.id, starts_at=starts_at,
                                    ends_at=ends_at, quantity=quantity, purpose=purpose.strip()[:255]))
    db.commit()
    flash(request, "Interne Reservierung angelegt.")
    return redirect("/resources/intern")

@app.post("/resources/intern/buchungen/{booking_id:int}/{action}", dependencies=[Depends(check_csrf)])
def internal_asset_transition(request: Request, booking_id: int, action: str,
                              user: User = Depends(current_user), db: Session = Depends(get_db)):
    _access(user)
    booking = db.get(InternalAssetReservation, booking_id)
    if booking is None:
        raise HTTPException(404)
    # Statuswechsel ebenfalls unter Schreibsperre, bevor der Zustand geprüft wird.
    db.execute(update(InternalAssetReservation).where(InternalAssetReservation.id == booking_id)
               .values(quantity=InternalAssetReservation.quantity))
    db.refresh(booking)
    if action == "cancel" and booking.status == "reserved" and (booking.user_id == user.id or user.is_admin):
        booking.status = "cancelled"
    elif action == "issue" and booking.status == "reserved":
        booking.status, booking.issued_at = "issued", utcnow()
    elif action == "return" and booking.status == "issued":
        booking.status, booking.returned_at = "returned", utcnow()
    else:
        raise HTTPException(409, "Dieser Statuswechsel ist nicht möglich.")
    db.commit()
    flash(request, "Status aktualisiert.")
    return redirect("/resources/intern")
