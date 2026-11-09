"""Resumable, bounded index queue for published, admin-approved legal texts.

Chunks are embedded in batches of at most 8; every batch is checked against
current source fingerprints and legal permissions before being committed.
No legal text, answer, key or query is logged or copied into job metadata.
"""
import asyncio
import json
import logging
from datetime import timedelta

from sqlalchemy import delete, func, or_, select, update

from . import ai_law_vector, ai_provider, ai_vector
from .ai_models import AILawIndexJob, AILawVector
from .db import LawText, LawVersion, SessionLocal, get_settings, utcnow

BATCH_SIZE = 8
LEASE_SECONDS = 360


def active(db) -> bool:
    cfg = get_settings(db)
    return (
        cfg.get("module_ai") == "1" and
        cfg.get("module_laws", "1") == "1" and
        cfg.get("ai_vector_auto_index") == "1" and
        ai_vector._settings(db) is not None
    )


def targets(db) -> list[tuple[LawText, int, LawVersion | None]]:
    """Dynamic all-published rules and individual approvals, including old versions."""
    if not active(db):
        return []
    result = []
    cfg = get_settings(db)
    for law in db.scalars(select(LawText).where(
        LawText.published.is_(True)).order_by(LawText.id)
    ):
        if not ai_law_vector.allowed(db, law, None, cfg=cfg):
            continue
        for version_id, version in ai_law_vector.versions_for_index(law):
            result.append((law, version_id, version))
    return result


def _counts(db) -> dict[tuple[int, int, str, str], int]:
    return {
        (law_id, version_id, model_id, fingerprint): int(count)
        for law_id, version_id, model_id, fingerprint, count in db.execute(
            select(AILawVector.law_id, AILawVector.version_id,
                   AILawVector.model_id, AILawVector.source_hash,
                   func.count(AILawVector.id)).group_by(
                AILawVector.law_id, AILawVector.version_id,
                AILawVector.model_id, AILawVector.source_hash
            )
        )
    }


def _expected(law, version, job, fingerprint, model_id) -> int:
    if (job is not None and job.desired_hash == fingerprint and
            job.model_id == model_id and job.expected_chunks > 0):
        return job.expected_chunks
    return len(ai_law_vector.passages(law, version))


def reconcile(db) -> dict[str, int]:
    """Synchronize current permissions, public historical versions and model changes."""
    if not active(db):
        return {"pending": 0, "running": 0, "done": 0, "failed": 0}
    provider, model_id = ai_vector._settings(db)
    del provider
    wanted = {(law.id, version_id): (law, version) for law, version_id, version in targets(db)}
    jobs = {(job.law_id, job.version_id): job for job in db.scalars(select(AILawIndexJob))}
    counts = _counts(db)
    now = utcnow()
    # Scrub every revoked, unpublished, removed or stale version copy as
    # soon as the index worker reconciles. Read-time checks act immediately.
    for key, job in jobs.items():
        if key not in wanted:
            db.execute(delete(AILawVector).where(
                AILawVector.law_id == key[0], AILawVector.version_id == key[1]))
            db.delete(job)
    for (law_id, version_id), (law, version) in wanted.items():
        key = (law.id, version_id)
        fingerprint = ai_law_vector.fingerprint(law, version)
        job = jobs.get(key)
        try:
            expected = _expected(law, version, job, fingerprint, model_id)
        except ai_provider.AIProviderError:
            expected = -1
        # Stale vectors are source data and must be purged, not merely skipped.
        db.execute(delete(AILawVector).where(
            AILawVector.law_id == law.id,
            AILawVector.version_id == version_id,
            or_(AILawVector.model_id != model_id,
                AILawVector.source_hash != fingerprint)
        ))
        count = counts.get((law.id, version_id, model_id, fingerprint), 0)
        if job is None:
            job = AILawIndexJob(
                law_id=law.id, version_id=version_id, model_id=model_id,
                desired_hash=fingerprint, expected_chunks=max(expected, 0),
                status="pending", attempts=0, next_attempt_at=now,
                updated_at=now,
            )
            db.add(job)
        if expected < 0:
            job.status = "failed"
            job.expected_chunks = 0
            job.next_attempt_at = None
            job.lease_until = None
            continue
        change = job.desired_hash != fingerprint or job.model_id != model_id
        job.desired_hash, job.model_id, job.expected_chunks = fingerprint, model_id, expected
        if expected == 0 or count == expected:
            job.status = "done"
            job.attempts = 0
            job.next_attempt_at = None
            job.lease_until = None
        elif change or job.status == "done":
            job.status = "pending"
            job.attempts = 0
            job.next_attempt_at = now
            job.lease_until = None
        job.updated_at = now
    # Vectors for a law or version no longer in the corpus (possibly with no
    # corresponding queue row, e.g. after a backup restore).
    for law_id, version_id in set(db.execute(select(
        AILawVector.law_id, AILawVector.version_id
    ).distinct()).all()) - set(wanted):
        db.execute(delete(AILawVector).where(
            AILawVector.law_id == law_id, AILawVector.version_id == version_id))
    db.commit()
    return queue_counts(db)


def queue_counts(db) -> dict[str, int]:
    rows = dict(db.execute(select(AILawIndexJob.status, func.count(
        AILawIndexJob.id)).group_by(AILawIndexJob.status)).all())
    return {status: int(rows.get(status, 0)) for status in (
        "pending", "running", "failed", "done")}


def progress(db) -> dict:
    """Read-only status; progress reflects only current valid hashes and model."""
    cfg = get_settings(db)
    setting = ai_vector._settings(db)
    if not setting or cfg.get("module_laws", "1") != "1":
        return {
            "enabled": False, "total": 0, "ready": 0, "total_chunks": 0,
            "ready_chunks": 0, "percent": 0,
            "jobs": queue_counts(db), "laws": {},
        }
    model_id = setting[1]
    counts = _counts(db)
    jobs = {(job.law_id, job.version_id): job
            for job in db.scalars(select(AILawIndexJob))}
    count_sources = ready_sources = total_chunks = ready_chunks = 0
    per_law = {}
    for law, version_id, version in targets(db) if active(db) else []:
        fingerprint = ai_law_vector.fingerprint(law, version)
        job = jobs.get((law.id, version_id))
        try:
            expected = _expected(law, version, job, fingerprint, model_id)
        except ai_provider.AIProviderError:
            expected = 0
        count = min(expected, counts.get((law.id, version_id, model_id, fingerprint), 0))
        count_sources += 1
        if expected == count and expected > 0:
            ready_sources += 1
        total_chunks += expected
        ready_chunks += count
        law_row = per_law.setdefault(str(law.id), {
            "total": 0, "ready": 0, "chunks_total": 0,
            "chunks_ready": 0, "percent": 0,
        })
        law_row["total"] += 1
        law_row["ready"] += int(count == expected and expected > 0)
        law_row["chunks_total"] += expected
        law_row["chunks_ready"] += count
    for item in per_law.values():
        item["percent"] = round(
            100 * item["chunks_ready"] / item["chunks_total"]
        ) if item["chunks_total"] else 0
    return {
        "enabled": active(db),
        "total": count_sources, "ready": ready_sources,
        "total_chunks": total_chunks, "ready_chunks": ready_chunks,
        "percent": round(100 * ready_chunks / total_chunks) if total_chunks else 0,
        "jobs": queue_counts(db), "laws": per_law,
    }


async def tick(law_id: int | None = None) -> int:
    """Index one bounded embedding batch per invocation with an atomic lease."""
    with SessionLocal() as db:
        if not active(db):
            return 0
        reconcile(db)
        now = utcnow()
        due = or_(
            AILawIndexJob.status == "pending",
            (AILawIndexJob.status == "failed") & (
                AILawIndexJob.next_attempt_at <= now),
            (AILawIndexJob.status == "running") & (
                AILawIndexJob.lease_until <= now),
        )
        queue = select(AILawIndexJob.id).where(due)
        if law_id is not None:
            queue = queue.where(AILawIndexJob.law_id == law_id)
        chosen = db.scalar(queue.order_by(AILawIndexJob.id).limit(1))
        if chosen is None:
            return 0
        claimed = db.execute(update(AILawIndexJob).where(
            AILawIndexJob.id == chosen, due).values(
                status="running", lease_until=now + timedelta(seconds=LEASE_SECONDS),
                updated_at=now,
            ))
        if claimed.rowcount != 1:
            db.rollback()
            return 0
        job = db.get(AILawIndexJob, chosen)
        law_id, version_id, expected_hash, model_id = (
            job.law_id, job.version_id, job.desired_hash, job.model_id)
        db.commit()

    success, finished, inserted = False, False, 0
    try:
        with SessionLocal() as db:
            if not active(db) or ai_vector._settings(db)[1] != model_id:
                return 0
            law = db.get(LawText, law_id)
            version = db.get(LawVersion, version_id) if version_id else None
            if (version_id and version is None) or not ai_law_vector.allowed(db, law, version):
                return 0
            if ai_law_vector.fingerprint(law, version) != expected_hash:
                return 0
            pieces = ai_law_vector.passages(law, version)
            have = set(db.scalars(select(AILawVector.chunk_no).where(
                AILawVector.law_id == law_id,
                AILawVector.version_id == version_id,
                AILawVector.model_id == model_id,
                AILawVector.source_hash == expected_hash,
            )))
            todo = [(number, passage) for number, passage in enumerate(pieces)
                    if number not in have][:BATCH_SIZE]
            if todo:
                provider, active_model = ai_vector._settings(db)
                vectors = await ai_provider.embed(
                    provider, [passage.text for _, passage in todo], active_model
                )
                db.expire_all()
                law = db.get(LawText, law_id)
                version = db.get(LawVersion, version_id) if version_id else None
                if (not active(db) or (version_id and version is None) or
                        not ai_law_vector.allowed(db, law, version) or
                        ai_vector._settings(db)[1] != model_id or
                        ai_law_vector.fingerprint(law, version) != expected_hash):
                    return 0
                for (number, passage), vector in zip(todo, vectors):
                    db.add(AILawVector(
                        law_id=law_id, version_id=version_id,
                        chunk_no=number, anchor=passage.anchor,
                        section_title=passage.section_title,
                        chunk_text=passage.text,
                        model_id=model_id, source_hash=expected_hash,
                        vector_json=json.dumps(vector), created_at=utcnow(),
                    ))
                db.commit()
                inserted = len(todo)
            finished = len(have) + inserted >= len(pieces)
            success = True
    except Exception:  # noqa: BLE001 – no source data or secrets in logs
        success = False
    finally:
        with SessionLocal() as db:
            job = db.get(AILawIndexJob, chosen)
            if job is not None and job.status == "running":
                if job.model_id != model_id or job.desired_hash != expected_hash:
                    job.status = "pending"
                    job.attempts = 0
                    job.next_attempt_at = utcnow()
                elif success:
                    job.status = "done" if finished else "pending"
                    job.attempts = 0
                    job.next_attempt_at = None if finished else utcnow()
                else:
                    job.status = "failed"
                    job.attempts += 1
                    job.next_attempt_at = utcnow() + timedelta(
                        seconds=min(21600, 60 * 2 ** min(job.attempts, 8)))
                job.lease_until = None
                job.updated_at = utcnow()
                db.commit()
    return inserted


async def run_forever() -> None:
    logger = logging.getLogger("portal.ai_law_index")
    while True:
        try:
            await tick()
        except Exception:  # noqa: BLE001 – no source contents in logging
            logger.warning("KI-Rechtstextindex wird beim nächsten Lauf erneut geprüft.")
        await asyncio.sleep(20)
