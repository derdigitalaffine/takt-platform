"""Ortsrecht read-only LLM pipeline endpoints; owner and AI rights always checked."""
import asyncio
import json

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import law_ai_agents, law_ai_agent_jobs, law_ai_coverage
from .db import SessionLocal, User, get_settings, utcnow
from .law_ai_agent_models import LawAiAnalysis
from .main import app, check_csrf, get_db, rate_limit, redirect, render, require
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




def _progress_payload(job: LawAiAnalysis | None) -> dict:
    if not job:
        return {"status": "none", "step": "none", "ready": False,
                "failure": "", "progress_done": 0, "progress_total": 0,
                "stream_active": False, "stream_characters": 0,
                "stream_chunks": 0, "validated_items": 0,
                "retry_attempts": 0}
    return {
        "status": job.status, "step": job.step,
        "ready": job.status in ("done", "failed", "cancelled"),
        "failure": job.failure if job.status == "failed" else "",
        "progress_done": job.progress_done,
        "retry_attempts": job.retry_attempts,
        "progress_total": job.progress_total,
        "stream_active": bool(job.stream_active and job.status == "running"),
        "stream_characters": job.stream_characters,
        "stream_chunks": job.stream_chunks,
        "validated_items": job.validated_items,
    }


def _owned_progress(draft_id: int, job_id: int, user_id: int) -> dict:
    """Fresh ACL and module check on every SSE snapshot (not just connection)."""
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or not user.active:
            raise PermissionError("Berechtigung verloren")
        try:
            _ai_permission(user, db)
            _own(db, draft_id, user)
        except HTTPException as exc:
            raise PermissionError("Berechtigung verloren") from exc
        job = db.get(LawAiAnalysis, job_id)
        if job is None or job.draft_id != draft_id or job.requested_by != user_id:
            raise PermissionError("Auftrag nicht sichtbar")
        return _progress_payload(job)


@app.get("/laws-assistant/{draft_id:int}/agents/{job_id:int}/events")
async def law_ai_agents_events(
    request: Request, draft_id: int, job_id: int,
    user: User = Depends(law_user), db: Session = Depends(get_db),
):
    """Same-origin SSE carrying *only* counters and validated-item totals."""
    _ai_permission(user, db)
    _own(db, draft_id, user)
    job = db.get(LawAiAnalysis, job_id)
    if job is None or job.draft_id != draft_id or job.requested_by != user.id:
        raise HTTPException(404, "KI-Prüfauftrag nicht gefunden.")
    rate_limit(request, "law-ai-event-stream", limit=15, window=60, key=str(user.id))
    user_id = user.id
    # FastAPI may retain yield dependencies for a StreamingResponse. Release
    # the request's SQLite connection *before* the long-lived SSE loop, which
    # opens short-lived independent sessions for every authorized snapshot.
    db.close()

    async def events():
        last = None
        for tick in range(1200):  # 20 minute cap, then client can reconnect.
            if await request.is_disconnected():
                return
            try:
                payload = await asyncio.to_thread(
                    _owned_progress, draft_id, job_id, user_id
                )
            except PermissionError:
                yield 'event: access-lost\ndata: {"status":"unauthorized"}\n\n'
                return
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            if encoded != last:
                yield f"data: {encoded}\n\n"
                last = encoded
            elif tick % 15 == 0:
                yield ": keepalive\n\n"
            if payload["ready"]:
                return
            await asyncio.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "private, no-store",
                                      "X-Accel-Buffering": "no",
                                      "X-Content-Type-Options": "nosniff"})

@app.get("/laws-assistant/{draft_id:int}/agents/status")
def law_ai_agents_status(
    draft_id: int, user: User = Depends(law_user), db: Session = Depends(get_db),
):
    _ai_permission(user, db)
    _own(db, draft_id, user)
    job = db.scalar(select(LawAiAnalysis).where(
        LawAiAnalysis.draft_id == draft_id,
        LawAiAnalysis.requested_by == user.id,
    ).order_by(LawAiAnalysis.id.desc()).limit(1))
    return JSONResponse(_progress_payload(job),
                        headers={"Cache-Control": "private, no-store"})


def _report_json(value: str, list_key: str) -> dict:
    """Bound stored, untrusted model findings before rendering an HTML report."""
    try:
        data = json.loads(value or "{}")
    except (ValueError, TypeError):
        return {list_key: [], "warnings": ["Prüfdaten sind nicht auswertbar."]}
    if not isinstance(data, dict):
        return {list_key: [], "warnings": ["Prüfdaten sind nicht auswertbar."]}
    entries = data.get(list_key)
    warnings = data.get("warnings")
    result = {
        list_key: [x for x in entries[:150] if isinstance(x, dict)]
        if isinstance(entries, list) else [],
        "warnings": [str(x)[:250] for x in warnings[:50]]
        if isinstance(warnings, list) else [],
        "sampled": data.get("sampled") is True,
    }
    coverage = data.get("coverage")
    result["coverage"] = coverage if isinstance(coverage, dict) else {}
    return result


@app.get("/laws-assistant/{draft_id:int}/agents/{job_id:int}/report")
def law_ai_agent_report(
    request: Request, draft_id: int, job_id: int,
    user: User = Depends(law_user), db: Session = Depends(get_db),
):
    """Print-friendly, private and source-version-checked AI evidence report.

    This is neither an official PDF nor legal approval. It never publishes or
    modifies the editorial copy or the immutable imported OCR source.
    """
    _ai_permission(user, db)
    draft = _own(db, draft_id, user)
    job = db.get(LawAiAnalysis, job_id)
    if job is None or job.draft_id != draft_id or job.requested_by != user.id:
        raise HTTPException(404, "KI-Prüfbericht nicht gefunden.")
    if job.status != "done":
        raise HTTPException(409, "Ein Prüfbericht ist erst nach abgeschlossener Analyse verfügbar.")
    if job.source_sha256 != law_ai_agents.source_hash(draft.proposed_md or ""):
        raise HTTPException(409, "Die Textquelle hat sich geändert. Bitte neu analysieren.")
    rate_limit(request, "law-ai-report", limit=60, window=3600, key=str(user.id))
    try:
        models = json.loads(job.provider_map_json)
        if not isinstance(models, dict):
            models = {}
    except (ValueError, TypeError):
        models = {}
    results = {
        "structure": _report_json(job.outline_json, "headings"),
        "metadata": _report_json(job.metadata_json, "fields"),
        "verification": _report_json(job.verification_json, "findings"),
    }
    response = render(
        request, "law_ai_agent_report.html", user, selected=draft,
        analysis=job, results=results, models=models,
        agent_stages=law_ai_agents.STAGES,
    )
    response.headers.update({
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Robots-Tag": "noindex, nofollow",
    })
    return response


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
    ).values(status="cancelled", step="cancelled", stream_active=False,
             updated_at=utcnow(),
             failure="Durch den Benutzer abgebrochen. Bereits versendete Daten können nicht zurückgerufen werden."))
    db.commit()
    if updated.rowcount != 1:
        raise HTTPException(409, "Kein aktiver KI-Auftrag mehr vorhanden.")
    return redirect(f"/laws-assistant/{draft_id}")
