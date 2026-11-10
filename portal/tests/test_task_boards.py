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
    assert '<fieldset disabled' in c.get(f'/aufgaben/{t.id}').text
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


def test_write_rechecks_membership_after_board_lock(db,task_people,monkeypatch):
    a,_,editor,_=task_people;b=board(db,a);t=make(db,task_people);card=attach(db,b,t,a);membership=member(db,b,editor)
    original=kb.lock
    def revoke(connection,board,version):
        original(connection,board,version)
        connection.delete(connection.get(TaskBoardMember,membership.id));connection.flush()
    monkeypatch.setattr(kb,'lock',revoke)
    response=post(client_for(editor),db,b,'edit',card=card.id,version=t.version,priority='urgent')
    assert response.status_code==404
    db.refresh(t);assert t.priority=='normal'


def test_upload_io_error_never_discloses_internal_paths(db,task_people,monkeypatch):
    a=task_people[0];b=board(db,a);t=make(db,task_people);card=attach(db,b,t,a)
    async def fail(*args,**kwargs):raise OSError('private database /secret/internal-path')
    monkeypatch.setattr(ts,'attach_files',fail)
    response=post(client_for(a),db,b,'upload',card=card.id,version=t.version)
    assert response.status_code==422
    assert 'Dateien konnten nicht gespeichert' in response.json()['detail']
    assert 'internal-path' not in response.text and '/secret/' not in response.text


def test_survey_cards_keep_live_status_and_source_permissions(db,task_people,monkeypatch):
    import secrets
    from app import main
    from app.db import Vote,VoteShare
    a,_,reader,_=task_people
    monkeypatch.setattr(main,'enabled_modules',lambda:{'tasks','polls'})
    vote=Vote(owner_id=a.id,title='Teamentscheidung',public_token=secrets.token_hex(20));db.add(vote);db.commit()
    try:
        b=board(db,a,mode='free');member(db,b,reader,1)
        key=f'survey:vote:{vote.id}'
        assert key in kb.source_items(db,a) and key not in kb.source_items(db,reader)
        assert post(client_for(a),db,b,'attach',column=kb.columns(db,b)[0].id,source=key).status_code==200
        vote.title='Aktualisierte Entscheidung';vote.status='closed';db.commit()
        visible=kb.visible_cards(db,a,b)
        assert visible[0]['source']['title']==vote.title
        assert visible[0]['source']['status']!='Entwurf'
        page=client_for(a).get(f'/tasks/boards/{b.id}?kind=task')
        assert page.status_code==200 and 'data-kind="source"' not in page.text
        page=client_for(a).get(f'/tasks/boards/{b.id}?kind=survey&q=Aktualisierte')
        assert page.status_code==200 and 'data-kind="source"' in page.text
        assert not kb.visible_cards(db,reader,b)
        share=VoteShare(vote_id=vote.id,user_id=reader.id,level=1);db.add(share);db.commit()
        assert kb.visible_cards(db,reader,b)[0]['source']['title']==vote.title
        db.delete(share);db.commit();assert not kb.visible_cards(db,reader,b)
    finally:db.delete(vote);db.commit()


def test_neutral_column_preserves_status_on_move_create_attach_and_status_change(db,task_people):
    a=task_people[0];b=board(db,a);c=client_for(a)
    assert post(c,db,b,'column',title='Ideenspeicher',status='').status_code==200
    neutral=kb.columns(db,b)[-1]
    assert neutral.status==''
    task=make(db,task_people);card=attach(db,b,task,a)
    assert post(c,db,b,'move',card=card.id,version=task.version,column=neutral.id).status_code==200
    db.refresh(task);db.refresh(card);assert task.status=='open' and card.column_id==neutral.id
    assert post(c,db,b,'status',card=card.id,version=task.version,status='in_progress').status_code==200
    db.refresh(task);assert task.status=='in_progress'
    assert next(v for v in kb.visible_cards(db,a,b) if v['card'].id==card.id)['column'].id==neutral.id
    assert post(c,db,b,'create',column=neutral.id,title='Neutrale Aufgabe').status_code==200
    created=db.scalar(select(Task).where(Task.title=='Neutrale Aufgabe'))
    assert created.status=='open'
    assert db.scalar(select(TaskBoardCard).where(TaskBoardCard.task_id==created.id)).column_id==neutral.id
    other=make(db,task_people)
    assert post(c,db,b,'attach',column=neutral.id,task=other.id).status_code==200
    assert db.scalar(select(TaskBoardCard).where(TaskBoardCard.task_id==other.id)).column_id==neutral.id


def test_column_mapping_can_be_changed_inline_without_mutating_tasks(db,task_people):
    a,_,editor,reader=task_people;b=board(db,a);t=make(db,task_people);card=attach(db,b,t,a);col=kb.columns(db,b)[0];c=client_for(a)
    member(db,b,editor,2);member(db,b,reader,1)
    for person in (editor,reader):
        assert post(client_for(person),db,b,'column',column=col.id,title='Unzulässig',status='').status_code==404
    version=b.version
    assert post(c,db,b,'column',column=col.id,title='Eingang',status='').status_code==200
    db.refresh(t);db.refresh(col);assert t.status=='open' and col.title=='Eingang' and col.status==''
    assert post(c,db,b,'column',column=col.id,title='Erledigungen',status='done').status_code==200
    db.refresh(t);assert t.status=='open'
    assert post(c,db,b,'column',column=col.id,title='Falsch',status='invalid').status_code==422
    assert post(c,db,b,'column',column=col.id,title='',status='').status_code==422
    response=c.post(f'/tasks/boards/{b.id}/action',data={'csrf':csrf_of(c.get(f'/tasks/boards/{b.id}').text),'board_version':version,'action':'column','column':col.id,'title':'Alt','status':''},headers={'Accept':'application/json'})
    assert response.status_code==409


def test_neutral_move_still_checks_version_and_status_rules(db,task_people):
    a=task_people[0];b=board(db,a);t=make(db,task_people);card=attach(db,b,t,a);c=client_for(a)
    assert post(c,db,b,'column',title='Ablage',status='').status_code==200
    neutral=kb.columns(db,b)[-1]
    old=t.version
    assert post(c,db,b,'status',card=card.id,version=t.version,status='in_progress').status_code==200
    assert post(c,db,b,'move',card=card.id,version=old,column=neutral.id).status_code==422
    db.refresh(t)
    check=TaskCheck(task_id=t.id,title='Pflichtpunkt');db.add(check);db.commit()
    assert post(c,db,b,'move',card=card.id,version=t.version,column=neutral.id).status_code==200
    db.refresh(t)
    assert post(c,db,b,'status',card=card.id,version=t.version,status='done').status_code==422
    db.refresh(t);assert t.status=='in_progress'


def test_legacy_board_view_preserves_task_filters_without_second_board_ui(db,task_people):
    c=client_for(task_people[0])
    response=c.get('/tasks?view=board&perspective=delegated&tag=Planung',follow_redirects=False)
    assert response.status_code==303
    target=response.headers['location']
    assert 'view=list' in target and 'perspective=delegated' in target and 'tag=Planung' in target
    page=c.get(target)
    assert page.status_code==200 and 'Aufgabenboards öffnen' in page.text
    assert 'data-task-column=' not in page.text


def test_undo_from_status_column_restores_status_in_neutral_column(db,task_people):
    a=task_people[0];b=board(db,a);c=client_for(a);t=make(db,task_people)
    assert post(c,db,b,'column',title='Sammlung',status='').status_code==200
    neutral=kb.columns(db,b)[-1];card=kb.add_native(db,a,b,neutral,t);db.commit()
    progress=next(col for col in kb.columns(db,b) if col.status=='in_progress')
    assert post(c,db,b,'move',card=card.id,version=t.version,column=progress.id).status_code==200
    db.refresh(t);assert t.status=='in_progress'
    assert post(c,db,b,'move',card=card.id,version=t.version,column=neutral.id,undo='1',restore_status='open').status_code==200
    db.refresh(t);db.refresh(card);assert t.status=='open' and card.column_id==neutral.id


def test_status_board_source_placement_does_not_change_source(db,task_people,monkeypatch):
    a=task_people[0];b=board(db,a);c=client_for(a)
    key='survey:vote:example';source=dict(title='Umfrage',source='survey',source_label='Umfrage',href='/umfragen',detail='Offen',status='Offen',due=None)
    monkeypatch.setattr(kb,'source_items',lambda db,u:{key:source})
    assert post(c,db,b,'column',title='Sammlung',status='').status_code==200
    cols=kb.columns(db,b)
    assert post(c,db,b,'attach',column=cols[-1].id,source=key).status_code==200
    card=db.scalar(select(TaskBoardCard).where(TaskBoardCard.board_id==b.id))
    assert post(c,db,b,'move',card=card.id,column=cols[3].id).status_code==200
    assert source['status']=='Offen'
    monkeypatch.setattr(kb,'source_items',lambda db,u:{})
    assert post(c,db,b,'move',card=card.id,column=cols[-1].id).status_code==404


def test_duplicate_status_columns_honor_selected_destination(db,task_people):
    a=task_people[0];b=board(db,a);c=client_for(a);t=make(db,task_people)
    assert post(c,db,b,'column',title='Zweiter Eingang',status='open').status_code==200
    duplicate=kb.columns(db,b)[-1]
    card=kb.add_native(db,a,b,duplicate,t);db.commit();assert card.column_id==duplicate.id
    assert post(c,db,b,'move',card=card.id,version=t.version,column=kb.columns(db,b)[0].id).status_code==200
    db.refresh(t)
    assert post(c,db,b,'move',card=card.id,version=t.version,column=duplicate.id).status_code==200
    db.refresh(card);assert card.column_id==duplicate.id


def test_card_presentation_is_board_local_and_validated(db,task_people):
    a=task_people[0];b=board(db,a);other=board(db,a,'Andere Ansicht');t=make(db,task_people)
    card=attach(db,b,t,a);second=attach(db,other,t,a);c=client_for(a)
    assert post(c,db,b,'edit',card=card.id,version=t.version,card_type='idea',cover_color='grape').status_code==200
    db.refresh(card);db.refresh(second);db.refresh(t)
    assert (card.card_type,card.cover_color)==('idea','grape')
    assert (second.card_type,second.cover_color)==('task','') and t.status=='open'
    title=t.title
    assert post(c,db,b,'edit',card=card.id,version=t.version,title='Nicht speichern',card_type='bad').status_code==422
    db.refresh(t);db.refresh(card)
    assert t.title==title and card.card_type=='idea'
    # A stale board rejects presentation changes as well.
    db.refresh(b);version=b.version;token=csrf_of(c.get(f'/tasks/boards/{b.id}').text)
    assert post(c,db,b,'edit',card=card.id,version=t.version,cover_color='teal').status_code==200
    response=c.post(f'/tasks/boards/{b.id}/action',data=dict(csrf=token,board_version=version,action='edit',card=card.id,version=t.version,cover_color='pink'),headers={'Accept':'application/json'})
    assert response.status_code==409
    db.refresh(card);assert card.cover_color=='teal'


def test_card_type_create_and_filter(db,task_people):
    a=task_people[0];b=board(db,a);c=client_for(a);col=kb.columns(db,b)[0]
    for kind in kb.CARD_TYPES:
        assert post(c,db,b,'create',column=col.id,title='Karte '+kind,card_type=kind).status_code==200
    cards=list(db.scalars(select(TaskBoardCard).where(TaskBoardCard.board_id==b.id)))
    assert {card.card_type for card in cards}==set(kb.CARD_TYPES)
    assert 'Karte idea' in c.get(f'/tasks/boards/{b.id}?kind=idea').text
    assert c.get(f'/tasks/boards/{b.id}?kind=idea').text.count('data-card-json=')==1
    assert post(c,db,b,'create',column=col.id,title='Ungültige Karte',card_type='invalid').status_code==422
    assert not db.scalar(select(Task.id).where(Task.title=='Ungültige Karte'))


def test_card_json_badges_and_access(db,task_people):
    from app.db import utcnow
    from app.task_models import TaskComment,TaskAttachment
    a,_,reader,outsider=task_people;b=board(db,a);t=make(db,task_people);card=attach(db,b,t,a)
    membership=member(db,b,reader,1)
    db.add_all([TaskCheck(task_id=t.id,title='Offen'),TaskCheck(task_id=t.id,title='Fertig',done=True),
        TaskComment(task_id=t.id,author_id=a.id,body='Kommentar **fett** <script>alert(1)</script>'),TaskComment(task_id=t.id,author_id=a.id,body='Entfernt',removed_at=utcnow()),
        TaskAttachment(task_id=t.id,name='plan.txt',storage_key='a'*64,size=5,mime='text/plain',uploaded_by=a.id)])
    db.commit();c=client_for(reader);url=f'/tasks/boards/{b.id}/cards/{card.id}'
    response=c.get(url,headers={'Accept':'application/json'});assert response.status_code==200
    data=response.json();assert data['level']==1
    assert (data['card']['checks'],data['card']['checked'],data['card']['comments'],data['card']['files'])==(2,1,1,1)
    assert [item['body'] for item in data['comments']]==['Kommentar **fett** <script>alert(1)</script>']
    assert '<strong>fett</strong>' in data['comments'][0]['html']
    assert '<script>' not in data['comments'][0]['html']
    assert data['files'][0]['name']=='plan.txt'
    assert client_for(outsider).get(url,headers={'Accept':'application/json'}).status_code==404
    db.delete(membership);db.commit()
    assert c.get(url,headers={'Accept':'application/json'}).status_code==404


def test_source_preview_rechecks_original_access(db,task_people,monkeypatch):
    a,_,reader,_=task_people;b=board(db,a,mode='free');member(db,b,reader,1)
    key='application:synthetic'
    monkeypatch.setattr(kb,'source_items',lambda db,u:{key:dict(title='Fachinhalt',href='/synthetic',source='application',source_label='Antrag',detail='Prüfen',due=None)} if u.id==a.id else {})
    c=client_for(a);assert post(c,db,b,'attach',column=kb.columns(db,b)[0].id,source=key).status_code==200
    card=db.scalar(select(TaskBoardCard).where(TaskBoardCard.board_id==b.id));url=f'/tasks/boards/{b.id}/cards/{card.id}'
    assert c.get(url,headers={'Accept':'application/json'}).json()['card']['title']=='Fachinhalt'
    assert client_for(reader).get(url,headers={'Accept':'application/json'}).status_code==404
    monkeypatch.setattr(kb,'source_items',lambda db,u:{})
    assert c.get(url,headers={'Accept':'application/json'}).status_code==404


def test_old_card_schema_adds_presentation_defaults_without_rewriting_rows(tmp_path,monkeypatch):
    from sqlalchemy import create_engine,text
    from app import db as database
    engine=create_engine('sqlite:///'+str(tmp_path/'old-board.sqlite'))
    database.Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE task_board_cards DROP COLUMN card_type'))
        connection.execute(text('ALTER TABLE task_board_cards DROP COLUMN cover_color'))
        connection.execute(text('INSERT INTO task_board_cards (id,board_id,column_id,task_id,position,shareable) VALUES (1,9,7,5,3,1)'))
    monkeypatch.setattr(database,'engine',engine)
    database._migrate();database._migrate()
    with engine.connect() as connection:
        row=connection.execute(text('SELECT board_id,column_id,task_id,position,shareable,card_type,cover_color FROM task_board_cards')).one()
        assert tuple(row)==(9,7,5,3,1,'task','')
    engine.dispose()


def test_badge_counts_use_batched_queries(db,task_people):
    from sqlalchemy import event
    a=task_people[0];b=board(db,a)
    for i in range(12):attach(db,b,make(db,task_people),a)
    visible=kb.visible_cards(db,a,b);queries=[]
    def count(*args):queries.append(args[2])
    event.listen(db.bind,'before_cursor_execute',count)
    try:
        stats=kb.card_statistics(db,visible)
        summaries=[kb.card_summary(db,item,stats) for item in visible]
    finally:event.remove(db.bind,'before_cursor_execute',count)
    assert len(summaries)==12 and len(queries)==3
