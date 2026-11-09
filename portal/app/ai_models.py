"""Persistent AI provider, conversation, and curated knowledge records.

No credentials or user prompts are stored in plaintext settings or logs.
Tables are additive and registered during init_db().
"""
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
    stream_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
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


class AIKnowledgeVector(Base):
    """Local, optional vector cache for explicitly approved AIKnowledge sources.

    Source ACLs and content fingerprints are checked against live objects
    before results are returned; cache entries alone grant no access.
    """
    __tablename__ = "ai_knowledge_vectors"

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_id: Mapped[int] = mapped_column(
        ForeignKey("ai_knowledge.id", ondelete="CASCADE"), index=True)
    chunk_no: Mapped[int] = mapped_column(Integer)
    model_id: Mapped[str] = mapped_column(String(200))
    source_hash: Mapped[str] = mapped_column(String(64))
    chunk_text: Mapped[str] = mapped_column(Text)
    vector_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class AIIndexJob(Base):
    """Durable indexing work; each curated document has at most one queued job.

    A lease makes interrupted jobs retryable after a worker restart. No source
    contents, prompts, or provider response text are persisted here.
    """
    __tablename__ = "ai_index_jobs"
    __table_args__ = (UniqueConstraint("knowledge_id", name="uq_ai_index_doc"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_id: Mapped[int] = mapped_column(
        ForeignKey("ai_knowledge.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[str] = mapped_column(String(200), default="")
    desired_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[object] = mapped_column(DateTime, nullable=True)
    lease_until: Mapped[object] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class AIDmsSource(Base):
    """Explicit AI-use approval for a DMS manual record; no source text copied.

    Original DMS area/user ACLs remain authoritative at retrieval time.
    """
    __tablename__ = "ai_dms_sources"
    record_id: Mapped[int] = mapped_column(
        ForeignKey("dms_records.id", ondelete="CASCADE"), primary_key=True)


class AgentAudit(Base):
    """Successful confirmed operations; no prompts, answers or record contents."""
    __tablename__ = "agent_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    tool: Mapped[str] = mapped_column(String(40))
    target_url: Mapped[str] = mapped_column(String(200))
    target_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
