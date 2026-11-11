"""TAKT Wissen: additive, private-by-default organizational knowledge tables.

Content and history stay in the authoritative portal database; vector search
never acts as a permission boundary. No source is indexed automatically.
"""
from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow


class KnowledgeSpace(Base):
    __tablename__ = "knowledge_spaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    required_approvals: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'review', 'published')"),
        CheckConstraint("scope IN ('inherit', 'restricted')"),
        CheckConstraint("kind IN ('article', 'process', 'checklist', 'faq', 'experience')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_spaces.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="article")
    body_md: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    scope: Mapped[str] = mapped_column(String(20), default="inherit")
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    required_approvals: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    version: Mapped[int] = mapped_column(Integer, default=1)
    authority: Mapped[str] = mapped_column(String(20), default="unconfirmed")
    review_due_on: Mapped[object | None] = mapped_column(Date, nullable=True)
    last_reviewed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class KnowledgeAmendment(Base):
    """A working proposal; published content stays untouched until approval.

    One proposal per article; applied proposals are reused for future changes.
    All proposal versions are retained in KnowledgeAmendmentRevision.
    """
    __tablename__ = "knowledge_amendments"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'review', 'applied')"),
        CheckConstraint("kind IN ('article', 'process', 'checklist', 'faq', 'experience')"),
        UniqueConstraint("article_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True
    )
    base_version: Mapped[int] = mapped_column(Integer)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    version: Mapped[int] = mapped_column(Integer, default=1)
    cycle_start_version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    body_md: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    creator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_editor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class KnowledgeAmendmentRevision(Base):
    """Immutable evidence for every amendment state/content transition."""
    __tablename__ = "knowledge_amendment_revisions"
    __table_args__ = (UniqueConstraint("article_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    base_version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    body_md: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(16), default="edit")
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class KnowledgeGrant(Base):
    __tablename__ = "knowledge_grants"
    __table_args__ = (
        CheckConstraint("resource_kind IN ('space', 'article')"),
        CheckConstraint("principal_kind IN ('user', 'group', 'org')"),
        CheckConstraint("capability IN ('read', 'edit', 'publish', 'manage', 'ai')"),
        CheckConstraint("effect IN ('allow', 'deny')"),
        UniqueConstraint(
            "resource_kind", "resource_id", "principal_kind", "principal_id",
            "capability", name="uq_knowledge_grant",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    resource_kind: Mapped[str] = mapped_column(String(12), index=True)
    resource_id: Mapped[int] = mapped_column(Integer, index=True)
    principal_kind: Mapped[str] = mapped_column(String(12))
    principal_id: Mapped[int] = mapped_column(Integer)
    capability: Mapped[str] = mapped_column(String(12))
    effect: Mapped[str] = mapped_column(String(8))
    include_children: Mapped[bool] = mapped_column(Boolean, default=False)


class KnowledgeRevision(Base):
    """Immutable revision snapshot after each content/state change."""
    __tablename__ = "knowledge_revisions"
    __table_args__ = (UniqueConstraint("article_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    authority: Mapped[str] = mapped_column(String(20), default="unconfirmed")
    review_due_on: Mapped[object | None] = mapped_column(Date, nullable=True)
    editor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class KnowledgeAudit(Base):
    """Metadata-only event trail, never prompts or complete document bodies."""
    __tablename__ = "knowledge_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    space_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_spaces.id", ondelete="SET NULL"), nullable=True
    )
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class KnowledgeApproval(Base):
    """A reviewer decision tied to a particular submitted version."""
    __tablename__ = "knowledge_approvals"
    __table_args__ = (UniqueConstraint("article_id", "amendment", "version", "reviewer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="CASCADE")
    )
    amendment: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(Integer)
    reviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
