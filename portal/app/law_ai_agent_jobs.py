"""Persistent, bounded sequential multi-agent Ortsrecht review queue.

No automatic publication, tool execution, outbound URLs from source documents,
implicit provider fallback, chat-context reuse, or AI processing without a human
initiating a job and approving the exact data recipients.
"""
import asyncio
import json
import logging
import time
from datetime import timedelta

from sqlalchemy import select, update

from . import ai_provider, ai_task_routing, law_ai_agents, law_ai_coverage
from .ai_models import AITaskProfile, AIProvider
from .db import SessionLocal, User, get_settings, utcnow
from .law_ai_agent_models import LawAiAnalysis
from .law_ai_models import LawAiDraft

logger = logging.getLogger("portal.law_ai_agents")
POLL_SECONDS = 4
STAGE_TIMEOUT = 70
MAX_JOB_SECONDS = 12 * 60  # fail closed when a slow server exhausts the budget


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
            "destination": provider.base_url,
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
    """Run read-only agents against complete sections only in advanced mode.

    Each chunk is individually validated against the exact submitted excerpt.
    The law text is never updated and partial results are never shown as done.
    """
    started = time.monotonic()
    with SessionLocal() as db:
        job = db.get(LawAiAnalysis, job_id)
        if not job or job.status != "running":
            return
        try:
            source = _allowed(db, job, db.get(LawAiDraft, job.draft_id))
            routes = json.loads(job.provider_map_json)
            if routes != configured_routes(db):
                raise ValueError("Ein KI-Anbieter oder Modell wurde nach der Freigabe geändert.")
            if job.mode == "advanced":
                sections = law_ai_coverage.sections(source)
            elif job.mode == "simple":
                sections = [law_ai_coverage.Section(1, 0, len(source), source)]
            else:
                raise ValueError("Unbekannter KI-Analysemodus.")
            mode = job.mode
        except (ValueError, TypeError) as exc:
            _fail(db, job, str(exc))
            return

    for task, _label in law_ai_agents.STAGES:
        stage_parts = []
        for section in sections:
            try:
                remaining = MAX_JOB_SECONDS - (time.monotonic() - started)
                if remaining < 1:
                    raise ValueError("Das sichere Zeitbudget ist erschöpft; keine unvollständige Analyse freigegeben.")
                with SessionLocal() as db:
                    job = db.get(LawAiAnalysis, job_id)
                    if not job or job.status != "running":
                        return
                    source_now = _allowed(db, job, db.get(LawAiDraft, job.draft_id))
                    if source_now != source or json.loads(job.provider_map_json) != configured_routes(db):
                        raise ValueError("Text oder KI-Modellzuweisung wurde geändert; neue Freigabe erforderlich.")
                    provider = ai_task_routing.select_provider(db, task)
                    if (provider.id != routes[task]["provider_id"] or
                            provider.model_id != routes[task]["model_id"] or
                            provider.base_url != routes[task]["destination"]):
                        raise ValueError("Der freigegebene KI-Datenempfänger wurde geändert.")
                    messages, sampled = law_ai_agents.prompt(task, section.text)
                    if mode == "advanced" and sampled:
                        raise ValueError("Mindestens ein Textabschnitt würde unvollständig übertragen.")
                    job.step = f"{task}:{section.number}/{len(sections)}"
                    job.updated_at = utcnow()
                    db.commit()

                answer = await asyncio.wait_for(
                    ai_provider.complete(provider, messages, max_tokens=3072),
                    timeout=min(STAGE_TIMEOUT, remaining),
                )
                result = law_ai_agents.validate(task, answer, section.text)
                stage_parts.append((section, result, sampled))
                with SessionLocal() as db:
                    job = db.get(LawAiAnalysis, job_id)
                    if not job or job.status != "running":
                        return
                    _allowed(db, job, db.get(LawAiDraft, job.draft_id))
                    if json.loads(job.provider_map_json) != configured_routes(db):
                        raise ValueError("Das KI-Profil wurde während der Analyse verändert.")
                    job.updated_at = utcnow()  # heartbeat; no unvalidated outputs persisted
                    db.commit()

            except (ai_provider.AIProviderError, ValueError, TypeError, KeyError,
                    asyncio.TimeoutError) as exc:
                # Never log document text, provider response, or prompt.
                reason = (str(exc) if isinstance(exc, (ValueError, ai_provider.AIProviderError))
                          else "Eine KI-Antwort ist ausgefallen oder hat zu lange gedauert.")
                with SessionLocal() as db:
                    job = db.get(LawAiAnalysis, job_id)
                    if job is not None and job.status == "running":
                        _fail(db, job, reason)
                return

        try:
            combined = law_ai_coverage.aggregate(task, stage_parts, source, mode)
        except ValueError as exc:
            with SessionLocal() as db:
                job = db.get(LawAiAnalysis, job_id)
                if job and job.status == "running":
                    _fail(db, job, str(exc))
            return
        with SessionLocal() as db:
            job = db.get(LawAiAnalysis, job_id)
            if not job or job.status != "running":
                return
            try:
                source_now = _allowed(db, job, db.get(LawAiDraft, job.draft_id))
                if source_now != source or json.loads(job.provider_map_json) != configured_routes(db):
                    raise ValueError("Quelltext oder Modellzuweisung wurde zwischenzeitlich verändert.")
            except ValueError as exc:
                _fail(db, job, str(exc))
                return
            field = {
                "law_structure": "outline_json", "law_metadata": "metadata_json",
                "law_verify": "verification_json",
            }[task]
            setattr(job, field, json.dumps(combined, ensure_ascii=False))
            job.updated_at = utcnow()
            db.commit()

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
    polls = 0
    while True:
        job_id = None
        try:
            if polls % 15 == 0:
                await asyncio.to_thread(mark_interrupted)
            polls += 1
            job_id = await asyncio.to_thread(_claim_next)
            if job_id is not None:
                await process_one(job_id)
                continue
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            # Avoid infinite running jobs and keep unknown model/backend
            # exceptions from exposing document content in logs.
            if "job_id" in locals() and job_id is not None:
                with SessionLocal() as db:
                    job = db.get(LawAiAnalysis, job_id)
                    if job is not None and job.status == "running":
                        _fail(db, job, "Ein interner Fehler hat die KI-Analyse abgebrochen.")
            logger.warning("KI-Rechtstext-Worker: interner Fehler, Auftrag sicher beendet")
        await asyncio.sleep(POLL_SECONDS)
