"""Strictly scoped internal administration of RLP paper-based staff council elections.

No online ballot, voter-to-vote link, or cross-module index is stored here.
Database creation is additive; first deployment requires separate legal/security sign-off.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow


class PRElection(Base):
    __tablename__ = "pr_elections"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180))
    body_type: Mapped[str] = mapped_column(String(30), default="personalrat")
    service_name: Mapped[str] = mapped_column(String(180))
    election_day: Mapped[date | None] = mapped_column(Date)
    election_end_day: Mapped[date | None] = mapped_column(Date)
    election_location: Mapped[str] = mapped_column(String(240), default="")
    status: Mapped[str] = mapped_column(String(20), default="preparation")
    legal_source_version: Mapped[str] = mapped_column(String(160), default="")
    legal_gate: Mapped[str] = mapped_column(String(24), default="pending")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PRMandate(Base):
    __tablename__ = "pr_mandates"
    __table_args__ = (UniqueConstraint("election_id", "user_id", name="uq_pr_mandate"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    election_id: Mapped[int] = mapped_column(ForeignKey("pr_elections.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    role: Mapped[str] = mapped_column(String(25))
    appointment_reference: Mapped[str] = mapped_column(String(250), default="")
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PRTask(Base):
    __tablename__ = "pr_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    election_id: Mapped[int] = mapped_column(ForeignKey("pr_elections.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    kind: Mapped[str] = mapped_column(String(32), default="custom")
    due_on: Mapped[date | None] = mapped_column(Date)
    legal_reference: Mapped[str] = mapped_column(String(150), default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    completion_note: Mapped[str] = mapped_column(String(350), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PRDocument(Base):
    """Each saved edit creates a new row; previous document revisions stay immutable."""
    __tablename__ = "pr_documents"
    __table_args__ = (UniqueConstraint("election_id", "document_key", "revision", name="uq_pr_doc_revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    election_id: Mapped[int] = mapped_column(ForeignKey("pr_elections.id", ondelete="RESTRICT"), index=True)
    document_key: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(45))
    title: Mapped[str] = mapped_column(String(180))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    current: Mapped[bool] = mapped_column(Boolean, default=True)
    payload_enc: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(20), default="draft")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    resolution_reference: Mapped[str] = mapped_column(String(250), default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PRAudit(Base):
    """Minimal metadata audit; never contains private form data, votes or elector identifiers."""
    __tablename__ = "pr_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    election_id: Mapped[int] = mapped_column(ForeignKey("pr_elections.id", ondelete="RESTRICT"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(45))
    target: Mapped[str] = mapped_column(String(70), default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
