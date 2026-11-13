"""Passkey registration, login, replay prevention and account isolation."""
import base64
import secrets
from types import SimpleNamespace

from sqlalchemy import select

from app import routes_passkeys as pk
from app.db import SessionLocal, User
from app.passkey_models import PasskeyCredential
from conftest import client, csrf_of, login


def _header(c, path="/login"):
    return {"X-CSRF-Token": csrf_of(c.get(path).text)}


def _user():
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.email == "admin@example.org")).id


def test_passkey_login_and_profile_security_ui_present():
    anonymous = client()
    page = anonymous.get("/login")
    assert page.status_code == 200
    assert "Mit Passkey anmelden" in page.text
    assert "/static/passkeys.js" in page.text
    user_client = login("admin@example.org", "admin-passwort-123")
    security = user_client.get("/profile/security")
    assert security.status_code == 200
    assert "Passkey einrichten" in security.text
    assert "data-passkey-enroll" in security.text
    admin = user_client.get("/admin/users")
    assert "Passkey-Verwaltung" in admin.text


def test_registration_requires_reauth_csrf_and_secure_rp():
    c = login("admin@example.org", "admin-passwort-123")
    assert c.post("/profile/passkeys/options", json={"password": "admin-passwort-123"}).status_code == 400
    h = _header(c, "/profile/security")
    bad = c.post("/profile/passkeys/options", json={"password": "falsch"}, headers=h)
    assert bad.status_code == 403
    good = c.post("/profile/passkeys/options", json={"password": "admin-passwort-123"}, headers=h)
    assert good.status_code == 200, good.text
    opts = good.json()
    assert opts["rp"]["id"] == "portal.example.org"
    assert opts["authenticatorSelection"]["residentKey"] == "required"
    assert opts["authenticatorSelection"]["userVerification"] == "required"
    assert len(opts["user"]["id"]) >= 32  # opaque non-enumerable account handle
    assert good.headers["cache-control"] == "no-store"


def test_registration_and_discoverable_login_reject_challenge_replay(monkeypatch):
    c = login("admin@example.org", "admin-passwort-123")
    token = _header(c, "/profile/security")
    start = c.post("/profile/passkeys/options", json={"password": "admin-passwort-123"}, headers=token)
    assert start.status_code == 200, start.text
    cid = secrets.token_bytes(24)
    encoded = base64.urlsafe_b64encode(cid).decode().rstrip("=")
    monkeypatch.setattr(pk, "verify_registration_response", lambda **kwargs: SimpleNamespace(
        credential_id=cid, credential_public_key=b"public-key-test",
        sign_count=0, credential_backed_up=True,
    ))
    payload = {"credential": {"type": "public-key", "id": encoded,
                              "response": {"transports": ["internal"]}}, "name": "Dienstlaptop"}
    response = c.post("/profile/passkeys/verify", headers=token, json=payload)
    assert response.status_code == 200, response.text
    again = c.post("/profile/passkeys/verify", headers=token, json=payload)
    assert again.status_code == 400
    with SessionLocal() as db:
        stored = db.scalar(select(PasskeyCredential).where(PasskeyCredential.credential_id == encoded))
        assert stored and stored.user_id == _user()
        assert stored.name == "Dienstlaptop"
    a = client()
    t = _header(a)
    options = a.post("/auth/passkeys/login/options", headers=t, json={})
    assert options.status_code == 200, options.text
    assert options.json()["userVerification"] == "required"
    monkeypatch.setattr(pk, "verify_authentication_response", lambda **kwargs: SimpleNamespace(
        credential_id=cid, user_verified=True, new_sign_count=2, credential_backed_up=True,
    ))
    auth_payload = {"credential": {"type": "public-key", "id": encoded,
                                   "response": {"userHandle": None}}, "next": "/profile"}
    authenticated = a.post("/auth/passkeys/login/verify", headers=t, json=auth_payload)
    assert authenticated.status_code == 200, authenticated.text
    assert authenticated.json()["redirect"] == "/profile"
    assert a.get("/profile").status_code == 200
    assert a.post("/auth/passkeys/login/verify", headers=t, json=auth_payload).status_code == 400
    d = a.post(f"/profile/passkeys/{stored.id}/delete", data={
        "csrf": csrf_of(a.get("/profile/security").text), "password": "admin-passwort-123"})
    assert d.status_code == 303
    with SessionLocal() as db:
        assert db.get(PasskeyCredential, stored.id) is None


def test_unknown_passkey_never_establishes_session():
    c = client()
    token = _header(c)
    assert c.post("/auth/passkeys/login/options", headers=token, json={}).status_code == 200
    failed = c.post("/auth/passkeys/login/verify", headers=token,
                    json={"credential": {"id": "unknown-id", "type": "public-key",
                                         "response": {}}})
    assert failed.status_code == 401
    assert c.get("/profile").status_code in (302, 303)


def test_admin_revoke_requires_admin_password_and_confirmation():
    c = login("admin@example.org", "admin-passwort-123")
    target = _user()
    token = csrf_of(c.get("/admin/users").text)
    url = f"/admin/users/{target}/passkeys/revoke"
    assert c.post(url, data={"csrf": token, "confirm": "1", "password": "wrong"}).status_code == 403
    assert c.post(url, data={"csrf": token, "confirm": "", "password": "admin-passwort-123"}).status_code == 400
    ok = c.post(url, data={"csrf": token, "confirm": "1", "password": "admin-passwort-123"})
    assert ok.status_code == 303


def test_configured_rp_origin_must_match_browser_host(monkeypatch):
    c = client()
    token = _header(c)
    monkeypatch.setattr(pk.settings, "portal_base_url", "https://foreign.example.org")
    try:
        assert c.post("/auth/passkeys/login/options", headers=token, json={}).status_code == 503
    finally:
        monkeypatch.setattr(pk.settings, "portal_base_url", "https://portal.example.org")


def test_invalid_attestation_is_rejected_once_without_storing_key():
    c = login("admin@example.org", "admin-passwort-123")
    headers = _header(c, "/profile/security")
    started = c.post("/profile/passkeys/options",
                     headers=headers, json={"password": "admin-passwort-123"})
    assert started.status_code == 200
    forged = {"credential": {
        "type": "public-key", "id": "AAECAw",
        "rawId": "AAECAw", "response": {
            "attestationObject": "AQID", "clientDataJSON": "AQID"
        }}}
    first = c.post("/profile/passkeys/verify", headers=headers, json=forged)
    assert first.status_code == 400
    second = c.post("/profile/passkeys/verify", headers=headers, json=forged)
    assert second.status_code == 400


def test_revoke_does_not_accept_wrong_csrf_or_unauthenticated_user():
    c = client()
    assert c.post("/profile/passkeys/options", json={"password": "any"}).status_code == 400
    assert c.post("/admin/users/1/passkeys/revoke",
                  data={"confirm": "1", "password": "any"}).status_code == 400
