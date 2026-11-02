"""Shared board UI; mutations use board and task versions and existing task rules."""
from datetime import datetime
from fastapi import Depends,HTTPException,Request
from fastapi.responses import JSONResponse
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from . import tasks as ts,task_boards as boards
from .db import User,Group,utcnow
from .task_models import Task,TaskBoard,TaskBoardMember,TaskBoardColumn,TaskBoardCard,TaskCheck,TaskComment,TaskAttachment,TaskActivity
from .main import app,current_user,get_db,check_csrf,render,redirect,enabled_modules
from .routes_tasks import module_on


def number(value):
    try:return int(value)
    except (TypeError,ValueError):raise HTTPException(422,'Bitte eine gültige Auswahl treffen.')


@app.get('/tasks/boards')
def board_list(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    module_on()
    return render(request,'task_boards.html',user,boards=list(db.scalars(select(TaskBoard).where(TaskBoard.id.in_(boards.board_ids(user))).order_by(TaskBoard.title))),can_create=ts.may_create(user))


@app.post('/tasks/boards',dependencies=[Depends(check_csrf)])
async def board_create(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    module_on()
    if not ts.may_create(user):raise HTTPException(403)
    data=await request.form();title=str(data.get('title','')).strip()
    if not title or len(title)>255:raise HTTPException(422,'Boardname erforderlich (maximal 255 Zeichen).')
    row=TaskBoard(owner_id=user.id,title=title);db.add(row);db.flush()
    for pos,(status,label) in enumerate(ts.STATUSES.items()):db.add(TaskBoardColumn(board_id=row.id,title=label,status=status,position=pos))
    db.commit();return redirect(f'/tasks/boards/{row.id}')


@app.get('/tasks/boards/{bid:int}')
def board_page(request:Request,bid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    module_on();board=boards.get(db,user,bid);cols=boards.columns(db,board);cards=boards.visible_cards(db,user,board)
    query=request.query_params.get('q','').strip().lower()[:200];sort=request.query_params.get('sort','manual')
    if sort not in {'manual','priority','due'}:sort='manual'
    priority=request.query_params.get('priority','');person=request.query_params.get('person','')
    cards=[v for v in cards if (not query or query in (v['task'].title+' '+v['task'].description+' '+v['task'].tags if v['task'] else v['source']['title']).lower()) and (not priority or v['task'] and v['task'].priority==priority) and (not person or v['task'] and str(v['task'].assignee_id)==person)]
    if sort=='priority':cards.sort(key=lambda v:({'urgent':0,'high':1,'normal':2,'low':3}.get(v['task'].priority,2) if v['task'] else 4,v['card'].position,v['card'].id))
    elif sort=='due':cards.sort(key=lambda v:(v['task'].due_at if v['task'] else v['source'].get('due')) or datetime.max)
    checks={}
    for v in cards:
        if v['task']:checks[v['task'].id]=list(db.scalars(select(TaskCheck).where(TaskCheck.task_id==v['task'].id).order_by(TaskCheck.position,TaskCheck.id)))
    level=boards.level(db,user,board)
    return render(request,'task_board.html',user,board=board,columns=cols,cards=cards,checks=checks,level=level,ts=ts,sort=sort,q=query,priority=priority,person=person,now=utcnow(),people=ts.users(db),groups=list(db.scalars(select(Group).order_by(Group.name))) if level==3 else [],members=list(db.scalars(select(TaskBoardMember).where(TaskBoardMember.board_id==bid))) if level==3 else [],
        candidates=list(db.scalars(ts.visible_query(user).where(Task.archived_at.is_(None)).order_by(Task.updated_at.desc()).limit(200))) if level>=2 else [],sources=boards.source_items(db,user) if level>=2 else {})


@app.get('/tasks/boards/{bid:int}/cards/{cid:int}')
def card_detail(request:Request,bid:int,cid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    module_on();board=boards.get(db,user,bid)
    card=db.get(TaskBoardCard,cid)
    if not card or card.board_id!=bid or not card.task_id:raise HTTPException(404)
    row=ts.get(db,user,card.task_id)
    return render(request,'_task_board_detail.html',user,board=board,card=card,task=row,ts=ts,level=boards.level(db,user,board),people=ts.users(db),
        checks=list(db.scalars(select(TaskCheck).where(TaskCheck.task_id==row.id).order_by(TaskCheck.position,TaskCheck.id))),
        comments=list(db.scalars(select(TaskComment).where(TaskComment.task_id==row.id,TaskComment.removed_at.is_(None)).order_by(TaskComment.created_at))),
        files=list(db.scalars(select(TaskAttachment).where(TaskAttachment.task_id==row.id,TaskAttachment.removed_at.is_(None)))),
        activity=list(db.scalars(select(TaskActivity).where(TaskActivity.task_id==row.id).order_by(TaskActivity.id.desc()).limit(30))))


@app.post('/tasks/boards/{bid:int}/action',dependencies=[Depends(check_csrf)])
async def board_action(request:Request,bid:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    module_on();data=await request.form();action=str(data.get('action',''))
    required=3 if action in {'settings','column','column_delete','member','member_remove','delete'} else 2
    board=boards.get(db,user,bid,required)
    paths=[]
    try:
        boards.lock(db,board,data.get('board_version'))
        board=boards.get(db,user,bid,required)
        def column(value):
            col=db.get(TaskBoardColumn,number(value))
            if not col or col.board_id!=bid:raise HTTPException(404)
            return col
        card=None
        if data.get('card'):
            card=db.get(TaskBoardCard,number(data['card']))
            if not card or card.board_id!=bid:raise HTTPException(404)
        if action=='settings':
            title=str(data.get('title','')).strip();mode=data.get('mode')
            if not title or len(title)>255 or mode not in {'status','free'}:raise ts.Invalid('Boardname und Modus prüfen.')
            if mode=='status' and set(ts.STATUSES)-{c.status for c in boards.columns(db,board)}:raise ts.Invalid('Für den Statusmodus muss jeder Aufgabenstatus mindestens einer Spalte zugeordnet sein.')
            board.title=title;board.mode=mode;board.description=str(data.get('description',''))[:10000]
        elif action=='column':
            title=str(data.get('title','')).strip();status=data.get('status','open')
            if not title or len(title)>100 or status not in ts.STATUSES:raise ts.Invalid('Spaltenname und Status prüfen.')
            cols=boards.columns(db,board)
            if data.get('column'):
                col=column(data['column'])
                if board.mode=='status' and col.status!=status:raise ts.Invalid('Statuszuordnung im freien Modus ändern; danach bewusst zum Statusmodus wechseln.')
                col.title=title;col.status=status
                index=max(0,min(number(data.get('position',col.position)),len(cols)-1));cols.remove(col);cols.insert(index,col)
                for i,c in enumerate(cols):c.position=i
            else:
                if len(cols)>=30:raise ts.Invalid('Maximal 30 Spalten je Board.')
                db.add(TaskBoardColumn(board_id=bid,title=title,status=status,position=len(cols)))
        elif action=='column_delete':
            col=column(data['column'])
            if len(boards.columns(db,board))<=1 or db.scalar(select(TaskBoardCard.id).where(TaskBoardCard.column_id==col.id)):raise ts.Invalid('Nur leere Spalten löschen; mindestens eine Spalte bleibt erhalten.')
            if board.mode=='status' and not any(c.id!=col.id and c.status==col.status for c in boards.columns(db,board)):raise ts.Invalid('Die letzte Spalte eines Aufgabenstatus bleibt im Statusmodus erhalten.')
            db.delete(col)
        elif action in {'member','member_remove'}:
            if action=='member_remove':
                item=db.get(TaskBoardMember,number(data.get('member')))
                if not item or item.board_id!=bid:raise HTTPException(404)
                db.delete(item)
            else:
                if not boards.may_share(db,user,board):raise HTTPException(403,'Einige Aufgaben dürfen Sie nicht für zusätzliche Personen freigeben. Entfernen Sie diese Karten zuerst.')
                raw=str(data.get('target',''));kind,_,value=raw.partition(':');target_id=number(value)
                if kind not in {'user','group'}:raise ts.Invalid('Person oder Gruppe wählen.')
                target=db.get(User if kind=='user' else Group,target_id)
                if not target or kind=='user' and not target.active:raise ts.Invalid('Auswahl nicht verfügbar.')
                role=number(data.get('level'))
                if role not in {1,2,3}:raise ts.Invalid('Ungültige Rolle.')
                attr=TaskBoardMember.user_id if kind=='user' else TaskBoardMember.group_id
                item=db.scalar(select(TaskBoardMember).where(TaskBoardMember.board_id==bid,attr==target_id))
                if not item:item=TaskBoardMember(board_id=bid,user_id=target_id if kind=='user' else None,group_id=target_id if kind=='group' else None);db.add(item)
                item.level=role
        elif action=='delete':
            if board.owner_id!=user.id:raise HTTPException(403)
            db.delete(board);db.commit()
            return JSONResponse({'redirect':'/tasks/boards'}) if request.headers.get('accept')=='application/json' else redirect('/tasks/boards')
        elif action in {'create','attach'}:
            col=column(data.get('column'))
            if action=='create':
                row=ts.create(db,user,{**dict(data),'assignee_id':data.get('assignee_id') or str(user.id)},board=board)
                ts.add_initial_checks(db,user,row,ts.initial_checklist(data.get('checklist','')))
                if board.mode=='status' and col.status!='open':ts.transition(db,user,row,col.status)
            elif data.get('task'):row=ts.get(db,user,number(data['task']))
            else:
                key=str(data.get('source',''))
                if key not in boards.source_items(db,user):raise HTTPException(404)
                if not db.scalar(select(TaskBoardCard.id).where(TaskBoardCard.board_id==bid,TaskBoardCard.source_key==key)):db.add(TaskBoardCard(board_id=bid,column_id=col.id,source_key=key,position=1000000))
                row=None
            if row:boards.add_native(db,user,board,col,row)
        elif action=='move' and card:
            if card.task_id:ts.check_version(ts.get(db,user,card.task_id),data)
            boards.move(db,user,board,card,column(data.get('column')),number(data.get('position',0)))
        elif action=='remove' and card:
            if card.source_key and card.source_key not in boards.source_items(db,user):raise HTTPException(404)
            db.delete(card)
        elif action in {'edit','status','check','check_add','check_remove','comment','upload'} and card and card.task_id:
            row=ts.get(db,user,card.task_id);ts.check_version(row,data)
            if action=='edit':ts.update(db,user,row,{**ts.form_values(row),**dict(data)})
            elif action=='status':ts.transition(db,user,row,str(data.get('status','')),str(data.get('comment','')))
            elif action=='comment':ts.comment(db,user,row,data.get('comment',''))
            elif action=='upload':await ts.attach_files(db,user,row,data.getlist('files'),paths,required=True);ts.audit(db,row,user,'attachment','Dateien über Board hinzugefügt.')
            else:
                if row.archived_at or row.status in {'done','cancelled'}:raise ts.Invalid('Aufgabe vor Checklistenänderungen wieder öffnen.')
                if action=='check_add':
                    title=str(data.get('check_title','')).strip()
                    if not title or len(title)>500:raise ts.Invalid('Checklistenpunkt mit 1 bis 500 Zeichen erforderlich.')
                    db.add(TaskCheck(task_id=row.id,title=title,position=(db.scalar(select(func.max(TaskCheck.position)).where(TaskCheck.task_id==row.id)) or 0)+1))
                else:
                    check=db.get(TaskCheck,number(data.get('check')))
                    if not check or check.task_id!=row.id:raise HTTPException(404)
                    if action=='check':check.done=not check.done
                    else:db.delete(check)
                ts.audit(db,row,user,'check','Checkliste über Board aktualisiert.')
        else:raise ts.Invalid('Aktion nicht verfügbar.')
        db.commit()
    except ts.Invalid as error:
        db.rollback();ts.discard_files(paths)
        message=error.args[0] if error.args and isinstance(error.args[0],str) else 'Bitte die Eingaben prüfen.'
        if request.headers.get('accept')=='application/json':return JSONResponse({'detail':message},status_code=422)
        raise HTTPException(422,message)
    except HTTPException as error:
        db.rollback();ts.discard_files(paths)
        if request.headers.get('accept')=='application/json':return JSONResponse({'detail':error.detail},status_code=error.status_code)
        raise
    except StaleDataError:
        db.rollback();ts.discard_files(paths)
        message='Die Aufgabe wurde inzwischen geändert. Bitte den aktuellen Stand laden.'
        if request.headers.get('accept')=='application/json':return JSONResponse({'detail':message},status_code=409)
        raise HTTPException(409,message)
    except OSError:
        db.rollback();ts.discard_files(paths)
        message='Die Dateien konnten nicht gespeichert werden. Bitte wählen Sie sie erneut aus.'
        if request.headers.get('accept')=='application/json':return JSONResponse({'detail':message},status_code=422)
        raise HTTPException(422,message)
    return JSONResponse({'ok':True}) if request.headers.get('accept')=='application/json' else redirect(f'/tasks/boards/{bid}')
