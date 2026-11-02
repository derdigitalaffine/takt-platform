"""Planner-only JSON transfer with explicit creation of a fresh draft."""
import json
from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from . import seminar_transfer as transfer
from .main import app, current_user, get_db, check_csrf, render, redirect, flash
from .db import User
from .routes_seminars import staff_of, protect
from .routes_seminar_planning import allowed


@app.get('/seminare/{sid:int}/export.json')
def export_json(sid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=staff_of(db,user,sid,True)
    payload=transfer.export_series(db,row)
    body=(json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    if len(body)>2*1024*1024:raise HTTPException(413,'Die Reihenplanung überschreitet die maximale JSON-Dateigröße von 2 MB.')
    return protect(Response(body,media_type='application/json',
        headers={'Content-Disposition':f'attachment; filename="seminarreihe-{sid}.json"','X-Content-Type-Options':'nosniff'}))


@app.get('/seminare/importieren')
def import_page(request:Request,user:User=Depends(current_user)):
    allowed(user)
    return protect(render(request,'seminar_import.html',user))


@app.post('/seminare/importieren',dependencies=[Depends(check_csrf)])
async def import_json(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    allowed(user);data=await request.form();upload=data.get('file')
    if not getattr(upload,'filename',''):raise HTTPException(422,'Bitte eine JSON-Datei auswählen.')
    body=await upload.read(2*1024*1024+1)
    if len(body)>2*1024*1024:raise HTTPException(413,'JSON-Dateien maximal 2 MB.')
    row=transfer.import_series(db,user,transfer.parse_document(body));db.commit()
    flash(request,'Seminarreihe als neuer Entwurf importiert. Bitte Dozenten, Räume und Onlinezugänge prüfen; Unterlagen und Formularverknüpfungen bei Bedarf ergänzen.')
    return redirect(f'/seminare/{row.id}/planen')
