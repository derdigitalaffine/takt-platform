"""Additive organization membership, scoped roles and audit records."""

from sqlalchemy import (
    Boolean,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    Index,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow


class OrgKind(Base):
    __tablename__ = "organization_kinds"
    key: Mapped[str] = mapped_column(String(20), primary_key=True)
    label: Mapped[str] = mapped_column(String(100))


class OrgState(Base):
    __tablename__ = "organization_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class OrgMembership(Base):
    __tablename__ = "organization_memberships"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    counts_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    capacity_percent: Mapped[int] = mapped_column(Integer, default=100)
    __table_args__ = (
        UniqueConstraint("user_id", "org_id"),
        CheckConstraint("capacity_percent >= 0 AND capacity_percent <= 100"),
        Index(
            "uq_organization_primary_user",
            "user_id",
            unique=True,
            sqlite_where=text("is_primary = 1"),
            postgresql_where=text("is_primary = true"),
        ),
    )


class OrgRoleGrant(Base):
    __tablename__ = "organization_role_grants"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(30))
    include_children: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND group_id IS NULL) OR (user_id IS NULL AND group_id IS NOT NULL)"
        ),
        UniqueConstraint("org_id", "user_id", "role"),
        UniqueConstraint("org_id", "group_id", "role"),
    )


class OrgAudit(Base):
    __tablename__ = "organization_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
