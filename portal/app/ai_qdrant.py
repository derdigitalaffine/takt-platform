"""Optional, isolated-network Qdrant accelerator for approved TAKT vectors.

SQLite is authoritative. Qdrant receives ONLY numeric vector IDs and finite
embedding coordinates, never document text, titles, ACLs, user prompts or
credentials. Every result is checked against live SQLite document authorization.

Endpoint is fixed to the optional Docker Compose rag_private network.
"""
import hashlib
import json
import math

import httpx
from sqlalchemy import select

from .ai_models import AIKnowledge, AIKnowledgeVector
from .db import get_settings, set_setting

_ENDPOINT = "http://qdrant:6333"
_MAX_BODY = 1_500_000
_MAX_POINTS = 5000
_BATCH = 64


class QdrantError(Exception):
    """Safe UI message without remote response bodies or private data."""


def configured(db) -> bool:
    cfg = get_settings(db)
    return (cfg.get("module_ai") == "1" and cfg.get("ai_vector_enabled") == "1"
            and cfg.get("ai_knowledge_enabled") == "1"
            and cfg.get("ai_qdrant_enabled") == "1")


def active(db) -> bool:
    """Never query a stale cache after source, model or embedding changes."""
    cfg = get_settings(db)
    return configured(db) and (cfg.get("ai_qdrant_revision", "0") ==
                               cfg.get("ai_qdrant_synced_revision", "-1"))


def invalidate(db) -> None:
    """Must commit in the same transaction as every authoritative source change."""
    cfg = get_settings(db)
    try:
        revision = int(cfg.get("ai_qdrant_revision", "0"))
    except ValueError:
        revision = 0
    set_setting(db, "ai_qdrant_revision", str(revision + 1))


def _collection(model: str) -> str:
    return "takt_ai_" + hashlib.sha256(model.encode("utf-8")).hexdigest()[:18]


def _vector(value: object) -> list[float] | None:
    if not isinstance(value, list) or not 2 <= len(value) <= 4096:
        return None
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool)
               and math.isfinite(x) for x in value):
        return None
    return [float(x) for x in value]


async def _request(method: str, path: str, payload: dict | None = None,
                   *, not_found_ok: bool = False) -> dict | None:
    """Only allow caller-owned paths; never follow redirects or use host proxies."""
    if not path.startswith("/collections/takt_ai_") or ".." in path or any(
            c in path for c in ("\r", "\n", "\\", "#", "?")):
        raise QdrantError("Ungültiger Qdrant-Aufruf.")
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12), follow_redirects=False, trust_env=False
        ) as client:
            async with client.stream(method, _ENDPOINT + path,
                                     params={"wait": "true"} if method == "PUT" and path.endswith("/points") else None,
                                     json=payload) as response:
                if response.status_code == 404 and not_found_ok:
                    return None
                if response.status_code < 200 or response.status_code >= 300:
                    raise QdrantError("Der interne Qdrant-Index antwortet nicht wie erwartet.")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > _MAX_BODY:
                        raise QdrantError("Qdrant-Antwort ist zu groß.")
                    raw.extend(chunk)
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("status") not in ("ok", "success", None):
            raise QdrantError("Ungültiges Qdrant-Antwortformat.")
        return data
    except (httpx.HTTPError, ValueError, UnicodeDecodeError) as exc:
        raise QdrantError("Der interne Qdrant-Cache ist nicht erreichbar.") from exc


async def rebuild(db) -> int:
    """Explicit administrator action: replace this model's cache with live data."""
    if not configured(db):
        raise QdrantError("Qdrant ist nicht aktiviert.")
    revision = get_settings(db).get("ai_qdrant_revision", "0")
    from . import ai_vector
    selection = ai_vector._settings(db)
    if selection is None:
        raise QdrantError("Zuerst den Embedding-Provider konfigurieren.")
    _provider, model = selection
    rows = db.execute(select(AIKnowledgeVector, AIKnowledge).join(
        AIKnowledge, AIKnowledgeVector.knowledge_id == AIKnowledge.id
    ).where(AIKnowledge.enabled.is_(True),
            AIKnowledgeVector.model_id == model).limit(_MAX_POINTS + 1)).all()
    if len(rows) > _MAX_POINTS:
        raise QdrantError("Der lokale Index überschreitet die sichere Qdrant-Stapelgrenze.")
    points = []
    dimension = None
    for row, doc in rows:
        if row.source_hash != ai_vector.source_hash(doc.body_md or ""):
            continue
        try:
            vector = _vector(json.loads(row.vector_json))
        except (TypeError, ValueError):
            continue
        if not vector:
            continue
        if dimension is None:
            dimension = len(vector)
        if len(vector) != dimension:
            continue
        points.append({"id": row.id, "vector": vector})
    name = _collection(model)
    # Release the SQLite read transaction while potentially expensive HTTP calls run.
    db.rollback()
    # Delete old vectors even when no source is currently approved.
    await _request("DELETE", "/collections/" + name, not_found_ok=True)
    if not points:
        db.expire_all()
        if get_settings(db).get("ai_qdrant_revision", "0") == revision:
            set_setting(db, "ai_qdrant_synced_revision", revision)
            db.commit()
        return 0
    await _request("PUT", "/collections/" + name,
                   {"vectors": {"size": dimension, "distance": "Cosine"}})
    for start in range(0, len(points), _BATCH):
        await _request("PUT", "/collections/" + name + "/points",
                       {"points": points[start:start + _BATCH]})
    db.expire_all()
    if get_settings(db).get("ai_qdrant_revision", "0") == revision:
        set_setting(db, "ai_qdrant_synced_revision", revision)
        db.commit()
    return len(points)


async def query(db, model_id: str, query_vector: list[float], *,
                limit: int = 30) -> list[tuple[int, float]]:
    """Only return opaque IDs/scores; caller must revalidate ACL/source hash."""
    if not active(db):
        return []
    vector = _vector(query_vector)
    if vector is None:
        return []
    try:
        data = await _request("POST", "/collections/" + _collection(model_id) + "/points/query",
                              {"query": vector, "limit": max(1, min(limit, 70)),
                               "with_payload": False, "with_vector": False},
                              not_found_ok=True)
    except QdrantError:
        return []  # Local cosine search remains authoritative.
    points = data.get("result", {}).get("points", []) if isinstance(data, dict) else []
    if not isinstance(points, list):
        return []
    out = []
    for item in points[:70]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            continue
        score = item.get("score")
        if not isinstance(score, (int, float)) or not math.isfinite(score):
            continue
        out.append((item["id"], float(score)))
    return out
