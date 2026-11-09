"""Read-only internal knowledge retrieval for TAKT's first AI integration.

No crawling and no separate copies of law texts. Sources must be expressly
enabled by an administrator; rights and publication state are checked for
every request, including citations shown to the user.
"""
import re
from datetime import date
from sqlalchemy import select

from .ai_models import AIKnowledge, AILawSource
from .db import LawSection, LawText, get_settings
from . import laws

_WORD_RE = re.compile(r"[^\W_]{3,}", re.UNICODE)
_DAY_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DE_DAY_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
_STOP = {"und", "die", "der", "das", "ist", "sind", "ein", "eine", "einer", "oder",
         "mit", "für", "von", "zur", "zum", "auf", "des", "den", "wie", "was",
         "welche", "welcher", "welches", "kann", "ich", "mir", "bitte", "über"}


def terms(question: str) -> list[str]:
    return list(dict.fromkeys(w for w in _WORD_RE.findall(question.casefold()) if w not in _STOP))[:24]


def requested_day(question: str) -> str | None:
    m = _DAY_RE.search(question)
    if m:
        try:
            return date.fromisoformat(m.group(1)).isoformat()
        except ValueError:
            return None
    m = _DE_DAY_RE.search(question)
    if m:
        try:
            return date(int(m[3]), int(m[2]), int(m[1])).isoformat()
        except ValueError:
            return None
    return None


def _score(title: str, body: str, words: list[str]) -> int:
    title, body = title.casefold(), body.casefold()
    return sum((5 if w in title else 0) + min(body.count(w), 4) for w in words)


def retrieve(db, user, question: str, limit: int = 5) -> list[dict]:
    """Return short, user-authorized source snippets, not full database documents."""
    cfg = get_settings(db)
    if cfg.get("ai_knowledge_enabled") != "1" or not user.can("ai_knowledge"):
        return []
    words = terms(question)
    if not words:
        return []
    found: list[tuple[int, dict]] = []
    for doc in db.scalars(select(AIKnowledge).where(AIKnowledge.enabled.is_(True)).limit(200)):
        body = doc.body_md or ""
        score = _score(doc.title, body, words)
        if score > 0:
            found.append((score, {"title": doc.title, "url": f"/ki/wissen/{doc.id}",
                                  "text": body[:1800], "kind": "Internes Wissen"}))

    # The current authenticated user may read published internal laws;
    # unpublished drafts are never exposed by AI retrieval.
    if cfg.get("module_laws", "1") == "1":
        ids = select(AILawSource.law_id)
        law_rows = db.scalars(select(LawText).where(LawText.id.in_(ids),
                                                     LawText.published.is_(True)).limit(300)).all()
        day = requested_day(question)
        for law in law_rows:
            if day:
                version = laws.version_for_date(law, day, include_internal=True)
                if version is None and law.valid_from and day < law.valid_from:
                    continue
                if version is not None:
                    if version.internal and not user.can("laws"):
                        continue
                    if not version.public:
                        continue
                    segments = [
                        (v.section.number, v.section.title, v.section.plain, v.section.anchor)
                        for v in laws.tree_of(version.body_md, law.outline)[1] if v.section.kind != "group"
                    ]
                    url_prefix = f"/recht/{law.slug}/fassung/{version.id}"
                    validity = f"Fassung gültig ab {version.valid_from or 'unbekannt'}"
                else:
                    segments = [(s.number, s.title, s.plain, s.anchor) for s in law.sections
                                if s.kind != "group"]
                    url_prefix = f"/recht/{law.slug}"
                    validity = f"Gültig ab {law.valid_from or 'unbekannt'}"
            else:
                segments = [(s.number, s.title, s.plain, s.anchor) for s in law.sections
                            if s.kind != "group"]
                url_prefix = f"/recht/{law.slug}"
                validity = f"Gültig ab {law.valid_from or 'unbekannt'}"
            for number, section_title, plain, anchor in segments[:700]:
                if not plain:
                    continue
                title = " · ".join(x for x in (law.title, number, section_title) if x)
                score = _score(title, plain, words)
                if score > 0:
                    found.append((score, {
                        "title": title + " (" + validity + ")",
                        "url": url_prefix + ("/" + anchor if anchor else ""),
                        "text": plain[:1800],
                        "kind": "Rechtstext",
                    }))
    found.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _score_value, item in found[:max(0, min(limit, 8))]]


def context_text(sources: list[dict]) -> str:
    if not sources:
        return ""
    return "\n\n".join(
        f"[Quelle {idx}] {item['title']}\nPfad: {item['url']}\nAuszug:\n{item['text']}"
        for idx, item in enumerate(sources, 1)
    )



def sources_accessible(db, user, sources: list[dict]) -> bool:
    """Re-check original source ACL when reopening/exporting a historical answer."""
    if not sources:
        return True
    cfg = get_settings(db)
    if cfg.get("ai_knowledge_enabled") != "1" or not user.can("ai_knowledge"):
        return False
    for source in sources:
        path = source.get("url", "")
        if not isinstance(path, str) or not path.startswith("/"):
            return False
        if path.startswith("/ki/wissen/"):
            try:
                doc_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                return False
            doc = db.get(AIKnowledge, doc_id)
            if doc is None or not doc.enabled:
                return False
        elif path.startswith("/recht/"):
            if cfg.get("module_laws", "1") != "1":
                return False
            parts = path.strip("/").split("/")
            law = db.scalar(select(LawText).where(LawText.slug == parts[1])) if len(parts) > 1 else None
            if law is None or not law.published or db.get(AILawSource, law.id) is None:
                return False
            if len(parts) >= 4 and parts[2] == "fassung":
                from .db import LawVersion
                try:
                    version = db.get(LawVersion, int(parts[3]))
                except ValueError:
                    return False
                if version is None or version.law_id != law.id or not version.public:
                    return False
                if version.internal and not user.can("laws"):
                    return False
        else:
            return False
    return True
