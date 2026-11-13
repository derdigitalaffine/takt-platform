"""Ortsrecht read-only LLM pipeline endpoints; owner and AI rights always checked."""
import json

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import law_ai_agents, law_ai_agent_jobs, law_ai_coverage
from .db import User, get_settings, utcnow
from .law_ai_agent_models import LawAiAnalysis
from .main import app, check_csrf, get_db, rate_limit, redirect, require
from .routes_law_ai import _own

law_user = require("laws")


def _ai_permission(user: User, db: Session):
    if not user.can("ai_chat"):
        raise HTTPException(403, "KI-Analyse erfordert zusätzlich das Recht 'TAKT Agent verwenden'.")
    cfg = get_settings(db)
    if cfg.get("module_ai") != "1" or cfg.get("module_laws") != "1":
        raise HTTPException(404, "KI oder Ortsrecht ist nicht eingeschaltet.")


@app.post("/laws-assistant/{draft_id:int}/agents", dependencies=[Depends(check_csrf)])
def start_law_ai_agents(
    request: Request, draft_id: int, mode: str = Form("simple"),
    transmission_confirmed: str = Form(""),
    user: User = Depends(law_user), db: Session = Depends(get_db),
):
    """An explicit click authorizes only this exact source and these providers."""
    _ai_permission(user, db)
    rate_limit(request, "law-llm-analysis", limit=5, window=3600, key=str(user.id))
    draft = _own(db, draft_id, user)
    if draft.status not in ("staged", "ocr_review"):
        raise HTTPException(409, "Bitte zuerst den OCR-Import fertigstellen oder einen neuen Entwurf verwenden.")
    source = draft.proposed_md or ""
    if not source.strip() or len(source) > law_ai_agents.MAX_SOURCE_CHARS:
        raise HTTPException(413, "Für diese KI-Analyse sind 1 bis 120.000 Textzeichen zulässig.")
    if mode not in ("simple", "advanced"):
        raise HTTPException(422, "Unbekannter Analysemodus.")
    try:
        # Bound external calls and fail before authorization/queue creation
        # if the entire source cannot be divided without omissions.
        law_ai_coverage.count_calls(source, mode)
    except ValueError as exc:
        raise HTTPException(413, str(exc)) from exc
    if transmission_confirmed != "1":
        raise HTTPException(422, "Bitte die Übermittlung an die ausgewählten KI-Server bestätigen.")
    selected = law_ai_agent_jobs.configured_routes(db)
    if len(selected) != len(law_ai_agents.STAGES):
        raise HTTPException(503, "Bitte zuerst alle drei Ortsrecht-KI-Profile in der Administration konfigurieren.")
    if db.scalar(select(LawAiAnalysis.id).where(
            LawAiAnalysis.draft_id == draft_id,
            LawAiAnalysis.status.in_(("queued", "running"))).limit(1)) is not None:
        raise HTTPException(409, "Dieser Import wird bereits analysiert.")
    job = LawAiAnalysis(
        draft_id=draft_id, requested_by=user.id,
        source_sha256=law_ai_agents.source_hash(source),
        source_chars=len(source), provider_map_json=json.dumps(selected, ensure_ascii=False),
        mode=mode, status="queued", step="waiting",
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Für diesen Import läuft bereits eine KI-Analyse.") from None
    return redirect(f"/laws-assistant/{draft_id}")


@app.get("/laws-assistant/{draft_id:int}/agents/status")
def law_ai_agents_status(
    draft_id: int, user: User = Depends(law_user), db: Session = Depends(get_db),
):
    _own(db, draft_id, user)
    job = db.scalar(select(LawAiAnalysis).where(
        LawAiAnalysis.draft_id == draft_id,
        LawAiAnalysis.requested_by == user.id,
    ).order_by(LawAiAnalysis.id.desc()).limit(1))
    return JSONResponse({
        "status": job.status if job else "none",
        "step": job.step if job else "none",
        "ready": bool(job and job.status in ("done", "failed", "cancelled")),
        "failure": job.failure if job and job.status == "failed" else "",
    }, headers={"Cache-Control": "private, no-store"})


@app.post("/laws-assistant/{draft_id:int}/agents/{job_id:int}/cancel",
          dependencies=[Depends(check_csrf)])
def law_ai_agents_cancel(
    request: Request, draft_id: int, job_id: int,
    user: User = Depends(law_user), db: Session = Depends(get_db),
):
    _ai_permission(user, db)
    _own(db, draft_id, user)
    updated = db.execute(update(LawAiAnalysis).where(
        LawAiAnalysis.id == job_id,
        LawAiAnalysis.draft_id == draft_id,
        LawAiAnalysis.requested_by == user.id,
        LawAiAnalysis.status.in_(("queued", "running")),
    ).values(status="cancelled", step="cancelled", updated_at=utcnow(),
             failure="Durch den Benutzer abgebrochen. Bereits versendete Daten können nicht zurückgerufen werden."))
    db.commit()
    if updated.rowcount != 1:
        raise HTTPException(409, "Kein aktiver KI-Auftrag mehr vorhanden.")
    return redirect(f"/laws-assistant/{draft_id}")
