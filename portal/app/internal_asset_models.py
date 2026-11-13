"""Interner Gerätepool – eigene Fachobjekte, keine öffentlichen Preise oder Verkaufsbuchungen."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base, utcnow

class InternalAsset(Base):
    __tablename__ = "internal_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="Sonstiges")
    location: Mapped[str] = mapped_column(String(200), default="")
    inventory_code: Mapped[str] = mapped_column(String(80), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reservations: Mapped[list["InternalAssetReservation"]] = relationship(back_populates="asset")
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_internal_asset_quantity"),)

class InternalAssetReservation(Base):
    __tablename__ = "internal_asset_reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("internal_assets.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    purpose: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default="reserved")
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    asset: Mapped[InternalAsset] = relationship(back_populates="reservations")
    user = relationship("User")
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_internal_reservation_quantity"), CheckConstraint("ends_at > starts_at", name="ck_internal_reservation_range"))
