"""Scoped operational pages: settings, templates, communications and attendance."""
import base64
import io
import json
from datetime import timedelta
from email.utils import getaddresses
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
import segno
from . import seminar_operations as ops, seminars as sm, seminar_series as series, seminar_learning as learning, seminar_hybrid as hybrid, notify
from .db import (Seminar, SeminarSession, SeminarEnrollment, SeminarFavorite, SeminarTemplate,
                 SeminarMailDraft, SeminarLecturerAccess, SeminarMaterial, SeminarAttendance,
                 User, Group, get_settings, utcnow)
from .main import app, current_user, get_db, check_csrf, render, redirect, flash, rate_limit
from .routes_seminars import staff_of, row_of, can_read, protect


def qr_data(link):
    stream=io.BytesIO();segno.make(link, micro=False).save(stream,kind='svg',scale=5)
    return 'data:image/svg+xml;base64,'+base64.b64encode(stream.getvalue()).decode()


@app.get('/seminare/{sid:int}/organisation')
def organisation(request:Request,sid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=staff_of(db,user,sid,True)
    return protect(render(request,'seminar_operations.html',user,row=row,options=ops.options(row),terms=sm.sessions(db,row,False),
        guest_terms=[(t,g) for t in sm.sessions(db,row,False) for g in json.loads(t.guests_json)]))


@app.post('/seminare/{sid:int}/organisation',dependencies=[Depends(check_csrf)])
async def organisation_save(request:Request,sid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=staff_of(db,user,sid,True);data=await request.form();sm.lock(db,row,sm.integer(data.get('revision')))
    config={key:data.get(key)=='1' for key in ('standing','self_checkin','guest_materials','guest_publish')}
    config['teacher_days']=sm.integer(data.get('teacher_days',30),1,365)
    config['mail_subject']=str(data.get('mail_subject',ops.options(row)['mail_subject'])).strip()
    config['mail_body']=str(data.get('mail_body',ops.options(row)['mail_body'])).strip()
    if not config['mail_subject'] or len(config['mail_subject'])>200 or any(c in config['mail_subject'] for c in '\r\n') or not config['mail_body'] or len(config['mail_body'])>10000:raise HTTPException(422,'Bitte gültige Mailvorlagen eingeben.')
    row.operations_json=json.dumps(config);sm.event(db,row,'operations_settings',user);db.commit()
    flash(request,'Organisation gespeichert.');return redirect(f'/seminare/{sid}/organisation')


@app.post('/seminare/{sid:int}/favorite',dependencies=[Depends(check_csrf)])
async def favorite(request:Request,sid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=row_of(db,sid)
    if not can_read(db,user,row):raise HTTPException(404)
    data=await request.form();sm.lock(db,row)
    item=db.scalar(select(SeminarFavorite).where(SeminarFavorite.seminar_id==sid,SeminarFavorite.user_id==user.id))
    if data.get('enabled')=='1':
        if not item:db.add(SeminarFavorite(seminar_id=sid,user_id=user.id))
    elif item:db.delete(item)
    db.commit();return redirect('/seminare?tab=favorites')


@app.get('/seminare/vorlagen')
def templates(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .routes_seminar_planning import allowed
    allowed(user)
    rows=list(db.scalars(select(SeminarTemplate).where(SeminarTemplate.owner_id==user.id).order_by(SeminarTemplate.name)))
    return protect(render(request,'seminar_templates.html',user,templates=rows))


@app.post('/seminare/{sid:int}/template',dependencies=[Depends(check_csrf)])
async def template_save(request:Request,sid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=staff_of(db,user,sid,True);data=await request.form();name=str(data.get('name','')).strip()
    if not name or len(name)>255:raise HTTPException(422,'Vorlagenname erforderlich (maximal 255 Zeichen).')
    db.add(SeminarTemplate(owner_id=user.id,name=name,config_json=json.dumps(ops.template_values(row))))
    db.commit();return redirect('/seminare/vorlagen')


@app.post('/seminare/vorlagen/new',dependencies=[Depends(check_csrf)])
async def template_use(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .routes_seminar_planning import allowed
    allowed(user);data=await request.form()
    if data.get('template')=='wissenshaeppchen':
        values=dict(booking_mode='individual',channels='internal',certificates=True,certificate_scope='term',
                    operations_json=json.dumps({**ops.DEFAULTS,'self_checkin':True,'guest_materials':True}))
        title='Wissenshäppchen'
    else:
        template=db.get(SeminarTemplate,sm.integer(data.get('template'),1))
        if not template or template.owner_id!=user.id:raise HTTPException(404)
        values={k:v for k,v in json.loads(template.config_json).items() if k in ops.TEMPLATE_FIELDS};title=template.name
    row=Seminar(owner_id=user.id,title=title,**values);db.add(row);db.flush()
    if data.get('template')=='wissenshaeppchen':row.planning_json=json.dumps({'schedule':{'kind':'fortnightly','duration':30,'count':6}})
    sm.event(db,row,'from_template',user);db.commit();return redirect(f'/seminare/{row.id}/planen')


@app.post('/seminare/vorlagen/{tid:int}/delete',dependencies=[Depends(check_csrf)])
def template_delete(tid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    template=db.get(SeminarTemplate,tid)
    if not template or template.owner_id!=user.id:raise HTTPException(404)
    db.delete(template);db.commit();return redirect('/seminare/vorlagen')


def audience(db,row,data):
    targets={}
    def add(name,email,member=None,distribution=False):
        email=email.strip().lower()
        if len(email)>255 or not sm.re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',email):raise HTTPException(422,'Ungültige Empfängeradresse.')
        known=db.scalar(select(User).where(User.email==email))
        if known and not known.active:raise HTTPException(422,'Eine Empfängeradresse gehört zu einem deaktivierten Benutzer.')
        member=known or member
        if member and 'internal' not in row.channels.split(','):raise HTTPException(422,'Interner Zugang ist deaktiviert.')
        if not member and not distribution and 'guest' not in row.channels.split(',') and data.get('kind')=='invite':raise HTTPException(422,'Gasteinladungen sind deaktiviert.')
        old=targets.get(email)
        distribution=distribution or bool(old and old['distribution'])
        targets[email]=dict(name=(member.name if member else name or email)[:255],email=email,user_id=member.id if member else None,distribution=distribution)
    for uid in data.getlist('users'):
        member=db.get(User,sm.integer(uid,1))
        if not member or not member.active:raise HTTPException(422,'Empfänger nicht verfügbar.')
        add(member.name,member.email,member)
    for gid in data.getlist('groups'):
        group=db.get(Group,sm.integer(gid,1))
        if not group:raise HTTPException(422)
        for member in group.members:
            if member.active:add(member.name,member.email,member)
    for key in ('addresses','distributors'):
        for line in str(data.get(key,'')).splitlines():
            if not line.strip():continue
            if ';' in line:
                name,email=line.split(';',1);add(name.strip(),email,distribution=key=='distributors')
            else:
                for name,email in getaddresses([line]):add(name,email,distribution=key=='distributors')
    if not targets or len(targets)>500:raise HTTPException(422,'Bitte 1 bis 500 Empfänger auswählen.')
    return list(targets.values())


@app.get('/seminare/{sid:int}/mail')
def mail_page(request:Request,sid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=staff_of(db,user,sid,True)
    return protect(render(request,'seminar_mail.html',user,row=row,terms=sm.sessions(db,row),
        people=list(db.scalars(select(User).where(User.active.is_(True)).order_by(User.name))),
        groups=list(db.scalars(select(Group).order_by(Group.name))),draft=None,options=ops.options(row)))


@app.post('/seminare/{sid:int}/mail/preview',dependencies=[Depends(check_csrf)])
async def mail_preview(request:Request,sid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=staff_of(db,user,sid,True);data=await request.form()
    if row.status!='published':raise HTTPException(409,'Zuerst veröffentlichen.')
    kind=data.get('kind');scope=sm.integer(data.get('scope_id') or 0)
    if kind not in {'notice','invite'}:raise HTTPException(422)
    if scope and scope not in [t.id for t in sm.sessions(db,row)]:raise HTTPException(422)
    if kind=='invite' and not scope and row.booking_mode=='individual':raise HTTPException(422,'Für persönliche Einladungen einen Termin auswählen.')
    if kind=='invite' and scope and row.booking_mode=='series':raise HTTPException(422,'Diese Veranstaltung bietet ausschließlich Reihenbuchungen an.')
    subject=str(data.get('subject','')).strip();body=str(data.get('body','')).strip()
    if not subject or len(subject)>200 or '\n' in subject or '\r' in subject or not body or len(body)>10000:raise HTTPException(422,'Betreff (max. 200 Zeichen) und Nachricht (max. 10.000 Zeichen) erforderlich.')
    targets=audience(db,row,data)
    if (kind=='notice' or any(t['distribution'] for t in targets)) and not {'internal','public'}.intersection(row.channels.split(',')):raise HTTPException(422,'Allgemeine Hinweise benötigen einen internen oder öffentlichen Veranstaltungszugang.')
    payload=dict(kind=kind,scope=scope,subject=subject,body=body,targets=targets,revision=row.revision)
    draft=SeminarMailDraft(seminar_id=sid,owner_id=user.id,payload_json=json.dumps(payload));db.add(draft);db.commit()
    terms=[t for t in sm.sessions(db,row) if not scope or t.id==scope]
    link=sm.links.module_url(db,'seminars',f'/seminare/{sid}')
    example_subject,example=ops.mail_content(payload,row,targets[0],'[Persönlicher Einladungslink]' if kind=='invite' and not targets[0]['distribution'] else link,terms)
    return protect(render(request,'seminar_mail.html',user,row=row,draft=draft,payload=payload,example=example,example_subject=example_subject,terms=terms))


@app.post('/seminare/{sid:int}/mail/{did:int}/send',dependencies=[Depends(check_csrf)])
def mail_send(request:Request,sid:int,did:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=staff_of(db,user,sid,True);sm.lock(db,row);rate_limit(request,'seminar-mail',limit=10)
    draft=db.get(SeminarMailDraft,did)
    if not draft or draft.seminar_id!=sid or draft.owner_id!=user.id:raise HTTPException(404)
    if draft.sent_at:raise HTTPException(409,'Diese Nachricht wurde bereits eingereiht.')
    payload=json.loads(draft.payload_json)
    if row.status!='published' or payload['revision']!=row.revision or draft.created_at<utcnow()-timedelta(hours=1):raise HTTPException(409,'Vorschau veraltet. Bitte neu erstellen.')
    if not notify.mail_configured(get_settings(db)):raise HTTPException(503,'E-Mail-Versand zuerst einrichten.')
    terms=[t for t in sm.sessions(db,row) if not payload['scope'] or t.id==payload['scope']]
    count=0
    for target in payload['targets']:
        link=sm.links.module_url(db,'seminars',f'/seminare/{sid}')
        if payload['kind']=='invite' and not target['distribution']:
            member=db.get(User,target['user_id']) if target['user_id'] else None
            if target['user_id'] and (not member or not member.active or member.email.strip().lower()!=target['email']):raise HTTPException(409,'Empfänger inzwischen deaktiviert. Vorschau erneuern.')
            rec=db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==sid,SeminarEnrollment.scope_id==payload['scope'],SeminarEnrollment.email==target['email']))
            if not rec:rec=sm.new_enrollment(db,row,payload['scope'],target['name'],target['email'],member)
            link=sm.personal_link(db,rec)
        subject,body=ops.mail_content(payload,row,target,link,terms)
        if not notify.enqueue(db,target['email'],subject,body,'seminar',per_hour=20):raise HTTPException(409,'Versandlimit erreicht. Keine Nachrichten dieses Entwurfs gespeichert; bitte später erneut versuchen.')
        count+=1
    draft.sent_at=utcnow();sm.event(db,row,'mail_queued',user,f'{payload["kind"]}: {count} Empfänger');db.commit()
    flash(request,f'{count} Nachrichten in die Versandwarteschlange aufgenommen.');return redirect(f'/seminare/{sid}/mail')


@app.get('/seminare/{sid:int}/durchfuehrung/{tid:int}')
def conduct(request:Request,sid:int,tid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=staff_of(db,user,sid);term=series.term_of(db,row,tid)
    if not series.may_term(db,user,row,term):raise HTTPException(404)
    records=list(db.scalars(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==sid,SeminarEnrollment.scope_id.in_([0,tid]),SeminarEnrollment.status=='confirmed').order_by(SeminarEnrollment.name)))
    attendance={a.enrollment_id:a for a in db.scalars(select(SeminarAttendance).where(SeminarAttendance.session_id==tid))}
    link=sm.links.module_url(db,'seminars','/seminare/checkin/'+ops.checkin_token(row,term))
    return protect(render(request,'seminar_conduct.html',user,row=row,term=term,records=records,attendance=attendance,
        checkin=ops.checkin_enabled(row,term),checkin_override=json.loads(term.overrides_json).get('self_checkin'),checkin_link=link,qr=qr_data(link),planner=sm.may_plan(db,user,row)))


@app.post('/seminare/{sid:int}/durchfuehrung/{tid:int}',dependencies=[Depends(check_csrf)])
async def conduct_save(request:Request,sid:int,tid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=staff_of(db,user,sid);term=series.term_of(db,row,tid);data=await request.form();sm.lock(db,row)
    if not series.may_term(db,user,row,term):raise HTTPException(404)
    if data.get('action')=='settings':
        if not sm.may_plan(db,user,row):raise HTTPException(403)
        overrides=json.loads(term.overrides_json);value=data.get('self_checkin')
        if value=='inherit':overrides.pop('self_checkin',None)
        elif value in {'yes','no'}:overrides['self_checkin']=value=='yes'
        else:raise HTTPException(422)
        term.overrides_json=json.dumps(overrides);term.revision+=1
    else:
        rec=db.get(SeminarEnrollment,sm.integer(data.get('enrollment'),1))
        if not rec or rec.seminar_id!=sid:raise HTTPException(404)
        if data.get('present') not in {'0','1'}:raise HTTPException(422)
        learning.mark_attendance(db,row,rec,term,user,data.get('present')=='1')
    db.commit();return redirect(f'/seminare/{sid}/durchfuehrung/{tid}')


@app.get('/seminare/checkin/{token}')
def self_checkin_page(request:Request,token:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row,term=ops.checkin_term(db,token);row_of(db,row.id)
    rec=db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==row.id,SeminarEnrollment.scope_id.in_([0,term.id]),SeminarEnrollment.user_id==user.id,SeminarEnrollment.status=='confirmed'))
    if not rec:raise HTTPException(403,'Für diesen Termin liegt keine bestätigte Buchung vor.')
    return protect(render(request,'seminar_self_checkin.html',user,row=row,term=term,token=token))


@app.post('/seminare/checkin/{token}',dependencies=[Depends(check_csrf)])
def self_checkin_save(request:Request,token:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row,term=ops.checkin_term(db,token);row_of(db,row.id);sm.lock(db,row)
    row,term=ops.checkin_term(db,token)
    rec=db.scalar(select(SeminarEnrollment).where(SeminarEnrollment.seminar_id==row.id,SeminarEnrollment.scope_id.in_([0,term.id]),SeminarEnrollment.user_id==user.id,SeminarEnrollment.status=='confirmed'))
    if not rec:raise HTTPException(403)
    existing=db.scalar(select(SeminarAttendance).where(SeminarAttendance.enrollment_id==rec.id,SeminarAttendance.session_id==term.id))
    if existing and existing.source=='staff':raise HTTPException(409,'Anwesenheit bereits durch die Betreuung erfasst. Bitte für Korrekturen dort melden.')
    if not existing:learning.mark_attendance(db,row,rec,term,user,True,self_service=True)
    db.commit();flash(request,'Ihre Anwesenheit wurde bestätigt.');return redirect(sm.personal_path(rec))


@app.post('/seminare/{sid:int}/teacher-access/{tid:int}',dependencies=[Depends(check_csrf)])
async def teacher_access(request:Request,sid:int,tid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=staff_of(db,user,sid,True);term=series.term_of(db,row,tid);data=await request.form();sm.lock(db,row)
    email=str(data.get('email','')).strip().lower()
    if not any(g.get('email','').strip().lower()==email for g in json.loads(term.guests_json)):raise HTTPException(422,'Dozent ist diesem Termin nicht zugeordnet.')
    if data.get('action')=='revoke':
        access=db.scalar(select(SeminarLecturerAccess).where(SeminarLecturerAccess.term_id==tid,SeminarLecturerAccess.email==email))
        if access:db.delete(access)
        sm.event(db,row,'teacher_access_revoked',user)
    else:
        if row.status!='published' or not term.published or term.cancelled:raise HTTPException(409,'Zuerst den Termin veröffentlichen.')
        if not notify.mail_configured(get_settings(db)):raise HTTPException(503,'E-Mail-Versand zuerst einrichten.')
        link=hybrid.invite_teacher(db,row,term,email)
        if not notify.enqueue(db,email,row.title+' · Persönlicher Dozentenzugang',
            (term.title or row.title)+'\n'+sm.local_input(term.starts_at)+'\n'+link+'\nBitte diesen persönlichen Link nicht weitergeben.', 'seminar',per_hour=20):raise HTTPException(409,'Versandlimit erreicht.')
        sm.event(db,row,'teacher_access_invited',user)
    db.commit();flash(request,'Dozentenzugang aktualisiert.');return redirect(f'/seminare/{sid}/organisation')


async def uploaded_material(data,row):
    import hashlib,mimetypes,secrets
    from pathlib import Path
    title=str(data.get('title','')).strip()
    if not title or len(title)>255:raise HTTPException(422,'Titel erforderlich (maximal 255 Zeichen).')
    upload=data.get('file');suffix=Path(getattr(upload,'filename','') or '').suffix.lower()
    if suffix not in {'.pdf','.txt','.md','.png','.jpg','.jpeg','.docx','.xlsx','.pptx','.odt','.ods','.odp'}:raise HTTPException(422,'Dateityp nicht unterstützt.')
    body=await upload.read(20*1024*1024+1)
    if not body or len(body)>20*1024*1024:raise HTTPException(413,'Bitte eine nicht leere Datei bis 20 MB verwenden.')
    filename=secrets.token_hex(16)+suffix;learning.files_dir(row).joinpath(filename).write_bytes(body)
    return title,dict(kind='file',title=title,file=filename,mime=mimetypes.guess_type(filename)[0] or 'application/octet-stream',sha256=hashlib.sha256(body).hexdigest())


@app.post('/seminare/dozent/{token}/materials',dependencies=[Depends(check_csrf)])
async def guest_material_add(request:Request,token:str,db:Session=Depends(get_db)):
    row,term,access,teacher=hybrid.guest_teacher(db,token);rate_limit(request,'seminar-teacher-upload',limit=30)
    if not ops.options(row)['guest_materials']:raise HTTPException(403)
    data=await request.form();sm.lock(db,row)
    row,term,access,teacher=hybrid.guest_teacher(db,token)
    if not ops.options(row)['guest_materials']:raise HTTPException(403)
    mode=data.get('mode','manual')
    if mode not in {'immediate','scheduled','manual'}:raise HTTPException(422)
    release=sm.parse_time(data.get('release_at'),True) if mode=='scheduled' else None
    if mode=='scheduled' and not release:raise HTTPException(422,'Freigabezeit erforderlich.')
    title,item=await uploaded_material(data,row)
    direct=ops.options(row)['guest_publish']
    material=SeminarMaterial(seminar_id=row.id,scope_id=term.id,title=title,item_json=json.dumps(item),
        author_access_id=access.id,release_at=release,manual_release=mode=='manual' or not direct,published=mode!='manual' and direct)
    db.add(material);sm.event(db,row,'guest_material_uploaded',detail=f'Termin {term.id}: {title}')
    series.staff_message(db,row,'Dozentenunterlage prüfen',title,[term],only_owner=True)
    db.commit();flash(request,'Unterlage gespeichert.' if direct else 'Unterlage zur Freigabe eingereicht.')
    return redirect('/seminare/dozent/'+token)


@app.post('/seminare/dozent/{token}/materials/{mid:int}',dependencies=[Depends(check_csrf)])
async def guest_material_update(request:Request,token:str,mid:int,db:Session=Depends(get_db)):
    row,term,access,teacher=hybrid.guest_teacher(db,token)
    if not ops.options(row)['guest_materials']:raise HTTPException(403)
    data=await request.form();sm.lock(db,row)
    row,term,access,teacher=hybrid.guest_teacher(db,token)
    if not ops.options(row)['guest_materials']:raise HTTPException(403)
    material=db.get(SeminarMaterial,mid)
    if not material or material.seminar_id!=row.id or material.scope_id!=term.id or material.author_access_id!=access.id:raise HTTPException(404)
    if not ops.options(row)['guest_publish']:raise HTTPException(403,'Änderungen nach Einreichung bitte mit der Planung abstimmen.')
    mode=data.get('mode')
    if mode not in {'immediate','scheduled','manual'}:raise HTTPException(422)
    release=sm.parse_time(data.get('release_at'),True) if mode=='scheduled' else None
    if mode=='scheduled' and not release:raise HTTPException(422,'Freigabezeit erforderlich.')
    material.release_at=release;material.manual_release=mode=='manual';material.published=mode!='manual'
    sm.event(db,row,'guest_material_release',detail=f'Termin {term.id}, Unterlage {mid}')
    db.commit();return redirect('/seminare/dozent/'+token)


@app.get('/seminare/dozent/{token}/materials/{mid:int}')
def guest_material_download(request:Request,token:str,mid:int,db:Session=Depends(get_db)):
    row,term,access,teacher=hybrid.guest_teacher(db,token);material=db.get(SeminarMaterial,mid)
    if (not ops.options(row)['guest_materials'] or not material or material.seminar_id!=row.id
        or material.scope_id!=term.id or material.author_access_id!=access.id):raise HTTPException(404)
    from .routes_seminar_learning import material_file
    return material_file(row,material)
