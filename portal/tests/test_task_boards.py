"""Shared board permissions, organization and concurrency preserve task rules."""
import pytest
from sqlalchemy import select
from app import task_boards as kb,tasks as ts
from app.db import Group,GroupMember,SessionLocal
from app.task_models import Task,TaskBoard,TaskBoardMember,TaskBoardColumn,TaskBoardCard,TaskCheck
from conftest import csrf_of,login
from test_native_tasks import task_people,make


def client_for(person):return login(person.email,'task-passwort-123')


def board(db,owner,title='Teamboard',mode='status'):
    b=TaskBoard(owner_id=owner.id,title=title,mode=mode);db.add(b);db.flush()
    for i,(key,label) in enumerate(ts.STATUSES.items()):db.add(TaskBoardColumn(board_id=b.id,title=label,status=key,position=i))
    db.commit();return b


def member(db,b,user,level=2):
    item=TaskBoardMember(board_id=b.id,user_id=user.id,level=level);db.add(item);db.commit();return item


def attach(db,b,t,owner):
    card=kb.add_native(db,owner,b,kb.columns(db,b)[0],t);db.commit();return card


def post(c,db,b,action,**data):
    db.refresh(b)
    return c.post(f'/tasks/boards/{b.id}/action',data={'csrf':csrf_of(c.get(f'/tasks/boards/{b.id}').text),'board_version':b.version,'action':action,**data},headers={'Accept':'application/json'})


def test_private_board_and_reader_cannot_mutate_through_task_routes(db,task_people):
    a,assigned,reader,outsider=task_people;b=board(db,a);t=make(db,task_people);card=attach(db,b,t,a)
    assert client_for(outsider).get(f'/tasks/boards/{b.id}').status_code==404
    membership=member(db,b,reader,1);c=client_for(reader);page=c.get(f'/tasks/boards/{b.id}');assert page.status_code==200
    assert c.get(f'/tasks/boards/{b.id}/cards/{card.id}').status_code==200
    assert post(c,db,b,'edit',card=card.id,version=t.version,priority='urgent').status_code==404
    assert c.post(f'/aufgaben/{t.id}/aktion',data={'csrf':csrf_of(page.text),'version':t.version,'action':'check_add','check_title':'No'}).status_code==403
    db.delete(membership);db.commit()
    assert c.get(f'/aufgaben/{t.id}').status_code==404


def test_multi_board_common_edits_and_free_positions(db,task_people):
    a,_,editor,_=task_people;t=make(db,task_people);b=board(db,a,mode='free');other=board(db,a,'Anderes',mode='free')
    card=attach(db,b,t,a);second=attach(db,other,t,a);member(db,b,editor);c=client_for(editor)
    assert post(c,db,b,'edit',card=card.id,version=t.version,priority='urgent').status_code==200
    db.refresh(t);assert t.priority=='urgent'
    assert post(c,db,b,'move',card=card.id,version=t.version,column=kb.columns(db,b)[2].id,position=0).status_code==200
    db.refresh(card);db.refresh(second);assert card.column_id!=kb.columns(db,b)[0].id and second.column_id==kb.columns(db,other)[0].id
    db.refresh(t);assert t.status=='open'


def test_status_move_review_and_checklist_protection(db,task_people):
    a,_,editor,_=task_people;b=board(db,a);t=make(db,task_people,requires_review='1');card=attach(db,b,t,a);member(db,b,editor);c=client_for(editor)
    check=TaskCheck(task_id=t.id,title='Prüfen');db.add(check);db.commit();cols={col.status:col for col in kb.columns(db,b)}
    assert post(c,db,b,'move',card=card.id,version=t.version,column=cols['done'].id).status_code==422
    assert post(c,db,b,'check',card=card.id,version=t.version,check=check.id).status_code==200
    db.refresh(t)
    assert post(c,db,b,'move',card=card.id,version=t.version,column=cols['done'].id).status_code==200
    db.refresh(t);db.refresh(card);assert t.status=='review' and card.column_id==cols['review'].id
    assert post(c,db,b,'status',card=card.id,version=t.version,status='done').status_code==403
    assert post(c,db,b,'edit',card=card.id,version=t.version,requires_review='').status_code==403


def test_share_cannot_leak_assigned_task_on_private_board(db,task_people):
    a,assigned,other,_=task_people;t=make(db,task_people);b=board(db,assigned);attach(db,b,t,assigned);c=client_for(assigned)
    assert post(c,db,b,'member',target=f'user:{other.id}',level=1).status_code==403
    assert not db.scalar(select(TaskBoardMember).where(TaskBoardMember.board_id==b.id))
    shared=board(db,assigned,'Geteilt');member(db,shared,other)
    assert post(c,db,shared,'attach',column=kb.columns(db,shared)[0].id,task=t.id).status_code==403


def test_group_access_and_revocation(db,task_people):
    a,_,editor,_=task_people;b=board(db,a);t=make(db,task_people);attach(db,b,t,a)
    g=Group(name='Boardteam');db.add(g);db.flush();gm=GroupMember(group_id=g.id,user_id=editor.id);db.add(gm)
    db.add(TaskBoardMember(board_id=b.id,group_id=g.id,level=2));db.commit()
    assert kb.level(db,editor,b)==2 and ts.get(db,editor,t.id).id==t.id
    db.delete(gm);db.commit()
    with pytest.raises(Exception):ts.get(db,editor,t.id)
    db.delete(g);db.commit()


def test_stale_board_and_cross_board_column_rejected(db,task_people):
    a=task_people[0];b=board(db,a);other=board(db,a,'Zwei');t=make(db,task_people);card=attach(db,b,t,a);c=client_for(a)
    page=c.get(f'/tasks/boards/{b.id}');token=csrf_of(page.text);version=b.version
    assert post(c,db,b,'settings',title='Neu',mode='free').status_code==200
    response=c.post(f'/tasks/boards/{b.id}/action',data={'csrf':token,'board_version':version,'action':'remove','card':card.id},headers={'Accept':'application/json'})
    assert response.status_code==409
    assert post(c,db,b,'move',card=card.id,version=t.version,column=kb.columns(db,other)[0].id).status_code==404
    assert db.get(TaskBoardCard,card.id)


def test_stale_task_on_other_board_does_not_overwrite(db,task_people):
    a=task_people[0];b=board(db,a);t=make(db,task_people);card=attach(db,b,t,a);c=client_for(a);version=t.version
    with SessionLocal() as other:
        task=other.get(Task,t.id);task.title='Neu';other.commit()
    assert post(c,db,b,'move',card=card.id,version=version,column=kb.columns(db,b)[1].id).status_code==422


def test_contributor_create_without_global_create_permission(db,task_people):
    a,_,_,editor=task_people;b=board(db,a);member(db,b,editor);c=client_for(editor)
    response=post(c,db,b,'create',column=kb.columns(db,b)[0].id,title='Teamaufgabe',checklist='Eins\nZwei')
    assert response.status_code==200
    task=db.scalar(select(Task).where(Task.title=='Teamaufgabe',Task.creator_id==editor.id))
    assert task and len(list(db.scalars(select(TaskCheck).where(TaskCheck.task_id==task.id))))==2
    # Existing test fixture removes tasks by creator, including this contributor.


def test_mode_switch_and_deleting_board_keep_tasks(db,task_people):
    a=task_people[0];b=board(db,a);t=make(db,task_people);card=attach(db,b,t,a);c=client_for(a)
    assert post(c,db,b,'settings',title='Frei',mode='free').status_code==200
    assert post(c,db,b,'move',card=card.id,version=t.version,column=kb.columns(db,b)[3].id).status_code==200
    assert post(c,db,b,'settings',title='Status',mode='status').status_code==200
    assert kb.visible_cards(db,a,b)[0]['column'].status=='open'
    assert post(c,db,b,'delete').status_code==200
    assert db.get(Task,t.id)


def test_source_cards_resolve_per_user_and_do_not_mutate_source(db,task_people,monkeypatch):
    a,_,reader,_=task_people;b=board(db,a,mode='free');member(db,b,reader,1)
    key='application:/forms/1/applications/1#schritt'
    monkeypatch.setattr(kb,'source_items',lambda db,u: {key:dict(title='Geschützter Antrag',href='/forms/1/applications/1#schritt',source='application',source_label='Antrag',detail='Prüfen',due=None)} if u.id==a.id else {})
    c=client_for(a)
    assert post(c,db,b,'attach',column=kb.columns(db,b)[0].id,source=key).status_code==200
    assert 'Geschützter Antrag' in c.get(f'/tasks/boards/{b.id}').text
    assert 'Geschützter Antrag' not in client_for(reader).get(f'/tasks/boards/{b.id}').text
    card=db.scalar(select(TaskBoardCard).where(TaskBoardCard.board_id==b.id))
    assert post(c,db,b,'move',card=card.id,column=kb.columns(db,b)[1].id).status_code==200
    monkeypatch.setattr(kb,'source_items',lambda db,u:{})
    assert not kb.visible_cards(db,a,b)


def test_board_admin_can_share_previously_authorized_cards(db,task_people):
    a,_,admin,reader=task_people;b=board(db,a);t=make(db,task_people);attach(db,b,t,a);member(db,b,admin,3)
    assert post(client_for(admin),db,b,'member',target=f'user:{reader.id}',level=1).status_code==200
    assert client_for(reader).get(f'/aufgaben/{t.id}').status_code==200


def test_board_edit_keeps_foreign_group_context_and_can_reassign(db,task_people):
    a,_,editor,_=task_people;b=board(db,a);t=make(db,task_people);g=Group(name='Fachkontext');db.add(g);db.flush();t.group_id=g.id;db.commit()
    card=attach(db,b,t,a);member(db,b,editor)
    assert post(client_for(editor),db,b,'edit',card=card.id,version=t.version,priority='high',assignee_id=editor.id).status_code==200
    db.refresh(t);assert t.group_id==g.id and t.assignee_id==editor.id and t.priority=='high'
    t.group_id=None;db.delete(g);db.commit()
