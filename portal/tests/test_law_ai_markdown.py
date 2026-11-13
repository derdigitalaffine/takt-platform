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


def test_ai_heading_validation_uses_canonical_markdown():
    import json
    from app.law_ai_agents import validate

    source = "# Satzung\\n\\n## Erster Teil\\n\\n### § 1 Name\\n(1) Inhalt"
    source = source.replace("\\\\n", "\\n")
    answer = json.dumps({"headings": [
        {"quote": "### § 1 Name", "level": 2},
        {"quote": "## Erster Teil", "level": 5},
    ], "warnings": []})
    parsed = validate("law_structure", answer, source)
    assert parsed["headings"][0]["markdown_suggestion"] == "### § 1 Name"
    assert parsed["headings"][1]["markdown_suggestion"] == "## Erster Teil"


def test_review_endpoint_requires_auth_and_does_not_persist():
    from conftest import client, csrf_of, login, settings

    settings(module_laws="1")
    anon = client()
    response = anon.post("/laws-assistant/markdown/review",
                         data={"body_md": "# Satzung\\n\\n§ 1 Name"})
    assert response.status_code in (302, 303, 401, 403)

    c = login("admin@example.org", "admin-passwort-123")
    csrf = csrf_of(c.get("/laws-assistant").text)
    response = c.post("/laws-assistant/markdown/review",
                      data={"csrf": csrf, "body_md": "# Satzung\\n\\n§ 1 Name\\n(1) Test"})
    assert response.status_code == 200, response.text
    assert response.json()["proposed_md"].startswith("# Satzung")
    assert response.headers["cache-control"] == "no-store"


def test_workspace_subviews_are_addressable():
    from conftest import login, settings

    settings(module_laws="1")
    c = login("admin@example.org", "admin-passwort-123")
    for tab in ("uebersicht", "import", "ki", "editor"):
        response = c.get("/laws-assistant?bereich=" + tab)
        assert response.status_code == 200
        assert 'data-view="' + tab + '"' in response.text
