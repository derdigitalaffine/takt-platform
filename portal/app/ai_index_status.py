"""Read-only live embedding/index diagnostics for administrators.

All health data comes from current local SQL rows; never ping external model
providers during page rendering and never expose embeddings or source texts.
"""
from sqlalchemy import select

from . import ai_vector, ai_vector_jobs, ai_qdrant, ai_law_vector_jobs
from .ai_models import AIIndexJob, AIKnowledge, AIKnowledgeVector
from .db import get_settings


def status(db, docs: list[AIKnowledge] | None = None) -> dict:
    cfg = get_settings(db)
    selection = ai_vector._settings(db)
    model = selection[1] if selection else ""
    provider_name = selection[0].name if selection else ""
    if docs is None:
        docs = list(db.scalars(select(AIKnowledge).order_by(AIKnowledge.id)))
    stored = {}
    for row in db.execute(select(
        AIKnowledgeVector.knowledge_id, AIKnowledgeVector.model_id,
        AIKnowledgeVector.source_hash,
    )):
        doc_id, model_id, fingerprint = row
        key = (doc_id, model_id, fingerprint)
        stored[key] = stored.get(key, 0) + 1
    jobs = {job.knowledge_id: job.status for job in db.scalars(select(AIIndexJob))}
    doc_status = {}
    ready = 0
    missing = 0
    chunks_total = 0
    chunks_ready = 0
    for doc in docs:
        expected = len(ai_vector.chunks(doc.body_md or "")) if doc.enabled and selection else 0
        count = min(expected, stored.get((
            doc.id, model, ai_vector.source_hash(doc.body_md or "")
        ), 0)) if expected else 0
        chunks_total += expected
        chunks_ready += count
        if not doc.enabled:
            info = {"label": "Nicht freigegeben", "color": "secondary"}
        elif not selection:
            info = {"label": "Embeddings deaktiviert", "color": "secondary"}
        else:
            if expected and count == expected:
                info = {"label": f"{count} Chunks aktuell", "color": "success"}
                ready += 1
            else:
                missing += 1
                state = jobs.get(doc.id)
                info = {
                    "pending": {"label": "Wartet auf Embedding", "color": "warning"},
                    "running": {"label": "Wird indiziert", "color": "warning"},
                    "failed": {"label": "Embedding fehlgeschlagen", "color": "danger"},
                }.get(state, {"label": "Noch nicht indiziert" if count == 0 else "Index unvollständig",
                               "color": "secondary"})
        info["chunks_ready"] = count
        info["chunks_total"] = expected
        info["percent"] = round(count * 100 / expected) if expected else 0
        doc_status[str(doc.id)] = info
    percent = round(chunks_ready * 100 / chunks_total) if chunks_total else 0
    return {
        "active": bool(selection),
        "model": model,
        "provider": provider_name,
        "total": sum(bool(doc.enabled) for doc in docs),
        "ready": ready,
        "missing": missing,
        "vectors": sum(stored.values()),
        "chunks_total": chunks_total,
        "chunks_ready": chunks_ready,
        "percent": percent,
        "jobs": ai_vector_jobs.counts(db),
        "qdrant": "Aktuell" if ai_qdrant.active(db) else (
            "Neuaufbau nötig" if ai_qdrant.configured(db) else "Aus"),
        "documents": doc_status,
        "law_embedding": ai_law_vector_jobs.progress(db),
        "dms_embedding": "Nur Textsuche – kein Embedding-Index",
    }
