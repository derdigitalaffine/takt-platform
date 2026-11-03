"""Full module access for navigation visual contracts; isolated temporary database."""
from seminar_ui_app import app
from app import main
from app.db import SessionLocal, User, Resource, set_setting
with SessionLocal() as db:
    for _, setting, _ in main.MODULES.values():
        set_setting(db, setting, '1')
    user=db.query(User).filter_by(email='planner@example.org').one()
    user.is_admin=True
    db.add(Resource(name="Navigationsraum",slug="navigation-room",owner_id=user.id,manager_user_id=user.id))
    db.commit()
main._module_cache['at']=0
