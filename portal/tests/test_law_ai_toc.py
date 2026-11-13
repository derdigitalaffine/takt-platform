"""TOC-safe evidence and conservative legal heading regression cases."""
import json

from app import law_ai_coverage, law_ai_toc
from app.law_ai_agents import validate
from app.law_ai_markdown import review


SOURCE = (
    "# Satzung über Beiträge\n\n"
    "Inhaltsverzeichnis\n"
    "§ 1 Geltungsbereich ........ 2\n"
    "§ 2 Gebühren ................ 3\n\n"
    "§ 1 Geltungsbereich\n"
    "(1) Die Satzung gilt im gesamten Gebiet.\n\n"
    "§ 2 Gebühren\n"
    "(1) Die Gebühr beträgt 8 Euro.\n\n"
    "Ausgefertigt am 14.10.2026.\n"
    "Diese Satzung tritt am 01.01.2027 in Kraft.\n"
)


def test_toc_detection_and_body_offsets():
    spans = law_ai_toc.toc_ranges(SOURCE)
    assert len(spans) == 1
    toc = SOURCE.index("§ 1 Geltungsbereich ........ 2")
    actual = SOURCE.index("§ 1 Geltungsbereich\n(1)")
    assert law_ai_toc.in_toc(toc, toc + 10, spans)
    assert not law_ai_toc.in_toc(actual, actual + 10, spans)
    assert law_ai_toc.preferred_quote_offset(SOURCE, "§ 1 Geltungsbereich") == actual


def test_markdown_formatter_does_not_promote_toc_entries():
    result = review(SOURCE)
    assert result["contents_blocks"] == 1
    assert "### § 1 Geltungsbereich\n" in result["proposed_md"]
    assert "§ 1 Geltungsbereich ........ 2" in result["proposed_md"]
    assert "### § 1 Geltungsbereich ........ 2" not in result["proposed_md"]


def test_validator_filters_toc_only_headings_and_grounds_real_heading():
    answer = json.dumps({"headings": [
        {"quote": "§ 1 Geltungsbereich ........ 2", "level": 3},
        {"quote": "§ 1 Geltungsbereich", "level": 2},
    ], "warnings": []})
    result = validate("law_structure", answer, SOURCE)
    assert [x["quote"] for x in result["headings"]] == ["§ 1 Geltungsbereich"]
    combined = law_ai_coverage.aggregate(
        "law_structure",
        [(law_ai_coverage.Section(1, 0, len(SOURCE), SOURCE), result, False)],
        SOURCE, "advanced",
    )
    assert combined["headings"][0]["source_start"] == SOURCE.index(
        "§ 1 Geltungsbereich\n(1)")
    assert combined["headings"][0]["quote_occurrences"] == 1


def test_metadata_rejects_date_without_correct_event():
    answer = json.dumps({"fields": [
        {"field": "issued_on", "value": "14.10.2026",
         "evidence": "Ausgefertigt am 14.10.2026."},
        {"field": "valid_from", "value": "14.10.2026",
         "evidence": "Ausgefertigt am 14.10.2026."},
        {"field": "valid_from", "value": "01.01.2027",
         "evidence": "Diese Satzung tritt am 01.01.2027 in Kraft."},
    ]})
    result = validate("law_metadata", answer, SOURCE)
    assert [(x["field"], x["value"]) for x in result["fields"]] == [
        ("issued_on", "2026-10-14"), ("valid_from", "2027-01-01")
    ]


def test_unrelated_document_without_toc_keeps_heading_untouched():
    source = "# Satzung\n\n§ 1 Aufgaben\n(1) Die Gemeinde nimmt Aufgaben wahr.\n"
    assert not law_ai_toc.toc_ranges(source)
    assert "### § 1 Aufgaben" in review(source)["proposed_md"]


def test_plain_legal_body_titled_inhalt_is_not_misread_as_toc():
    source = ("# Inhalt\\n\\n§ 1 Gegenstand\\n(1) Inhalt\\n\\n"
              "§ 2 Geltung\\n(1) Hiermit gilt die Regel.")
    source = source.replace("\\\\n", "\\n")
    assert law_ai_toc.toc_ranges(source) == []


def test_deterministic_hints_are_cited_and_do_not_guess():
    from app.law_ai_metadata_hints import hints
    result = {item["field"]: item for item in hints(SOURCE)}
    assert result["title"]["value"] == "Satzung über Beiträge"
    assert result["doc_type"]["value"] == "satzung"
    assert result["issued_on"]["value"] == "2026-10-14"
    assert result["valid_from"]["value"] == "2027-01-01"
    for item in result.values():
        assert item["evidence"] in SOURCE
    truncated = hints("## Innerer Teil\\nAusgefertigt am 14.10.2026.".replace("\\\\n", "\\n"),
                      allow_header=False)
    assert "title" not in {item["field"] for item in truncated}


def test_stage_metadata_complements_empty_llm_output_when_authorized():
    result = validate("law_metadata", '{"fields":[]}', SOURCE, with_hints=True)
    keys = {item["field"] for item in result["fields"]}
    assert {"title", "doc_type", "issued_on", "valid_from"} <= keys
    assert all(item.get("origin") == "rule_based" for item in result["fields"])
