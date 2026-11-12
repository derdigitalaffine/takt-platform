"""Isolated fixtures for the passive-signage browser smoke test."""
from sqlalchemy import select
from app.db import Organization, SessionLocal, User, init_db, set_setting
from app.org_models import OrgMembership
from app.main import app
from app.security import hash_password
from app.signage_models import SignageBuilding, SignageFloor, SignageRoom, SignageWayEdge, SignageWayNode, SignageOffice

init_db()
with SessionLocal() as db:
    set_setting(db, "module_signage", "1")
    db.add(User(name="Signage-Redaktion", email="signage@example.org",
                password_hash=hash_password("browser-test-password"), permissions="signage_manage"))
    root = Organization(name="Verwaltung", kind="verwaltung")
    db.add(root); db.flush()
    team = Organization(name="Service", kind="team", parent_id=root.id)
    finance = Organization(name="Finanzen", kind="team", parent_id=root.id)
    db.add_all([team, finance]); db.flush()
    for name, address, org_id in [
        ("Anja Zander", "anja-sg@example.org", team.id),
        ("Lars Berg", "lars-sg@example.org", team.id),
        ("Tina Bereich", "tina-sg@example.org", finance.id),
    ]:
        worker = User(name=name, email=address, password_hash=hash_password("browser-test-password"))
        db.add(worker); db.flush()
        db.add(OrgMembership(user_id=worker.id, org_id=org_id, is_primary=True))
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
    # Public names are independently consented; private assignments are
    # created in the browser test and must remain absent on the kiosk.
    public_user = db.scalar(select(User).where(User.email == "anja-sg@example.org"))
    db.add(SignageOffice(user_id=public_user.id, room_id=room.id,
                         public=True, is_primary=True))
    db.commit()
