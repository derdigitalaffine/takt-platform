from datetime import timedelta
import pytest
from fastapi import HTTPException
from app.main import _plan_values
from app import seminar_planning
from app.db import Meeting
from conftest import login,csrf_of


@pytest.mark.parametrize('start,end,minutes',[
    ('2027-01-02T10:00','2027-01-02T11:15',75),
    ('2027-01-02T23:30','2027-01-03T01:00',90),
])
def test_meeting_duration_and_explicit_end_agree(start,end,minutes):
    assert _plan_values(start,str(minutes))==_plan_values(start,'60',end,'end')


@pytest.mark.parametrize('end',['','invalid','2027-01-02T09:00','2027-01-02T10:00','2027-01-04T10:00'])
def test_invalid_meeting_end_is_rejected(end):
    assert _plan_values('2027-01-02T10:00','60',end,'end')[2]


def test_create_edit_and_calendar_use_explicit_end(db):
    c=login('admin@example.org','admin-passwort-123')
    token=csrf_of(c.get('/meetings/plan').text)
    response=c.post('/meetings/plan',data={'csrf':token,'title':'Zeitbereich Test','start':'2027-01-02T10:00','timing_mode':'end','end':'2027-01-02T11:15'})
    assert response.status_code==303
    mid=int(response.headers['location'].split('/')[2]);meeting=db.get(Meeting,mid)
    try:
        assert meeting.duration_minutes==75
        assert 'value="75"' in c.get(f'/meetings/{mid}').text
        assert c.get(f'/meetings/{mid}/calendar.ics').status_code==200
        assert c.post(f'/meetings/{mid}/schedule',data={'csrf':token,'start':'2027-01-02T23:30','timing_mode':'end','end':'2027-01-03T01:00'}).status_code==303
        db.refresh(meeting);assert meeting.duration_minutes==90
        assert c.post(f'/meetings/{mid}/schedule',data={'csrf':token,'start':'2027-01-02T10:00','timing_mode':'duration','duration':'45','end':'invalid'}).status_code==303
        db.refresh(meeting);assert meeting.duration_minutes==45
    finally:db.delete(meeting);db.commit()


def test_seminar_recurrence_end_and_duration_agree():
    schedule={'kind':'weekly','first':'2027-01-02','time':'23:30','duration':90,'count':3}
    duration=seminar_planning.preview({'schedule':schedule})
    explicit=seminar_planning.preview({'schedule':{**schedule,'timing_mode':'end','ends_at':'2027-01-03T01:00','duration':0}})
    assert duration==explicit
    for end in ('','2027-01-02T23:30','2027-01-01T12:00','2027-01-12T12:00'):
        with pytest.raises(HTTPException):seminar_planning.preview({'schedule':{**schedule,'timing_mode':'end','ends_at':end}})
