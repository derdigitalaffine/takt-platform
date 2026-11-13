"""Isolierte Fachobjekte des digitalen Verbandsbuchs.

Keine Gesundheitsdaten in den globalen FormResponses, Aufgaben, Suchindizes, Audittexten
oder allgemeinen Benutzerprofilen. Nur Fernet-Chiffrate im Fachbereich.
"""
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow


class FirstAidSite(Base):
    __tablename__ = "first_aid_sites"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FirstAidGrant(Base):
    __tablename__ = "first_aid_grants"
    __table_args__ = (UniqueConstraint("site_id", "user_id", "role"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("first_aid_sites.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # capture / review
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FirstAidCase(Base):
    __tablename__ = "first_aid_cases"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    site_id: Mapped[int] = mapped_column(ForeignKey("first_aid_sites.id"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    payload_enc: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    retention_due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    legal_hold_reason_enc: Mapped[str] = mapped_column(Text, default="")


class FirstAidCorrection(Base):
    __tablename__ = "first_aid_corrections"
    __table_args__ = (UniqueConstraint("case_id", "revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("first_aid_cases.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload_enc: Mapped[str] = mapped_column(Text)
    reason_enc: Mapped[str] = mapped_column(Text)
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FirstAidAudit(Base):
    __tablename__ = "first_aid_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    happened_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FirstAidDeletionProof(Base):
    """Nur zufallsbezogener Referenz-Hash, Zeitpunkt und Anzahl; keine Gesundheitsfelder."""
    __tablename__ = "first_aid_deletion_proofs"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_hash: Mapped[str] = mapped_column(String(64), unique=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reason: Mapped[str] = mapped_column(String(30), default="retention")
