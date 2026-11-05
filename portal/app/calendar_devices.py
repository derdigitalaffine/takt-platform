"""Personal high-entropy calendar credentials; never accept the portal password."""

import hashlib, hmac, secrets
from datetime import timedelta
from sqlalchemy import select
from fastapi import HTTPException
from .db import User, utcnow, get_settings
from .calendar_models import Calendar, CalendarDevice, CalendarDeviceScope
from . import calendars


def create(db, user, name, choices):
    if not user or not user.active:
        raise HTTPException(403)
    if (
        len(
            list(
                db.scalars(
                    select(CalendarDevice.id).where(
                        CalendarDevice.user_id == user.id,
                        CalendarDevice.revoked.is_(False),
                    )
                )
            )
        )
        >= 100
    ):
        raise HTTPException(
            409, "Zuerst einen nicht mehr benötigten Gerätezugang widerrufen."
        )
    name = str(name).strip()
    if not name or len(name) > 100 or not choices:
        raise HTTPException(422, "Gerätename und mindestens einen Kalender auswählen.")
    scopes = []
    for cid, write in choices:
        cal = db.get(Calendar, cid)
        if (
            not cal
            or not calendars.access(db, user, cal)
            or write
            and not calendars.access(db, user, cal, True)
        ):
            raise HTTPException(403)
        scopes.append((cal.id, write))
    secret = secrets.token_urlsafe(32)
    try:
        days = int(get_settings(db).get("calendar_device_days", "0"))
    except ValueError:
        days = 0
    if days < 0 or days > 3650:
        raise HTTPException(422, "Ungültige Laufzeitvorgabe.")
    device = CalendarDevice(
        user_id=user.id,
        username="takt-" + secrets.token_hex(12),
        secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
        name=name,
        expires_at=utcnow() + timedelta(days=days) if days else None,
    )
    db.add(device)
    db.flush()
    for cid, write in set(scopes):
        db.add(
            CalendarDeviceScope(device_id=device.id, calendar_id=cid, can_write=write)
        )
    return device, secret


def authenticate(db, username, password):
    device = db.scalar(
        select(CalendarDevice).where(CalendarDevice.username == username)
    )
    if (
        not device
        or device.revoked
        or device.expires_at
        and device.expires_at <= utcnow()
    ):
        return None
    user = db.get(User, device.user_id)
    if (
        not user
        or not user.active
        or not hmac.compare_digest(
            device.secret_hash, hashlib.sha256(password.encode()).hexdigest()
        )
    ):
        return None
    return device, user


def allowed(db, device, user, cid, write=False):
    scope = db.get(CalendarDeviceScope, (device.id, cid))
    cal = db.get(Calendar, cid)
    return (
        cal
        if scope
        and cal
        and (not write or scope.can_write)
        and calendars.access(db, user, cal, write)
        else None
    )
