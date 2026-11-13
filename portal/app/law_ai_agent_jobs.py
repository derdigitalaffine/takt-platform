"""Persistent, bounded sequential multi-agent Ortsrecht review queue.

No automatic publication, tool execution, outbound URLs from source documents,
implicit provider fallback, chat-context reuse, or AI processing without a human
initiating a job and approving the exact data recipients.
"""
import asyncio
import json
import logging
import time
from dataclasses import replace
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
MAX_JOB_SECONDS = 18 * 60  # legacy/default budget
LOCAL_JOB_SECONDS = 45 * 60  # slower local 24B–30B execution; still bounded


ALL_TASKS = tuple(task for task, _ in law_ai_agents.STAGES)


def parse_tasks(value: str) -> tuple[str, ...]:
    """Read stored, canonical selected stages. Reject edits to the job plan."""
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        raise ValueError("Ungültiger gespeicherter KI-Prüfplan.") from None
    if (not isinstance(data, list) or not data
            or len(set(data)) != len(data) or any(task not in ALL_TASKS for task in data)):
        raise ValueError("Ungültige Auswahl der KI-Prüfschritte.")
    return tuple(task for task in ALL_TASKS if task in data)


def configured_routes(db, tasks=None) -> dict:
    """Explicit assigned providers, optionally only the selected tasks."""
    requested = ALL_TASKS if tasks is None else tuple(tasks)
    if not requested or any(task not in ALL_TASKS for task in requested):
        return {}
    result = {}
    for task in requested:
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
            "stream_enabled": bool(provider.stream_enabled),
        }
    return result


def _fail(db, job: LawAiAnalysis, message: str) -> None:
    job.status, job.step, job.failure = "failed", "failed", message[:240]
    job.stream_active = False
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




def _stream_progress(job_id: int, step: str, char_count: int, chunk_count: int) -> None:
    """Short transaction, no text or tokens stored; cancellation stops updates."""
    with SessionLocal() as db:
        job = db.get(LawAiAnalysis, job_id)
        if job is None or job.status != "running" or job.step != step:
            raise ValueError("Der KI-Auftrag wurde abgebrochen oder geändert.")
        _allowed(db, job, db.get(LawAiDraft, job.draft_id))
        if json.loads(job.provider_map_json) != configured_routes(db, tasks=parse_tasks(job.selected_tasks_json)):
            raise ValueError("Der KI-Provider wurde während des Streams geändert.")
        db.execute(update(LawAiAnalysis).where(
            LawAiAnalysis.id == job_id,
            LawAiAnalysis.status == "running",
            LawAiAnalysis.step == step,
        ).values(stream_characters=char_count, stream_chunks=chunk_count,
                 updated_at=utcnow()))
        db.commit()


async def _answer(provider, messages: list[dict], job_id: int, step: str,
                  *, remaining: float, max_tokens: int = 3072,
                  stage_timeout: int = STAGE_TIMEOUT,
                  json_mode: bool = False) -> str:
    """Use server SSE only when explicitly enabled; never resend on stream error.

    Raw chunks are kept inside the worker and validated as a complete JSON
    object before being persisted. Browser gets progress counters, not legal
    prose or partial/possibly malicious output.
    """
    options = {"response_format": {"type": "json_object"}} if json_mode else {}
    if not provider.stream_enabled:
        return await asyncio.wait_for(
            ai_provider.complete(provider, messages, max_tokens=max_tokens, **options),
            timeout=min(stage_timeout, remaining),
        )

    async def receive() -> str:
        parts: list[str] = []
        size = 0
        count = 0
        last = time.monotonic()
        async for fragment in ai_provider.stream_completion(
            provider, messages, max_tokens=max_tokens, **options,
        ):
            if not isinstance(fragment, str):
                raise ValueError("Der Modellstream hat ein ungültiges Format.")
            size += len(fragment)
            count += 1
            if size > 40_000:
                raise ValueError("Das Streaming-Ergebnis ist zu groß.")
            parts.append(fragment)
            # At most about one DB heartbeat/second; protects SQLite against
            # excessive writes from token-by-token local LLM streams.
            now = time.monotonic()
            if now - last >= 1.0:
                _stream_progress(job_id, step, size, count)
                last = now
        _stream_progress(job_id, step, size, count)
        if not parts:
            raise ValueError("Der Modellserver lieferte keine Textantwort.")
        return "".join(parts)

    return await asyncio.wait_for(receive(), timeout=min(stage_timeout, remaining))

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
            tasks = parse_tasks(job.selected_tasks_json)
            quality_profile = job.quality_profile
            json_mode_enabled = bool(job.json_mode)
            if quality_profile not in ("standard", "local_24b"):
                raise ValueError("Ungültiges Modellprofil.")
            if routes != configured_routes(db, tasks=tasks):
                raise ValueError("Ein KI-Anbieter oder Modell wurde nach der Freigabe geändert.")
            if job.mode == "advanced":
                sections = law_ai_coverage.sections(source, profile=quality_profile)
            elif job.mode == "simple":
                sections = [law_ai_coverage.Section(1, 0, len(source), source)]
            else:
                raise ValueError("Unbekannter KI-Analysemodus.")
            mode = job.mode
            job.progress_total = len(sections) * len(tasks)
            job.progress_done = 0
            job.retry_attempts = 0
            job.stream_characters = 0
            job.stream_chunks = 0
            job.stream_active = False
            job.validated_items = 0
            job.updated_at = utcnow()
            db.commit()
        except (ValueError, TypeError) as exc:
            _fail(db, job, str(exc))
            return

    for task in tasks:
        stage_parts = []
        # Adaptively bisect only if a model returned invalid/incomplete JSON.
        # The original source remains untouched, with a single retry depth.
        pending = [(piece, 0) for piece in sections]
        while pending:
            section, depth = pending.pop(0)
            try:
                remaining = (LOCAL_JOB_SECONDS if quality_profile == "local_24b"
                             else MAX_JOB_SECONDS) - (time.monotonic() - started)
                if remaining < 1:
                    raise ValueError("Das sichere Zeitbudget ist erschöpft; keine unvollständige Analyse freigegeben.")
                with SessionLocal() as db:
                    job = db.get(LawAiAnalysis, job_id)
                    if not job or job.status != "running":
                        return
                    source_now = _allowed(db, job, db.get(LawAiDraft, job.draft_id))
                    if source_now != source or json.loads(job.provider_map_json) != configured_routes(db, tasks=parse_tasks(job.selected_tasks_json)):
                        raise ValueError("Text oder KI-Modellzuweisung wurde geändert; neue Freigabe erforderlich.")
                    provider = ai_task_routing.select_provider(db, task)
                    if (provider.id != routes[task]["provider_id"] or
                            provider.model_id != routes[task]["model_id"] or
                            provider.base_url != routes[task]["destination"]):
                        raise ValueError("Der freigegebene KI-Datenempfänger wurde geändert.")
                    messages, sampled = law_ai_agents.prompt(
                        task, section.text,
                        context_limit=(6000 if depth and mode == "simple"
                                       else 6000 if quality_profile == "local_24b"
                                       else law_ai_agents.MAX_CONTEXT_CHARS),
                    )
                    if depth:
                        messages[0]["content"] += (
                            " KORREKTURVERSUCH: Gib ausschließlich EIN vollständiges "
                            "kompaktes JSON-Objekt mit dem vorgegebenen Schema aus, "
                            "maximal 3 Fundstellen, keine Einleitung und keinen Markdown-Zaun."
                        )
                    if mode == "advanced" and sampled:
                        raise ValueError("Mindestens ein Textabschnitt würde unvollständig übertragen.")
                    job.step = f"{task}:{len(stage_parts) + 1}/{len(stage_parts) + 1 + len(pending)}"
                    job.stream_active = bool(provider.stream_enabled)
                    job.stream_characters = 0
                    job.stream_chunks = 0
                    job.updated_at = utcnow()
                    db.commit()
                    step = job.step

                answer = await _answer(
                    provider, messages, job_id, step, remaining=remaining,
                    max_tokens=(3072 if depth else 1536) if quality_profile == "local_24b"
                               else (4096 if depth else 3072),
                    stage_timeout=(law_ai_coverage.LOCAL_MODEL_TIMEOUT
                                   if quality_profile == "local_24b" else STAGE_TIMEOUT),
                    json_mode=json_mode_enabled,
                )
                result = law_ai_agents.validate(task, answer, section.text)
                # Number only *successfully* validated sections, in document
                # order, for unambiguous global character offsets.
                stage_parts.append((replace(section, number=len(stage_parts) + 1),
                                    result, sampled))
                with SessionLocal() as db:
                    job = db.get(LawAiAnalysis, job_id)
                    if not job or job.status != "running":
                        return
                    _allowed(db, job, db.get(LawAiDraft, job.draft_id))
                    if json.loads(job.provider_map_json) != configured_routes(db, tasks=parse_tasks(job.selected_tasks_json)):
                        raise ValueError("Das KI-Profil wurde während der Analyse verändert.")
                    job.progress_done += 1
                    field_key = {"law_structure": "headings",
                                 "law_metadata": "fields",
                                 "law_verify": "findings"}[task]
                    job.validated_items += len(result.get(field_key, []))
                    job.stream_active = False
                    job.updated_at = utcnow()
                    db.commit()

            except (law_ai_agents.InvalidAgentJSON, ai_provider.AIOutputTruncated,
                    ai_provider.AIContextLimit) as exc:
                # No automatic retries for 401/403/429, network failures or
                # provider changes; only malformed/length-limited responses.
                halves = (law_ai_coverage.bisect(section)
                          if depth < law_ai_coverage.MAX_RECOVERY_SPLITS else None)
                if depth < law_ai_coverage.MAX_RECOVERY_SPLITS:
                    with SessionLocal() as db:
                        job = db.get(LawAiAnalysis, job_id)
                        if not job or job.status != "running":
                            return
                        try:
                            _allowed(db, job, db.get(LawAiDraft, job.draft_id))
                            if json.loads(job.provider_map_json) != configured_routes(db, tasks=parse_tasks(job.selected_tasks_json)):
                                raise ValueError("Anbieterzuweisung nach Freigabe geändert.")
                        except ValueError as permission_error:
                            _fail(db, job, str(permission_error))
                            return
                        # A failed original call plus its two smaller
                        # replacements means at most 3 requests/section.
                        job.retry_attempts += 1
                        if halves is not None:
                            job.progress_total += 1
                        job.stream_active = False
                        job.updated_at = utcnow()
                        db.commit()
                    # Short passages cannot be bisected sensibly. Re-ask
                    # this same consented model just once with a compact
                    # JSON-only prompt, without changing the source.
                    if halves is None:
                        pending.insert(0, (section, depth + 1))
                    else:
                        pending = [(halves[0], depth + 1),
                                   (halves[1], depth + 1)] + pending
                    continue
                with SessionLocal() as db:
                    job = db.get(LawAiAnalysis, job_id)
                    if job is not None and job.status == "running":
                        cause = ("Antwort am Tokenlimit abgeschnitten."
                                 if isinstance(exc, ai_provider.AIOutputTruncated)
                                 else "Eingabe überschreitet die Kontextgrenze des Modells."
                                 if isinstance(exc, ai_provider.AIContextLimit)
                                 else "Kein vollständiges gültiges JSON erhalten.")
                        _fail(db, job, "KI-Ausgabe von " + task +
                              " konnte auch nach begrenzter Abschnittsverkleinerung "
                              "nicht sicher ausgewertet werden: " + cause +
                              " Bitte Modell oder Ausgabelimit prüfen.")
                return
            except (ai_provider.AIProviderError, ValueError, TypeError, KeyError,
                    asyncio.TimeoutError) as exc:
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
                if source_now != source or json.loads(job.provider_map_json) != configured_routes(db, tasks=parse_tasks(job.selected_tasks_json)):
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
            if json.loads(job.provider_map_json) != configured_routes(db, tasks=parse_tasks(job.selected_tasks_json)):
                raise ValueError("Die Freigabe für das KI-Modell ist nicht mehr aktuell.")
        except ValueError as exc:
            _fail(db, job, str(exc))
            return
        job.status, job.step, job.failure = "done", "done", ""
        job.stream_active = False
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
        ).values(status="failed", step="failed", stream_active=False,
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
