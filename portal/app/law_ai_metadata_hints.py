"""Evidence-only deterministic metadata hints for municipal legal documents.

LLMs may miss obvious headings/dates, especially on local 24–30B models.
These hints complement (never overwrite) model output; no legal interpretation.
"""
import re

from . import laws_meta
from .law_ai_toc import toc_ranges, in_toc

_DATE = r"(?:[0-3]?\d\.\s*[01]?\d\.\s*\d{4}|\d{4}-[01]?\d-[0-3]?\d)"
_EVENTS = (
    ("issued_on", re.compile(r"(?i)(?:ausgefertigt|ausfertigung)\s*(?:am|vom|:)?\s*(" + _DATE + ")")),
    ("valid_from", re.compile(r"(?i)(?:tritt|treten).{0,80}?\b(?:am|zum)\s*(" + _DATE + r")\s+in\s+kraft|\b(?:gilt|gelten)\s+ab\s+(" + _DATE + ")")),
    ("valid_until", re.compile(r"(?i)(?:tritt|treten).{0,80}?\b(?:am|zum)\s*(" + _DATE + r")\s+außer\s+kraft")),
)
_KIND = re.compile(r"(?i)\b((?:Haupt|Gebühren|Haushalts)?satzung|Verordnung|Richtlinie|Dienstanweisung|Geschäftsordnung|Bekanntmachung|Gesetz|Vertrag)\b")


def hints(source: str, *, allow_header: bool = True) -> list[dict[str, str]]:
    spans = toc_ranges(source)
    found = {}
    offset = 0
    for index, raw in enumerate(source.splitlines(keepends=True)):
        line = raw.strip()
        if in_toc(offset, offset + len(raw.rstrip("\r\n")), spans):
            offset += len(raw)
            continue
        if not line:
            offset += len(raw)
            continue
        # Title only from the document's opening header, not later citations.
        if allow_header and index < 16 and "title" not in found:
            match = re.fullmatch(r"#{1,2}\s+(.{8,200})", line)
            if match and not line.lower().endswith("inhaltsverzeichnis"):
                found["title"] = {"field": "title", "value": match.group(1), "evidence": line}
            elif (index < 10 and len(line) >= 18 and len(line) <= 200
                  and _KIND.search(line) and not line.startswith(("§", "(", "-", "*"))
                  and not line.endswith((".", ":", ";"))
                  and "inhaltsverzeichnis" not in line.casefold()):
                found["title"] = {"field": "title", "value": line, "evidence": line}
        if allow_header and index < 26 and "doc_type" not in found:
            match = _KIND.search(line)
            if match:
                kind = match.group(1).casefold()
                key = {"geschäftsordnung": "geschaeftsordnung"}.get(kind,
                      "satzung" if kind.endswith("satzung") else kind)
                found["doc_type"] = {"field": "doc_type", "value": key,
                                     "evidence": line[:300]}
        for field, pattern in _EVENTS:
            if field in found:
                continue
            match = pattern.search(line)
            if match:
                value = next((g for g in match.groups() if g), None)
                normalized = laws_meta.parse_date(value) if value else None
                if normalized:
                    found[field] = {"field": field, "value": normalized,
                                    "evidence": line[:300]}
        offset += len(raw)
    return list(found.values())
