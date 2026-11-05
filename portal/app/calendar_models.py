"""Calendar objects and explicit ACLs; business events retain their source records."""

from sqlalchemy import (
    ForeignKey,
    String,
    Text,
    Boolean,
    Integer,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import uuid
from sqlalchemy import DateTime
from .db import Base, utcnow


class Calendar(Base):
    __tablename__ = "calendars"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    visibility: Mapped[str] = mapped_column(String(12), default="private")
    source: Mapped[str] = mapped_column(String(20), default="free")
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    include_children: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        CheckConstraint("visibility IN ('private','internal','public','organization')"),
    )


class CalendarGrant(Base):
    __tablename__ = "calendar_grants"
    id: Mapped[int] = mapped_column(primary_key=True)
    calendar_id: Mapped[int] = mapped_column(
        ForeignKey("calendars.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=True
    )
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint("(user_id IS NULL) != (group_id IS NULL)"),
        UniqueConstraint("calendar_id", "user_id"),
        UniqueConstraint("calendar_id", "group_id"),
    )


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    calendar_id: Mapped[int] = mapped_column(
        ForeignKey("calendars.id", ondelete="CASCADE"), index=True
    )
    uid: Mapped[str] = mapped_column(String(100))
    dav_name: Mapped[str] = mapped_column(
        String(200),
        default=lambda: uuid.uuid4().hex + ".ics",
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ical_data: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(500), default="")
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    include_children: Mapped[bool] = mapped_column(Boolean, default=True)
    starts_at: Mapped[str] = mapped_column(String(40))
    ends_at: Mapped[str] = mapped_column(String(40))
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("calendar_id", "uid"),
        UniqueConstraint("calendar_id", "dav_name"),
    )


class CalendarDevice(Base):
    __tablename__ = "calendar_devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    username: Mapped[str] = mapped_column(String(80), unique=True)
    secret_hash: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(100))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CalendarDeviceScope(Base):
    __tablename__ = "calendar_device_scopes"
    device_id: Mapped[int] = mapped_column(
        ForeignKey("calendar_devices.id", ondelete="CASCADE"), primary_key=True
    )
    calendar_id: Mapped[int] = mapped_column(
        ForeignKey("calendars.id", ondelete="CASCADE"), primary_key=True
    )
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)


class CalendarFeed(Base):
    __tablename__ = "calendar_feeds"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    calendar_id: Mapped[int] = mapped_column(
        ForeignKey("calendars.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class CalendarSyncState(Base):
    """Bounded per-device snapshots, including removed source resources, for WebDAV sync."""

    __tablename__ = "calendar_sync_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("calendar_devices.id", ondelete="CASCADE"), index=True
    )
    calendar_id: Mapped[int] = mapped_column(
        ForeignKey("calendars.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(100), unique=True)
    state_json: Mapped[str] = mapped_column(Text)


class CalendarAudit(Base):
    """Write provenance without copying event descriptions or device credentials."""

    __tablename__ = "calendar_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    calendar_id: Mapped[int] = mapped_column(
        ForeignKey("calendars.id", ondelete="CASCADE"), index=True
    )
    event_uid: Mapped[str] = mapped_column(String(100), default="")
    event_title: Mapped[str] = mapped_column(String(200), default="")
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("calendar_devices.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
