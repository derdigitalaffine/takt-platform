import json
from datetime import timedelta
import pytest
from fastapi import HTTPException
from app import seminars as sm, seminar_series as series, seminar_planning as plan
from app.db import SeminarSession
from app.routes_seminar_planning import save, state
from conftest import login, csrf_of
from test_seminars import people, make, rec
from test_seminar_planning import data


@pytest.mark.parametrize('kind',['admin','planner','lead','teacher','user'])
def test_role_routes_and_scope(db,people,kind):
    owner,assigned,teacher,normal=people
    row,term=make(db,people)
    row.lecturers_json=json.dumps([teacher.id])
    row.lead_id=normal.id
    row.planning_json=json.dumps({'planner_ids':[assigned.id]})
    other=SeminarSession(seminar_id=row.id,title='Restricted term',starts_at=term.starts_at+timedelta(days=7),ends_at=term.ends_at+timedelta(days=7),lecturers_json='[]')
    db.add(other);db.flush()
    a=rec(db,row,term,assigned);sm.request_place(db,row,a)
    b=sm.new_enrollment(db,row,other.id,'Restricted participant','restricted@example.org',normal);sm.request_place(db,row,b)
    unrelated,_=make(db,people);db.commit()
    if kind=='admin':c=login('admin@example.org','admin-passwort-123')
    else:c=login({'planner':assigned,'lead':normal,'teacher':teacher,'user':assigned}[kind].email,'passwort-test-123')
    if kind=='user':row.planning_json='{}';db.commit()
    full=kind in {'admin','planner','lead'}
    for suffix in ('planen','edit','mail','organisation'):
        assert c.get(f'/seminare/{row.id}/{suffix}').status_code==(200 if full else 404)
    assert c.get(f'/seminare/{row.id}').status_code==200
    assert c.get(f'/seminare/{row.id}/terms/{term.id}').status_code==(404 if kind=='user' else 200)
    assert c.get(f'/seminare/{row.id}/durchfuehrung/{other.id}').status_code==(200 if full else 404)
    assert c.get(f'/seminare/{unrelated.id}/planen').status_code==(200 if kind=='admin' else 404)
    csrf=csrf_of(c.get(f'/seminare/{row.id}').text)
    if not full:
        assert c.post(f'/seminare/{row.id}/planen',json={'csrf':csrf}).status_code==404
        for suffix in ('edit','publish','invite'):
            assert c.post(f'/seminare/{row.id}/{suffix}',data={'csrf':csrf}).status_code==404
    if kind=='user':
        assert c.get(f'/seminare/{row.id}/participants').status_code==404
        return
    participants=c.get(f'/seminare/{row.id}/participants')
    assert participants.status_code==200
    assert ('Restricted participant' in participants.text)==full
    for suffix in ('participants','participants.csv','participants.pdf','materials'):
        assert c.get(f'/seminare/{row.id}/{suffix}?tid={other.id}').status_code==(200 if full else 404)
    for scope in (0,term.id,other.id):
        result=c.post(f'/seminare/{row.id}/materials',data={'csrf':csrf,'action':'markdown','title':'Material','body':'Content','scope_id':scope})
        assert result.status_code==(303 if full or scope==term.id else 404)
    if kind=='teacher':assert not series.whole_staff(db,teacher,row)


def test_planner_roundtrip_validation_revocation(db,people):
    owner,assigned,teacher,_=people
    value=data(action='draft',planner_ids=[assigned.id,str(teacher.id),assigned.id]);value['terms']=plan.preview(value)['terms']
    row=save(db,owner,value);db.commit()
    assert state(db,row)['planner_ids']==[assigned.id,teacher.id]
    assert sm.may_plan(db,assigned,row) and not assigned.can('seminars')
    c=login(assigned.email,'passwort-test-123')
    page=c.get(f'/seminare/{row.id}/planen');assert page.status_code==200
    assert 'id="sp-planners"' in page.text and 'multiple' in page.text
    csrf=csrf_of(page.text)
    preview={'csrf':csrf,'seminar_id':row.id,'schedule':value['schedule'],'locations':value['locations']}
    assert c.post('/seminare/planen/vorschau',json=preview).status_code==200
    assert c.post('/seminare/planen/vorschau',json={**preview,'seminar_id':None}).status_code==403
    assert c.get('/seminare/planen').status_code==403
    loaded=state(db,row);loaded.update(csrf=csrf,action='draft',planner_ids=[teacher.id])
    assert c.post(f'/seminare/{row.id}/planen',json=loaded).status_code==200
    assert c.get(f'/seminare/{row.id}/planen').status_code==404
    db.expire_all();assert sm.planner_ids(row)==[teacher.id]
    teacher.active=False;db.commit();assert not sm.may_plan(db,teacher,row)
    with pytest.raises(HTTPException):save(db,owner,{**state(db,row),'action':'draft','planner_ids':[teacher.id]},row)
    db.rollback()


@pytest.mark.parametrize('raw',['null','[]','invalid','{"planner_ids":"2"}','{"planner_ids":[true,"2",{},null]}'])
def test_malformed_planners_fail_closed(db,people,raw):
    row,_=make(db,people);row.planning_json=raw
    assert sm.planner_ids(row)==[] and not sm.may_plan(db,people[1],row)


def test_staff_notifications_follow_series_and_term_responsibility(db,people,monkeypatch):
    owner,planner,teacher,lead=people
    row,term=make(db,people)
    row.planning_json=json.dumps({'planner_ids':[planner.id]})
    row.lead_id=lead.id;row.lecturers_json=json.dumps([teacher.id]);term.lecturers_json='[]';db.commit()
    recipients=[]
    monkeypatch.setattr(series.notify,'enqueue',lambda db,email,*args,**kwargs:recipients.append(email))
    series.staff_message(db,row,'Test','Test',[term])
    assert set(recipients)=={owner.email,planner.email,lead.email}
    recipients.clear();term.lecturers_json=json.dumps([teacher.id]);db.commit()
    series.staff_message(db,row,'Test','Test',[term])
    assert teacher.email in recipients
    recipients.clear();series.staff_message(db,row,'Test','Test',[term],only_owner=True)
    assert set(recipients)=={owner.email,planner.email,lead.email}
