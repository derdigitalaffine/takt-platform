"""No-loss full-document LLM batching and source-position validation."""
import pytest

from app import law_ai_coverage as coverage


def test_split_covers_every_codepoint_once_with_stable_offsets():
    blocks = [
        "# Satzung der Gemeinde\n",
        ("§ 1 Die Gebühr beträgt 10 €. Keine Ausnahme.\n" * 500),
        ("Abschnitt Zwei – ändert keine Fristen. 😊\n" * 530),
        "Bekanntmachung vom 13.11.2026\n",
    ]
    full = "".join(blocks)
    pieces = coverage.sections(full)
    assert len(full) > 30_000
    assert 2 <= len(pieces) <= coverage.MAX_CHUNKS
    assert all(0 < len(p.text) <= coverage.MAX_CHUNK_CHARS for p in pieces)
    assert pieces[0].start == 0 and pieces[-1].end == len(full)
    assert "".join(section.text for section in pieces) == full
    assert all(a.end == b.start for a, b in zip(pieces, pieces[1:]))
    assert [p.number for p in pieces] == list(range(1, len(pieces) + 1))
    assert coverage.count_calls(full, "advanced") == 3 * len(pieces)
    assert coverage.count_calls(full, "simple") == 3


def test_pathological_long_line_never_truncates_and_flags_split():
    source = "X" * 120_000
    sections = coverage.sections(source)
    assert len(sections) <= 10
    assert "".join(x.text for x in sections) == source
    assert any(s.split_line for s in sections)
    with pytest.raises(ValueError):
        coverage.sections("X" * 120_001)
    with pytest.raises(ValueError):
        coverage.sections("")
    with pytest.raises(ValueError):
        coverage.count_calls("Satzung", "fake")


def test_combined_evidence_positions_and_conflicts():
    source = "Ausgefertigt am 13.11.2026\n" + "X" * 20_000 + "\nAusgefertigt am 14.11.2026"
    segments = coverage.sections(source)
    first = {
        "schema": 1, "fields": [{"field": "issued_on", "value": "2026-11-13",
                                 "evidence": "13.11.2026"}], "warnings": [],
    }
    last = {
        "schema": 1, "fields": [{"field": "issued_on", "value": "2026-11-14",
                                 "evidence": "14.11.2026"}], "warnings": [],
    }
    items = [(section, first if idx == 0 else last if idx == len(segments) - 1 else
             {"schema": 1, "fields": [], "warnings": []}, False)
             for idx, section in enumerate(segments)]
    combined = coverage.aggregate("law_metadata", items, source, "advanced")
    assert combined["coverage"]["mode"] == "full_text_submitted"
    assert combined["coverage"]["source_chars"] == len(source)
    assert combined["coverage"]["sections_total"] == len(segments)
    assert len(combined["fields"]) == 2
    for field in combined["fields"]:
        assert source[field["source_start"]:field["source_end"]] == field["evidence"]
    assert any("Mehrdeutige" in note for note in combined["warnings"])
    assert any("keine Garantie" in note for note in combined["warnings"])


def test_fail_closed_on_missing_or_sampled_segment():
    source = "§ 1 Rechtstext\n" * 2600
    chunks = coverage.sections(source)
    stage = {"schema": 1, "headings": [], "warnings": []}
    with pytest.raises(ValueError, match="Textabschnitt fehlt"):
        coverage.aggregate("law_structure",
                           [(chunk, stage, False) for chunk in chunks[:-1]],
                           source, "advanced")
    with pytest.raises(ValueError, match="Textabdeckung"):
        coverage.aggregate("law_structure",
                           [(chunk, stage, chunk.number == 1) for chunk in chunks],
                           source, "advanced")
    fast = coverage.aggregate("law_structure",
                              [(coverage.Section(1, 0, len(source), source), stage, True)],
                              source, "simple")
    assert fast["sampled"] is True
    assert fast["coverage"]["mode"] == "excerpts_only"


def test_unsupported_llm_result_quotes_do_not_enter_combined_proposals():
    source = "§ 1 Kommunalabgabe"
    section = coverage.sections(source)[0]
    result = {"schema": 1, "findings": [{"severity": "high",
              "quote": "Unbelegte erfundene Quelle",
              "reason": "Sollte abgelehnt werden."}], "warnings": []}
    combined = coverage.aggregate("law_verify", [(section, result, False)], source, "advanced")
    assert combined["findings"] == []
    assert combined["coverage"]["proposals_omitted"] == 1



def test_duplicate_citation_is_flagged_as_ambiguous():
    source = "§ 1 Die Gebühr beträgt 10 €.\n" * 3
    section = coverage.sections(source)[0]
    quote = "Die Gebühr beträgt 10 €."
    result = {"schema": 1, "findings": [{
        "severity": "high", "quote": quote, "reason": "Original prüfen",
    }], "warnings": []}
    assembled = coverage.aggregate("law_verify", [(section, result, False)],
                                   source, "advanced")
    finding = assembled["findings"][0]
    assert finding["quote_occurrences"] == 3
    assert source[finding["source_start"]:finding["source_end"]] == quote



def test_context_recovery_picks_nearest_paragraph_boundary_not_end_of_window():
    source = "§ 5 Keine Gebühr ohne Beschluss.\n" * 190
    whole = coverage.sections(source)[0]
    result = coverage.bisect(whole)
    assert result is not None
    left, right = result
    assert left.text + right.text == source
    assert left.end == right.start
    # A trailing break towards 2/3 of the allowed window would leave the
    # first request too large for a model with a 4000-char context ceiling.
    assert max(len(left.text), len(right.text)) < 4000
    assert abs(len(left.text) - len(right.text)) < 100
