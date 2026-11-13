"""Identify *document navigation* rather than legal provisions in OCR imports.

Offsets are source-character positions, not rendered Markdown positions.
A detected contents block is never deleted from the original; AI suggestions
must use the real provisions that follow it.
"""
import re

_TOC_TITLE = re.compile(r"^\s{0,3}(?:#{1,5}\s*)?(?:inhaltsverzeichnis|inhalt|übersicht der regelungen|gliederungsübersicht)\s*:?[\s#]*$", re.I)
_TOC_ENTRY = re.compile(r"^\s*(?:#{1,5}\s+)?(?:§{1,2}\s*\d+[a-z]?|(?:Art\.|Artikel)\s*\d+[a-z]?|(?:Teil|Kapitel|Abschnitt|Anlage|Buch)\s+[\dIVX]+)", re.I)
_PAGE_SUFFIX = re.compile(r"(?:\.{3,}|…{2,}|\s{2,}|\s+Seite\s+)\s*\d{1,4}\s*$", re.I)
_BODY_START = re.compile(r"^\s{0,3}(?:#{1,5}\s+)?(?:präambel|eingangsformel|aufgrund\s+des|der\s+(?:gemeinderat|stadtrat|verbandsgemeinderat))\b", re.I)


def toc_ranges(source: str) -> list[tuple[int, int]]:
    """Return conservative navigational intervals in full-source coordinates.

    Stop before the repeated first entry (actual paragraph), preamble or when
    the scanned listing becomes prose; never consume a whole short document.
    """
    lines = source.splitlines(keepends=True)
    offsets = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    spans = []
    for start, line in enumerate(lines):
        if not _TOC_TITLE.fullmatch(line.strip()) or start >= len(lines) - 2:
            continue
        first = None
        entries = 0
        page_entries = 0
        repeated = False
        end = start + 1
        for index in range(start + 1, min(len(lines), start + 130)):
            clean = lines[index].strip()
            if _BODY_START.match(clean):
                break
            if _TOC_TITLE.fullmatch(clean) and index > start + 1:
                break
            is_entry = bool(_TOC_ENTRY.match(clean))
            # A repeated entry is most likely the beginning of the real law.
            token = re.sub(r"\s+\d{1,4}\s*$", "", clean)
            token = _PAGE_SUFFIX.sub("", token).strip()
            if is_entry and first and token == first and entries >= 2:
                repeated = True
                break
            if is_entry:
                entries += 1
                if _PAGE_SUFFIX.search(clean):
                    page_entries += 1
                if first is None:
                    first = token
            elif clean and entries >= 2 and not (
                    _PAGE_SUFFIX.search(clean) or re.match(r"^\d{1,4}\s*$", clean)):
                break
            end = index + 1
        if entries >= 2 and (page_entries >= 1 or repeated):
            spans.append((offsets[start], offsets[end] if end < len(lines) else len(source)))
    return spans


def in_toc(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= start and end <= b for a, b in spans)


def source_line_offsets(source: str, quote: str) -> list[int]:
    """Return each occurrence (including repeated TOC listings)."""
    positions = []
    at = 0
    while (idx := source.find(quote, at)) >= 0:
        positions.append(idx)
        at = idx + max(1, len(quote))
    return positions


def preferred_quote_offset(source: str, quote: str) -> int | None:
    spans = toc_ranges(source)
    non_toc = [p for p in source_line_offsets(source, quote)
               if not in_toc(p, p + len(quote), spans)]
    return non_toc[0] if len(non_toc) == 1 else None
