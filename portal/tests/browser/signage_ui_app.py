"""Isolated fixtures for the passive-signage browser smoke test."""
from app.db import SessionLocal, User, init_db, set_setting
from app.main import app
from app.security import hash_password
from app.signage_models import SignageBuilding, SignageFloor, SignageRoom, SignageWayEdge, SignageWayNode

init_db()
with SessionLocal() as db:
    set_setting(db, "module_signage", "1")
    db.add(User(name="Signage-Redaktion", email="signage@example.org",
                password_hash=hash_password("browser-test-password"), permissions="signage_manage"))
    building = SignageBuilding(name="Rathaus")
    db.add(building)
    db.flush()
    floor = SignageFloor(building_id=building.id, name="Erdgeschoss")
    db.add(floor)
    db.flush()
    room = SignageRoom(floor_id=floor.id, number="01", name="Bürgerbüro")
    db.add(room)
    db.flush()
    start = SignageWayNode(floor_id=floor.id, label="Eingang", x_pct=20, y_pct=50)
    destination = SignageWayNode(floor_id=floor.id, room_id=room.id, label="Zimmer 01", x_pct=60, y_pct=50)
    db.add_all([start, destination])
    db.flush()
    db.add(SignageWayEdge(from_node_id=start.id, to_node_id=destination.id))
    db.commit()
