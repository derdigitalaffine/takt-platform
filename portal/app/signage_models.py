"""Digital Signage: additive location, screen and credential models.

Rooms and offices reference the canonical PortalLocation, Organization, User,
Resource and Calendar models rather than copying those source records.
"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow


class SignageBuilding(Base):
    __tablename__ = "signage_buildings"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("portal_locations.id", ondelete="SET NULL"), nullable=True, index=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    code: Mapped[str] = mapped_column(String(40), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SignageFloor(Base):
    __tablename__ = "signage_floors"
    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("signage_buildings.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    level: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("building_id", "level"),)


class SignageRoom(Base):
    __tablename__ = "signage_rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    floor_id: Mapped[int] = mapped_column(ForeignKey("signage_floors.id", ondelete="CASCADE"), index=True)
    number: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(180), default="")
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True, index=True)
    calendar_id: Mapped[int | None] = mapped_column(ForeignKey("calendars.id", ondelete="SET NULL"), nullable=True)
    accessible: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("floor_id", "number"),)


class SignageOffice(Base):
    """Opt-in public staff directory; never expose encrypted voluntary profiles."""
    __tablename__ = "signage_offices"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("signage_rooms.id", ondelete="CASCADE"), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("user_id", "room_id"),)


class SignageScreen(Base):
    __tablename__ = "signage_screens"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180))
    kind: Mapped[str] = mapped_column(String(24), default="agenda")
    visibility: Mapped[str] = mapped_column(String(16), default="private")
    data_level: Mapped[str] = mapped_column(String(16), default="busy")
    room_id: Mapped[int | None] = mapped_column(ForeignKey("signage_rooms.id", ondelete="SET NULL"), nullable=True)
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    direction: Mapped[str] = mapped_column(String(100), default="")
    subtitle: Mapped[str] = mapped_column(String(250), default="")
    layout_json: Mapped[str] = mapped_column(Text, default='["clock","status","agenda"]')
    theme_json: Mapped[str] = mapped_column(Text, default='{"background":"#111e30","foreground":"#f8fafc","accent":"#42d4ad"}')
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SignageLink(Base):
    __tablename__ = "signage_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    screen_id: Mapped[int] = mapped_column(ForeignKey("signage_screens.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SignageDevice(Base):
    __tablename__ = "signage_devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    screen_id: Mapped[int] = mapped_column(ForeignKey("signage_screens.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    secret_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SignageRevision(Base):
    """Immutable design history; publication/credentials are deliberately excluded."""
    __tablename__ = "signage_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    screen_id: Mapped[int] = mapped_column(ForeignKey("signage_screens.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("screen_id", "version"),)


class SignageWayNode(Base):
    """Indoor wayfinding node; coordinates are normalized for future SVG overlays."""
    __tablename__ = "signage_way_nodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    floor_id: Mapped[int] = mapped_column(ForeignKey("signage_floors.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("signage_rooms.id", ondelete="SET NULL"), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="corridor")
    x_pct: Mapped[float] = mapped_column(Float, default=50.0)
    y_pct: Mapped[float] = mapped_column(Float, default=50.0)
    accessible: Mapped[bool] = mapped_column(Boolean, default=True)


class SignageWayEdge(Base):
    """Bidirectional or directed connection with accessibility semantics."""
    __tablename__ = "signage_way_edges"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("signage_way_nodes.id", ondelete="CASCADE"), index=True)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("signage_way_nodes.id", ondelete="CASCADE"), index=True)
    distance_m: Mapped[int] = mapped_column(Integer, default=5)
    accessible: Mapped[bool] = mapped_column(Boolean, default=True)
    bidirectional: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("from_node_id", "to_node_id"),)


class SignageDisplayAnchor(Base):
    """Starting position of a physical wayfinding display."""
    __tablename__ = "signage_display_anchors"
    screen_id: Mapped[int] = mapped_column(ForeignKey("signage_screens.id", ondelete="CASCADE"), primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("signage_way_nodes.id", ondelete="CASCADE"), index=True)


class SignagePassiveConfig(Base):
    __tablename__ = "signage_passive_configs"
    screen_id: Mapped[int] = mapped_column(ForeignKey("signage_screens.id", ondelete="CASCADE"), primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("signage_buildings.id", ondelete="CASCADE"), index=True)
    floor_id: Mapped[int | None] = mapped_column(ForeignKey("signage_floors.id", ondelete="SET NULL"))
    facing: Mapped[str] = mapped_column(String(8), default="")
    radius_m: Mapped[int] = mapped_column(Integer, default=25)
    barrier_free: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_arrow: Mapped[str] = mapped_column(String(12), default="")
    manual_label: Mapped[str] = mapped_column(String(120), default="")
    manual_only: Mapped[bool] = mapped_column(Boolean, default=False)


class SignagePublicDestination(Base):
    """Explicitly publish a room number and display label on passive signs."""
    __tablename__ = "signage_public_destinations"
    room_id: Mapped[int] = mapped_column(ForeignKey("signage_rooms.id", ondelete="CASCADE"), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), default="")


class SignageDestinationOverride(Base):
    __tablename__ = "signage_destination_overrides"
    screen_id: Mapped[int] = mapped_column(ForeignKey("signage_screens.id", ondelete="CASCADE"), primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("signage_rooms.id", ondelete="CASCADE"), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    arrow: Mapped[str] = mapped_column(String(12), default="")
    rank: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)


class SignageSpecial(Base):
    """Display-specific publication with its own copy and approval provenance."""
    __tablename__ = "signage_specials"
    id: Mapped[int] = mapped_column(primary_key=True)
    screen_id: Mapped[int] = mapped_column(ForeignKey("signage_screens.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("signage_rooms.id", ondelete="CASCADE"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("calendar_events.id", ondelete="CASCADE"))
    preset: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(String(250), default="")
    priority: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(10))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    published: Mapped[bool] = mapped_column(Boolean, default=False)


class SignageCampaign(Base):
    """Approved special signage event with a building-wide or targeted scope.

    No raw calendar titles or user profile fields are copied to public output.
    """
    __tablename__ = "signage_campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("signage_buildings.id", ondelete="CASCADE"), index=True)
    floor_id: Mapped[int | None] = mapped_column(ForeignKey("signage_floors.id", ondelete="SET NULL"), nullable=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("signage_rooms.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("calendar_events.id", ondelete="SET NULL"), nullable=True)
    scope: Mapped[str] = mapped_column(String(16), default="building")
    preset: Mapped[str] = mapped_column(String(16), default="event")
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(String(250), default="")
    priority: Mapped[int] = mapped_column(Integer, default=30)
    mode: Mapped[str] = mapped_column(String(10), default="overlay")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lead_minutes: Mapped[int] = mapped_column(Integer, default=30)
    tail_minutes: Mapped[int] = mapped_column(Integer, default=0)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SignageCampaignScreen(Base):
    """Explicit include/exclude override; normal campaigns discover screens live."""
    __tablename__ = "signage_campaign_screens"
    campaign_id: Mapped[int] = mapped_column(ForeignKey("signage_campaigns.id", ondelete="CASCADE"), primary_key=True)
    screen_id: Mapped[int] = mapped_column(ForeignKey("signage_screens.id", ondelete="CASCADE"), primary_key=True)
    included: Mapped[bool] = mapped_column(Boolean, default=True)
