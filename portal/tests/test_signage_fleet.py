"""Device fleet and credential safety acceptance tests."""
import re
from datetime import timedelta

from conftest import client, csrf_of
from test_signage import _admin, _screen
from app import signage_fleet
from app.db import SessionLocal, utcnow
from app.signage_models import SignageDevice, SignageDeviceTelemetry


def _paired():
    c = _admin()
    sid = _screen(c, "Gerätebetrieb Empfang")
    csrf = csrf_of(c.get(f"/signage/{sid}/edit").text)
    response = c.post(f"/signage/{sid}/device",
                      data={"csrf": csrf, "name": "Info-Terminal EG"})
    assert response.status_code == 200
    found = re.search(r"Gerät-ID: (\d+)\s+Bearer: ([\w-]+)", response.text)
    assert found
    return c, sid, int(found.group(1)), found.group(2)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_allowlisted_telemetry_and_fleet_dashboard():
    c, sid, did, secret = _paired()
    info = {
        "platform": "linux", "client_version": "1.2.3",
        "screen_width": 1920, "screen_height": 1080,
        "reported_screen_version": 1, "diagnostic_code": "render_error",
    }
    pulse = client().post(f"/signage/api/device/{did}/heartbeat",
                          json=info, headers=_auth(secret))
    assert pulse.status_code == 200, pulse.text
    assert pulse.json()["screen_id"] == sid
    assert "server_time" in pulse.json()
    with SessionLocal() as db:
        detail = db.get(SignageDeviceTelemetry, did)
        assert detail.platform == "linux" and detail.client_version == "1.2.3"
        assert detail.screen_width == 1920 and detail.diagnostic_code == "render_error"
    dashboard = c.get("/signage/fleet")
    assert dashboard.status_code == 200
    assert "Info-Terminal EG" in dashboard.text
    assert "render_error" not in dashboard.text  # human-readable safe diagnostic only
    assert "Darstellungsfehler" in dashboard.text
    assert secret not in dashboard.text
    feed = c.get("/signage/fleet/status")
    assert feed.status_code == 200
    assert feed.headers["cache-control"] == "no-store"
    device = next(item for item in feed.json()["devices"] if item["id"] == did)
    assert device["status"] == "online"
    assert device["diagnostic_code"] == "render_error"
    assert device["reported_version"] == 1
    assert secret not in feed.text


def test_invalid_telemetry_never_writes_or_exposes_device_details():
    c, sid, did, token = _paired()
    url = f"/signage/api/device/{did}/heartbeat"
    for invalid in (
        {"hostname": "private-username-computer"},
        {"platform": "free-text-personal"},
        {"client_version": "<script>"},
        {"screen_width": True},
        {"screen_height": -1},
        {"reported_screen_version": 10000000},
        {"diagnostic_code": "this is a private employee"},
        ["not", "a", "dictionary"],
    ):
        response = client().post(url, json=invalid, headers=_auth(token))
        assert response.status_code == 422, (invalid, response.text)
    too_large = client().post(url, content=b'{' + b'x' * 3000 + b'}',
                              headers={**_auth(token), "Content-Type": "application/json"})
    assert too_large.status_code == 413
    with SessionLocal() as db:
        assert db.get(SignageDeviceTelemetry, did) is None
        assert db.get(SignageDevice, did).last_seen_at is None
    assert client().get("/signage/fleet").status_code in (303, 401, 403)
    assert client().get("/signage/fleet/status").status_code in (303, 401, 403)
    assert client().post(url, json={"platform": "windows"}).status_code == 403


def test_device_rotation_immediately_revokes_previous_secret():
    c, sid, did, token = _paired()
    url = f"/signage/api/device/{did}/heartbeat"
    assert client().post(url, headers=_auth(token),
                         json={"platform": "windows"}).status_code == 200
    rotation = f"/signage/{sid}/device/{did}/rotate"
    assert c.post(rotation, data={"csrf": "invalid"}).status_code in (400, 403)
    csrf = csrf_of(c.get("/signage/fleet").text)
    resp = c.post(rotation, data={"csrf": csrf})
    assert resp.status_code == 200
    found = re.search(r"Gerät-ID: (\d+)\s+Bearer: ([\w-]+)", resp.text)
    assert found and int(found.group(1)) == did
    new_token = found.group(2)
    assert new_token != token
    assert client().post(url, headers=_auth(token)).status_code == 403
    assert client().get(f"/signage/api/device/{did}/manifest", headers=_auth(token)).status_code == 403
    assert client().post(url, headers=_auth(new_token)).status_code == 200
    with SessionLocal() as db:
        assert db.get(SignageDeviceTelemetry, did) is None
    assert new_token not in c.get("/signage/fleet").text
    assert new_token not in c.get(f"/signage/{sid}/edit").text
    assert resp.headers["cache-control"] == "no-store"


def test_health_uses_server_time_and_flags_stale_or_revoked_devices():
    c, sid, did, token = _paired()
    now = utcnow()
    with SessionLocal() as db:
        device = db.get(SignageDevice, did)
        assert signage_fleet.health(device, now=now)["code"] == "new"
        device.last_seen_at = now - timedelta(seconds=181)
        assert signage_fleet.health(device, now=now)["code"] == "delayed"
        device.last_seen_at = now - timedelta(seconds=901)
        assert signage_fleet.health(device, now=now)["code"] == "offline"
        device.revoked = True
        assert signage_fleet.health(device, now=now)["code"] == "revoked"


def test_rotating_a_revoked_or_other_screen_device_is_rejected():
    c, sid, did, secret = _paired()
    other = _screen(c, "Andere Anzeige")
    csrf = csrf_of(c.get(f"/signage/{sid}/edit").text)
    assert c.post(f"/signage/{other}/device/{did}/rotate", data={"csrf": csrf}).status_code == 404
    assert c.post(f"/signage/{sid}/device/{did}/revoke", data={"csrf": csrf}).status_code == 303
    assert c.post(f"/signage/{sid}/device/{did}/rotate", data={"csrf": csrf}).status_code == 404


def test_public_kiosk_is_explicitly_marked_and_fails_closed_when_connection_lost():
    c = _admin()
    sid = _screen(c, "Statische Rathausanzeige", visibility="public")
    visitor = client()
    page = visitor.get(f"/signage/view/{sid}")
    assert page.status_code == 200
    assert page.headers["x-takt-signage"] == "display"
    assert "no-store" in page.headers["cache-control"]
    assert 'data-sg-auto-refresh="60"' in page.text
    assert 'data-sg-stale' in page.text
    assert "Informationen momentan nicht verfügbar" in page.text
    assert "<noscript><meta http-equiv=\"refresh\"" in page.text
    preview = c.get(f"/signage/{sid}/preview")
    assert preview.status_code == 200
    assert 'data-sg-auto-refresh="0"' in preview.text


def test_telemetry_state_and_credential_revoke_does_not_expose_old_diagnostics():
    c, sid, did, secret = _paired()
    client().post(f"/signage/api/device/{did}/heartbeat", headers=_auth(secret),
                  json={"platform": "android", "diagnostic_code": "network_error",
                        "client_version": "2.4.0"})
    feed = c.get("/signage/fleet/status").json()
    assert any(x["id"] == did and x["diagnostic_code"] == "network_error"
               for x in feed["devices"])
    csrf = csrf_of(c.get(f"/signage/{sid}/edit").text)
    assert c.post(f"/signage/{sid}/device/{did}/revoke", data={"csrf": csrf}).status_code == 303
    feed = c.get("/signage/fleet/status").json()
    assert any(x["id"] == did and x["status"] == "revoked" for x in feed["devices"])
    assert client().post(f"/signage/api/device/{did}/heartbeat",
                         headers=_auth(secret)).status_code == 403
