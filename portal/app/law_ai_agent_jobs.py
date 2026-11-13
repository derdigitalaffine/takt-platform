"""Persistent, bounded sequential multi-agent Ortsrecht review queue.

No automatic publication, tool execution, outbound URLs from source documents,
implicit provider fallback, chat-context reuse, or AI processing without a human
initiating a job and approving the exact data recipients.
"""
import asyncio
import json
import logging
from datetime import timedelta

from sqlalchemy import select, update

from . import ai_provider, ai_task_routing, law_ai_agents
from .ai_models import AITaskProfile, AIProvider
from .db import SessionLocal, User, get_settings, utcnow
from .law_ai_agent_models import LawAiAnalysis
from .law_ai_models import LawAiDraft

logger = logging.getLogger("portal.law_ai_agents")
POLL_SECONDS = 4
STAGE_TIMEOUT = 70


def configured_routes(db) -> dict:
    """Explicit law task assignments only; no default public AI provider."""
    result = {}
    for task, _label in law_ai_agents.STAGES:
        assignment = db.get(AITaskProfile, task)
        if assignment is None:
            return {}
        provider = db.get(AIProvider, assignment.provider_id)
        if (provider is None or not provider.active or not provider.text_key_enc):
            return {}
        result[task] = {
            "provider_id": provider.id, "name": provider.name,
            "model_id": assignment.model_id or provider.model_id,
        }
    return result


def _fail(db, job: LawAiAnalysis, message: str) -> None:
    job.status, job.step, job.failure = "failed", "failed", message[:240]
    job.updated_at = utcnow()
    db.commit()


def _allowed(db, job: LawAiAnalysis, draft: LawAiDraft | None) -> str:
    if draft is None or draft.owner_id != job.requested_by or draft.status not in ("staged", "ocr_review"):
        raise ValueError("Der zugehörige Entwurf ist nicht mehr in redaktioneller Bearbeitung.")
    user = db.get(User, job.requested_by)
    if user is None or not user.active or not user.can("laws") or not user.can("ai_chat"):
        raise ValueError("Die Berechtigung für die KI-Rechtstextprüfung fehlt.")
    cfg = get_settings(db)
    if cfg.get("module_ai") != "1" or cfg.get("module_laws") != "1":
        raise ValueError("Die erforderlichen TAKT-Module sind deaktiviert.")
    source = draft.proposed_md or ""
    if (law_ai_agents.source_hash(source) != job.source_sha256
            or len(source) != job.source_chars):
        raise ValueError("Der importierte Text hat sich seit dem Prüfauftrag verändert.")
    if len(source) > law_ai_agents.MAX_SOURCE_CHARS:
        raise ValueError("Der Import ist für die KI-Analyse zu groß.")
    return source


async def process_one(job_id: int) -> None:
    """Revalidate each task route, input hash, active user and provider on every step."""
    with SessionLocal() as db:
        job = db.get(LawAiAnalysis, job_id)
        if not job or job.status != "running":
            return
        try:
            source = _allowed(db, job, db.get(LawAiDraft, job.draft_id))
            routes = json.loads(job.provider_map_json)
            if routes != configured_routes(db):
                raise ValueError("Ein KI-Anbieter oder Modell wurde nach der Freigabe geändert.")
        except (ValueError, TypeError) as exc:
            _fail(db, job, str(exc))
            return

    partial = {}
    for task, _label in law_ai_agents.STAGES:
        try:
            with SessionLocal() as db:
                job = db.get(LawAiAnalysis, job_id)
                if not job or job.status != "running":
                    return
                source = _allowed(db, job, db.get(LawAiDraft, job.draft_id))
                if json.loads(job.provider_map_json) != configured_routes(db):
                    raise ValueError("KI-Modellzuweisung hat sich verändert; erneute Freigabe erforderlich.")
                provider = ai_task_routing.select_provider(db, task)
                if (provider.id != routes[task]["provider_id"] or
                        provider.model_id != routes[task]["model_id"]):
                    raise ValueError("Der freigegebene KI-Anbieter wurde verändert.")
                messages, sampled = law_ai_agents.prompt(task, source)
                job.step = task
                job.updated_at = utcnow()
                db.commit()

            # Keep database transactions short; network calls are async and bounded.
            response = await asyncio.wait_for(
                ai_provider.complete(provider, messages, max_tokens=3072),
                timeout=STAGE_TIMEOUT,
            )
            result = law_ai_agents.validate(task, response, source)
            result["sampled"] = sampled
            partial[task] = result

            with SessionLocal() as db:
                job = db.get(LawAiAnalysis, job_id)
                if not job or job.status != "running":
                    return
                _allowed(db, job, db.get(LawAiDraft, job.draft_id))
                if json.loads(job.provider_map_json) != configured_routes(db):
                    raise ValueError("Die Modellzuweisung wurde während der Analyse verändert.")
                field = {
                    "law_structure": "outline_json", "law_metadata": "metadata_json",
                    "law_verify": "verification_json",
                }[task]
                setattr(job, field, json.dumps(result, ensure_ascii=False))
                job.updated_at = utcnow()
                db.commit()
        except (ai_provider.AIProviderError, ValueError, TypeError,
                KeyError, asyncio.TimeoutError) as exc:
            # Never record prompts, source text or raw LLM outputs in logs.
            reason = str(exc) if isinstance(exc, (ValueError, ai_provider.AIProviderError)) else (
                "KI-Anbieterantwort ist fehlgeschlagen oder hat zu lange gedauert."
            )
            with SessionLocal() as db:
                job = db.get(LawAiAnalysis, job_id)
                if job is not None and job.status == "running":
                    _fail(db, job, reason)
            return

    with SessionLocal() as db:
        job = db.get(LawAiAnalysis, job_id)
        if job is None or job.status != "running":
            return
        try:
            _allowed(db, job, db.get(LawAiDraft, job.draft_id))
            if json.loads(job.provider_map_json) != configured_routes(db):
                raise ValueError("Die Freigabe für das KI-Modell ist nicht mehr aktuell.")
        except ValueError as exc:
            _fail(db, job, str(exc))
            return
        job.status, job.step, job.failure = "done", "done", ""
        job.updated_at = utcnow()
        db.commit()


def _claim_next() -> int | None:
    with SessionLocal() as db:
        job = db.scalar(select(LawAiAnalysis).where(
            LawAiAnalysis.status == "queued"
        ).order_by(LawAiAnalysis.created_at, LawAiAnalysis.id).limit(1))
        if not job:
            return None
        id_ = job.id
        updated = db.execute(update(LawAiAnalysis).where(
            LawAiAnalysis.id == id_, LawAiAnalysis.status == "queued"
        ).values(status="running", step="preparing", updated_at=utcnow()))
        db.commit()
        return id_ if updated.rowcount == 1 else None


def mark_interrupted() -> None:
    """Fail stale leases; never silently re-send legal text to an external LLM."""
    with SessionLocal() as db:
        db.execute(update(LawAiAnalysis).where(
            LawAiAnalysis.status == "running",
            LawAiAnalysis.updated_at < utcnow() - timedelta(minutes=15),
        ).values(status="failed", step="failed",
                 failure="KI-Auftrag unterbrochen. Bitte nach Prüfung erneut starten.",
                 updated_at=utcnow()))
        db.commit()


async def run_forever():
    mark_interrupted()
    while True:
        try:
            job_id = await asyncio.to_thread(_claim_next)
            if job_id is not None:
                await process_one(job_id)
                continue
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Fehler im KI-Rechtstext-Worker (keine Dokumentdaten protokolliert)")
        await asyncio.sleep(POLL_SECONDS)
