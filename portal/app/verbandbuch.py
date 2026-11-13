"""Fachlogik und Kryptogrenze des digitalen Verbandsbuchs."""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import delete, select
from .config import settings
from .db import LOCAL_TZ, SessionLocal, Organization, User, utcnow
from .verbandbuch_models import (
    FirstAidAudit, FirstAidCase, FirstAidCorrection, FirstAidDeletionProof,
    FirstAidGrant, FirstAidSite,
)

log = logging.getLogger("portal.verbandbuch")
FIELD_LIMITS = {
    "person_name": 160, "person_group": 40, "incident_at": 32,
    "incident_place": 200, "incident_description": 2500, "injury": 2000,
    "aid_at": 32, "aid_description": 2000, "aider_name": 160,
    "witnesses": 700,
}
REQUIRED = ("person_name", "incident_at", "incident_place", "incident_description",
            "injury", "aid_at", "aid_description", "aider_name")
FIELD_LABELS = {
    "person_name": "Betroffene Person", "person_group": "Personenkreis",
    "incident_at": "Zeitpunkt des Ereignisses", "incident_place": "Ort des Ereignisses",
    "incident_description": "Hergang", "injury": "Art und Umfang der Verletzung / Erkrankung",
    "aid_at": "Zeitpunkt der Ersten Hilfe", "aid_description": "Erste-Hilfe-Maßnahmen",
    "aider_name": "Ersthelfende Person", "witnesses": "Zeuginnen und Zeugen",
}


def _key_path() -> Path:
    """Persistente Datei im bereits gemounteten TAKT-Datenverzeichnis, nie im Webroot."""
    return Path(settings.data_dir) / "verbandbuch" / "fachschluessel.key"


def key_source() -> str:
    if os.environ.get("VERBANDBUCH_ENCRYPTION_KEY", "").strip():
        return "environment"
    return "file" if _key_path().is_file() else "missing"


def _key_bytes() -> bytes:
    env_value = os.environ.get("VERBANDBUCH_ENCRYPTION_KEY", "").strip()
    if env_value:
        return env_value.encode("ascii")
    try:
        return _key_path().read_bytes().strip()
    except OSError as exc:
        raise HTTPException(503, "Fachverschlüsselung nicht eingerichtet.") from exc


def generate_key_once() -> None:
    """Serverseitig generieren, atomar exklusiv speichern; niemals an Browser ausgeben.

    Bei extern verwaltetem Key oder existierenden Fällen kein neues Material erzeugen.
    Die Betriebsfreigabe bleibt unabhängig davon gesperrt.
    """
    if key_source() != "missing":
        raise HTTPException(409, "Ein Fachschlüssel ist bereits eingerichtet.")
    from sqlalchemy import func
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(FirstAidCase)):
            raise HTTPException(409, "Bestehende Akten verhindern eine neue Schlüsselgenerierung.")
    path = _key_path()
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # O_EXCL verhindert parallele Erzeugung und Überschreiben bestehender Schlüssel.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise HTTPException(409, "Ein Fachschlüssel ist bereits eingerichtet.") from exc
    except OSError as exc:
        log.exception("Fachschlüssel konnte nicht sicher angelegt werden")
        raise HTTPException(503, "Sicherer Schlüsselspeicher nicht verfügbar.") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(Fernet.generate_key() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.exception("Unvollständige Schlüsseldatei konnte nicht entfernt werden")
        raise
    log.info("Verbandbuch-Fachschlüssel serverseitig initialisiert")


def _cipher() -> Fernet:
    # Bewusst NICHT aus PORTAL_SECRET_KEY oder API-Key-Verschlüsselung abgeleitet.
    try:
        return Fernet(_key_bytes())
    except (ValueError, TypeError, UnicodeError) as exc:
        raise HTTPException(503, "Fachverschlüsselung ungültig oder nicht eingerichtet.") from exc


def ready() -> bool:
    try:
        _cipher()
        return True
    except HTTPException:
        return False


def approved() -> bool:
    # Fachliches Gate, kein automatischer Nachweis einer DSFA oder Rechtsfreigabe.
    return os.environ.get("VERBANDBUCH_PRODUCTION_APPROVED", "") == "1"


def seal(data: dict | str) -> str:
    value = json.dumps(data, ensure_ascii=False, separators=(",", ":")) if isinstance(data, dict) else data
    return _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def open_sealed(value: str) -> dict:
    try:
        data = _cipher().decrypt(value.encode("ascii"))
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("invalid payload type")
        return result
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise HTTPException(503, "Geschützter Eintrag konnte nicht entschlüsselt werden.") from exc


def local_time(raw: str) -> str:
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is not None or dt.year < 2000:
            raise ValueError()
        # Speichere den eingegebenen lokalen Zeitpunkt verlustfrei, nur im Chiffrat.
        utc = dt.replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)
        if utc > utcnow() + timedelta(days=366):
            raise ValueError()
        return dt.isoformat(timespec="minutes")
    except ValueError:
        raise ValueError("Ungültiger Zeitpunkt. Bitte Datum und Uhrzeit prüfen.") from None


def validate(raw) -> tuple[dict, list[str]]:
    values, errors = {}, []
    for field, limit in FIELD_LIMITS.items():
        value = str(raw.get(field) or "").strip()
        values[field] = value
        if len(value) > limit:
            errors.append(f"{FIELD_LABELS[field]} ist zu lang (maximal {limit} Zeichen).")
        elif field in REQUIRED and not value:
            errors.append(f"Bitte „{FIELD_LABELS[field]}“ ausfüllen.")
    for field in ("incident_at", "aid_at"):
        if values[field]:
            try:
                values[field] = local_time(values[field])
            except ValueError as exc:
                errors.append(f"{FIELD_LABELS[field]}: {exc}")
    if values["person_group"] not in ("", "beschaeftigt", "gast", "extern", "ehrenamt", "andere"):
        errors.append("Bitte einen gültigen Personenkreis wählen.")
    return values, errors


def retention_date(created: datetime) -> datetime:
    try:
        return created.replace(year=created.year + 5)
    except ValueError:  # 29. Februar
        return created.replace(year=created.year + 5, day=28)


def qr_token(site_id: int) -> str:
    return URLSafeSerializer(settings.secret_key, salt="takt-first-aid-site-v1").dumps({"site": site_id})


def qr_site(db, token: str) -> FirstAidSite:
    try:
        data = URLSafeSerializer(settings.secret_key, salt="takt-first-aid-site-v1").loads(token)
        sid = data["site"]
        if not isinstance(sid, int):
            raise ValueError()
    except (BadSignature, ValueError, TypeError, KeyError):
        raise HTTPException(404, "Dieser Standort-QR-Code ist ungültig.") from None
    site = db.get(FirstAidSite, sid)
    if site is None or not site.active or not (org := db.get(Organization, site.org_id)) or not org.active:
        raise HTTPException(404, "Standort nicht verfügbar.")
    return site


def sites_for(db, user, role: str) -> list[FirstAidSite]:
    # Adminrecht ist bewusst KEIN Ersatz für medizinische Fallrechte.
    perm = "verbandbuch_capture" if role == "capture" else "verbandbuch_review"
    if not user.active or perm not in user.perms:
        return []
    allowed = select(FirstAidGrant.site_id).where(
        FirstAidGrant.user_id == user.id, FirstAidGrant.role == role,
        (FirstAidGrant.valid_until.is_(None)) | (FirstAidGrant.valid_until > utcnow()),
    )
    return db.scalars(select(FirstAidSite).join(
        Organization, Organization.id == FirstAidSite.org_id
    ).where(
        FirstAidSite.id.in_(allowed), FirstAidSite.active.is_(True),
        Organization.active.is_(True),
    ).order_by(FirstAidSite.title)).all()


def may(db, user, site_id: int, role: str) -> bool:
    return any(site.id == site_id for site in sites_for(db, user, role))


def record_for_review(db, user, case_id: str) -> FirstAidCase:
    record = db.get(FirstAidCase, case_id)
    # 404 auch für unbefugte Zugriffe; weder Fall-Existenz noch Standort verraten.
    if record is None or not may(db, user, record.site_id, "review"):
        raise HTTPException(404, "Eintrag nicht gefunden.")
    return record


def snapshot(db, record: FirstAidCase) -> tuple[dict, list[FirstAidCorrection]]:
    revisions = db.scalars(select(FirstAidCorrection).where(
        FirstAidCorrection.case_id == record.id
    ).order_by(FirstAidCorrection.revision.desc())).all()
    encrypted = revisions[0].payload_enc if revisions else record.payload_enc
    return open_sealed(encrypted), revisions


def log_access(db, user_id: int | None, action: str, case_id: str | None = None) -> None:
    db.add(FirstAidAudit(case_id=case_id, actor_id=user_id, action=action))


def purge_due(now: datetime | None = None) -> int:
    """Fünfjahresfrist pro Eintrag; Legal Holds verhindern automatische Löschung.

    Backup-Löschung, Rechtsprüfung und Wiederherstellungsproben bleiben eigene
    Betriebsfreigaben. Der Schlüssel wird absichtlich nicht benötigt.
    """
    now = now or utcnow()
    with SessionLocal() as db:
        cases = db.scalars(select(FirstAidCase).where(
            FirstAidCase.retention_due_at <= now, FirstAidCase.legal_hold.is_(False)
        ).limit(100)).all()
        for record in cases:
            db.execute(delete(FirstAidCorrection).where(FirstAidCorrection.case_id == record.id))
            db.execute(delete(FirstAidAudit).where(FirstAidAudit.case_id == record.id))
            # HMAC-artiger Nachweis mit getrenntem Namespace, kein Gesundheitsinhalt.
            case_hash = hashlib.sha256(("first-aid-purged:" + settings.secret_key + ":" + record.id).encode()).hexdigest()
            db.add(FirstAidDeletionProof(case_hash=case_hash))
            db.delete(record)
        db.commit()
        if cases:
            log.info("Verbandbuch: %d abgelaufene Einträge gelöscht", len(cases))
        return len(cases)


async def retention_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(purge_due)
        except Exception:
            log.exception("Verbandbuch: Fristenlauf fehlgeschlagen")
        await asyncio.sleep(24 * 60 * 60)
