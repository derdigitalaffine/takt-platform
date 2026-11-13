"""Deterministic, complete-source batching for human-reviewed Ortsrecht analyses.

Every source character belongs to exactly one consecutive segment. No semantic
retrieval, OCR correction, silent truncation or automatic legal text changes.
"""
from dataclasses import dataclass
from . import law_ai_agents, law_ai_toc

MAX_CHUNK_CHARS = 14_000
MIN_CHUNK_CHARS = 12_000
MAX_CHUNKS = 10
MAX_COMBINED_ITEMS = 100
MAX_WARNINGS = 20
MAX_CALLS = MAX_CHUNKS * len(law_ai_agents.STAGES)


@dataclass(frozen=True)
class Section:
    number: int
    start: int
    end: int
    text: str
    split_line: bool = False


def sections(source: str) -> list[Section]:
    """Cover the entire source with no inserted labels or missed characters."""
    if not isinstance(source, str) or not 0 < len(source) <= law_ai_agents.MAX_SOURCE_CHARS:
        raise ValueError("Für die vollständige Analyse sind 1 bis 120.000 Zeichen zulässig.")
    pieces: list[Section] = []
    pos = 0
    while pos < len(source):
        end = min(len(source), pos + MAX_CHUNK_CHARS)
        split_line = False
        if end < len(source):
            # Find the last line ending near the chosen boundary. Do not split
            # well-behaved paragraphs, but still bound pathological long lines.
            newline = source.rfind("\n", pos + MIN_CHUNK_CHARS, end)
            if newline >= 0:
                end = newline + 1
            else:
                split_line = True
        piece = source[pos:end]
        pieces.append(Section(len(pieces) + 1, pos, end, piece, split_line))
        if len(pieces) > MAX_CHUNKS:
            raise ValueError("Der Text benötigt mehr als 10 Modellabschnitte; bitte fachlich aufteilen.")
        pos = end
    if "".join(chunk.text for chunk in pieces) != source:
        raise ValueError("Die vollständige Übertragung kann nicht nachgewiesen werden.")
    return pieces


MIN_RECOVERY_CHARS = 600  # don't split tiny passages into meaningless snippets
MAX_RECOVERY_SPLITS = 1   # per originally consented model section


def bisect(section: Section) -> tuple[Section, Section] | None:
    """Deterministic one-level output-error recovery, preserving every char.

    Only used for invalid/truncated model output (not network/permission
    errors). We never silently delete or summarize normative source text.
    """
    size = len(section.text)
    if size < 2 * MIN_RECOVERY_CHARS:
        return None
    middle = size // 2
    # Prefer a nearby paragraph break to avoid cutting a provision in two.
    low = max(MIN_RECOVERY_CHARS, middle - size // 7)
    high = min(size - MIN_RECOVERY_CHARS, middle + size // 7)
    before = section.text.rfind("\n", low, middle)
    after = section.text.find("\n", middle, high)
    candidates = [idx + 1 for idx in (before, after)
                  if idx >= 0 and MIN_RECOVERY_CHARS <= idx + 1
                  <= size - MIN_RECOVERY_CHARS]
    # Nearest newline to the middle, not the *last* newline in the window:
    # the latter can produce an unhelpful 65/35 split that still overflows.
    pivot = min(candidates, key=lambda pos: abs(pos - middle)) if candidates else middle
    if not MIN_RECOVERY_CHARS <= pivot <= size - MIN_RECOVERY_CHARS:
        return None
    left = Section(section.number, section.start, section.start + pivot,
                   section.text[:pivot], section.split_line or not candidates)
    right = Section(section.number, section.start + pivot, section.end,
                    section.text[pivot:], section.split_line or not candidates)
    if left.text + right.text != section.text or left.end != right.start:
        raise ValueError("Fehler bei der verlustfreien Teilung der Rechtsquelle.")
    return left, right


def count_calls(source: str, mode: str) -> int:
    if mode == "advanced":
        return len(sections(source)) * len(law_ai_agents.STAGES)
    if mode == "simple":
        return len(law_ai_agents.STAGES)
    raise ValueError("Unbekannter KI-Analysemodus.")


def _field_key(stage: str) -> str:
    return {"law_structure": "headings", "law_metadata": "fields",
            "law_verify": "findings"}[stage]


def aggregate(stage: str, parts: list[tuple[Section, dict, bool]],
              full_source: str, mode: str) -> dict:
    """Merge validated proposals, with local source offsets and honest coverage.

    'complete_input' says every character was included in an LLM request. It
    never claims semantic completeness, correct OCR or a legally valid text.
    """
    if not parts or mode not in ("simple", "advanced"):
        raise ValueError("Unvollständige KI-Auswertung.")
    key = _field_key(stage)
    accumulated = []
    warnings: list[str] = []
    seen = set()
    metadata_values: dict[str, set[str]] = {}
    excluded = 0
    navigation = law_ai_toc.toc_ranges(full_source)
    for section, result, sampled in parts:
        if sampled:
            warnings.append(f"Abschnitt {section.number}: Nur ausgewählte Textteile analysiert.")
        if section.split_line:
            warnings.append(f"Abschnitt {section.number}: Überlange Zeile an der Abschnittsgrenze geteilt.")
        for warning in result.get("warnings", []):
            if isinstance(warning, str) and warning not in warnings:
                warnings.append(warning[:220])
        for item in result.get(key, []):
            if not isinstance(item, dict):
                excluded += 1
                continue
            quote = item.get("evidence" if stage == "law_metadata" else "quote")
            if not isinstance(quote, str) or not quote or quote not in section.text:
                excluded += 1
                continue
            offsets = [section.start + p for p in law_ai_toc.source_line_offsets(section.text, quote)]
            usable = [p for p in offsets if not law_ai_toc.in_toc(
                p, p + len(quote), navigation)]
            # A repeated quote in the body is not a unique anchor:
            # reject for structures and mark metadata as ambiguous.
            if not usable:
                excluded += 1
                continue
            absolute_pos = usable[0]
            if full_source[absolute_pos:absolute_pos + len(quote)] != quote:
                excluded += 1
                continue
            candidate = dict(item)
            candidate.update({
                "section": section.number,
                "source_start": absolute_pos,
                "source_end": absolute_pos + len(quote),
                # A quote can be repeated in the same source section. In that
                # case no precise *semantic* occurrence is proven; prohibit
                # direct one-click transformations in the UI.
                "quote_occurrences": len(usable),
            })
            fingerprint = (candidate.get("field"), candidate.get("value"),
                           candidate.get("level"), quote, absolute_pos)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            if stage == "law_metadata":
                metadata_values.setdefault(str(item.get("field")), set()).add(str(item.get("value")))
            if len(accumulated) < MAX_COMBINED_ITEMS:
                accumulated.append(candidate)
            else:
                excluded += 1
    if excluded:
        warnings.append(
            f"{excluded} Fundstelle(n) nicht übernommen oder wegen des Anzeigelimits ausgelassen."
        )
    if stage == "law_metadata":
        for field, values in metadata_values.items():
            if len(values) > 1:
                warnings.append(f"Mehrdeutige Stammdaten für „{field}“: unterschiedliche belegte Werte. Manuell klären.")
    if mode == "advanced":
        if any(sampled for _, _, sampled in parts):
            raise ValueError("Die vollständige Textabdeckung konnte nicht bestätigt werden.")
        if "".join(section.text for section, _, _ in parts) != full_source:
            raise ValueError("Ein Textabschnitt fehlt. Es wird keine vollständige Analyse behauptet.")
    # Never discard the completeness and legal caveats even if model warnings
    # fill the per-document warning budget.
    critical = [
        "Quelltext-Fundstellen stammen aus OCR/MarkItDown, nicht zwingend aus einem amtlich richtigen Original.",
        "Auch bei vollständiger Übermittlung keine Garantie für OCR-, Text- oder Rechtsrichtigkeit.",
    ]
    if mode == "simple" and any(sampled for _, _, sampled in parts):
        critical.insert(0, "Schnellprüfung nutzte Textauszüge; nicht alle Abschnitte gingen an die KI.")
    return {
        "schema": 2, key: accumulated,
        "warnings": (critical + warnings)[:MAX_WARNINGS],
        "sampled": any(sampled for _, _, sampled in parts),
        "coverage": {
            "mode": "full_text_submitted" if mode == "advanced" or
                    (len(parts) == 1 and not parts[0][2] and
                     parts[0][0].text == full_source) else "excerpts_only",
            "source_chars": len(full_source),
            "sections_total": len(parts),
            "sections_analyzed": len(parts),
            "model_calls": len(parts),
            "proposals_displayed": len(accumulated),
            "proposals_omitted": excluded,
        },
    }
