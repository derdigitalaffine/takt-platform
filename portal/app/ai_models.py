"""Persistent AI provider, conversation, and curated knowledge records.

No credentials or user prompts are stored in plaintext settings or logs.
Tables are additive and registered during init_db().
"""
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


class AIProvider(Base):
    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(String(500))
    model_id: Mapped[str] = mapped_column(String(200))
    text_key_enc: Mapped[str] = mapped_column(Text, default="")
    image_key_enc: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_private: Mapped[bool] = mapped_column(Boolean, default=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=180)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="Neue Unterhaltung")
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    messages: Mapped[list["AIMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
        order_by="AIMessage.id", passive_deletes=True,
    )


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True,
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    model_id: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    conversation: Mapped[AIConversation] = relationship(back_populates="messages")


class AIKnowledge(Base):
    """Admin-curated internal text; always gated independently of model access."""

    __tablename__ = "ai_knowledge"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AILawSource(Base):
    """Explicit admin opt-in for an existing law, no duplicate law content."""

    __tablename__ = "ai_law_sources"
    law_id: Mapped[int] = mapped_column(
        ForeignKey("law_texts.id", ondelete="CASCADE"), primary_key=True,
    )
