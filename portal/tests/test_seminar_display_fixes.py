import re

from app import seminar_learning as learning, seminar_operations as ops
from conftest import client, login
from test_seminars import make, people, rec


def test_mail_term_dates_are_german(db, people):
    row, term = make(db, people)
    text = ops.render_message('{termine}', row, 'Person', 'https://example.invalid', [term])
    assert re.search(r'\b\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}\b', text)
    assert not re.search(r'\b\d{4}-\d{2}-\d{2}(?:T| )\d{2}:\d{2}\b', text)


def test_participant_pdf_table_stays_inside_a4_width():
    available = 595.275590551 - 72
    widths = learning._table_widths(4, available)
    assert len(widths) == 4
    assert sum(widths) <= available + 0.01
    pdf = learning.pdf_document(
        'Teilnehmerliste',
        ['02.11.2026 14:00 · Raum mit einem längeren Namen'],
        [
            ['Name', 'Organisation', 'Teilnahmeart', 'Unterschrift'],
            ['Eine Person mit einem sehr langen Namen', 'Eine Organisation mit einem besonders langen Namen und Zusatz', 'Vor Ort', ''],
        ],
    )
    assert pdf.startswith(b'%PDF')


def test_participant_quick_view_is_staff_only_and_links_full_list(db, people):
    row, term = make(db, people)
    rec(db, row, term, people[1], status='confirmed')
    rec(db, row, term, people[2], status='pending')
    db.commit()

    staff = login(people[0].email, 'passwort-test-123')
    page = staff.get(f'/seminare/{row.id}')
    assert page.status_code == 200
    assert 'data-participant-preview' in page.text
    assert f'/seminare/{row.id}/participants' in page.text
    overview = staff.get('/seminare')
    assert overview.status_code == 200
    assert f'/seminare/{row.id}/participants?tid={term.id}' in overview.text

    public = client().get(f'/seminare/{row.id}')
    assert public.status_code == 200
    assert 'data-participant-preview' not in public.text
    public_overview = client().get('/seminare')
    assert 'data-participant-preview' not in public_overview.text

    pdf = staff.get(f'/seminare/{row.id}/participants.pdf')
    assert pdf.status_code == 200
    assert pdf.headers['content-type'].startswith('application/pdf')
    assert pdf.content.startswith(b'%PDF')


def test_admin_sees_participant_quick_view_in_seminar_overview(db, people):
    row, term = make(db, people)
    rec(db, row, term, people[1], status='confirmed')
    people[3].is_admin = True
    db.commit()

    admin = login(people[3].email, 'passwort-test-123')
    page = admin.get('/seminare')
    assert page.status_code == 200
    assert f'/seminare/{row.id}/participants?tid={term.id}' in page.text
    participants = admin.get(f'/seminare/{row.id}/participants')
    assert participants.status_code == 200
    assert people[1].name in participants.text


def preview_blocks(html):
    return {int(tid):(attributes,body) for attributes,tid,body in re.findall(
        r'<details([^>]*data-participant-preview[^>]*data-term-id="(\d+)"[^>]*)>(.*?)</details>',html,re.S)}


def test_preview_is_per_term_collapsed_and_one_person_per_line(db,people):
    from datetime import timedelta
    from app.db import SeminarSession
    row,term=make(db,people,booking_mode='both')
    second=SeminarSession(seminar_id=row.id,title='Zweiter Termin',starts_at=term.starts_at+timedelta(days=7),ends_at=term.ends_at+timedelta(days=7))
    db.add(second);db.flush()
    rec(db,row,term,people[1],status='confirmed')
    rec(db,row,second,people[2],status='confirmed')
    from app import seminars as sm
    sm.new_enrollment(db,row,0,'Ganze Reihe','series@example.org',status='confirmed')
    rec(db,row,term,people[3],status='pending');db.commit()
    staff=login(people[0].email,'passwort-test-123')
    for url in ('/seminare',f'/seminare/{row.id}'):
        blocks=preview_blocks(staff.get(url).text)
        assert term.id in blocks and second.id in blocks
        first_attrs,first=blocks[term.id];second_attrs,last=blocks[second.id]
        assert 'open' not in first_attrs and 'open' not in second_attrs
        assert people[1].name in first and people[1].name not in last
        assert people[2].name in last and people[2].name not in first
        for body in (first,last):
            assert 'Ganze Reihe' in body
            assert people[3].name not in body
            assert len(re.findall(r'<li\b',body))==2
            assert '(2)' in body
        assert f'participants?tid={term.id}' in first
        assert f'participants?tid={second.id}' in last


def test_preview_respects_effective_term_assignment(db,people):
    import json
    from datetime import timedelta
    from app.db import SeminarSession
    row,term=make(db,people);row.lecturers_json=json.dumps([people[2].id])
    second=SeminarSession(seminar_id=row.id,starts_at=term.starts_at+timedelta(days=7),ends_at=term.ends_at+timedelta(days=7),lecturers_json='[]')
    db.add(second);db.flush()
    rec(db,row,second,people[1],status='confirmed');db.commit()
    teacher=login(people[2].email,'passwort-test-123')
    for url in ('/seminare',f'/seminare/{row.id}'):
        blocks=preview_blocks(teacher.get(url).text)
        assert term.id in blocks and second.id not in blocks
        assert 'Noch keine bestätigten Anmeldungen.' in blocks[term.id][1]



def test_single_term_pdf_header_and_participants_are_scoped(db,people):
    import io
    import json
    from datetime import timedelta
    from pypdf import PdfReader
    from app.db import SeminarSession, to_local
    row,term=make(db,people)
    row.title='Fortbildungsreihe Digitalisierung'
    term.title='Dokumentenmanagement in der Praxis';term.location='Rathaus, Schulungsraum 2'
    term.delivery_mode='hybrid';term.lecturers_json=json.dumps([people[2].id])
    other=SeminarSession(seminar_id=row.id,title='Anderer Termin',location='Anderer Raum',starts_at=term.starts_at+timedelta(days=7),ends_at=term.ends_at+timedelta(days=7))
    db.add(other);db.flush()
    rec(db,row,term,people[1],status='confirmed');rec(db,row,other,people[3],status='confirmed');db.commit()
    staff=login(people[0].email,'passwort-test-123')
    response=staff.get(f'/seminare/{row.id}/participants.pdf?tid={term.id}')
    assert response.status_code==200
    reader=PdfReader(io.BytesIO(response.content))
    text=' '.join(page.extract_text() for page in reader.pages)
    for value in (row.title,'Einzeltermin: '+term.title,
                  'Beginn: '+to_local(term.starts_at).strftime('%d.%m.%Y %H:%M')+' Uhr',
                  'Ende: '+to_local(term.ends_at).strftime('%d.%m.%Y %H:%M')+' Uhr',
                  'Ort: '+term.location,'Hybrid: vor Ort oder online',people[1].name):
        assert value in text
    assert other.title not in text and other.location not in text and people[3].name not in text
    assert text.index(term.title)<text.index('Unterschrift')
    teacher=login(people[2].email,'passwort-test-123')
    assert teacher.get(f'/seminare/{row.id}/participants.pdf?tid={other.id}').status_code==404


def test_internal_seminar_requires_login_without_disclosing_content(db,people):
    row,term=make(db,people);row.channels='internal';row.title='Vertrauliches Seminarthema';db.commit()
    page=client().get(f'/seminare/{row.id}')
    assert page.status_code==401
    assert 'Dieser Bereich erfordert eine Anmeldung' in page.text
    assert f'/login?next=%2Fseminare%2F{row.id}' in page.text
    assert row.title not in page.text
    assert page.headers['cache-control']=='no-store'
    assert login(people[1].email,'passwort-test-123').get(f'/seminare/{row.id}').status_code==200
    assert client().get('/seminare/999999999').status_code==404
