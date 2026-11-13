"""Regression tests for review-only TAKT Markdown normalization."""
import pytest

from app.law_ai_markdown import review


def test_norms_formatted_without_rewriting_wording():
    source = "# Hauptsatzung\n\n§ 1 Name\n(1) Der Name lautet Testgemeinde.\n\n§ 2 Gebühren\n(1) Gebühr: 12,50 €.\n"
    result = review(source)
    assert result["changed"]
    assert result["suggestion_count"] == 2
    assert "### § 1 Name" in result["proposed_md"]
    assert "### § 2 Gebühren" in result["proposed_md"]
    assert "(1) Gebühr: 12,50 €." in result["proposed_md"]
    assert result["norms"] == 2
    assert review(result["proposed_md"])["changed"] is False


def test_does_not_change_ambiguous_statutory_references_in_prose():
    source = "# Text\n\n§ 3 gilt entsprechend.\n\nDie Vorschrift in § 5 ist anwendbar."
    result = review(source)
    assert result["changed"] is False
    assert result["proposed_md"] == source


def test_code_fences_are_not_rewritten():
    source = "# Titel\n\n```text\n§ 1 Foo\n```\n"
    result = review(source)
    assert result["changed"] is False
    assert result["proposed_md"] == source


def test_existing_markdown_heading_remains_untouched():
    source = "# Titel\n\n## Erster Abschnitt\n\n### § 1 Name\n\n(1) Inhalt"
    result = review(source)
    assert result["proposed_md"] == source


def test_missing_title_is_reported():
    result = review("§ 1 Name\n\n(1) Inhalt")
    assert any("Titel" in item for item in result["diagnostics"])


def test_empty_and_large_inputs_are_rejected():
    with pytest.raises(ValueError):
        review(" ")
    with pytest.raises(ValueError):
        review("x" * 2_000_001)
