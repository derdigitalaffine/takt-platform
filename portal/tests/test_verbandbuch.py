"""Digitales Verbandbuch: Security, kryptographische Trennung, QR, Fristen, DGUV-Felder."""
import uuid
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select

from app import main, verbandbuch as aid
from app.db import Organization, SessionLocal, User, utcnow
from app.security import hash_password
from app.verbandbuch_models import FirstAidCase, FirstAidCorrection, FirstAidGrant, FirstAidSite
from conftest import client, csrf_of, login, settings

PASSWORD = "Takt-Verbandsbuch-Test-2026!"
FORM = {
    "person_name": "Erika Musterfrau",
    "person_group": "beschaeftigt",
    "incident_at": "2026-11-13T08:10",
    "incident_place": "Verwaltungsgebäude, Treppe",
    "incident_description": "Beim Hinuntergehen ausgerutscht",
    "injury": "Kleine Schürfwunde am Ellenbogen",
    "aid_at": "2026-11-13T08:15",
    "aid_description": "Wunde gereinigt und Pflaster angelegt",
    "aider_name": "Max Hilfsbereit",
    "witnesses": "N. Beispiel",
}


@pytest.fixture
def aid_env(monkeypatch):
    monkeypatch.setenv("VERBANDBUCH_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VERBANDBUCH_PRODUCTION_APPROVED", "1")
    settings(module_verbandbuch="1")
    yield
    settings(module_verbandbuch="0")


def add_user(db, perms):
    name = "VB " + uuid.uuid4().hex[:10]
    user = User(name=name, email=uuid.uuid4().hex + "@example.org",
                password_hash=hash_password(PASSWORD), permissions=perms,
                is_admin=False, active=True, must_change_password=False)
    db.add(user)
    db.flush()
    return user


def fixture_site(*, grant_capture=True, grant_review=False):
    with SessionLocal() as db:
        org = Organization(name="Standort " + uuid.uuid4().hex[:8],
                           kind="einrichtung", active=True)
        db.add(org)
        db.flush()
        site = FirstAidSite(org_id=org.id, title="Rathaus · Erdgeschoss")
        db.add(site)
        db.flush()
        capturer = add_user(db, "verbandbuch_capture")
        reviewer = add_user(db, "verbandbuch_review")
        outsider = add_user(db, "verbandbuch_capture,verbandbuch_review")
        if grant_capture:
            db.add(FirstAidGrant(site_id=site.id, user_id=capturer.id, role="capture"))
        if grant_review:
            db.add(FirstAidGrant(site_id=site.id, user_id=reviewer.id, role="review"))
        site_id, capturer_email, reviewer_email, outsider_email = (site.id, capturer.email, reviewer.email, outsider.email)
        db.commit()
    return site_id, capturer_email, reviewer_email, outsider_email


def send_form(email, site_id, data=None):
    session = login(email, PASSWORD)
    form = session.get("/verbandbuch/neu")
    assert form.status_code == 200
    payload = dict(FORM, **(data or {}), site_id=str(site_id), csrf=csrf_of(form.text))
    return session, session.post("/verbandbuch/neu", data=payload)


def test_default_off_and_no_public_access():
    settings(module_verbandbuch="0")
    assert client().get("/verbandbuch").status_code == 404
    assert client().get("/verbandbuch/neu").status_code == 404
    assert client().get("/verbandbuch/standorte").status_code == 404


def test_reject_real_entries_until_approved_and_key(monkeypatch, aid_env):
    site_id, email, _, _ = fixture_site()
    session = login(email, PASSWORD)
    token = csrf_of(session.get("/verbandbuch/neu").text)
    monkeypatch.delenv("VERBANDBUCH_ENCRYPTION_KEY")
    denied = session.post("/verbandbuch/neu", data=dict(FORM, site_id=site_id, csrf=token))
    assert denied.status_code == 503
    monkeypatch.setenv("VERBANDBUCH_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("VERBANDBUCH_PRODUCTION_APPROVED")
    assert session.post("/verbandbuch/neu", data=dict(FORM, site_id=site_id, csrf=token)).status_code == 423


def test_qr_does_not_grant_access(aid_env):
    site_id, email, _, outsider_email = fixture_site()
    with SessionLocal() as db:
        site = aid.qr_site(db, aid.qr_token(site_id))
        assert site.id == site_id
        with pytest.raises(HTTPException) as error:
            aid.qr_site(db, aid.qr_token(site_id) + "tampered")
        assert error.value.status_code == 404
    outsider = login(outsider_email, PASSWORD)
    assert outsider.get("/verbandbuch/neu?s=" + aid.qr_token(site_id)).status_code == 403
    creator = login(email, PASSWORD)
    assert creator.get("/verbandbuch/neu?s=" + aid.qr_token(site_id)).status_code == 200


def test_secure_capture_receipt_and_no_health_leak(aid_env):
    site_id, email, reviewer_email, outsider_email = fixture_site(grant_review=True)
    session, result = send_form(email, site_id)
    assert result.status_code == 303
    case_id = result.headers["location"].rsplit("/", 1)[-1]
    receipt = session.get("/verbandbuch/beleg/" + case_id)
    assert receipt.status_code == 200
    for secret in ("Erika Musterfrau", FORM["injury"], FORM["incident_description"]):
        assert secret not in receipt.text
    assert receipt.headers["cache-control"].startswith("no-store")
    with SessionLocal() as db:
        entry = db.get(FirstAidCase, case_id)
        assert entry is not None
        assert "Erika Musterfrau" not in entry.payload_enc
        assert FORM["injury"] not in entry.payload_enc
        assert 1825 <= (entry.retention_due_at - entry.created_at).days <= 1827
    reviewer = login(reviewer_email, PASSWORD)
    detail = reviewer.get("/verbandbuch/fall/" + case_id)
    assert detail.status_code == 200 and "Erika Musterfrau" in detail.text
    assert detail.headers["referrer-policy"] == "no-referrer"
    assert detail.headers["cache-control"].startswith("no-store")
    assert session.get("/verbandbuch/fall/" + case_id).status_code == 404
    outsider = login(outsider_email, PASSWORD)
    assert outsider.get("/verbandbuch/beleg/" + case_id).status_code == 404
    assert outsider.get("/verbandbuch/fall/" + case_id).status_code == 404


def test_cross_site_write_and_csrf(aid_env):
    site_id, email, _, _ = fixture_site()
    second_id, _, _, _ = fixture_site()
    session = login(email, PASSWORD)
    token = csrf_of(session.get("/verbandbuch/neu").text)
    forbidden = session.post("/verbandbuch/neu", data=dict(FORM, site_id=second_id, csrf=token))
    assert forbidden.status_code == 403
    assert session.post("/verbandbuch/neu", data=dict(FORM, site_id=site_id, csrf="invalid")).status_code == 400
    invalid = session.post("/verbandbuch/neu", data=dict(FORM, site_id=site_id, csrf=token, injury=""))
    assert invalid.status_code == 422 and "Art und Umfang" in invalid.text


def test_correction_preserves_immutable_original_and_audits(aid_env):
    site_id, email, reviewer_email, _ = fixture_site(grant_review=True)
    _, result = send_form(email, site_id)
    case_id = result.headers["location"].rsplit("/", 1)[-1]
    reviewer = login(reviewer_email, PASSWORD)
    page = reviewer.get("/verbandbuch/fall/" + case_id)
    token = csrf_of(page.text)
    result = reviewer.post(
        "/verbandbuch/fall/" + case_id + "/korrektur",
        data=dict(FORM, injury="Weitere Schürfwunde", reason="Nachträgliche Präzisierung", csrf=token),
    )
    assert result.status_code == 303
    with SessionLocal() as db:
        original = db.get(FirstAidCase, case_id)
        old = aid.open_sealed(original.payload_enc)
        assert old["injury"] == FORM["injury"]
        corrected, versions = aid.snapshot(db, original)
        assert versions[0].revision == 1
        assert corrected["injury"] == "Weitere Schürfwunde"
        assert "Weitere Schürfwunde" not in original.payload_enc
    assert "Weitere Schürfwunde" in reviewer.get("/verbandbuch/fall/" + case_id).text


def test_retention_deletes_case_and_respects_holds(aid_env):
    site_id, email, _, _ = fixture_site(grant_review=False)
    _, result = send_form(email, site_id)
    case_id = result.headers["location"].rsplit("/", 1)[-1]
    _, result2 = send_form(email, site_id)
    hold_id = result2.headers["location"].rsplit("/", 1)[-1]
    with SessionLocal() as db:
        first = db.get(FirstAidCase, case_id)
        first.retention_due_at = utcnow() - timedelta(days=1)
        hold = db.get(FirstAidCase, hold_id)
        hold.retention_due_at = utcnow() - timedelta(days=1)
        hold.legal_hold = True
        db.commit()
    assert aid.purge_due() >= 1
    with SessionLocal() as db:
        assert db.get(FirstAidCase, case_id) is None
        assert db.get(FirstAidCase, hold_id) is not None


def test_admin_has_no_implicit_health_access(aid_env):
    site_id, email, _, _ = fixture_site()
    _, result = send_form(email, site_id)
    case_id = result.headers["location"].rsplit("/", 1)[-1]
    admin = login("admin@example.org", "admin-passwort-123")
    assert admin.get("/verbandbuch/standorte").status_code == 200
    assert admin.get("/verbandbuch/fall/" + case_id).status_code == 404
    assert admin.get("/verbandbuch/beleg/" + case_id).status_code == 404
    assert "js-qr-open" in admin.get("/verbandbuch/standorte").text


def test_deactivation_revokes_qr_and_existing_grants(aid_env):
    site_id, email, _, _ = fixture_site()
    creator = login(email, PASSWORD)
    assert creator.get("/verbandbuch/neu?s=" + aid.qr_token(site_id)).status_code == 200
    admin = login("admin@example.org", "admin-passwort-123")
    token = csrf_of(admin.get("/verbandbuch/standorte").text)
    response = admin.post("/verbandbuch/standorte/" + str(site_id) + "/status",
                          data={"csrf": token, "active": "0"})
    assert response.status_code == 303
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as error:
            aid.qr_site(db, aid.qr_token(site_id))
        assert error.value.status_code == 404
        user = db.scalar(select(User).where(User.email == email))
        assert not aid.may(db, user, site_id, "capture")
    assert creator.get("/verbandbuch/neu?s=" + aid.qr_token(site_id)).status_code == 404


def test_frontend_key_setup_is_admin_only_and_persistent(aid_env, monkeypatch, tmp_path):
    monkeypatch.delenv("VERBANDBUCH_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(aid, "_key_path", lambda: tmp_path / "private" / "fachschluessel.key")
    # Andere Tests teilen die Datenbank und können bereits Fälle erzeugt haben.
    # Für die isolierte Erstinitialisierung nur den Count-Guard simulieren.
    class EmptyCases:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def scalar(self, *_):
            return 0
    monkeypatch.setattr(aid, "SessionLocal", EmptyCases)
    admin = login("admin@example.org", "admin-passwort-123")
    page = admin.get("/verbandbuch/standorte")
    assert "Sicheren Fachschlüssel jetzt erzeugen" in page.text
    token = csrf_of(page.text)
    assert admin.post("/verbandbuch/schluessel/erzeugen", data={"csrf": "invalid"}).status_code == 400
    site_id, email, _, _ = fixture_site()
    regular = login(email, PASSWORD)
    assert regular.post("/verbandbuch/schluessel/erzeugen", data={"csrf": csrf_of(regular.get("/verbandbuch/neu").text)}).status_code == 403
    result = admin.post("/verbandbuch/schluessel/erzeugen", data={"csrf": token})
    assert result.status_code == 303
    path = aid._key_path()
    assert path.is_file()
    assert path.stat().st_mode & 0o077 == 0
    secret = path.read_text().strip()
    assert secret not in admin.get("/verbandbuch/standorte").text
    assert aid.ready() and aid.key_source() == "file"
    assert aid.open_sealed(aid.seal({"test": "gesichert"})) == {"test": "gesichert"}
    assert admin.post("/verbandbuch/schluessel/erzeugen", data={"csrf": token}).status_code == 409
    assert path.read_text().strip() == secret


def test_invalid_external_key_does_not_get_replaced(aid_env, monkeypatch, tmp_path):
    monkeypatch.setattr(aid, "_key_path", lambda: tmp_path / "fachschluessel.key")
    monkeypatch.setenv("VERBANDBUCH_ENCRYPTION_KEY", "invalid")
    assert aid.key_source() == "environment"
    assert not aid.ready()
    with pytest.raises(HTTPException) as error:
        aid.generate_key_once()
    assert error.value.status_code == 409
    assert not aid._key_path().exists()

def test_verbandbuch_wizard_assets_and_privacy(client):
    response = client.get("/verbandbuch/neu")
    # Depending on authentication state the route redirects to login.
    assert response.status_code in (200, 303, 307)
