"""Election event planner with opt-in member notifications and private ICS exports."""
from uuid import uuid4
from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import User, Notification, utcnow
from .calendar_models import Calendar, CalendarGrant, CalendarEvent
from .main import app, check_csrf, current_user, get_db, render, redirect, flash
from .prwahl import scope, record, clean
from .prwahl_models import PRMandate
from .prwahl_schedule import PRScheduleEvent, KINDS, local_to_utc, display_local, calendar_file

def _event(db, election_id, event_id):
    event = db.scalar(select(PRScheduleEvent).where(PRScheduleEvent.election_id == election_id, PRScheduleEvent.id == event_id))
    if not event:
        raise HTTPException(404, "Wahltermin nicht gefunden.")
    return event

@app.get("/personalratswahl/{election_id:int}/termine")
def prwahl_schedule(request: Request, election_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role = scope(db, election_id, user)
    events = db.scalars(select(PRScheduleEvent).where(PRScheduleEvent.election_id == election.id).order_by(PRScheduleEvent.starts_at)).all()
    return render(request, "prwahl_schedule.html", user, election=election, role=role, events=events,
                  kinds=KINDS, display_local=display_local, can_edit=role in {"coordinator","chair","member","clerk"})

@app.post("/personalratswahl/{election_id:int}/termine/neu", dependencies=[Depends(check_csrf)])
def prwahl_schedule_add(request: Request, election_id: int, kind: str = Form(...), title: str = Form(...),
                       starts_at: str = Form(...), ends_at: str = Form(...), location: str = Form(""),
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role = scope(db, election_id, user, "edit")
    if kind not in KINDS:
        raise HTTPException(422, "Unbekannte Terminart.")
    start, end = local_to_utc(starts_at), local_to_utc(ends_at)
    if end <= start or (end-start).total_seconds() > 14*86400:
        raise HTTPException(422, "Das Ende muss nach dem Beginn liegen; maximal 14 Tage.")
    title, location = clean(title,180), clean(location,240)
    if not title:
        raise HTTPException(422, "Bitte eine Terminbezeichnung angeben.")
    event = PRScheduleEvent(election_id=election.id, uid=str(uuid4())+"@takt-prwahl",
                            kind=kind, title=title, location=location, starts_at=start, ends_at=end, created_by=user.id)
    db.add(event)
    db.flush()
    record(db,user.id,election.id,"schedule_created",f"event:{event.id}")
    db.commit()
    flash(request,"Termin gespeichert. Einladungen werden aus Datenschutzgründen nur nach ausdrücklicher Freigabe versendet.")
    return redirect(f"/personalratswahl/{election.id}/termine")

@app.post("/personalratswahl/{election_id:int}/termine/{event_id:int}/absagen", dependencies=[Depends(check_csrf)])
def prwahl_schedule_cancel(request: Request, election_id: int, event_id: int,
                           user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role = scope(db,election_id,user,"manage")
    event = _event(db,election.id,event_id)
    if event.status == "cancelled":
        raise HTTPException(409,"Termin bereits abgesagt.")
    event.status, event.sequence, event.updated_at = "cancelled", event.sequence+1, utcnow()
    record(db,user.id,election.id,"schedule_cancelled",f"event:{event.id}")
    db.commit()
    flash(request,"Termin abgesagt. Bereits exportierte Kalenderdateien werden nicht automatisch aktualisiert.")
    return redirect(f"/personalratswahl/{election.id}/termine")

@app.get("/personalratswahl/{election_id:int}/termine/{event_id:int}.ics")
def prwahl_schedule_ics(election_id: int, event_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role = scope(db,election_id,user)
    event = _event(db,election.id,event_id)
    return Response(calendar_file(event), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition":f'attachment; filename="prwahl-termin-{event.id}.ics"',
                             "Cache-Control":"private, no-store", "X-Content-Type-Options":"nosniff"})

@app.post("/personalratswahl/{election_id:int}/termine/{event_id:int}/benachrichtigen", dependencies=[Depends(check_csrf)])
def prwahl_schedule_notify(request: Request, election_id: int, event_id: int,
                           user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role = scope(db,election_id,user,"board")
    event = _event(db,election.id,event_id)
    if event.status != "planned":
        raise HTTPException(409,"Abgesagte Termine dürfen nicht eingeladen werden.")
    members = db.execute(select(User).join(PRMandate,PRMandate.user_id==User.id).where(
        PRMandate.election_id==election.id,PRMandate.role.in_(["chair","member","clerk"]),
        User.active.is_(True))).scalars().all()
    already = db.scalar(select(Notification.id).where(Notification.kind == "prwahl",
        Notification.subject == f"TAKT · Wahltermin #{event.id} · Einladung").limit(1))
    if already:
        raise HTTPException(409, "Für diesen Termin wurden bereits Benachrichtigungen vorgemerkt. Bitte Versandstatus in der Benachrichtigungsverwaltung prüfen.")
    queued = 0
    for member in members:
        address = getattr(member,"email",None)
        if not address:
            continue
        # No nomination, roll or count details in e-mail: metadata only.
        body = ("Du hast einen Termin im geschützten Wahl-Arbeitsbereich.\n"
                f"Termin: {event.title}\nBeginn: {display_local(event.starts_at)} (Europe/Berlin)\n"
                f"Ende: {display_local(event.ends_at)} (Europe/Berlin)\n"
                "Bitte melde dich im TAKT-Portal an, um die Einzelheiten zu prüfen.\n"
                "Eine Kalendereinladung ersetzt keine rechtlich vorgeschriebene Zustellung oder Bekanntmachung.")
        db.add(Notification(kind="prwahl",to_addr=address,subject=f"TAKT · Wahltermin #{event.id} · Einladung",
                            body=body,status="pending"))
        queued += 1
    if not queued:
        raise HTTPException(409,"Kein aktives Wahlvorstandsmitglied mit E-Mail-Adresse vorhanden.")
    record(db,user.id,election.id,"schedule_notification",f"event:{event.id}:recipients:{queued}")
    db.commit()
    flash(request,f"{queued} E-Mail-Benachrichtigungen zur Zustellung vorgemerkt. Die Versandwarteschlange bestimmt den tatsächlichen Zustellstatus.")
    return redirect(f"/personalratswahl/{election.id}/termine")

@app.post("/personalratswahl/{election_id:int}/termine/{event_id:int}/kalender", dependencies=[Depends(check_csrf)])
def prwahl_schedule_calendar(request: Request, election_id: int, event_id: int,
                            user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Explicitly publish a minimal event into a private, member-ACL calendar."""
    election, role = scope(db, election_id, user, "board")
    event = _event(db, election.id, event_id)
    if event.status != "planned":
        raise HTTPException(409, "Abgesagte Termine können nicht übernommen werden.")
    calendar = db.scalar(select(Calendar).where(Calendar.owner_id == user.id,
        Calendar.source == "prwahl", Calendar.visibility == "private",
        Calendar.org_id == election.org_id, Calendar.title == f"Wahlteam · {election.id}"))
    if calendar is None:
        calendar = Calendar(owner_id=user.id, title=f"Wahlteam · {election.id}",
                            visibility="private", source="prwahl", org_id=election.org_id,
                            include_children=False)
        db.add(calendar)
        db.flush()
    members = db.scalars(select(PRMandate).where(PRMandate.election_id == election.id,
        PRMandate.role.in_(["chair", "member", "clerk"]))).all()
    for mandate in members:
        if mandate.user_id != user.id and not db.scalar(select(CalendarGrant.id).where(
            CalendarGrant.calendar_id == calendar.id, CalendarGrant.user_id == mandate.user_id)):
            db.add(CalendarGrant(calendar_id=calendar.id, user_id=mandate.user_id, can_write=False))
    existing = db.scalar(select(CalendarEvent).where(CalendarEvent.calendar_id == calendar.id,
                                                      CalendarEvent.uid == event.uid))
    if existing:
        raise HTTPException(409, "Der Termin ist bereits im Wahlteam-Kalender vorhanden.")
    db.add(CalendarEvent(calendar_id=calendar.id, uid=event.uid,
        title=event.title, location=event.location, description="Geschützter Wahlteam-Termin.",
        org_id=None, include_children=False, starts_at=event.starts_at.isoformat()+"Z",
        ends_at=event.ends_at.isoformat()+"Z", ical_data=calendar_file(event)))
    record(db, user.id, election.id, "calendar_exported", f"event:{event.id}")
    db.commit()
    flash(request, "Termin im privaten TAKT-Wahlteam-Kalender angelegt. Nur ausdrücklich berechtigte Mitglieder haben Zugriff.")
    return redirect(f"/personalratswahl/{election.id}/termine")
