"""Opt-in RLP staff council paper-election workspace.

All routes have login and object-level Fachmandate checks. No legally effective
publication, e-voting, automatic deadlines or result certification is implemented.
"""
import uuid
from datetime import datetime

from fastapi import Depends, HTTPException, Form, Request
from fastapi.responses import Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import prwahl as pw
from . import organization as org_access
from .org_models import OrgMembership
from .db import Organization, User, Group, GroupMember, utcnow
from .prwahl_models import PRElection, PRMandate, PRTask, PRDocument, PRAudit
from .main import app, check_csrf, current_user, flash, get_db, redirect, render


def _eligible_staff_ids(db: Session, org_id: int) -> set[int]:
    """Active staff assigned to the election node or any active descendant.

    Use the central organization's active_path so disabled ancestors and
    unrelated branches cannot leak into a board picker or be assigned by POST.
    """
    nodes = {node.id: node for node in db.scalars(select(Organization))}
    if not org_access.active_path(db, org_id, nodes):
        return set()
    descendants = {node_id for node_id in nodes
                   if org_id in org_access.active_path(db, node_id, nodes)}
    if not descendants:
        return set()
    staff = set(db.scalars(select(OrgMembership.user_id).join(
        User, User.id == OrgMembership.user_id).where(
        OrgMembership.org_id.in_(descendants), User.active.is_(True))))
    # Native group nodes are part of the same organizational tree, but their
    # canonical memberships are stored separately from OrgMembership.
    staff.update(db.scalars(select(GroupMember.user_id).join(
        Group, Group.id == GroupMember.group_id).join(
        User, User.id == GroupMember.user_id).where(
        Group.org_id.in_(descendants), User.active.is_(True))))
    return staff


def _setup(user: User):
    if not user.can("prwahl_setup"):
        raise HTTPException(403, "Zum Einrichten einer Wahl wird das ausdrückliche Modulrecht benötigt.")


def _member(db: Session, election_id: int, user: User, capability: str = "read"):
    return pw.scope(db, election_id, user, capability)


def _doc(db: Session, election_id: int, document_id: int, user: User, capability: str = "read"):
    election, role = _member(db, election_id, user, capability)
    if role == "auditor":
        raise HTTPException(403, "Dokumentinhalte sind für diese Prüfrolle nicht freigegeben.")
    doc = db.scalar(select(PRDocument).where(PRDocument.id == document_id,
                      PRDocument.election_id == election.id))
    if doc is None:
        raise HTTPException(404, "Der Vordruck wurde nicht gefunden.")
    return election, role, doc


@app.get("/personalratswahl/demo")
def prwahl_demo(request: Request, user: User = Depends(current_user)):
    """Read-only fictional demonstration, completely separate from election data."""
    return render(request, "prwahl_demo.html", user, demo=True, form_kinds=pw.FORM_KINDS)


@app.get("/personalratswahl/demo/dokumente/{kind}")
def prwahl_demo_document(request: Request, kind: str, user: User = Depends(current_user)):
    if kind not in pw.FORM_KINDS:
        raise HTTPException(404)
    from .prwahl_demo import sample_values
    return render(request, "prwahl_demo_document.html", user, demo=True, kind=kind,
                  form_def=pw.FORM_KINDS[kind], values=sample_values(kind))


@app.get("/personalratswahl/demo/dokumente/{kind}/{filetype}")
def prwahl_demo_download(kind: str, filetype: str,
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    if kind not in pw.FORM_KINDS or filetype not in {"pdf", "docx"}:
        raise HTTPException(404)
    from types import SimpleNamespace
    from .prwahl_demo import election, sample_values
    demo_doc = SimpleNamespace(kind=kind, revision=1)
    demo_election = election()
    demo_values = sample_values(kind)
    if filetype == "pdf":
        from .prwahl_pdf import build
        content = build(db, demo_election, demo_doc, values_override=demo_values, demo=True)
        media_type = "application/pdf"
    else:
        from .prwahl_docx import build
        content = build(demo_election, demo_doc, values_override=demo_values, demo=True)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(content, media_type=media_type, headers={
        "Cache-Control": "private, no-store, max-age=0",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="MUSTER-prwahl-{kind}.{filetype}"',
    })


@app.get("/personalratswahl")
def prwahl_index(request: Request, q: str = "", user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    election_ids = select(PRMandate.election_id).where(PRMandate.user_id == user.id)
    elections = [e for e in db.scalars(select(PRElection).where(PRElection.id.in_(election_ids))
                           .order_by(PRElection.updated_at.desc()).limit(100)).all()
                 if org_access.active_path(db, e.org_id)]
    # Search only among already authorized elections; never expose other tenants.
    q = pw.clean(q, 100).strip()
    if q:
        needle = q.casefold()
        elections = [e for e in elections if needle in e.title.casefold() or
                     needle in e.service_name.casefold() or
                     needle in pw.BODY_TYPES.get(e.body_type, e.body_type).casefold()]
    orgs = [org for org in db.scalars(select(Organization).where(Organization.active.is_(True))
                      .order_by(Organization.name)).all() if org_access.active_path(db, org.id) and
                      (user.is_admin or db.scalar(select(OrgMembership.id).where(
                          OrgMembership.user_id == user.id, OrgMembership.org_id == org.id)) is not None or
                       org_access.allows(db, user, org.id, "settings"))] if user.can("prwahl_setup") else []
    return render(request, "prwahl_index.html", user, elections=elections,
                  orgs=orgs, bodies=pw.BODY_TYPES, can_create=user.can("prwahl_setup"), search_query=q)


@app.post("/personalratswahl/neu", dependencies=[Depends(check_csrf)])
def prwahl_create(request: Request,
                  title: str = Form(...), org_id: int = Form(...),
                  body_type: str = Form("personalrat"), election_day: str = Form(""),
                  election_end_day: str = Form(""), election_location: str = Form(""),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    _setup(user)
    org = db.get(Organization, org_id)
    if org is None or not org_access.active_path(db, org.id):
        raise HTTPException(422, "Bitte eine aktive Dienststelle mit aktiven übergeordneten Einheiten auswählen.")
    # A global setup permission is necessary but never sufficient to choose an arbitrary tenant.
    own_org = db.scalar(select(OrgMembership.id).where(OrgMembership.user_id == user.id,
                                                      OrgMembership.org_id == org.id))
    if not (user.is_admin or own_org is not None or org_access.allows(db, user, org.id, "settings")):
        raise HTTPException(403, "Die Wahl darf nur für eine eigene oder zur Verwaltung freigegebene Organisationseinheit angelegt werden.")
    if body_type not in pw.BODY_TYPES:
        raise HTTPException(422, "Unbekannte Wahlart.")
    start, end = pw.parse_date(election_day), pw.parse_date(election_end_day)
    if start and end and end < start:
        raise HTTPException(422, "Der letzte Wahltag liegt vor dem ersten.")
    election = PRElection(
        title=pw.clean(title, 180), org_id=org.id, body_type=body_type,
        service_name=pw.clean(org.name, 180), election_day=start, election_end_day=end,
        election_location=pw.clean(election_location, 240), created_by=user.id,
    )
    if not election.title:
        raise HTTPException(422, "Eine Wahlbezeichnung ist erforderlich.")
    db.add(election)
    db.flush()
    db.add(PRMandate(election_id=election.id, user_id=user.id,
                     role="coordinator", assigned_by=user.id,
                     appointment_reference="Technische Einrichtung; keine Wahlvorstandsbestellung"))
    db.add_all(PRTask(election_id=election.id, title=label, kind=kind,
                      legal_reference=reference) for label, kind, reference in pw.INITIAL_TASKS)
    pw.record(db, user.id, election.id, "election_created")
    db.commit()
    flash(request, "Wahl-Arbeitsbereich angelegt. Die rechtliche Freigabe und die Bestellung des Wahlvorstands stehen noch aus.")
    return redirect(f"/personalratswahl/{election.id}")


@app.get("/personalratswahl/{election_id:int}")
def prwahl_detail(request: Request, election_id: int, tab: str = "overview",
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role = _member(db, election_id, user)
    if tab not in {"overview", "tasks", "board", "docs", "audit"}:
        tab = "overview"
    tasks = db.scalars(select(PRTask).where(PRTask.election_id == election.id)
                       .order_by(PRTask.id)).all()
    mandates = db.execute(select(PRMandate, User)
                          .join(User, PRMandate.user_id == User.id)
                          .where(PRMandate.election_id == election.id)
                          .order_by(PRMandate.id)).all()
    documents = db.scalars(select(PRDocument).where(PRDocument.election_id == election.id,
                             PRDocument.current.is_(True)).order_by(PRDocument.created_at.desc())).all()
    audit = db.execute(select(PRAudit, User).join(User, PRAudit.actor_id == User.id)
                       .where(PRAudit.election_id == election.id)
                       .order_by(PRAudit.id.desc()).limit(80)).all() if tab == "audit" else []
    # Avoid listing all platform accounts as potential election team members.
    # Only users explicitly assigned to the selected organization are eligible here.
    eligible_ids = _eligible_staff_ids(db, election.org_id) if role in {"coordinator", "chair"} else set()
    users = db.scalars(select(User).where(User.id.in_(eligible_ids))
                       .order_by(User.name, User.id)).all() if eligible_ids else []
    return render(request, "prwahl_detail.html", user, election=election,
                  tab=tab, role=role, tasks=tasks, mandates=mandates,
                  users=users, documents=documents, audit=audit,
                  roles=pw.ROLES, bodies=pw.BODY_TYPES, kinds=pw.FORM_KINDS,
                  done=sum(1 for t in tasks if t.completed_at),
                  progress=round(100 * sum(1 for t in tasks if t.completed_at) / len(tasks)) if tasks else 0,
                  can_edit=role in pw.EDIT_ROLES,
                  can_manage=role in {"coordinator", "chair"})


@app.post("/personalratswahl/{election_id:int}/team", dependencies=[Depends(check_csrf)])
def prwahl_team(request: Request, election_id: int, user_id: int = Form(...),
                role: str = Form(...), appointment_reference: str = Form(""),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, _ = _member(db, election_id, user, "manage")
    if role not in pw.ROLES:
        raise HTTPException(422, "Unbekannte Fachrolle.")
    person = db.get(User, user_id)
    if person is None or not person.active:
        raise HTTPException(422, "Die Person ist nicht verfügbar.")
    if person.id not in _eligible_staff_ids(db, election.org_id):
        raise HTTPException(422, "Die Person gehört nicht zur gewählten Organisationseinheit oder einer aktiven Untereinheit.")
    appointment_reference = pw.clean(appointment_reference, 250)
    if role in {"chair", "member", "clerk"} and len(appointment_reference) < 6:
        raise HTTPException(422, "Bitte einen konkreten Bestellungs- oder Benennungsnachweis angeben.")
    existing = db.scalar(select(PRMandate).where(PRMandate.election_id == election.id,
                                                PRMandate.user_id == person.id))
    if existing and existing.role == "coordinator" and existing.user_id == election.created_by:
        raise HTTPException(409, "Das technische Einrichtungsmandat kann nicht überschrieben werden.")
    # The technical coordinator must not appoint themselves to the chair role.
    # A separate already-mandated chair may document the appointment instead.
    if role == "chair" and person.id == user.id and not (existing and existing.role == "chair"):
        raise HTTPException(403, "Der Wahlvorstandsvorsitz darf nicht durch Selbstzuweisung eingerichtet werden.")
    if existing:
        existing.role, existing.appointment_reference = role, appointment_reference
        existing.assigned_by, existing.assigned_at = user.id, utcnow()
    else:
        db.add(PRMandate(election_id=election.id, user_id=person.id, role=role,
                         appointment_reference=appointment_reference, assigned_by=user.id))
    pw.record(db, user.id, election.id, "mandate_assigned", f"user:{person.id}:{role}")
    db.commit()
    flash(request, "Fachrolle aktualisiert. Der Nachweis ersetzt keine rechtswirksame Bestellung.")
    return redirect(f"/personalratswahl/{election.id}?tab=board")


@app.post("/personalratswahl/{election_id:int}/team/{mandate_id:int}/entziehen", dependencies=[Depends(check_csrf)])
def prwahl_revoke(request: Request, election_id: int, mandate_id: int,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, _ = _member(db, election_id, user, "manage")
    mandate = db.scalar(select(PRMandate).where(PRMandate.id == mandate_id,
                      PRMandate.election_id == election.id))
    if not mandate:
        raise HTTPException(404)
    if mandate.role == "coordinator" and mandate.user_id == election.created_by:
        raise HTTPException(409, "Das letzte Einrichtungsmandat darf nicht entzogen werden.")
    if mandate.user_id == user.id:
        raise HTTPException(409, "Das eigene Mandat darf nicht über diesen Dialog entzogen werden.")
    target = mandate.user_id
    db.delete(mandate)
    pw.record(db, user.id, election.id, "mandate_revoked", f"user:{target}")
    db.commit()
    flash(request, "Zugriff entzogen.")
    return redirect(f"/personalratswahl/{election.id}?tab=board")


@app.post("/personalratswahl/{election_id:int}/daten", dependencies=[Depends(check_csrf)])
def prwahl_settings(request: Request, election_id: int,
                    title: str = Form(...), election_day: str = Form(""),
                    election_end_day: str = Form(""), election_location: str = Form(""),
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, _ = _member(db, election_id, user, "edit")
    title = pw.clean(title, 180)
    if not title:
        raise HTTPException(422, "Eine Wahlbezeichnung ist erforderlich.")
    start, end = pw.parse_date(election_day), pw.parse_date(election_end_day)
    if start and end and end < start:
        raise HTTPException(422, "Der letzte Wahltag liegt vor dem ersten.")
    election.title, election.election_day, election.election_end_day = title, start, end
    election.election_location = pw.clean(election_location, 240)
    pw.record(db, user.id, election.id, "election_updated")
    db.commit()
    flash(request, "Planungsdaten aktualisiert. Termine sind manuell eingegeben und nicht rechtlich geprüft.")
    return redirect(f"/personalratswahl/{election.id}")


@app.post("/personalratswahl/{election_id:int}/aufgaben/neu", dependencies=[Depends(check_csrf)])
def prwahl_task_add(request: Request, election_id: int, title: str = Form(...),
                    due_on: str = Form(""), legal_reference: str = Form(""),
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, _ = _member(db, election_id, user, "edit")
    title = pw.clean(title, 180)
    if not title:
        raise HTTPException(422, "Die Aufgabe benötigt einen Titel.")
    item = PRTask(election_id=election.id, title=title, due_on=pw.parse_date(due_on),
                  legal_reference=pw.clean(legal_reference,150))
    db.add(item)
    db.flush()
    pw.record(db, user.id, election.id, "task_added", f"task:{item.id}")
    db.commit()
    return redirect(f"/personalratswahl/{election.id}?tab=tasks")


@app.post("/personalratswahl/{election_id:int}/aufgaben/{task_id:int}/umschalten", dependencies=[Depends(check_csrf)])
def prwahl_task_toggle(request: Request, election_id: int, task_id: int,
                       note: str = Form(""), user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    election, _ = _member(db, election_id, user, "edit")
    task = db.scalar(select(PRTask).where(PRTask.election_id == election.id, PRTask.id == task_id))
    if not task:
        raise HTTPException(404)
    # Tracking physical completion is not the legal proof of the underlying action.
    note = pw.clean(note, 350)
    if task.completed_at is None:
        if len(note) < 5:
            raise HTTPException(422, "Bitte einen konkreten Erledigungsvermerk angeben.")
        task.completed_at, task.completed_by, task.completion_note = utcnow(), user.id, note
        action = "task_checked"
    else:
        task.completed_at, task.completed_by, task.completion_note = None, None, ""
        action = "task_reopened"
    pw.record(db, user.id, election.id, action, f"task:{task.id}")
    db.commit()
    return redirect(f"/personalratswahl/{election.id}?tab=tasks")


@app.get("/personalratswahl/{election_id:int}/dokumente/neu/{kind}")
def prwahl_document_new(request: Request, election_id: int, kind: str,
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role = _member(db, election_id, user, "edit")
    if kind not in pw.FORM_KINDS:
        raise HTTPException(404)
    from .prwahl_prefill import prefill_fields
    from .prwahl_schedule import PRScheduleEvent
    from .prwahl_workflow import PRCountRound
    mandates = db.execute(select(PRMandate, User).join(
        User, PRMandate.user_id == User.id).where(
        PRMandate.election_id == election.id)).all()
    events = db.scalars(select(PRScheduleEvent).where(
        PRScheduleEvent.election_id == election.id).order_by(PRScheduleEvent.starts_at)).all()
    rounds = db.scalars(select(PRCountRound).where(
        PRCountRound.election_id == election.id)).all() if kind in {
            "count_protocol", "count_reconciliation"} else []
    values, sources = prefill_fields(election, kind, mandates=mandates, events=events, rounds=rounds)
    return render(request, "prwahl_document.html", user, election=election,
                  role=role, versions=[], form_kind=kind, form_def=pw.FORM_KINDS[kind],
                  values=values, prefill_sources=sources,
                  field_summary=pw.document_field_summary(kind, values),
                  document=None, mode="new")


@app.get("/personalratswahl/{election_id:int}/dokumente/{document_id:int}")
def prwahl_document_edit(request: Request, election_id: int, document_id: int,
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role, doc = _doc(db, election_id, document_id, user)
    versions = db.scalars(select(PRDocument).where(
        PRDocument.election_id == election.id,
        PRDocument.document_key == doc.document_key,
    ).order_by(PRDocument.revision.desc())).all()
    values = pw.document_values(doc)
    return render(request, "prwahl_document.html", user, election=election,
                  role=role, versions=versions, form_kind=doc.kind, form_def=pw.FORM_KINDS[doc.kind],
                  values=values, prefill_sources={},
                  field_summary=pw.document_field_summary(doc.kind, values), document=doc,
                  mode="edit" if role in pw.EDIT_ROLES and doc.current else "readonly")


@app.post("/personalratswahl/{election_id:int}/dokumente/speichern", dependencies=[Depends(check_csrf)])
async def prwahl_document_save(request: Request, election_id: int,
                               kind: str = Form(...), document_id: int = Form(0),
                               user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, _ = _member(db, election_id, user, "edit")
    if kind not in pw.FORM_KINDS:
        raise HTTPException(422, "Unbekannter Dokumenttyp.")
    data = dict(await request.form())
    payload = pw.secure_payload(data, kind)
    old = None
    if document_id:
        _, _, old = _doc(db, election_id, document_id, user, "edit")
        if not old.current or old.kind != kind:
            raise HTTPException(409, "Das Dokument wurde inzwischen geändert. Bitte neu öffnen.")
        result = db.execute(update(PRDocument).where(
            PRDocument.id == old.id, PRDocument.election_id == election.id,
            PRDocument.current.is_(True)).values(current=False))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Ein anderer Bearbeitungsvorgang war schneller.")
    doc = PRDocument(election_id=election.id, kind=kind,
                     document_key=old.document_key if old else str(uuid.uuid4()),
                     revision=old.revision + 1 if old else 1,
                     title=pw.FORM_KINDS[kind][0], payload_enc=payload, created_by=user.id)
    db.add(doc)
    db.flush()
    pw.record(db, user.id, election.id, "document_revised" if old else "document_created",
              f"document:{doc.id}:v{doc.revision}")
    db.commit()
    flash(request, "Neuer Prüfentwurf gespeichert. Frühere Fassungen bleiben im Wahlaktenverlauf erhalten.")
    return redirect(f"/personalratswahl/{election.id}/dokumente/{doc.id}")


@app.post("/personalratswahl/{election_id:int}/dokumente/{document_id:int}/pruefen",
          dependencies=[Depends(check_csrf)])
def prwahl_document_review(request: Request, election_id: int, document_id: int,
                           resolution_reference: str = Form(...),
                           user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, _, doc = _doc(db, election_id, document_id, user, "board")
    reference = pw.clean(resolution_reference, 250)
    if not doc.current or doc.review_status != "draft":
        raise HTTPException(409, "Nur der aktuelle, ungeprüfte Entwurf kann geprüft werden.")
    if len(reference) < 8:
        raise HTTPException(422, "Bitte einen aussagekräftigen Beschluss- oder Prüfvermerk angeben.")
    if not pw.document_field_summary(doc.kind, pw.document_values(doc))["has_content"]:
        raise HTTPException(409, "Ein vollständig leerer Vordruck kann nicht als intern geprüft gekennzeichnet werden.")
    doc.review_status, doc.reviewed_by, doc.resolution_reference = "checked", user.id, reference
    pw.record(db, user.id, election.id, "document_checked", f"document:{doc.id}")
    db.commit()
    flash(request, "Interne Prüfung dokumentiert. Das PDF bleibt bis zur gesonderten Rechtsfreigabe ein Prüfentwurf.")
    return redirect(f"/personalratswahl/{election.id}/dokumente/{doc.id}")


@app.get("/personalratswahl/{election_id:int}/dokumente/{document_id:int}/docx")
def prwahl_document_docx(election_id: int, document_id: int,
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, _, doc = _doc(db, election_id, document_id, user)
    from .prwahl_docx import build
    content = build(election, doc)
    pw.record(db, user.id, election.id, "document_downloaded_docx", f"document:{doc.id}")
    db.commit()
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={
                        "Cache-Control": "private, no-store, max-age=0",
                        "Pragma": "no-cache",
                        "X-Content-Type-Options": "nosniff",
                        "Content-Disposition": f'attachment; filename="prwahl-{election.id}-dokument-{doc.id}-v{doc.revision}.docx"',
                    })


@app.get("/personalratswahl/{election_id:int}/dokumente/{document_id:int}/pdf")
def prwahl_document_pdf(election_id: int, document_id: int,
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, _, doc = _doc(db, election_id, document_id, user)
    from .prwahl_pdf import build
    pdf = build(db, election, doc)
    pw.record(db, user.id, election.id, "document_downloaded", f"document:{doc.id}")
    db.commit()
    return Response(pdf, media_type="application/pdf", headers={
        "Cache-Control": "private, no-store, max-age=0",
        "Pragma": "no-cache",
        "Content-Disposition": f'attachment; filename="prwahl-{election.id}-dokument-{doc.id}-v{doc.revision}.pdf"',
        "X-Content-Type-Options": "nosniff",
    })
