"""Boards organize shared tasks; business-source access is rechecked at use time."""
from sqlalchemy import select, or_, update
from sqlalchemy.orm import object_session
from fastapi import HTTPException
from .db import GroupMember, utcnow
from .task_models import TaskBoard,TaskBoardMember,TaskBoardColumn,TaskBoardCard,Task,TaskParticipant


def board_ids(user,level=1):
    groups=select(GroupMember.group_id).where(GroupMember.user_id==user.id)
    shared=select(TaskBoardMember.board_id).where(TaskBoardMember.level>=level,
        or_(TaskBoardMember.user_id==user.id,TaskBoardMember.group_id.in_(groups)))
    return select(TaskBoard.id).where(or_(TaskBoard.owner_id==user.id,TaskBoard.id.in_(shared)))


def task_ids(user,level=1):
    return select(TaskBoardCard.task_id).where(TaskBoardCard.board_id.in_(board_ids(user,level)),TaskBoardCard.task_id.is_not(None))


def editor(user,task):
    db=object_session(task)
    return bool(db and getattr(user,'id',None) and db.scalar(select(TaskBoardCard.id).where(TaskBoardCard.task_id==task.id,TaskBoardCard.board_id.in_(board_ids(user,2))).limit(1)))


def level(db,user,board):
    if board.owner_id==user.id:return 3
    groups=select(GroupMember.group_id).where(GroupMember.user_id==user.id)
    return max(db.scalars(select(TaskBoardMember.level).where(TaskBoardMember.board_id==board.id,
        or_(TaskBoardMember.user_id==user.id,TaskBoardMember.group_id.in_(groups)))),default=0)


def get(db,user,bid,required=1):
    board=db.get(TaskBoard,bid)
    if not board or level(db,user,board)<required:raise HTTPException(404,'Board nicht gefunden.')
    return board


def lock(db,board,version):
    try:version=int(version)
    except (ValueError,TypeError):raise HTTPException(409,'Bitte das aktuelle Board neu laden.')
    result=db.execute(update(TaskBoard).where(TaskBoard.id==board.id,TaskBoard.version==version).values(version=TaskBoard.version+1))
    if result.rowcount!=1:raise HTTPException(409,'Das Board wurde inzwischen geändert. Bitte neu laden; Ihre Änderung wurde nicht gespeichert.')
    db.flush();db.expire_all()


def columns(db,board):
    return list(db.scalars(select(TaskBoardColumn).where(TaskBoardColumn.board_id==board.id).order_by(TaskBoardColumn.position,TaskBoardColumn.id)))


def source_items(db,user):
    from .task_overview import collect
    from .main import enabled_modules
    work=collect(db,user,enabled_modules());result={}
    for key in ('ready','pool','waiting','delegated','history'):
        for item in work[key]:
            if item['source']!='native':result[item['source']+':'+item['href']]=item
    # Reuse the survey hub's visibility checks and live status, never public tokens.
    if 'polls' in enabled_modules():
        from . import surveys
        for state in ('active','archive'):
            for item in surveys.collect(db,user,enabled_modules(),state=state):
                key=f"survey:{item['kind']}:{item['id']}"
                result[key]=dict(source='survey',source_label=surveys.KINDS[item['kind']][0],
                    title=item['title'],href=item['href'],detail=f"{item['count']} {item['unit']}",
                    status=item['status'],due=None,icon='fa-square-poll-vertical')
    if 'forms' in enabled_modules():
        from . import forms as fm
        from .db import Form
        for form in db.scalars(select(Form).where(Form.kind=='survey',Form.deleted_at.is_(None))):
            if fm.access_level(db,form,user):
                result[f'form:{form.id}']=dict(source='form',source_label='Formularumfrage',title=form.title,
                    href=f'/forms/{form.id}',status='Archiviert' if form.archived_at else 'Offen' if fm.is_open(form) else 'Geschlossen',
                    detail='Fragebogen',due=None,icon='fa-file-lines')
    return result


def visible_cards(db,user,board):
    from . import tasks as ts
    sources=None;result=[];cols=columns(db,board)
    mapping={col.id:col for col in cols}
    for card in db.scalars(select(TaskBoardCard).where(TaskBoardCard.board_id==board.id).order_by(TaskBoardCard.position,TaskBoardCard.id)):
        task=db.get(Task,card.task_id) if card.task_id else None
        if task:
            if task.archived_at:continue
            col=mapping.get(card.column_id)
            if board.mode=='status' and (not col or col.status and col.status!=task.status):col=next((c for c in cols if c.status==task.status),col)
            result.append(dict(card=card,task=task,column=col,source=None))
        elif card.source_key:
            if sources is None:sources=source_items(db,user)
            item=sources.get(card.source_key)
            if item:result.append(dict(card=card,task=None,column=mapping.get(card.column_id),source=item))
    return result


def may_share(db,user,board):
    from . import tasks as ts
    return not db.scalar(select(TaskBoardCard.id).where(TaskBoardCard.board_id==board.id,TaskBoardCard.task_id.is_not(None),TaskBoardCard.shareable.is_(False)))


def add_native(db,user,board,column,task):
    from . import tasks as ts
    if not ts.may_edit(user,task) and db.scalar(select(TaskBoardMember.id).where(TaskBoardMember.board_id==board.id)):
        raise HTTPException(403,'Nur Ersteller und Aufgabenverwaltung dürfen eine Aufgabe für weitere Boardmitglieder freigeben.')
    old=db.scalar(select(TaskBoardCard).where(TaskBoardCard.board_id==board.id,TaskBoardCard.task_id==task.id))
    if old:return old
    if board.mode=='status' and column.status and column.status!=task.status:column=next((c for c in columns(db,board) if c.status==task.status),column)
    if not column:raise HTTPException(422,'Für diesen Aufgabenstatus fehlt eine Spalte.')
    card=TaskBoardCard(board_id=board.id,column_id=column.id,task_id=task.id,shareable=ts.may_edit(user,task),position=1000000)
    db.add(card);ts.audit(db,task,user,'board','Zum Board „'+board.title+'“ hinzugefügt.');db.flush();return card


def move(db,user,board,card,target,index=0):
    from . import tasks as ts
    if card.board_id!=board.id or target.board_id!=board.id:raise HTTPException(404)
    if card.task_id and board.mode=='status' and target.status:
        task=ts.get(db,user,card.task_id)
        ts.transition(db,user,task,target.status)
        # A completion requiring review lands in its actual resulting column.
        if target.status!=task.status:
            target=next((c for c in columns(db,board) if c.status==task.status),None) or db.get(TaskBoardColumn,card.column_id)
        if not target:raise HTTPException(422,'Für den resultierenden Aufgabenstatus fehlt eine Spalte.')
    elif card.source_key:
        if card.source_key not in source_items(db,user):raise HTTPException(404)
    card.column_id=target.id
    db.flush()
    items=list(db.scalars(select(TaskBoardCard).where(TaskBoardCard.board_id==board.id,TaskBoardCard.column_id==target.id,TaskBoardCard.id!=card.id).order_by(TaskBoardCard.position,TaskBoardCard.id)))
    items.insert(max(0,min(index,len(items))),card)
    for pos,item in enumerate(items):item.position=pos
