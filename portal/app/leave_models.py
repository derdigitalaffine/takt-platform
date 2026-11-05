"""Additive persistence for organization-scoped leave planning."""

from datetime import datetime
from sqlalchemy import (
    ForeignKey,
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow


class LeavePolicy(Base):
    __tablename__ = "leave_policies"
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    workflow: Mapped[str] = mapped_column(String(16), default="planning")
    version: Mapped[int] = mapped_column(Integer, default=1)
    sync_absence: Mapped[bool] = mapped_column(Boolean, default=False)
    minimum: Mapped[int] = mapped_column(Integer, default=0)
    conflict_mode: Mapped[str] = mapped_column(String(10), default="warning")
    external_url: Mapped[str] = mapped_column(String(1000), default="")
    external_attestation: Mapped[bool] = mapped_column(Boolean, default=True)
    advanced: Mapped[bool] = mapped_column(Boolean, default=False)
    minimum_capacity: Mapped[int] = mapped_column(Integer, default=0)
    internal_account: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_units: Mapped[str] = mapped_column(Text, default="[]")
    notify_only_warnings: Mapped[bool] = mapped_column(Boolean, default=False)
    holiday_state: Mapped[str] = mapped_column(String(8), default="inherit")
    __table_args__ = (
        CheckConstraint("workflow IN ('planning','internal','external')"),
        CheckConstraint("minimum >= 0"),
        CheckConstraint("conflict_mode IN ('warning','block')"),
    )


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    starts_on: Mapped[str] = mapped_column(String(10))
    ends_on: Mapped[str] = mapped_column(String(10))
    start_half: Mapped[str] = mapped_column(String(2), default="am")
    end_half: Mapped[str] = mapped_column(String(2), default="pm")
    status: Mapped[str] = mapped_column(String(16), default="planned", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    approval_path: Mapped[str] = mapped_column(Text, default="[]")
    approval_step: Mapped[int] = mapped_column(Integer, default=0)
    warning_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_workflow: Mapped[str] = mapped_column(String(16), default="")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    # Effective interval is separate: a proposed change never removes the old absence.
    effective_json: Mapped[str] = mapped_column(Text, default="")
    absence_id: Mapped[int | None] = mapped_column(
        ForeignKey("absences.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    attested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    attested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        CheckConstraint("start_half IN ('am','pm') AND end_half IN ('am','pm')"),
        CheckConstraint(
            "status IN ('planned','requested','binding','rejected','cancelled')"
        ),
    )


class LeaveAudit(Base):
    __tablename__ = "leave_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("leave_requests.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(24))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LeaveAbsencePeriod(Base):
    """Half-day boundaries on a leave-owned legacy absence; no delegation grants."""

    __tablename__ = "leave_absence_periods"
    absence_id: Mapped[int] = mapped_column(
        ForeignKey("absences.id", ondelete="CASCADE"), primary_key=True
    )
    start_half: Mapped[str] = mapped_column(String(2), default="am")
    end_half: Mapped[str] = mapped_column(String(2), default="pm")
    __table_args__ = (
        CheckConstraint("start_half IN ('am','pm') AND end_half IN ('am','pm')"),
    )
