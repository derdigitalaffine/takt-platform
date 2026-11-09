"""Opt-in versioned process bindings for internal Anliegen.

Storage-only foundation. Existing form workflows must not be invoked with synthetic
FormResponse objects: their authorization, messaging and payment effects assume a
real application. No executable launch path is registered in this module.
"""
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow


class AnliegenProcessRule(Base):
    __tablename__ = "anliegen_process_rules"
    __table_args__ = (
        UniqueConstraint("category_id", "process_id", "org_id", "revision",
                         name="uq_anliegen_process_rule_revision"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("anliegen_categories.id", ondelete="CASCADE"), index=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("processes.id", ondelete="RESTRICT"), index=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(16), default="draft")  # draft | review | active | retired
    policy_json: Mapped[str] = mapped_column(Text, default="{}")
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AnliegenProcessRun(Base):
    __tablename__ = "anliegen_process_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    anliegen_id: Mapped[int] = mapped_column(
        ForeignKey("anliegen.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("anliegen_process_rules.id", ondelete="RESTRICT"), index=True)
    process_version_id: Mapped[int] = mapped_column(
        ForeignKey("process_versions.id", ondelete="RESTRICT"), index=True)
    launch_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    origin: Mapped[str] = mapped_column(String(16))  # submit | handler | auto
    state: Mapped[str] = mapped_column(String(24), default="requested")
    requested_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # No case description, attachment, or confidential personal data in this link.
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AnliegenProcessAudit(Base):
    __tablename__ = "anliegen_process_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("anliegen_process_runs.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
