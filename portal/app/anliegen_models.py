"""Internal request intake, categories and audit; separate from native task ownership."""
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base, utcnow


class AnliegenCategory(Base):
    __tablename__ = "anliegen_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(255), default="")
    icon: Mapped[str] = mapped_column(String(48), default="fa-inbox")
    confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    routing: Mapped[str] = mapped_column(String(20), default="person")  # person | lead
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    assignee = relationship("User", foreign_keys=[assignee_id])


class Anliegen(Base):
    __tablename__ = "anliegen"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("anliegen_categories.id"), index=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    # Confidential payload is encrypted; title/description store neutral text only.
    title_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="new")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    category = relationship("AnliegenCategory")
    reporter = relationship("User", foreign_keys=[reporter_id])
    assignee = relationship("User", foreign_keys=[assignee_id])
    task = relationship("Task", foreign_keys=[task_id])

    @property
    def display_title(self) -> str:
        if self.confidential and self.title_enc:
            from .security import decrypt
            return decrypt(self.title_enc) or "Vertrauliches Anliegen"
        return self.title

    @property
    def display_description(self) -> str:
        if self.confidential and self.description_enc:
            from .security import decrypt
            return decrypt(self.description_enc)
        return self.description


class AnliegenEvent(Base):
    __tablename__ = "anliegen_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    anliegen_id: Mapped[int] = mapped_column(ForeignKey("anliegen.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
