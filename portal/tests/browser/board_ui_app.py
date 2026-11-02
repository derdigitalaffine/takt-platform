"""Isolated Kanban browser fixtures, without background workers or outbound mail."""
import os
os.environ.update(PORTAL_BASE_URL='http://127.0.0.1:8767',PORTAL_SECRET_KEY='board-test-secret-at-least-32-characters',JWT_APP_SECRET='board-test-jwt-at-least-32-characters')
from app import main
from app.db import init_db,SessionLocal,User,set_setting
from app.security import hash_password
init_db()
with SessionLocal() as db:
    set_setting(db,'module_tasks','1')
    for name,email,permission in [('Mara Planung','owner@example.org','tasks'),('Alex Mitarbeit','editor@example.org',''),('Sam Lesen','reader@example.org','')]:
        db.add(User(name=name,email=email,password_hash=hash_password('board-browser-password'),permissions=permission))
    db.commit()
app=main.app
