"""Optional semantic search for approved TAKT legal texts and public old versions.

Only approved, published law texts are embedded. Paragraph-aware chunks keep
canonical anchors, version identifiers and live authorization checks. An index
row is never a permission grant and is never considered an official source.
"""
import json
from dataclasses import dataclass

from sqlalchemy import select

from . import ai_knowledge, ai_provider, ai_source_policy, ai_vector, laws
from .ai_models import AILawVector
from .db import LawText, LawVersion, get_settings

CHUNK_SIZE = 900
CHUNK_OVERLAP = 100
MAX_CHUNKS_PER_VERSION = 1500


@dataclass(frozen=True)
class Passage:
    anchor: str
    section_title: str
    text: str


def fingerprint(law: LawText, version: LawVersion | None = None) -> str:
    """Complete provenance for corpus invalidation, including publication flags."""
    if version is None:
        return ai_knowledge.revision(
            law.id, law.slug, law.title, law.outline, laws.OUTLINE_VERSION, law.body_md,
            law.published, law.internal, law.valid_from, law.valid_until,
        )
    return ai_knowledge.revision(
        law.id, law.slug, law.title, law.outline, laws.OUTLINE_VERSION, law.published, law.internal,
        version.id, version.title, version.body_md, version.valid_from,
        version.valid_until, version.public, version.internal,
    )


def passages(law: LawText, version: LawVersion | None = None) -> list[Passage]:
    """Chunk on legal paragraph/article boundaries, without silently dropping tail text.

    Oversized sources raise instead of silently appearing fully indexed; an
    administrator can see a failed job, and lexical law search still works.
    """
    if version is not None:
        sections = [item.section for item in laws.tree_of(version.body_md, law.outline)[1]]
    else:
        sections = list(law.sections)
        if not sections and (law.body_md or "").strip():
            sections = [item.section for item in laws.tree_of(law.body_md, law.outline)[1]]
    output = []
    for section in sections:
        if section.kind == "group" or not (section.plain or "").strip():
            continue
        prefix = " · ".join(x for x in (
            law.title, section.number, section.title
        ) if x)[:700]
        body = section.plain.strip()
        step = CHUNK_SIZE - CHUNK_OVERLAP
        for offset in range(0, len(body), step):
            excerpt = body[offset:offset + CHUNK_SIZE].strip()
            if excerpt:
                output.append(Passage(
                    anchor=section.anchor or "",
                    section_title=prefix,
                    text=(prefix + "\n" + excerpt)[:1900],
                ))
            if len(output) > MAX_CHUNKS_PER_VERSION:
                raise ai_provider.AIProviderError(
                    "Der Rechtstext ist für die aktuelle Indexgröße zu umfangreich."
                )
            if offset + CHUNK_SIZE >= len(body):
                break
    return output


def versions_for_index(law: LawText) -> list[tuple[int, LawVersion | None]]:
    return [(0, None)] + [
        (version.id, version) for version in law.versions if version.public
    ]


def allowed(db, law: LawText | None, version: LawVersion | None,
            user=None, cfg=None) -> bool:
    cfg = cfg if cfg is not None else get_settings(db)
    if cfg.get("module_laws", "1") != "1" or law is None or not (
            ai_source_policy.law_included(db, law, cfg=cfg)):
        return False
    if user is not None and law.internal and not user.can("laws"):
        return False
    if version is not None:
        if version.law_id != law.id or not version.public:
            return False
        if user is not None and version.internal and not user.can("laws"):
            return False
    return True


async def retrieve(db, user, question: str, *, limit: int = 3) -> list[dict]:
    """Semantic law hits; date-filtered and independently permission-checked."""
    cfg = get_settings(db)
    if not user.can("ai_knowledge") or cfg.get("ai_knowledge_enabled") != "1":
        return []
    setting = ai_vector._settings(db)
    if not setting or cfg.get("module_laws", "1") != "1":
        return []
    provider, model_id = setting
    rows = db.execute(select(AILawVector, LawText).join(
        LawText, AILawVector.law_id == LawText.id
    ).where(AILawVector.model_id == model_id).limit(12000)).all()
    if not rows:
        return []
    day = ai_knowledge.requested_day(question)
    filtered = []
    for vector, law in rows:
        version = db.get(LawVersion, vector.version_id) if vector.version_id else None
        if vector.version_id and version is None:
            continue
        if not allowed(db, law, version, user=user, cfg=cfg):
            continue
        if day:
            effective_version = laws.version_for_date(law, day, include_internal=True)
            effective_id = effective_version.id if effective_version is not None else 0
            if effective_version is None and law.valid_from and day < law.valid_from:
                continue
            if vector.version_id != effective_id:
                continue
        elif vector.version_id != 0:
            # Historical content is not silently mixed into current-law answers.
            continue
        if vector.source_hash != fingerprint(law, version):
            continue
        filtered.append((vector, law, version))
    if not filtered:
        return []
    try:
        query_vector = (await ai_provider.embed(
            provider, [question[:3000]], model_id
        ))[0]
    except ai_provider.AIProviderError:
        return []  # Previous lexical paragraph search remains available.
    hits = []
    for vector, law, version in filtered:
        try:
            score = ai_vector._cosine(query_vector, json.loads(vector.vector_json))
        except (TypeError, ValueError, OverflowError, ZeroDivisionError):
            continue
        if score > 0.10:
            hits.append((score, vector, law, version))
    hits.sort(key=lambda item: item[0], reverse=True)
    result, seen, per_law = [], set(), {}
    for _score, vector, law, version in hits:
        if (law.id, vector.version_id, vector.anchor) in seen or per_law.get(law.id, 0) >= 2:
            continue
        db.refresh(law)
        if version is not None:
            db.refresh(version)
        if not allowed(db, law, version, user=user) or vector.source_hash != fingerprint(law, version):
            continue
        url = f"/recht/{law.slug}"
        if version is not None:
            url += f"/fassung/{version.id}"
        if vector.anchor:
            url += f"/{vector.anchor}"
        date_label = version.valid_from if version is not None else law.valid_from
        source = {
            "title": vector.section_title + f" (Fassung ab {date_label or 'unbekannt'})",
            "url": url,
            "text": vector.chunk_text[:1800],
            "kind": "Rechtstext",
            "revision": ai_knowledge.law_revision(law, version),
        }
        result.append(source)
        seen.add((law.id, vector.version_id, vector.anchor))
        per_law[law.id] = per_law.get(law.id, 0) + 1
        if len(result) >= limit:
            break
    return result
