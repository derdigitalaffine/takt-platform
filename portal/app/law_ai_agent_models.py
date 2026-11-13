"""Versioned, private LLM reviews for uploaded Ortsrecht documents.

A review is *never* a LawText or a planned legal revision; the three
read-only agents can only store evidence-backed, explicitly untrusted hints.
"""
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow


class LawAiAnalysis(Base):
    __tablename__ = "law_ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("law_ai_drafts.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    source_sha256: Mapped[str] = mapped_column(String(64))
    source_chars: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16), default="simple")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    step: Mapped[str] = mapped_column(String(32), default="waiting")
    # The live UI receives only counters and *validated* finding counts.
    # Untrusted/unfinished model JSON is never persisted or sent to browsers.
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    progress_done: Mapped[int] = mapped_column(Integer, default=0)
    stream_characters: Mapped[int] = mapped_column(Integer, default=0)
    stream_chunks: Mapped[int] = mapped_column(Integer, default=0)
    stream_active: Mapped[bool] = mapped_column(Boolean, default=False)
    validated_items: Mapped[int] = mapped_column(Integer, default=0)
    provider_map_json: Mapped[str] = mapped_column(Text, default="{}")
    outline_json: Mapped[str] = mapped_column(Text, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    verification_json: Mapped[str] = mapped_column(Text, default="{}")
    failure: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index(
            "uq_law_ai_analysis_active_draft", "draft_id", unique=True,
            sqlite_where=text("status IN ('queued','running')"),
        ),
    )
