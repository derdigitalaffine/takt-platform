"""Conservative TAKT Ortsrecht Markdown diagnostics and formatting proposals.

This module does not rewrite legal content or save documents. The output is a
reviewable suggestion only; applying it requires an explicit user action.
"""
import re

from . import laws

_NORMALIZE_MAX = 2_000_000
_HEAD = re.compile(r"^\s{0,3}#{1,6}\s+")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def review(markdown: str) -> dict:
    """Return a lossless heading-only proposal and real parser diagnostics."""
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("Bitte zuerst einen Rechtstext eingeben.")
    if len(markdown.encode("utf-8")) > _NORMALIZE_MAX:
        raise ValueError("Der Entwurf ist zu groß (maximal 2 MB).")
    source = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    output = list(lines)
    suggestions = []
    fence = None
    for index, line in enumerate(lines):
        match = _FENCE.match(line)
        if match:
            char = match.group(1)[0]
            if fence is None:
                fence = char
            elif fence == char:
                fence = None
            continue
        if fence or _HEAD.match(line) or line.startswith(("    ", "\t")):
            continue
        text = line.strip()
        prev = lines[index - 1].strip() if index else ""
        following = lines[index + 1].strip() if index + 1 < len(lines) else ""
        # Only standalone candidates after a blank line are safe to propose.
        # Preserve all content bytes on each line; only insert ATX markers.
        if prev or not text or len(text) > 120:
            continue
        if laws.NORM_RE.match(text) and (
            not following or following.startswith(("(", "§", "Art.", "Artikel"))):
            level = 3
        elif laws.GROUP_RE.match(text) and not following:
            level = 2
        else:
            continue
        output[index] = "#" * level + " " + line
        suggestions.append({"line": index + 1, "level": level, "text": text[:120]})
    proposed = "\n".join(output)
    parsed = laws.parse(proposed)
    issues = list(laws.check_outline(parsed))
    if not parsed.title:
        issues.insert(0, "Kein eindeutiger Dokumenttitel erkannt. Verwende # Titel.")
    if not parsed.nodes:
        issues.append("Keine Gliederungsüberschriften erkannt.")
    if not any(node.kind == "norm" for node in parsed.nodes):
        issues.append("Keine Einzelvorschriften erkannt: Gliederung und Unterste-Ebene-Einstellung prüfen.")
    # A formatting suggestion may add markers, never alter source words.
    def remove_added_markers(candidate: str) -> str:
        updated = candidate.split("\n")
        for item in suggestions:
            idx = item["line"] - 1
            updated[idx] = updated[idx][item["level"] + 1:]
        return "\n".join(updated)
    assert remove_added_markers(proposed) == source
    return {
        "proposed_md": proposed,
        "changed": bool(suggestions),
        "suggestions": suggestions[:100],
        "suggestion_count": len(suggestions),
        "diagnostics": issues[:30],
        "title": parsed.title,
        "norms": parsed.norms,
        "groups": parsed.groups,
        "note": "Nur Formatierungsvorschlag. Vor Übernahme jede Überschrift mit dem Original abgleichen.",
    }
