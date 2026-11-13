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
        norm = laws.NORM_RE.match(text)
        norm_title = norm.group("title").strip() if norm else ""
        if (norm and norm_title and norm_title[:1].isupper() and
                not norm_title.endswith((".", ";", ",")) and
                (not following or following.startswith(("(", "§", "Art.", "Artikel")))):
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
    title_lines = []
    open_fence = None
    for number, raw in enumerate(lines, 1):
        fence_match = _FENCE.match(raw)
        if fence_match:
            mark = fence_match.group(1)[0]
            open_fence = None if open_fence == mark else mark
            continue
        if open_fence:
            continue
        heading_match = laws.HEADING_RE.match(raw)
        if not heading_match:
            continue
        depth, heading = len(heading_match.group(1)), heading_match.group(2)
        if depth == 1:
            title_lines.append(number)
        if laws.NORM_RE.match(heading) and depth != 3:
            issues.append(f"Zeile {number}: Einzelvorschrift sollte ### verwenden.")
        if laws.GROUP_RE.match(heading) and depth == 1:
            issues.append(f"Zeile {number}: Gliederungsabschnitt sollte ## verwenden.")
    if open_fence:
        issues.append("Ein Markdown-Codeblock ist nicht geschlossen.")
    if len(title_lines) > 1:
        issues.append("Mehrere Überschriften der Ebene # erkannt; Dokumenttitel prüfen.")
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
