"""Opt-in local semantic RAG index for curated TAKT knowledge.

Deliberately small and self-hostable: SQLite stores vectors, embeddings use
an explicitly configured OpenAI-compatible provider. This is *not* a source
of authorization: each hit checks the live source, its published flag, and
its content hash. Inactive, removed and changed sources cannot be returned.
"""
import hashlib
import json
import math

from sqlalchemy import select

from . import ai_provider
from .ai_models import AIKnowledge, AIKnowledgeVector, AIProvider
from .db import get_settings, utcnow

MAX_CHUNKS = 12
CHUNK_SIZE = 950
CHUNK_OVERLAP = 140


def source_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def chunks(body: str) -> list[str]:
    """Bounded, overlapping chunks; never send an entire large document at once."""
    text = body.strip()[:14000]
    if not text:
        return []
    result = []
    step = CHUNK_SIZE - CHUNK_OVERLAP
    for offset in range(0, len(text), step):
        part = text[offset:offset + CHUNK_SIZE].strip()
        if part:
            result.append(part)
        if len(result) == MAX_CHUNKS or offset + CHUNK_SIZE >= len(text):
            break
    return result


def _settings(db):
    cfg = get_settings(db)
    if cfg.get("ai_vector_enabled") != "1" or cfg.get("ai_knowledge_enabled") != "1":
        return None
    try:
        provider_id = int(cfg.get("ai_vector_provider_id", "0"))
    except (TypeError, ValueError):
        return None
    model_id = cfg.get("ai_vector_model_id", "").strip()
    if not provider_id or not model_id:
        return None
    provider = db.get(AIProvider, provider_id)
    if not provider or not provider.active:
        return None
    return provider, model_id


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norms if norms else -1.0


async def reindex_document(db, doc_id: int) -> int:
    """Explicit admin operation. Old index stays available until the replacement succeeds."""
    selection = _settings(db)
    if not selection:
        raise ai_provider.AIProviderError("Vektorsuche muss mit einem aktiven Embedding-Provider eingerichtet sein.")
    provider, model_id = selection
    doc = db.get(AIKnowledge, doc_id)
    if not doc or not doc.enabled:
        raise ai_provider.AIProviderError("Nur freigegebene interne Wissenseinträge dürfen indiziert werden.")
    original_hash = source_hash(doc.body_md or "")
    passages = chunks(doc.body_md or "")
    if not passages:
        raise ai_provider.AIProviderError("Der Wissenseintrag enthält keinen indizierbaren Text.")
    vectors = await ai_provider.embed(provider, passages, model_id)
    db.refresh(doc)
    if not doc.enabled or source_hash(doc.body_md or "") != original_hash:
        raise ai_provider.AIProviderError("Die Wissensfreigabe wurde während der Indizierung geändert.")
    current = list(db.scalars(select(AIKnowledgeVector).where(
        AIKnowledgeVector.knowledge_id == doc.id)))
    for row in current:
        db.delete(row)
    for index, (passage, vector) in enumerate(zip(passages, vectors)):
        db.add(AIKnowledgeVector(
            knowledge_id=doc.id, chunk_no=index, model_id=model_id,
            source_hash=original_hash, chunk_text=passage,
            vector_json=json.dumps(vector), created_at=utcnow()))
    from . import ai_qdrant
    ai_qdrant.invalidate(db)
    db.commit()
    return len(passages)


async def retrieve(db, user, question: str, *, limit: int = 3) -> list[dict]:
    """Live ACL + opt-in checks precede any embedding request."""
    if not user.can("ai_knowledge"):
        return []
    selection = _settings(db)
    if not selection:
        return []
    provider, model_id = selection
    rows = db.execute(select(AIKnowledgeVector, AIKnowledge).join(
        AIKnowledge, AIKnowledgeVector.knowledge_id == AIKnowledge.id
    ).where(AIKnowledge.enabled.is_(True),
            AIKnowledgeVector.model_id == model_id).limit(1000)).all()
    if not rows:
        return []
    # Only valid current chunks participate in semantic selection.
    candidates = [(row, doc) for row, doc in rows if
                  row.source_hash == source_hash(doc.body_md or "")]
    if not candidates:
        return []
    try:
        query_vector = (await ai_provider.embed(provider, [question[:3000]], model_id))[0]
    except ai_provider.AIProviderError:
        return []  # Existing lexical retrieval remains functional.
    hits = []
    for row, doc in candidates:
        try:
            vector = json.loads(row.vector_json)
            if not isinstance(vector, list):
                continue
            score = _cosine(query_vector, vector)
        except (ValueError, TypeError, OverflowError):
            continue
        if score > 0.12:
            hits.append((score, row, doc))
    hits.sort(key=lambda item: item[0], reverse=True)
    # Optional Qdrant is only a ranking accelerator; never a source of
    # credentials, text or authorization. All its point IDs must resolve to
    # source-hash-checked current SQLite rows.
    from . import ai_qdrant, ai_knowledge
    if ai_qdrant.active(db):
        scores = await ai_qdrant.query(db, model_id, query_vector)
        by_id = {row.id: (score, row, doc) for score, row, doc in hits}
        remote_order = [by_id[point_id] for point_id, _remote_score in scores
                        if point_id in by_id]
        if remote_order:
            selected = {row.id for _score, row, _doc in remote_order}
            hits = remote_order + [entry for entry in hits if entry[1].id not in selected]
    result, used = [], set()
    for score, row, doc in hits:
        if doc.id in used:
            continue
        # Recheck source status/hash even after the similarity computation.
        db.refresh(doc)
        if not doc.enabled or row.source_hash != source_hash(doc.body_md or ""):
            continue
        result.append({"title": doc.title, "url": f"/ki/wissen/{doc.id}",
                       "text": row.chunk_text[:1800], "kind": "Internes Wissen",
                       "revision": ai_knowledge.knowledge_revision(doc)})
        used.add(doc.id)
        if len(result) >= limit:
            break
    return result
