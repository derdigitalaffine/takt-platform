"""Internes Anlagen-, Material- und Leihwesen. Getrennt vom öffentlichen Mietkatalog."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base, utcnow


class InternalStorageLocation(Base):
    __tablename__ = "internal_storage_locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    building: Mapped[str] = mapped_column(String(160), default="")
    detail: Mapped[str] = mapped_column(String(160), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InternalAsset(Base):
    __tablename__ = "internal_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="Sonstiges")
    location: Mapped[str] = mapped_column(String(200), default="")  # legacy/fallback free text
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("internal_storage_locations.id", ondelete="SET NULL"), nullable=True, index=True)
    storage_location: Mapped[InternalStorageLocation | None] = relationship()
    inventory_code: Mapped[str] = mapped_column(String(80), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    vehicle_plate: Mapped[str] = mapped_column(String(30), default="")
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
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_internal_reservation_quantity"),
        CheckConstraint("ends_at > starts_at", name="ck_internal_reservation_range"),
    )


class InternalAssetMaintenance(Base):
    __tablename__ = "internal_asset_maintenance"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("internal_assets.id", ondelete="RESTRICT"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_internal_maintenance_quantity"),
        CheckConstraint("ends_at > starts_at", name="ck_internal_maintenance_range"),
    )


class InternalAssetEvent(Base):
    """Unveränderliches Journal für organisatorisch relevante Bestandsaktionen."""
    __tablename__ = "internal_asset_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("internal_assets.id", ondelete="RESTRICT"), index=True)
    reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("internal_asset_reservations.id", ondelete="SET NULL"), nullable=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
