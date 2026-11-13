"""Protected RLP staff council paper-election workspace regression tests.

No online vote/token routes and no legal release are in scope. These tests exercise
module gating, object ACL, form revisions, secure PDF, CSRF and board-role review.
"""
import io
from zipfile import ZipFile
from uuid import uuid4
from sqlalchemy import select
from app.db import Organization, SessionLocal, User
from app.prwahl_models import PRElection, PRDocument, PRMandate
from app.org_models import OrgMembership
from app.routes_prwahl import _eligible_staff_ids
from app.security import hash_password
from conftest import csrf_of, login, settings


def _user(*, admin=False, setup=False):
    email = f"prwahl-{uuid4().hex[:16]}@example.org"
    with SessionLocal() as db:
        db.add(User(email=email, name="Test Wahlberechtigung", password_hash=hash_password("passwort-1234"),
                    is_admin=admin, active=True, must_change_password=False,
                    permissions="video,prwahl_setup" if setup else "video"))
        db.commit()
    return login(email, "passwort-1234")


def _create(c):
    settings(module_prwahl="1")
    with SessionLocal() as db:
        org = db.scalar(select(Organization).where(Organization.active.is_(True)))
        assert org is not None
        org_id = org.id
    form = c.get("/personalratswahl")
    assert form.status_code == 200
    response = c.post("/personalratswahl/neu", data={
        "csrf": csrf_of(form.text),
        "title": "Personalratswahl Test",
        "org_id": str(org_id),
        "body_type": "personalrat",
        "election_day": "2027-04-14",
        "election_end_day": "2027-04-14",
    })
    assert response.status_code == 303, response.text[:500]
    location = response.headers["location"]
    return int(location.rstrip("/").split("/")[-1])


def test_module_disabled_blocks_url_and_post():
    settings(module_prwahl="0")
    c = login("admin@example.org", "admin-passwort-123")
    assert c.get("/personalratswahl").status_code == 404
    assert c.get("/personalratswahl/1").status_code == 404
    response = c.post("/personalratswahl/neu", data={"title": "Test"})
    assert response.status_code == 404
    settings(module_prwahl="1")


def test_setup_is_explicit_and_admin_without_mandate_cannot_read_election():
    manager = _user(setup=True)
    eid = _create(manager)
    with SessionLocal() as db:
        election = db.get(PRElection, eid)
        assert election is not None and election.legal_gate == "pending"
        assert db.scalar(select(PRMandate).where(PRMandate.election_id == eid)) is not None
    other_admin = _user(admin=True)
    assert other_admin.get(f"/personalratswahl/{eid}").status_code == 404
    assert other_admin.get(f"/personalratswahl/{eid}/dokumente/1/pdf").status_code == 404
    unauthorized = _user()
    listing = unauthorized.get("/personalratswahl")
    assert listing.status_code == 200
    assert "Personalratswahl Test" not in listing.text
    assert unauthorized.post("/personalratswahl/neu", data={
        "csrf": csrf_of(listing.text), "title": "Unzulässig", "org_id": 1,
    }).status_code == 403
    assert unauthorized.get(f"/personalratswahl/{eid}").status_code == 404


def test_paper_form_encrypted_versioned_downloads_with_csrf_and_scope():
    owner = _user(setup=True)
    eid = _create(owner)
    edit_url = f"/personalratswahl/{eid}/dokumente/neu/board_notice"
    form = owner.get(edit_url)
    assert form.status_code == 200
    assert "A4-Layoutvorschau" in form.text
    document_url = f"/personalratswahl/{eid}/dokumente/speichern"
    secret = "GeheimnisNurImDokumentenInhalt"
    payload = {"csrf": csrf_of(form.text), "kind": "board_notice", "document_id": "0",
               "board_members": secret, "location": "Rathaus", "issued_on": "2026-11-30"}
    assert owner.post(document_url, data={**payload, "csrf": "invalid"}).status_code == 400
    saved = owner.post(document_url, data=payload)
    assert saved.status_code == 303
    docid = int(saved.headers["location"].rstrip("/").split("/")[-1])
    with SessionLocal() as db:
        first = db.get(PRDocument, docid)
        assert secret not in first.payload_enc
        assert first.revision == 1
        assert first.review_status == "draft"
    pdf = owner.get(f"/personalratswahl/{eid}/dokumente/{docid}/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert "no-store" in pdf.headers["cache-control"]
    docx = owner.get(f"/personalratswahl/{eid}/dokumente/{docid}/docx")
    assert docx.status_code == 200
    assert docx.content.startswith(b"PK")
    assert "no-store" in docx.headers["cache-control"]
    with ZipFile(io.BytesIO(docx.content)) as archive:
        assert "word/document.xml" in archive.namelist()
        assert secret.encode() in archive.read("word/document.xml")
    update_data = dict(payload, document_id=str(docid), board_members="Geändert")
    update_data["csrf"] = csrf_of(owner.get(f"/personalratswahl/{eid}/dokumente/{docid}").text)
    saved2 = owner.post(document_url, data=update_data)
    assert saved2.status_code == 303
    newer = int(saved2.headers["location"].rstrip("/").split("/")[-1])
    assert newer != docid
    with SessionLocal() as db:
        assert db.get(PRDocument, docid).current is False
        assert db.get(PRDocument, newer).revision == 2
        assert db.get(PRDocument, newer).current is True
    assert owner.post(document_url, data=update_data).status_code == 409
    page = owner.get(f"/personalratswahl/{eid}/dokumente/{newer}")
    assert page.status_code == 200
    assert "Fassung 1" in page.text and "Fassung 2" in page.text
    assert owner.get(f"/personalratswahl/{eid}/dokumente/{docid}/pdf").status_code == 200
    outsider = _user()
    assert outsider.get(f"/personalratswahl/{eid}/dokumente/{newer}").status_code == 404
    assert outsider.get(f"/personalratswahl/{eid}/dokumente/{newer}/pdf").status_code == 404
    assert outsider.get(f"/personalratswahl/{eid}/dokumente/{newer}/docx").status_code == 404


def test_form_review_requires_named_chair_and_traceable_reference():
    coordinator = _user(setup=True)
    eid = _create(coordinator)
    form = coordinator.get(f"/personalratswahl/{eid}/dokumente/neu/board_minutes")
    response = coordinator.post(f"/personalratswahl/{eid}/dokumente/speichern", data={
        "csrf": csrf_of(form.text), "kind": "board_minutes",
        "session": "Eröffnung", "decisions": "Beschluss, eigenhändige Signatur erforderlich",
    })
    docid = int(response.headers["location"].split("/")[-1])
    review = f"/personalratswahl/{eid}/dokumente/{docid}/pruefen"
    assert coordinator.post(review, data={
        "csrf": csrf_of(coordinator.get(f"/personalratswahl/{eid}").text),
        "resolution_reference": "Niederschrift am 13.11.2026",
    }).status_code == 403
    chair = _user()
    with SessionLocal() as db:
        chair_user = db.scalar(select(User).where(User.email.like("prwahl-%@example.org"))
                               .order_by(User.id.desc()))
        assert chair_user
        # appointment is documented but does not replace statutory board appointment
        chair_id = chair_user.id
    team_page = coordinator.get(f"/personalratswahl/{eid}?tab=board")
    assigned = coordinator.post(f"/personalratswahl/{eid}/team", data={
        "csrf": csrf_of(team_page.text), "user_id": chair_id,
        "role": "chair", "appointment_reference": "Beschluss 01 vom 13.11.2026",
    })
    assert assigned.status_code == 303
    chair_page = chair.get(f"/personalratswahl/{eid}/dokumente/{docid}")
    assert chair_page.status_code == 200 and "Interne Prüfung dokumentieren" in chair_page.text
    assert chair.post(review, data={
        "csrf": csrf_of(chair_page.text), "resolution_reference": "zu kurz",
    }).status_code == 422
    approved = chair.post(review, data={
        "csrf": csrf_of(chair_page.text), "resolution_reference": "Niederschrift am 13.11.2026",
    })
    assert approved.status_code == 303
    with SessionLocal() as db:
        doc = db.get(PRDocument, docid)
        assert doc.review_status == "checked" and doc.resolution_reference.startswith("Niederschrift")
    assert chair.post(review, data={
        "csrf": csrf_of(chair_page.text), "resolution_reference": "Zweiter Versuch",
    }).status_code == 409


def test_invalid_scope_and_input_cannot_be_accepted():
    owner = _user(setup=True)
    eid = _create(owner)
    page = owner.get(f"/personalratswahl/{eid}")
    csrf = csrf_of(page.text)
    assert owner.post(f"/personalratswahl/{eid}/daten", data={
        "csrf": csrf, "title": "Test", "election_day": "2027-12-31",
        "election_end_day": "2027-01-01",
    }).status_code == 422
    assert owner.post(f"/personalratswahl/{eid}/aufgaben/neu", data={
        "csrf": csrf, "title": "Test", "due_on": "not-a-date",
    }).status_code == 422
    assert owner.get(f"/personalratswahl/{eid}/dokumente/neu/not_a_form").status_code == 404
    assert owner.post(f"/personalratswahl/{eid}/dokumente/speichern", data={
        "csrf": csrf, "kind": "not_a_form",
    }).status_code == 422
    # Neither a legal E-vote API nor a generic /votes ballot is mounted under prwahl.
    assert owner.get(f"/personalratswahl/{eid}/stimmabgabe").status_code == 404


def test_board_staff_picker_includes_descendants_but_excludes_siblings_and_disabled_branches():
    """A parent election must see all staff below it, not only direct members."""
    with SessionLocal() as db:
        root = db.scalar(select(Organization).where(Organization.active.is_(True)))
        assert root is not None
        child = Organization(name="PRW Test Untereinheit", parent_id=root.id, active=True)
        grandchild = Organization(name="PRW Test Team", parent_id=None, active=True)
        disabled = Organization(name="PRW Test Inaktiv", parent_id=root.id, active=False)
        db.add_all([child, grandchild, disabled])
        db.flush()
        grandchild.parent_id = child.id
        people = [User(email=f"prwahl-tree-{uuid4().hex[:16]}@example.org",
                       name="PRW Test Person", password_hash=hash_password("passwort-1234"),
                       active=True, must_change_password=False, permissions="video") for _ in range(3)]
        db.add_all(people)
        db.flush()
        db.add_all([OrgMembership(user_id=people[0].id, org_id=child.id),
                    OrgMembership(user_id=people[1].id, org_id=grandchild.id),
                    OrgMembership(user_id=people[2].id, org_id=disabled.id)])
        db.flush()
        found = _eligible_staff_ids(db, root.id)
        assert people[0].id in found
        assert people[1].id in found
        assert people[2].id not in found
        assert people[1].id in _eligible_staff_ids(db, child.id)
        assert people[0].id not in _eligible_staff_ids(db, grandchild.id)
        db.rollback()
