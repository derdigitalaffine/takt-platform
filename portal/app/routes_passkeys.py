"""Passwordless WebAuthn with single-use server-side challenges and UV-required keys.

No browser-provided origin or RP ID is trusted. Existing password/OIDC paths stay
available. Credential public keys are not login secrets, but never sent to UI.
"""
import base64
import json
import secrets
import time
from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from webauthn import (
    base64url_to_bytes, generate_authentication_options, generate_registration_options,
    options_to_json, verify_authentication_response, verify_registration_response,
)
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
    ResidentKeyRequirement, UserVerificationRequirement,
)

from .config import settings
from .db import User, get_settings, utcnow
from .main import (
    app, admin_user, check_csrf, current_user, get_db, home_for, rate_limit,
    redirect, safe_next,
)
from .passkey_models import PasskeyCeremony, PasskeyCredential
from . import sessions, twofa
from .security import verify_password

TTL = timedelta(minutes=5)
MAX_RESPONSE = 32_768
MAX_KEYS_PER_USER = 15
HEADERS = {"Cache-Control": "no-store"}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _rp(request: Request) -> tuple[str, str]:
    """The configured portal origin is authoritative, never X-Forwarded-Host."""
    parsed = urlsplit(settings.portal_base_url)
    host = parsed.hostname or ""
    origin = f"{parsed.scheme}://{parsed.netloc}"
    localhost = host in ("localhost", "127.0.0.1")
    if (not host or not parsed.netloc or parsed.username or parsed.password
            or (parsed.scheme != "https" and not (localhost and parsed.scheme == "http"))
            or request.url.hostname != host
            or request.url.scheme != parsed.scheme
            or (request.url.port or (443 if parsed.scheme == "https" else 80))
               != (parsed.port or (443 if parsed.scheme == "https" else 80))):
        raise HTTPException(503, "Passkeys erfordern die korrekte HTTPS-Portaladresse (PORTAL_BASE_URL).")
    return host, origin


def _check_ownership(request: Request, challenge: PasskeyCeremony,
                     user: User | None, purpose: str) -> None:
    if challenge.purpose != purpose:
        raise HTTPException(400, "Der Passkey-Vorgang ist ungültig.")
    if purpose == "register":
        if not user or challenge.user_id != user.id or not challenge.session_sid_hash:
            raise HTTPException(403, "Der Passkey-Vorgang gehört nicht zu diesem Konto.")
        if challenge.session_sid_hash != sessions.current_hash(request):
            raise HTTPException(403, "Bitte die Einrichtung in derselben Anmeldung abschließen.")


def _consume(db: Session, request: Request, session_key: str,
             purpose: str, user: User | None = None) -> PasskeyCeremony:
    token = request.session.pop(session_key, None)
    if not isinstance(token, str) or len(token) > 90:
        raise HTTPException(400, "Die Passkey-Anfrage ist abgelaufen. Bitte erneut starten.")
    row = db.get(PasskeyCeremony, token)
    if row is None:
        raise HTTPException(400, "Die Passkey-Anfrage wurde bereits verwendet.")
    _check_ownership(request, row, user, purpose)
    # Atomic single-use claim before cryptographic validation. Even a bad
    # response burns its challenge; old signed session cookies cannot replay.
    claimed = db.execute(delete(PasskeyCeremony).where(PasskeyCeremony.id == token))
    db.commit()
    if claimed.rowcount != 1 or row.expires_at < utcnow():
        raise HTTPException(400, "Die Passkey-Anfrage ist abgelaufen.")
    rp, origin = _rp(request)
    if row.rp_id != rp or row.origin != origin:
        raise HTTPException(400, "Das Passkey-Ziel hat sich geändert.")
    return row


def _create(db: Session, request: Request, key: str, purpose: str,
            challenge: bytes, rp_id: str, origin: str,
            user: User | None = None) -> None:
    request.session.pop(key, None)
    token = secrets.token_urlsafe(32)
    db.add(PasskeyCeremony(
        id=token, purpose=purpose, challenge=_b64(challenge),
        rp_id=rp_id, origin=origin,
        user_id=user.id if user else None,
        session_sid_hash=sessions.current_hash(request) if user else None,
        expires_at=utcnow() + TTL,
    ))
    db.execute(delete(PasskeyCeremony).where(PasskeyCeremony.expires_at < utcnow()))
    db.commit()
    request.session[key] = token


def _verify_recent(user: User, request: Request, password: str) -> None:
    if user.password_set:
        if not password or not verify_password(user.password_hash, password):
            raise HTTPException(403, "Zur Änderung der Passkeys ist dein aktuelles Passwort nötig.")
    elif not (str(request.session.get("auth_method", "")).startswith("oidc")
              and time.time() - float(request.session.get("auth_at", 0)) < 600):
        raise HTTPException(403, "Bitte über OIDC erneut anmelden und die Änderung innerhalb von 10 Minuten bestätigen.")


async def _payload(request: Request) -> dict:
    if int(request.headers.get("content-length") or 0) > MAX_RESPONSE:
        raise HTTPException(413, "Passkey-Antwort ist zu groß.")
    body = await request.body()
    if len(body) > MAX_RESPONSE:
        raise HTTPException(413, "Passkey-Antwort ist zu groß.")
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise HTTPException(400, "Ungültige Passkey-Daten.") from None
    if not isinstance(data, dict):
        raise HTTPException(400, "Ungültige Passkey-Daten.")
    return data


def _credential(data: dict) -> dict:
    result = data.get("credential")
    if not isinstance(result, dict) or result.get("type") != "public-key":
        raise HTTPException(400, "Das Gerät hat keine gültige Passkey-Antwort geliefert.")
    cid = result.get("id")
    if not isinstance(cid, str) or not cid or len(cid) > 1024:
        raise HTTPException(400, "Ungültige Passkey-Kennung.")
    return result


@app.post("/auth/passkeys/login/options", dependencies=[Depends(check_csrf)])
async def passkey_login_options(request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "passkey-start", limit=12, window=900)
    rp_id, origin = _rp(request)
    opts = generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED,
        timeout=120000,
    )
    _create(db, request, "passkey_login", "login", opts.challenge, rp_id, origin)
    return JSONResponse(json.loads(options_to_json(opts)), headers=HEADERS)


@app.post("/auth/passkeys/login/verify", dependencies=[Depends(check_csrf)])
async def passkey_login_verify(request: Request, db: Session = Depends(get_db)):
    rate_limit(request, "passkey-verify", limit=15, window=900)
    data = await _payload(request)
    credential = _credential(data)
    flow = _consume(db, request, "passkey_login", "login")
    stored = db.scalar(select(PasskeyCredential).where(
        PasskeyCredential.credential_id == credential["id"]))
    if stored is None:
        raise HTTPException(401, "Passkey-Anmeldung nicht möglich.")
    user = db.get(User, stored.user_id)
    if user is None or not user.active:
        raise HTTPException(401, "Passkey-Anmeldung nicht möglich.")
    response = credential.get("response")
    if not isinstance(response, dict):
        raise HTTPException(401, "Passkey-Anmeldung nicht möglich.")
    handle = response.get("userHandle")
    if handle is not None and handle != _b64(user.id.to_bytes(8, "big")):
        raise HTTPException(401, "Passkey-Anmeldung nicht möglich.")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(flow.challenge),
            expected_rp_id=flow.rp_id, expected_origin=flow.origin,
            credential_public_key=base64url_to_bytes(stored.public_key),
            credential_current_sign_count=stored.sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, TypeError, KeyError):
        raise HTTPException(401, "Passkey-Anmeldung nicht möglich.") from None
    # Race-safe update: never let another parallel verification roll back a counter.
    previous = stored.sign_count
    changed = db.execute(update(PasskeyCredential).where(
        PasskeyCredential.id == stored.id,
        PasskeyCredential.sign_count == previous,
    ).values(sign_count=verified.new_sign_count,
             backed_up=bool(verified.credential_backed_up), last_used_at=utcnow()))
    db.commit()
    if changed.rowcount != 1:
        raise HTTPException(401, "Passkey-Anmeldung nicht möglich.")
    destination = safe_next(data.get("next") if isinstance(data.get("next"), str) else "/")
    if destination == "/":
        destination = home_for(user)
    request.session.clear()
    sessions.establish(request, db, user, method="passkey")
    if twofa.needs_setup(user, get_settings(db)):
        request.session["mfa_setup"] = True
    return JSONResponse({"ok": True, "redirect": destination}, headers=HEADERS)


@app.post("/profile/passkeys/options", dependencies=[Depends(check_csrf)])
async def passkey_register_options(request: Request, user: User = Depends(current_user),
                                    db: Session = Depends(get_db)):
    rate_limit(request, "passkey-register", limit=8, window=900, key=str(user.id))
    data = await _payload(request)
    _verify_recent(user, request, str(data.get("password") or ""))
    rp_id, origin = _rp(request)
    credentials = list(db.scalars(select(PasskeyCredential).where(PasskeyCredential.user_id == user.id)))
    if len(credentials) >= MAX_KEYS_PER_USER:
        raise HTTPException(409, "Maximal 15 Passkeys pro Benutzerkonto.")
    opts = generate_registration_options(
        rp_id=rp_id, rp_name="TAKT Portal",
        user_id=user.id.to_bytes(8, "big"),
        user_name=user.email, user_display_name=user.name,
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(k.credential_id))
                             for k in credentials],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        timeout=120000,
    )
    _create(db, request, "passkey_register", "register", opts.challenge, rp_id, origin, user)
    return JSONResponse(json.loads(options_to_json(opts)), headers=HEADERS)


@app.post("/profile/passkeys/verify", dependencies=[Depends(check_csrf)])
async def passkey_register_verify(request: Request, user: User = Depends(current_user),
                                   db: Session = Depends(get_db)):
    rate_limit(request, "passkey-enroll-verify", limit=10, window=900, key=str(user.id))
    data = await _payload(request)
    credential = _credential(data)
    flow = _consume(db, request, "passkey_register", "register", user)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(flow.challenge),
            expected_rp_id=flow.rp_id, expected_origin=flow.origin,
            require_user_verification=True,
        )
    except (ValueError, TypeError, KeyError):
        raise HTTPException(400, "Passkey konnte nicht verifiziert werden.") from None
    if _b64(verified.credential_id) != credential["id"]:
        raise HTTPException(400, "Passkey-Kennung widerspricht der Attestierung.")
    name = str(data.get("name") or "Mein Passkey").strip()[:100] or "Mein Passkey"
    response = credential.get("response")
    transports = response.get("transports") if isinstance(response, dict) else []
    if not isinstance(transports, list):
        transports = []
    db.add(PasskeyCredential(
        user_id=user.id, credential_id=_b64(verified.credential_id),
        public_key=_b64(verified.credential_public_key),
        sign_count=verified.sign_count, name=name,
        backed_up=bool(verified.credential_backed_up),
        transports_json=json.dumps([x for x in transports if isinstance(x, str)][:8]),
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Dieser Passkey ist bereits registriert.") from None
    return JSONResponse({"ok": True, "redirect": "/profile/security#passkeys"}, headers=HEADERS)


@app.post("/profile/passkeys/{credential_id:int}/delete", dependencies=[Depends(check_csrf)])
def passkey_delete(request: Request, credential_id: int, password: str = Form(""),
                   user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    rate_limit(request, "passkey-delete", limit=10, window=900, key=str(user.id))
    _verify_recent(user, request, password)
    key = db.scalar(select(PasskeyCredential).where(
        PasskeyCredential.id == credential_id, PasskeyCredential.user_id == user.id))
    if key is None:
        raise HTTPException(404, "Passkey nicht gefunden.")
    db.delete(key)
    db.commit()
    return redirect("/profile/security#passkeys")


@app.post("/admin/users/{target_id:int}/passkeys/revoke", dependencies=[Depends(check_csrf)])
def passkey_admin_revoke(request: Request, target_id: int, password: str = Form(""),
                         confirm: str = Form(""), user: User = Depends(admin_user),
                         db: Session = Depends(get_db)):
    rate_limit(request, "passkey-admin-revoke", limit=10, window=900, key=str(user.id))
    _verify_recent(user, request, password)
    if confirm != "1" or db.get(User, target_id) is None:
        raise HTTPException(400, "Kontobestätigung fehlt oder Konto unbekannt.")
    db.execute(delete(PasskeyCredential).where(PasskeyCredential.user_id == target_id))
    db.commit()
    # Revoking a potentially stolen key also invalidates any session it created.
    sessions.end_all(db, target_id)
    if target_id == user.id:
        request.session.clear()
    return redirect("/admin/users#benutzer")
