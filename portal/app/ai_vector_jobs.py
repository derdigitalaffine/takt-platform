"""Durable opt-in RAG index reconciliation and bounded background processing.

The worker may be restarted mid-request: expired leases are reclaimed. Source
hashes and model names are checked against current configuration before work.
No document content, API secret, or user query enters job state or logs.
"""
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, or_, select, update

from . import ai_vector
from .ai_models import AIIndexJob, AIKnowledge, AIKnowledgeVector
from .db import SessionLocal, get_settings, utcnow

BATCH_SIZE = 2
LEASE_SECONDS = 240


def active(db) -> bool:
    cfg = get_settings(db)
    return (cfg.get("module_ai") == "1" and cfg.get("ai_vector_auto_index") == "1"
            and ai_vector._settings(db) is not None)


def enqueue_document(db, doc: AIKnowledge) -> bool:
    """Mark any administratively changed opt-in document for indexing.

    Runs inside the caller's transaction so creating/editing a document and
    scheduling its index update commit together. Source content stays in
    AIKnowledge, never in job metadata.
    """
    if not active(db) or not doc.enabled or not (doc.body_md or "").strip():
        return False
    _provider, model_id = ai_vector._settings(db)
    db.flush()
    fingerprint = ai_vector.source_hash(doc.body_md or "")
    job = db.scalar(select(AIIndexJob).where(AIIndexJob.knowledge_id == doc.id))
    if job is None:
        db.add(AIIndexJob(knowledge_id=doc.id, model_id=model_id,
                          desired_hash=fingerprint, status="pending",
                          attempts=0, next_attempt_at=utcnow(), updated_at=utcnow()))
    else:
        job.model_id, job.desired_hash = model_id, fingerprint
        job.status = "pending"
        job.attempts = 0
        job.next_attempt_at = utcnow()
        job.lease_until = None
        job.updated_at = utcnow()
    return True


def reconcile(db) -> dict[str, int]:
    """Diff curated source state against the live index; enqueue only mismatches."""
    if not active(db):
        return {"pending": 0, "failed": 0}
    _provider, model_id = ai_vector._settings(db)
    docs = list(db.scalars(select(AIKnowledge).order_by(AIKnowledge.id).limit(1000)))
    indexed = set(db.execute(select(
        AIKnowledgeVector.knowledge_id, AIKnowledgeVector.model_id,
        AIKnowledgeVector.source_hash).distinct()).all())
    jobs = {job.knowledge_id: job for job in db.scalars(select(AIIndexJob))}
    now = utcnow()
    from . import ai_qdrant
    for doc in docs:
        job = jobs.get(doc.id)
        if not doc.enabled or not (doc.body_md or "").strip():
            # Prompt revocation always takes effect on read; purge copies as well.
            purged = db.execute(delete(AIKnowledgeVector).where(
                AIKnowledgeVector.knowledge_id == doc.id))
            if purged.rowcount:
                ai_qdrant.invalidate(db)
            if job:
                db.delete(job)
            continue
        fingerprint = ai_vector.source_hash(doc.body_md or "")
        # The SQLite index contains text chunks; scrub outdated copies, not
        # just hide them from the search result. Keep the newest live model.
        purged = db.execute(delete(AIKnowledgeVector).where(
            AIKnowledgeVector.knowledge_id == doc.id,
            or_(AIKnowledgeVector.model_id != model_id,
                AIKnowledgeVector.source_hash != fingerprint)))
        if purged.rowcount:
            ai_qdrant.invalidate(db)
        is_current = (doc.id, model_id, fingerprint) in indexed
        if job is None and not is_current:
            db.add(AIIndexJob(knowledge_id=doc.id, model_id=model_id,
                              desired_hash=fingerprint, status="pending",
                              attempts=0, next_attempt_at=now, updated_at=now))
        elif job is not None:
            if is_current:
                job.model_id, job.desired_hash = model_id, fingerprint
                job.status = "done"
                job.attempts = 0
                job.next_attempt_at = None
                job.lease_until = None
            elif (job.model_id != model_id or job.desired_hash != fingerprint
                  or job.status == "done"):
                job.model_id, job.desired_hash = model_id, fingerprint
                job.status = "pending"
                job.attempts = 0
                job.next_attempt_at = now
                job.lease_until = None
            # Otherwise retain pending/running/backoff states.
            job.updated_at = now
    db.commit()
    return counts(db)


def retry_failed(db, *, doc_id: int | None = None) -> int:
    """Administrator-requested retry without bypassing the automatic ACL checks.

    Reconciliation first removes stale/disabled sources. The scheduled worker
    handles embedding calls separately, avoiding long-running admin POSTs.
    """
    if not active(db):
        return 0
    reconcile(db)
    query = select(AIIndexJob).where(AIIndexJob.status == "failed")
    if doc_id is not None:
        query = query.where(AIIndexJob.knowledge_id == doc_id)
    jobs = list(db.scalars(query.order_by(AIIndexJob.id).limit(100)))
    for job in jobs:
        job.status = "pending"
        job.attempts = 0
        job.next_attempt_at = utcnow()
        job.lease_until = None
        job.updated_at = utcnow()
    db.commit()
    return len(jobs)


async def sync_qdrant_if_needed() -> int:
    """Bounded, explicitly opted-in cache repair after indexing has settled."""
    from . import ai_qdrant
    with SessionLocal() as db:
        cfg = get_settings(db)
        if cfg.get("ai_qdrant_auto_sync") != "1" or not ai_qdrant.configured(db):
            return 0
        if ai_qdrant.active(db):
            return 0
        if active(db):
            active_jobs = db.scalar(select(AIIndexJob.id).where(
                AIIndexJob.status.in_(("pending", "running"))).limit(1))
            if active_jobs is not None:
                return 0
        try:
            return await ai_qdrant.rebuild(db)
        except ai_qdrant.QdrantError:
            return 0  # Qdrant is optional; local search stays available.


def counts(db) -> dict[str, int]:
    rows = list(db.scalars(select(AIIndexJob.status)))
    return {key: rows.count(key) for key in ("pending", "running", "failed", "done")}


async def tick(doc_id: int | None = None) -> int:
    """Process at most BATCH_SIZE jobs; no model requests while disabled."""
    with SessionLocal() as db:
        if not active(db):
            return 0
        reconcile(db)
        now = utcnow()
        due = or_(
            AIIndexJob.status == "pending",
            (AIIndexJob.status == "failed") & (
                (AIIndexJob.next_attempt_at.is_(None)) |
                (AIIndexJob.next_attempt_at <= now)),
            (AIIndexJob.status == "running") & (
                (AIIndexJob.lease_until.is_(None)) |
                (AIIndexJob.lease_until <= now)),
        )
        jobs_query = select(AIIndexJob.id).where(due)
        if doc_id is not None:
            jobs_query = jobs_query.where(AIIndexJob.knowledge_id == doc_id)
        job_ids = list(db.scalars(jobs_query.order_by(AIIndexJob.id).limit(BATCH_SIZE)))
    done = 0
    for job_id in job_ids:
        with SessionLocal() as db:
            now = utcnow()
            due = or_(
                AIIndexJob.status == "pending",
                (AIIndexJob.status == "failed") & (
                    (AIIndexJob.next_attempt_at.is_(None)) |
                    (AIIndexJob.next_attempt_at <= now)),
                (AIIndexJob.status == "running") & (
                    (AIIndexJob.lease_until.is_(None)) |
                    (AIIndexJob.lease_until <= now)),
            )
            # Conditional UPDATE is a cross-process atomic claim (including SQLite).
            claimed = db.execute(update(AIIndexJob).where(
                AIIndexJob.id == job_id, due).values(
                status="running", lease_until=now + timedelta(seconds=LEASE_SECONDS),
                updated_at=now))
            if claimed.rowcount != 1:
                db.rollback()
                continue
            job = db.get(AIIndexJob, job_id)
            doc_id, desired_hash, model_id = job.knowledge_id, job.desired_hash, job.model_id
            db.commit()
        succeeded = False
        try:
            with SessionLocal() as db:
                if active(db) and ai_vector._settings(db)[1] == model_id:
                    doc = db.get(AIKnowledge, doc_id)
                    if doc and doc.enabled and ai_vector.source_hash(doc.body_md or "") == desired_hash:
                        await ai_vector.reindex_document(db, doc_id)
                        succeeded = True
        except Exception:  # noqa: BLE001 - failures are retried; never log source or provider errors
            succeeded = False

        with SessionLocal() as db:
            job = db.get(AIIndexJob, job_id)
            if job is None or job.status != "running":
                continue
            if job.model_id != model_id or job.desired_hash != desired_hash:
                # Source changed during an external call. Reconcile on the next tick.
                job.status = "pending"
                job.next_attempt_at = utcnow()
            elif succeeded:
                job.status = "done"
                job.attempts = 0
                job.next_attempt_at = None
                done += 1
            else:
                job.status = "failed"
                job.attempts += 1
                job.next_attempt_at = utcnow() + timedelta(
                    seconds=min(21600, 60 * (2 ** min(job.attempts, 8))))
            job.lease_until = None
            job.updated_at = utcnow()
            db.commit()
    return done



async def run_forever() -> None:
    """Dedicated low-priority loop; never block reminders or recording jobs."""
    log = logging.getLogger("portal.ai_index")
    while True:
        try:
            await tick()
            await sync_qdrant_if_needed()
        except Exception:  # noqa: BLE001 - never log source text or provider secrets
            log.warning("RAG-Indexlauf fehlgeschlagen; erneuter Versuch beim nächsten Intervall.")
        await asyncio.sleep(300)
