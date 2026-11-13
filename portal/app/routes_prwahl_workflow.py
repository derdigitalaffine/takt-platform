"""Guided election lifecycle, optional aggregate paper count and constitution."""
from fastapi import Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import User, utcnow
from .main import app, current_user, check_csrf, render, redirect, flash, get_db
from .prwahl import scope, record, clean, parse_date
from .prwahl_workflow import (
    PRMilestone, PRCountRound, PRCountEntry, STAGES, STAGE_IDS,
    validate_totals, parse_entries, check_count, _integer,
)


def _round(db, election_id, round_id):
    round_ = db.scalar(select(PRCountRound).where(
        PRCountRound.election_id == election_id, PRCountRound.id == round_id))
    if round_ is None:
        raise HTTPException(404, "Diese Auszählung ist nicht vorhanden.")
    return round_


@app.get("/personalratswahl/{election_id:int}/ablauf")
def prwahl_lifecycle(request: Request, election_id: int,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role = scope(db, election_id, user)
    milestones = {m.stage: m for m in db.scalars(select(PRMilestone).where(
        PRMilestone.election_id == election.id))}
    rounds = db.scalars(select(PRCountRound).where(
        PRCountRound.election_id == election.id).order_by(PRCountRound.id)).all()
    complete = sum(1 for m in milestones.values() if m.completed_at)
    return render(request, "prwahl_lifecycle.html", user, election=election,
                  role=role, stages=STAGES, milestones=milestones, rounds=rounds,
                  progress=round(complete * 100 / len(STAGES)),
                  can_edit=role in {"coordinator", "chair", "member", "clerk"})


@app.post("/personalratswahl/{election_id:int}/ablauf/{stage}/nachweis",
          dependencies=[Depends(check_csrf)])
def prwahl_milestone(request: Request, election_id: int, stage: str,
                     evidence: str = Form(...), effective_on: str = Form(""),
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role = scope(db, election_id, user, "edit")
    if stage not in STAGE_IDS:
        raise HTTPException(404)
    evidence = clean(evidence, 500)
    if len(evidence) < 12:
        raise HTTPException(422, "Bitte einen konkreten Akten-, Beschluss- oder Bekanntgabenachweis angeben.")
    if stage in {"determination", "constitution", "archive"} and role != "chair":
        raise HTTPException(403, "Der Wahlvorstandsvorsitz muss diesen Schritt dokumentieren.")
    if stage == "determination":
        rounds = db.scalars(select(PRCountRound).where(PRCountRound.election_id == election.id)).all()
        if not rounds or any(r.status != "confirmed" for r in rounds):
            raise HTTPException(409, "Vor der Ergebnisfeststellung müssen alle angelegten Auszählungen durch den Vorsitz bestätigt sein.")
    if stage == "constitution":
        prior = db.scalar(select(PRMilestone).where(PRMilestone.election_id == election.id,
                                                   PRMilestone.stage == "determination"))
        if prior is None or prior.completed_at is None:
            raise HTTPException(409, "Zuerst muss die Ergebnisfeststellung dokumentiert sein.")
    if stage == "archive":
        prior = db.scalar(select(PRMilestone).where(PRMilestone.election_id == election.id,
                                                   PRMilestone.stage == "constitution"))
        if prior is None or prior.completed_at is None:
            raise HTTPException(409, "Zuerst die konstituierende Sitzung dokumentieren.")
    item = db.scalar(select(PRMilestone).where(PRMilestone.election_id == election.id,
                                              PRMilestone.stage == stage))
    if item and item.completed_at:
        raise HTTPException(409, "Ein abgeschlossener Schritt kann nur nach dokumentierter Korrektur wieder geöffnet werden.")
    if not item:
        item = PRMilestone(election_id=election.id, stage=stage)
        db.add(item)
    item.evidence, item.effective_on = evidence, parse_date(effective_on)
    item.completed_by, item.completed_at = user.id, utcnow()
    record(db, user.id, election.id, "milestone_completed", stage)
    db.commit()
    flash(request, "Nachweis dokumentiert. Die formelle Wirksamkeit bleibt vom rechtmäßigen Wahlverfahren abhängig.")
    return redirect(f"/personalratswahl/{election.id}/ablauf")


@app.get("/personalratswahl/{election_id:int}/auszaehlung")
def prwahl_count_page(request: Request, election_id: int,
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role = scope(db, election_id, user)
    rounds = db.scalars(select(PRCountRound).where(
        PRCountRound.election_id == election.id).order_by(PRCountRound.id.desc())).all()
    details = {}
    for round_ in rounds:
        entries = db.scalars(select(PRCountEntry).where(
            PRCountEntry.round_id == round_.id).order_by(PRCountEntry.id)).all()
        try:
            result = check_count(round_.mode, round_.seats, round_.ballots_cast,
                                 round_.invalid_ballots, round_.abstentions,
                                 [(e.label, e.votes) for e in entries])
        except HTTPException:
            result = {"complete": False, "note": "Widersprüchliche Zähldaten – bitte prüfen."}
        details[round_.id] = {"entries": entries, "result": result}
    return render(request, "prwahl_count.html", user, election=election,
                  role=role, rounds=rounds, details=details,
                  can_edit=role in {"coordinator", "chair", "member", "clerk"})


@app.post("/personalratswahl/{election_id:int}/auszaehlung/erfassen",
          dependencies=[Depends(check_csrf)])
def prwahl_count_save(request: Request, election_id: int,
                      group_name: str = Form(...), mode: str = Form(...),
                      seats: int = Form(...), eligible: int = Form(...),
                      voters: int = Form(...), ballots_cast: int = Form(...),
                      invalid_ballots: int = Form(...), abstentions: int = Form(0),
                      entries: str = Form(...),
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, _ = scope(db, election_id, user, "edit")
    group_name = clean(group_name, 100)
    if not group_name:
        raise HTTPException(422, "Bitte einen Wahlkörper / eine Gruppe angeben.")
    eligible, voters, ballots_cast, invalid_ballots, abstentions = validate_totals(
        eligible=eligible, voters=voters, ballots_cast=ballots_cast,
        invalid_ballots=invalid_ballots, abstentions=abstentions)
    seats = _integer(seats, "Sitze", minimum=1, maximum=200)
    parsed = parse_entries(entries)
    check_count(mode, seats, ballots_cast, invalid_ballots, abstentions, parsed)
    round_ = PRCountRound(election_id=election.id, group_name=group_name, mode=mode,
                          seats=seats, eligible=eligible, voters=voters,
                          ballots_cast=ballots_cast, invalid_ballots=invalid_ballots,
                          abstentions=abstentions, created_by=user.id)
    db.add(round_)
    db.flush()
    db.add_all(PRCountEntry(round_id=round_.id, label=label, votes=votes)
               for label, votes in parsed)
    record(db, user.id, election.id, "count_recorded", f"round:{round_.id}")
    db.commit()
    flash(request, "Papierstimmen erfasst und rechnerisch geprüft. Die Auszählung ist noch nicht bestätigt.")
    return redirect(f"/personalratswahl/{election.id}/auszaehlung")


@app.post("/personalratswahl/{election_id:int}/auszaehlung/{round_id:int}/bestaetigen",
          dependencies=[Depends(check_csrf)])
def prwahl_count_confirm(request: Request, election_id: int, round_id: int,
                         count_reference: str = Form(...),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    election, role = scope(db, election_id, user, "board")
    round_ = _round(db, election.id, round_id)
    if round_.status != "draft":
        raise HTTPException(409, "Diese Auszählung wurde bereits bestätigt.")
    reference = clean(count_reference, 250)
    if len(reference) < 12:
        raise HTTPException(422, "Bitte die Niederschrift der öffentlichen Auszählung konkret bezeichnen.")
    entries = db.scalars(select(PRCountEntry).where(PRCountEntry.round_id == round_.id)).all()
    result = check_count(round_.mode, round_.seats, round_.ballots_cast,
                         round_.invalid_ballots, round_.abstentions,
                         [(e.label, e.votes) for e in entries])
    if round_.mode == "list" and not result["complete"]:
        raise HTTPException(409, "Bei Quotientengleichstand muss die gesetzlich vorgeschriebene Entscheidung gesondert nachgewiesen werden; keine automatische Losentscheidung.")
    round_.status, round_.confirmed_by, round_.confirmed_at = "confirmed", user.id, utcnow()
    round_.count_reference = reference
    record(db, user.id, election.id, "count_confirmed", f"round:{round_.id}")
    db.commit()
    flash(request, "Die Erfassung ist mit einem Niederschriftenverweis bestätigt; das amtliche Wahlergebnis stellt weiterhin der Wahlvorstand fest.")
    return redirect(f"/personalratswahl/{election.id}/auszaehlung")
