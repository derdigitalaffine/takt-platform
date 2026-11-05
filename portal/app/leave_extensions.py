"""Dated work patterns, closure staffing and optional internal leave accounts."""

from datetime import datetime
from sqlalchemy import (
    ForeignKey,
    String,
    Integer,
    Float,
    Text,
    CheckConstraint,
    UniqueConstraint,
    Boolean,
    DateTime,
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow


class WorkPattern(Base):
    __tablename__ = "leave_work_patterns"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    starts_on: Mapped[str] = mapped_column(String(10))
    ends_on: Mapped[str] = mapped_column(String(10))
    weekly_json: Mapped[str] = mapped_column(Text)


class Closure(Base):
    __tablename__ = "leave_closures"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    starts_on: Mapped[str] = mapped_column(String(10))
    ends_on: Mapped[str] = mapped_column(String(10))
    emergency_minimum: Mapped[int] = mapped_column(Integer, default=0)
    enrollment: Mapped[str] = mapped_column(String(10), default="lead")
    __table_args__ = (
        CheckConstraint("enrollment IN ('lead','self')"),
        CheckConstraint("emergency_minimum >= 0"),
    )


class WorkDay(Base):
    """Explicit one-day schedule, including a day off or holiday duty."""

    __tablename__ = "leave_work_days"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[str] = mapped_column(String(10))
    am: Mapped[float] = mapped_column(Float)
    pm: Mapped[float] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("person_id", "day"),
        CheckConstraint("am >= 0 AND am <= 1 AND pm >= 0 AND pm <= 1"),
    )


class EmergencyAssignment(Base):
    __tablename__ = "leave_emergency_assignments"
    closure_id: Mapped[int] = mapped_column(
        ForeignKey("leave_closures.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )


class LeaveAccount(Base):
    __tablename__ = "leave_accounts"
    person_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    entitlement: Mapped[float] = mapped_column(Float, default=0)
    carry: Mapped[float] = mapped_column(Float, default=0)
    __table_args__ = (CheckConstraint("entitlement >= 0 AND carry >= 0"),)


class LeaveInbox(Base):
    __tablename__ = "leave_inbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("leave_requests.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(250))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LeavePreference(Base):
    __tablename__ = "leave_preferences"
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    email_mode: Mapped[str] = mapped_column(String(12), default="none")
    __table_args__ = (CheckConstraint("email_mode IN ('none','immediate','daily')"),)
