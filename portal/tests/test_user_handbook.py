"""Regression checks for the modular TAKT user handbook.

The portal module registry must always have a corresponding user guide.
Relative Markdown links are checked without network access or a Markdown
renderer; external URLs and historical archive links are intentionally skipped.
"""
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
INDEX = DOCS / "BENUTZERHANDBUCH.md"
GUIDES = DOCS / "handbuch" / "module"
BASICS = DOCS / "handbuch" / "grundlagen.md"
ARCHIVE = DOCS / "handbuch" / "archiv" / "benutzerhandbuch-bisher.md"

MODULE_GUIDES = {
    "ai": "takt-agent.md",
    "knowledge": "wissensmanagement.md",
    "anliegen": "interne-anliegen.md",
    "calendars": "kalender-urlaub.md",
    "tasks": "aufgaben.md",
    "seminars": "seminare.md",
    "shortlinks": "kurzlinks.md",
    "forms": "formulare.md",
    "polls": "umfragen-abstimmungen.md",
    "bookings": "terminbuchung.md",
    "laws": "rechtstexte.md",
    "maps": "kartenbrowser.md",
    "applications": "online-antraege.md",
    "circulations": "umlaeufe-aushaenge.md",
    "dms": "ablage-dms.md",
    "resources": "ressourcen.md",
    "signage": "digital-signage.md",
    "krank": "krankmeldungen.md",
    "verbandbuch": "digitales-verbandbuch.md",
}
EXTRA_GUIDES = ("meetings.md", "abwesenheiten.md", "zahlungen.md")


def test_every_configurable_module_has_single_guide():
    main = (ROOT / "portal" / "app" / "main.py").read_text(encoding="utf-8")
    registry = main.split("MODULES = {", 1)[1].split("\n}", 1)[0]
    keys = set(re.findall(r'^\s*"([a-z_]+)":', registry, re.M))
    assert set(MODULE_GUIDES) == keys, (
        f"Handbuch-Module und App-Register unterschiedlich: "
        f"im Register fehlend {set(MODULE_GUIDES) - keys}, "
        f"ohne Anleitung {keys - set(MODULE_GUIDES)}"
    )
    home = INDEX.read_text(encoding="utf-8")
    assert "handbuch/grundlagen.md" in home
    assert BASICS.is_file()
    for name in (*MODULE_GUIDES.values(), *EXTRA_GUIDES):
        path = GUIDES / name
        assert path.is_file(), f"Fehlende Modulanleitung: {path}"
        body = path.read_text(encoding="utf-8")
        assert body.startswith("# ")
        assert "## Schnellstart" in body
        assert "Grundlagen" in body
        assert f"handbuch/module/{name}" in home


def test_handbook_links_resolve_locally():
    pages = [INDEX, BASICS, *sorted(GUIDES.glob("*.md"))]
    for path in pages:
        body = path.read_text(encoding="utf-8")
        for href in re.findall(r'\]\(([^)\s]+)(?:\s+"[^"]*")?\)', body):
            if href.startswith(("#", "/", "http:", "https:", "mailto:", "data:")):
                continue
            target = unquote(href.split("#", 1)[0])
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            assert resolved.is_file(), f"{path}: ungültiger Link {href}"


def test_original_handbook_is_preserved_and_old_links_have_targets():
    archived = ARCHIVE.read_text(encoding="utf-8")
    home = INDEX.read_text(encoding="utf-8")
    assert len(archived) > 100_000
    toc = archived.split("## Inhalt", 1)[1].split("\n---\n", 1)[0]
    for fragment in set(re.findall(r'\]\(#([^)]+)\)', toc)):
        assert f'<a id="{fragment}"></a>' in home, (
            f"Alter Kapitel-Link verloren: #{fragment}"
        )
