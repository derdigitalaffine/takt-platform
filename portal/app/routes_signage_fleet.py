"""Central operational status for paired signage devices and safe key rotation."""
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import signage, signage_fleet
from .db import User, utcnow
from .main import app, check_csrf, flash, get_db, redirect, render
from .routes_signage import _enabled, _screen, manage_user
from .signage_models import (
    SignageBuilding, SignageDevice, SignageDeviceTelemetry, SignageFloor,
    SignagePassiveConfig, SignageScreen,
)


def _inventory(db):
    now = utcnow()
    records = db.execute(select(SignageDevice, SignageScreen).join(
        SignageScreen, SignageDevice.screen_id == SignageScreen.id
    ).order_by(SignageScreen.name, SignageDevice.name, SignageDevice.id)).all()
    telemetry = {
        row.device_id: row for row in db.scalars(select(SignageDeviceTelemetry))
    }
    passive = {
        row.screen_id: row for row in db.scalars(select(SignagePassiveConfig))
    }
    buildings = {
        row.id: row for row in db.scalars(select(SignageBuilding))
    }
    items = []
    for device, screen in records:
        snapshot = signage_fleet.health(device, telemetry.get(device.id), now)
        config = passive.get(screen.id)
        building = buildings.get(config.building_id) if config else None
        items.append({
            "device": device, "screen": screen, "health": snapshot,
            "telemetry": telemetry.get(device.id),
            "building": building.name if building else "",
        })
    return items


def _status_count(items):
    counts = {"online": 0, "delayed": 0, "offline": 0, "new": 0, "revoked": 0}
    for row in items:
        counts[row["health"]["code"]] += 1
    return counts


@app.get("/signage/fleet")
def signage_fleet_home(request: Request, user: User = Depends(manage_user),
                       db: Session = Depends(get_db)):
    _enabled()
    devices = _inventory(db)
    response = render(request, "signage_fleet.html", user, devices=devices,
                      counts=_status_count(devices), now=utcnow(),
                      diagnostic_labels=signage_fleet.DIAGNOSTIC_CODES)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/signage/fleet/status")
def signage_fleet_status(request: Request, user: User = Depends(manage_user),
                         db: Session = Depends(get_db)):
    _enabled()
    devices = _inventory(db)
    return JSONResponse({
        "counts": _status_count(devices),
        "devices": [{
            "id": row["device"].id,
            "screen_id": row["screen"].id,
            "screen_version": row["screen"].version,
            "status": row["health"]["code"],
            "status_label": row["health"]["label"],
            "age_seconds": row["health"]["age_seconds"],
            "diagnostic_code": row["health"].get("diagnostic"),
            "reported_version": (
                row["telemetry"].reported_screen_version
                if row["telemetry"] else None),
        } for row in devices],
    }, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@app.post("/signage/{sid:int}/device/{device_id:int}/rotate",
          dependencies=[Depends(check_csrf)])
def signage_device_rotate(sid: int, device_id: int, request: Request,
                          user: User = Depends(manage_user),
                          db: Session = Depends(get_db)):
    """Replace the credential immediately, never display or persist its plaintext twice."""
    screen = _screen(db, sid)
    device = db.get(SignageDevice, device_id)
    if not device or device.screen_id != screen.id or device.revoked:
        raise HTTPException(404)
    raw = signage.token()
    device.secret_hash = signage.digest(raw)
    device.last_seen_at = None
    telemetry = db.get(SignageDeviceTelemetry, device_id)
    if telemetry:
        db.delete(telemetry)
    db.commit()
    response = render(request, "signage_secret.html", user, screen=screen,
                      label="Neuer Geräteschlüssel – alter Zugang sofort ungültig",
                      secret=f"Gerät-ID: {device.id}\nBearer: {raw}")
    response.headers.update({"Cache-Control": "no-store",
                             "Referrer-Policy": "no-referrer",
                             "X-Robots-Tag": "noindex, nofollow"})
    return response
