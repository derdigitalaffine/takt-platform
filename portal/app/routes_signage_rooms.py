"""Fast room-centric Signage directory and self-service workplace management."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import signage_offices, person_picker
from .db import User
from .main import app, check_csrf, current_user, flash, get_db, redirect, render
from .routes_signage import _enabled, _int, manage_user
from .signage_models import (
    SignageBuilding, SignageFloor, SignageRoom, SignageOffice
)


@app.get("/signage/rooms")
def signage_room_directory(request: Request, user: User = Depends(manage_user),
                           db: Session = Depends(get_db)):
    _enabled()
    b_id = _int(request.query_params.get("building"))
    query = str(request.query_params.get("q") or "").strip()[:80]
    page = max(1, min(10000, _int(request.query_params.get("page")) or 1))
    room_q = select(SignageRoom, SignageFloor, SignageBuilding).join(
        SignageFloor, SignageRoom.floor_id == SignageFloor.id
    ).join(SignageBuilding, SignageFloor.building_id == SignageBuilding.id)
    if b_id:
        room_q = room_q.where(SignageBuilding.id == b_id)
    if query:
        pattern = "%" + query.replace("%", r"\%").replace("_", r"\_") + "%"
        room_q = room_q.where(
            SignageRoom.name.ilike(pattern, escape="\\")
            | SignageRoom.number.ilike(pattern, escape="\\")
            | SignageBuilding.name.ilike(pattern, escape="\\"))
    count = db.scalar(select(func.count()).select_from(room_q.subquery())) or 0
    rooms = db.execute(room_q.order_by(
        SignageBuilding.name, SignageFloor.level,
        SignageRoom.number, SignageRoom.id).limit(150).offset((page-1)*150)).all()
    chosen_id = _int(request.query_params.get("room"))
    if chosen_id:
        chosen = db.execute(select(SignageRoom, SignageFloor, SignageBuilding).join(
            SignageFloor, SignageRoom.floor_id == SignageFloor.id).join(
            SignageBuilding, SignageFloor.building_id == SignageBuilding.id
        ).where(SignageRoom.id == chosen_id)).first()
        if not chosen:
            raise HTTPException(404)
    else:
        chosen = rooms[0] if rooms else None
    assignments = []
    if chosen:
        assignments = db.execute(select(SignageOffice, User).join(
            User, SignageOffice.user_id == User.id).where(
            SignageOffice.room_id == chosen[0].id).order_by(User.name)).all()
        assignments.sort(key=lambda pair: person_picker.surname_key(pair[1]))
    staff = person_picker.sort_people(list(db.scalars(select(User).where(
        User.active.is_(True)))))
    buildings = list(db.scalars(select(SignageBuilding).order_by(SignageBuilding.name)))
    return render(request, "signage_rooms.html", user, rooms=rooms, selected=chosen,
                  assigned=assignments, staff=staff, buildings=buildings,
                  room_count=count, page=page, pages=max(1, (count+149)//150),
                  selected_building=b_id, q=query)


@app.post("/signage/rooms/{room_id:int}/people", dependencies=[Depends(check_csrf)])
async def signage_room_people(room_id: int, request: Request,
                              user: User = Depends(manage_user),
                              db: Session = Depends(get_db)):
    _enabled()
    signage_offices.active_room(db, room_id)
    form = await request.form()
    action = str(form.get("action") or "add")
    if action == "add":
        raw = form.getlist("user_ids")
        if not raw or len(raw) > 200:
            raise HTTPException(422, "Bitte 1 bis 200 Personen auswählen.")
        try:
            ids = {int(value) for value in raw}
        except (ValueError, TypeError):
            raise HTTPException(422, "Ungültige Personenauswahl.")
        if not ids or any(uid < 1 or not (person := db.get(User, uid)) or not person.active
                          for uid in ids):
            raise HTTPException(422, "Mindestens eine Person ist nicht verfügbar.")
        for uid in ids:
            signage_offices.assign(
                db, user_id=uid, room_id=room_id,
                make_primary=form.get("primary") == "1")
        flash(request, f"{len(ids)} Person(en) zugeordnet. Öffentliche Anzeige erfordert deren Einwilligung.")
    elif action in ("remove", "primary"):
        uid = _int(form.get("user_id"))
        office = db.scalar(select(SignageOffice).where(
            SignageOffice.room_id == room_id, SignageOffice.user_id == uid))
        if not office:
            raise HTTPException(404)
        if action == "remove":
            signage_offices.remove(db, office)
            flash(request, "Bürozuordnung entfernt.")
        else:
            signage_offices.assign(db, user_id=uid, room_id=room_id, make_primary=True)
            flash(request, "Hauptbüro aktualisiert.")
    else:
        raise HTTPException(422, "Unbekannte Aktion.")
    db.commit()
    return redirect(f"/signage/rooms?room={room_id}")


@app.post("/profile/signage/office", dependencies=[Depends(check_csrf)])
async def signage_profile_assign_room(request: Request,
                                      user: User = Depends(current_user),
                                      db: Session = Depends(get_db)):
    """Users may assign their own physical office, never another person's."""
    _enabled()
    form = await request.form()
    room_id = _int(form.get("room_id"))
    signage_offices.permitted_for_self(db, user, room_id)
    signage_offices.assign(db, user_id=user.id, room_id=room_id,
                           make_primary=form.get("primary") == "1")
    db.commit()
    flash(request, "Dein Büro wurde hinterlegt – zunächst nur intern sichtbar.")
    return redirect("/profile#signage-offices")


@app.post("/profile/signage/office/{office_id:int}/remove",
          dependencies=[Depends(check_csrf)])
async def signage_profile_remove_room(office_id: int, request: Request,
                                      user: User = Depends(current_user),
                                      db: Session = Depends(get_db)):
    _enabled()
    office = db.get(SignageOffice, office_id)
    if not office or office.user_id != user.id:
        raise HTTPException(404)
    signage_offices.remove(db, office)
    db.commit()
    flash(request, "Deine Bürozuordnung wurde entfernt; die öffentliche Freigabe ist damit widerrufen.")
    return redirect("/profile#signage-offices")
