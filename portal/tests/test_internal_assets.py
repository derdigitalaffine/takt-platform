"""Kernregeln des internen Gerätepools."""
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base
from app.internal_asset_models import InternalAsset, InternalAssetReservation
from app.routes_internal_assets import _reserved, _date


def test_stock_overlap_and_issued_blocks_after_end():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = InternalAsset(name="Beamer", quantity=2, created_by_id=1)
        db.add(a)
        db.flush()
        now = datetime(2030, 1, 1, 10)
        db.add(InternalAssetReservation(asset_id=a.id, user_id=1, starts_at=now,
                                        ends_at=now + timedelta(hours=2), quantity=1, status="reserved"))
        db.flush()
        assert _reserved(db, a.id, now + timedelta(hours=1), now + timedelta(hours=3)) == 1
        assert _reserved(db, a.id, now + timedelta(hours=3), now + timedelta(hours=4)) == 0
        b = db.scalar(__import__("sqlalchemy").select(InternalAssetReservation))
        b.status = "issued"
        db.flush()
        assert _reserved(db, a.id, now + timedelta(days=5), now + timedelta(days=6)) == 1
        b.status = "returned"
        db.flush()
        assert _reserved(db, a.id, now + timedelta(days=5), now + timedelta(days=6)) == 0


def test_local_time_is_converted_to_utc():
    assert _date("2030-01-01T10:00") != datetime(2030, 1, 1, 10)
