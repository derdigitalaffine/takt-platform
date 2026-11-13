"""Private, unpublished, human-reviewed Ortsrecht import work items.

Never link this table to the scheduled-publication worker. OCR and AI processes
write only proposals here; only a separate authenticated editor action may
create an unpublished LawText. The immutable uploaded original stays separate.
"""
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow


class LawAiDraft(Base):
    __tablename__ = "law_ai_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    original_storage_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    original_sha256: Mapped[str] = mapped_column(String(64))
    original_size: Mapped[int] = mapped_column(Integer)
    original_mime: Mapped[str] = mapped_column(String(100))
    # Draft text is an untrusted machine extraction, never an authoritative text.
    proposed_md: Mapped[str] = mapped_column(Text, default="")
    proposed_title: Mapped[str] = mapped_column(String(400), default="")
    status: Mapped[str] = mapped_column(String(24), default="staged")
    accepted_law_id: Mapped[int | None] = mapped_column(
        ForeignKey("law_texts.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    accepted_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
