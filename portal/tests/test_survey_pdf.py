"""DIN A4 exports: layout geometry, aggregate-only output and access control."""
import io
import json

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app import forms as fm, survey_pdf
from app.db import (Form, FormResponse, Poll, PollOption, PollParticipant,
                    SessionLocal, User, utcnow)
from app.security import hash_password
from conftest import login, settings

PASS = "survey-report-test-password-123"


@pytest.fixture
def reports():
    settings(module_forms="1", module_polls="1")
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@example.org"))
        viewer = User(name="PDF outsider", email="survey-pdf-outsider@example.org",
                      password_hash=hash_password(PASS), permissions="",
                      active=True, must_change_password=False)
        db.add(viewer)
        db.flush()
        form = Form(owner_id=admin.id, title="Prüfung digitale Arbeitsmittel",
                    description="Eine Umfrage zur Benutzerfreundlichkeit.",
                    kind="survey", active=True, anonymous=True, notify=False,
                    schema_json=json.dumps(fm.clean_schema([
                        {"id": "q1", "type": "radio", "title": "Wie zufrieden?",
                         "options": [{"id": "a", "label": "Sehr zufrieden"},
                                     {"id": "b", "label": "Weniger zufrieden"}]},
                        {"id": "q2", "type": "long", "title": "Vertraulicher Kommentar"},
                    ])))
        poll = Poll(owner_id=admin.id, title="Teamtag Terminfindung",
                    description="Abstimmung zum Termin für den Teamtag.",
                    location="Bürgerhaus", published_at=utcnow(), closed=False)
        db.add_all([form, poll])
        db.flush()
        db.add(FormResponse(form_id=form.id, answers_json=json.dumps(
            {"q1": "Sehr zufrieden", "q2": "PERSONAL_SECRET_TEXT"}),
            email="person-private@example.org", name="Private Person"))
        option = PollOption(poll_id=poll.id, starts_at=utcnow(), note="Besprechung")
        db.add(option)
        db.flush()
        db.add(PollParticipant(poll_id=poll.id, name="DoNotPrintPerson",
                               email="do-not-print@example.org",
                               edit_token="survey-pdf-personal-test-token",
                               answered_at=utcnow(), answers_json=json.dumps({str(option.id): "yes"}),
                               comment="DoNotPrintPrivateComment"))
        db.commit()
        ids = dict(form=form.id, poll=poll.id, viewer=viewer.id)
    yield ids
    with SessionLocal() as db:
        for model, ident in ((Form, ids["form"]), (Poll, ids["poll"]),
                             (User, ids["viewer"])):
            row = db.get(model, ident)
            if row:
                db.delete(row)
        db.commit()


def _read(data):
    assert data.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(data))
    assert reader.pages
    for page in reader.pages:
        # DIN A4 geometry in PostScript points
        assert abs(float(page.mediabox.width) - 595.28) < 1
        assert abs(float(page.mediabox.height) - 841.89) < 1
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_manager_downloads_branded_form_and_poll_pdf_without_private_answers(reports):
    c = login("admin@example.org", "admin-passwort-123")
    for kind, resource in (("forms", reports["form"]), ("polls", reports["poll"])):
        result = c.get(f"/{kind}/{resource}/export.pdf")
        assert result.status_code == 200
        assert result.headers["content-type"].startswith("application/pdf")
        assert result.headers["cache-control"] == "private, no-store"
        assert "attachment" in result.headers["content-disposition"]
        pdftext = _read(result.content)
        assert "ERGEBNISBERICHT" in pdftext
        assert "Seite 1" in pdftext
        assert "PERSONAL_SECRET_TEXT" not in pdftext
        assert "Private Person" not in pdftext
        assert "do-not-print@example.org" not in pdftext
        assert "DoNotPrintPrivateComment" not in pdftext
    assert "Prüfung digitale Arbeitsmittel" in _read(c.get(
        f'/forms/{reports["form"]}/export.pdf').content)
    assert "Teamtag Terminfindung" in _read(c.get(
        f'/polls/{reports["poll"]}/export.pdf').content)
    assert "Ergebnisbericht (DIN A4)" in c.get(f'/forms/{reports["form"]}/results').text
    assert "Ergebnisbericht (DIN A4)" in c.get(f'/polls/{reports["poll"]}').text


def test_pdf_requires_same_manager_acl_as_csv_and_stays_closed_to_public(reports):
    outsider = login("survey-pdf-outsider@example.org", PASS)
    guest = __import__("conftest").client()
    for kind, ident in (("forms", reports["form"]), ("polls", reports["poll"])):
        assert outsider.get(f"/{kind}/{ident}/export.pdf").status_code in (403, 404)
        assert guest.get(f"/{kind}/{ident}/export.pdf").status_code in (302, 303, 401, 403, 404)


def test_online_application_excluded_from_survey_pdf(reports):
    with SessionLocal() as db:
        db.get(Form, reports["form"]).kind = "application"
        db.commit()
    c = login("admin@example.org", "admin-passwort-123")
    assert c.get(f'/forms/{reports["form"]}/export.pdf').status_code == 404


def test_report_handles_empty_and_long_content_over_multiple_a4_pages(reports):
    with SessionLocal() as db:
        poll = db.get(Poll, reports["poll"])
        poll.description = "Lange Beschreibung " * 180
        for n in range(48):
            db.add(PollOption(poll_id=poll.id, starts_at=utcnow(),
                              note="Terminvorschlag " + str(n)))
        db.commit()
        content = survey_pdf.poll_report(db, poll)
    pdftext = _read(content)
    assert len(PdfReader(io.BytesIO(content)).pages) >= 2
    assert "Terminvorschlag" in pdftext
