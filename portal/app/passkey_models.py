"""Persistent, server-verifiable WebAuthn credentials and single-use ceremonies."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow


class PasskeyCredential(Base):
    __tablename__ = "passkey_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(100), default="Passkey")
    transports_json: Mapped[str] = mapped_column(Text, default="[]")
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PasskeyCeremony(Base):
    __tablename__ = "passkey_ceremonies"

    id: Mapped[str] = mapped_column(String(90), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(16))
    challenge: Mapped[str] = mapped_column(String(128))
    rp_id: Mapped[str] = mapped_column(String(253))
    origin: Mapped[str] = mapped_column(String(350))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    session_sid_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
