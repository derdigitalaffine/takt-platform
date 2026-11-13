"""Lossless Markdown outline preview for TAKT's actual Rechtsakte parser.

This is an *editor suggestion*, never an authoritative reconstruction.
Only leading CommonMark heading markers are inserted; every original source
character, including all digits, punctuation, whitespace and newlines,
is retained in order. No model-generated prose ever replaces legal wording.
"""
from __future__ import annotations

import re
from . import laws

MAX_SOURCE = 120_000
_MAX_HEADING = 150
_TITLE = re.compile(r"^(?:\s{0,3}#\s+)?(.+?)\s*$")
_ATX = re.compile(r"^\s{0,3}(#{1,6})[ \t]+(.+?)\s*$")
_END_PUNCTUATION = (".", ",", ";", ":")
_GROUP_RANK = {"buch": 1, "teil": 2, "kapitel": 3, "titel": 3,
               "abschnitt": 4, "unterabschnitt": 5, "untertitel": 5,
               "anlage": 1, "anhang": 1}


def _classify(line: str) -> tuple[str, int] | None:
    """Conservative legal-heading recognition; avoid paragraphs mentioning §."""
    if not 0 < len(line) <= _MAX_HEADING:
        return None
    m = laws.NORM_RE.match(line)
    if m:
        title = m.group("title").strip()
        if not title or (not title.endswith(_END_PUNCTUATION)
                         and not laws._PROSE_RE.search(title)):
            return ("norm", 0)
        return None
    m = laws.GROUP_RE.match(line)
    if m:
        title = m.group("title").strip()
        if title.endswith((".", ",", ";")):
            return None
        word = next((w.lower() for w in _GROUP_RANK if
                     re.search(r"\b" + re.escape(w) + r"\b", line, re.I)), "")
        return ("group", _GROUP_RANK.get(word, 4))
    m = laws.UNIT_RE.match(line)
    if m and not m.group("title").strip().endswith(_END_PUNCTUATION):
        return ("norm", 0)
    return None


def outline_preview(source: str) -> dict:
    """Generate a complete deterministic legal Markdown *preview*.

    Heading insertion is intentionally restricted to standalone normative
    labels and groups already present in the imported source. The caller must
    verify the original document and manually accept any proposed formatting.
    """
    if not isinstance(source, str) or not 0 < len(source) <= MAX_SOURCE:
        raise ValueError("Für eine vollständige Markdown-Vorschau sind 1–120.000 Zeichen zulässig.")
    if "\x00" in source:
        raise ValueError("Die Rechtsquelle enthält ungültige Binärzeichen.")

    fragments = source.splitlines(keepends=True)
    if not fragments:
        fragments = [source]
    first = next((i for i, fragment in enumerate(fragments) if fragment.strip()), None)
    parsed_original = laws.parse(source)
    original_title = parsed_original.title.strip()
    out: list[str] = []
    recovered: list[str] = []
    changes: list[dict] = []
    warnings: list[str] = []
    group_stack: list[int] = []
    fenced = False

    for i, fragment in enumerate(fragments):
        line = fragment.rstrip("\r\n")
        bare = line.strip()
        prefix = ""
        if laws.FENCE_RE.match(line):
            fenced = not fenced
        elif not fenced and bare:
            existing = _ATX.match(line)
            if existing:
                plain = existing.group(2).strip()
                classified = _classify(plain)
                if classified and classified[0] == "group":
                    rank = classified[1]
                    while group_stack and group_stack[-1] >= rank:
                        group_stack.pop()
                    group_stack.append(rank)
            elif i == first and original_title and bare == original_title:
                prefix = "# "
            else:
                classified = _classify(bare)
                if classified:
                    kind, rank = classified
                    if kind == "group":
                        while group_stack and group_stack[-1] >= rank:
                            group_stack.pop()
                        group_stack.append(rank)
                        level = min(2 + len(group_stack) - 1, 6)
                    else:
                        level = min(2 + len(group_stack), 6)
                    prefix = "#" * level + " "
        if prefix:
            changes.append({"line": i + 1, "original": line,
                            "suggested_heading": prefix + line,
                            "level": len(prefix) - 1})
        out.append(prefix + fragment)
        recovered.append(fragment)

    candidate = "".join(out)
    if "".join(recovered) != source:
        raise ValueError("Die Vorschau würde den ursprünglichen Wortlaut verändern.")
    parsed = laws.parse(candidate)
    if not parsed.nodes:
        warnings.append("Keine sicher erkennbaren Einzelvorschriften; Gliederung am Original kontrollieren.")
    if not parsed.norms:
        warnings.append("Keine §-/Artikel-Einzelvorschriften erkannt; ggf. Unterste Ebene im Rechtstexteditor einstellen.")
    if fenced:
        warnings.append("Nicht geschlossenes Markdown-Codefeld erkannt – Strukturprüfung erforderlich.")
    if len(changes) > 300:
        warnings.append("Sehr viele Formatierungsvorschläge; bitte abschnittsweise gegenprüfen.")
    return {
        "markdown": candidate,
        "suggested_changes": len(changes),
        "changes": changes[:300],
        "changes_truncated": len(changes) > 300,
        "paragraphs": parsed.norms,
        "groups": parsed.groups,
        "title": parsed.title,
        "source_preserved": True,
        "warnings": warnings,
        "note": ("Die Vorschau fügt ausschließlich Markdown-Überschriftsmarker "
                 "ein. Sie korrigiert weder OCR-Fehler noch juristischen Inhalt. "
                 "Vor Übernahme stets mit der Originaldatei vergleichen."),
    }
