"""Bounded, deterministic, *non-authoritative* comparison for Ortsrecht editing.

No LLM calls, no legal interpretation, no persistence and no original mutations.
The line-oriented preview must never be presented as an authenticated copy
of a PDF/DOCX source; it compares only OCR/MarkItDown text and working draft.
"""
from __future__ import annotations

import difflib
import re

MAX_PREVIEW_CHARS = 120_000
MAX_PREVIEW_LINES = 4_000
MAX_OUTPUT_LINES = 100
MAX_LINE_WIDTH = 280
_CRITICAL = {
    "Zahlen und Beträge": re.compile(r"\b\d[\d.,/]*\b|€|\bEUR\b", re.I),
    "Verneinungen": re.compile(r"\b(?:nicht|kein|keine|keinen|ohne|unzulässig)\b", re.I),
    "Fristen und Wirksamkeit": re.compile(r"\b(?:frist|gültig|inkraft|in kraft|außerkraft|außer kraft|bis zum)\b", re.I),
    "Rechtsverweise": re.compile(r"§|Art\.\s*\d|Abs\.\s*\d", re.I),
}


def compare(source: str, working: str) -> dict:
    if not isinstance(source, str) or not isinstance(working, str):
        raise ValueError("Ungültiger Textvergleich.")
    same = source == working
    response = {
        "same": same, "source_characters": len(source),
        "working_characters": len(working), "preview_available": False,
        "truncated": False, "added_lines": 0, "removed_lines": 0,
        "sensitive_categories": [], "lines": [],
        "note": "Dies ist ein technischer Vergleich zum importierten Textvorschlag, kein Abgleich mit dem amtlichen Original.",
    }
    if same:
        response["preview_available"] = True
        return response
    if (max(len(source), len(working)) > MAX_PREVIEW_CHARS or
            max(source.count("\n"), working.count("\n")) > MAX_PREVIEW_LINES):
        response["note"] = (
            "Der Text ist für eine sichere Browser-Diff-Vorschau zu umfangreich. "
            "Bitte importierten Text und Original manuell vergleichen."
        )
        return response

    old = source.splitlines(keepends=True)
    new = working.splitlines(keepends=True)
    critical = set()
    output = []
    full_count = 0
    for change in difflib.unified_diff(old, new, fromfile="Import-/OCR-Text",
                                       tofile="Redaktionelle Arbeitsfassung",
                                       n=2, lineterm="\n"):
        full_count += 1
        if change.startswith("+++") or change.startswith("---") or change.startswith("@@"):
            kind = "meta"
        elif change.startswith("+"):
            kind = "add"
        elif change.startswith("-"):
            kind = "remove"
        else:
            kind = "context"
        if kind in ("add", "remove"):
            text = change[1:]
            for name, pattern in _CRITICAL.items():
                if pattern.search(text):
                    critical.add(name)
            response["added_lines" if kind == "add" else "removed_lines"] += 1
        if len(output) < MAX_OUTPUT_LINES:
            output.append({
                "kind": kind,
                "text": change.rstrip("\n")[:MAX_LINE_WIDTH],
            })
    response["preview_available"] = True
    response["truncated"] = full_count > MAX_OUTPUT_LINES
    response["sensitive_categories"] = sorted(critical)
    response["lines"] = output
    return response
