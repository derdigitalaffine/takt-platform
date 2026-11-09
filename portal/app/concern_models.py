"""Internal concerns, defects, procurement requests and confidential complaints.

The existing native Task remains the work item. This module owns the request,
category/routing policy and potentially confidential narrative.
"""
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


KINDS = {
    "defect": "Mangel / Störung",
    "supplies": "Büromaterial",
    "furniture": "Büromöbel",
    "complaint": "Beschwerde",
    "idea": "Verbesserungsvorschlag",
    "other": "Sonstiges",
}
ROUTES = {"person": "Feste zuständige Person", "lead": "Vorgesetzte/r der meldenden Person"}


class ConcernCategory(Base):
    __tablename__ = "concern_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(24), default="other")
    description: Mapped[str] = mapped_column(Text, default="")
    routing: Mapped[str] = mapped_column(String(16), default="person")
    responsible_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    responsible = relationship("User", foreign_keys=[responsible_id])


class Concern(Base):
    __tablename__ = "internal_concerns"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("concern_categories.id", ondelete="RESTRICT"), index=True
    )
    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    assignee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text)
    confidential: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    category = relationship("ConcernCategory")
    reporter = relationship("User", foreign_keys=[reporter_id])
    assignee = relationship("User", foreign_keys=[assignee_id])
    task = relationship("Task", foreign_keys=[task_id])

    @property
    def reference(self) -> str:
        year = self.created_at.year if self.created_at else utcnow().year
        return f"AN-{year}-{self.id:05d}"


DEFAULT_CATEGORIES = [
    ("Mangel oder Störung", "defect", "person", False),
    ("Büromaterial bestellen", "supplies", "person", False),
    ("Büromöbel beschaffen", "furniture", "person", False),
    ("Beschwerde", "complaint", "lead", True),
    ("Verbesserungsvorschlag", "idea", "lead", False),
    ("Sonstiges Anliegen", "other", "lead", False),
]


def seed_categories(db):
    from sqlalchemy import select
    if db.scalar(select(ConcernCategory.id).limit(1)) is not None:
        return
    for pos, (name, kind, routing, confidential) in enumerate(DEFAULT_CATEGORIES):
        db.add(ConcernCategory(
            title=name, kind=kind, routing=routing,
            confidential=confidential, position=pos,
        ))
