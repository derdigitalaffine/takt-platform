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
    script = staff.get('/static/seminar_participant_preview.js')
    assert script.status_code == 200
    assert 'Angemeldet' in script.text

    public = client().get(f'/seminare/{row.id}')
    assert public.status_code == 200
    assert 'data-participant-preview' not in public.text

    pdf = staff.get(f'/seminare/{row.id}/participants.pdf')
    assert pdf.status_code == 200
    assert pdf.headers['content-type'].startswith('application/pdf')
    assert pdf.content.startswith(b'%PDF')
