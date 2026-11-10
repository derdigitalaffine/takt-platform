"""Actual Chromium smoke: visual Markdown editor, reversible mode and safe submission."""
import os
import subprocess
import sys
import time

import httpx
from playwright.sync_api import expect, sync_playwright

BASE = 'http://127.0.0.1:8782'
FIXTURE = '/tests/browser/knowledge_editor_fixture.html'
server = subprocess.Popen(
    [sys.executable, '-m', 'http.server', '8782', '--bind', '127.0.0.1'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
try:
    for _ in range(80):
        try:
            if httpx.get(BASE + FIXTURE, timeout=1, trust_env=False).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(.1)
    else:
        raise AssertionError('Knowledge block-editor fixture was not available.')

    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch()
        page = browser.new_page(viewport={'width': 1340, 'height': 930})
        page_errors = []
        page.on('pageerror', lambda error: page_errors.append(str(error)))
        page.goto(BASE + FIXTURE)
        textarea = page.locator('[data-knowledge-markdown]')
        source = textarea.input_value()
        expect(page.locator('.knowledge-visual-shell')).to_be_visible()
        expect(page.get_by_role('button', name='Visuelle Ansicht', exact=True)).to_contain_text('Visuell')
        expect(page.get_by_role('button', name='Markdown-Quelltext', exact=True)).to_contain_text('Markdown')
        expect(page.locator('.knowledge-visual-card')).to_have_count(5)
        assert page.evaluate('window.TAKTKnowledgeBlocks.serialize(window.TAKTKnowledgeBlocks.parse(document.querySelector("[data-knowledge-markdown]").value)) === document.querySelector("[data-knowledge-markdown]").value')

        # A no-op mode switch must not touch any legacy Markdown syntax/spacing.
        page.get_by_role('button', name='Markdown-Quelltext', exact=True).click()
        expect(textarea).to_be_visible()
        assert textarea.input_value() == source
        page.get_by_role('button', name='Visuelle Ansicht', exact=True).click()
        expect(page.locator('.knowledge-visual-shell')).to_be_visible()
        assert textarea.input_value() == source

        # Existing raw HTML stays TEXT in an editor, never interpreted as DOM.
        expect(page.locator('custom-tag')).to_have_count(0)
        expect(page.locator('img')).to_have_count(0)
        paragraph = page.locator('.knowledge-visual-paragraph').first
        paragraph.get_by_role('textbox').fill('Ein neuer **wichtiger** Inhalt.')
        assert 'Ein neuer **wichtiger** Inhalt.' in textarea.input_value()
        assert '<custom-tag>Unbekannte Erweiterung</custom-tag>' in textarea.input_value()
        assert '<img src=x onerror=alert(1)>' not in textarea.input_value()

        # Move the original heading down via keyboard; content stays present.
        page.locator('.knowledge-visual-heading').first.get_by_role('textbox').focus()
        page.keyboard.press('Alt+ArrowDown')
        assert '# Titel' not in textarea.input_value().split('\n\n', 1)[0]

        # Checklist interaction stays editable without exposing raw markdown.
        checklist = page.locator('.knowledge-visual-checklist').first
        checklist.get_by_role('checkbox', name='Aufgabe 1 erledigt').check()
        assert '- [x] Kontrolle A' in textarea.input_value()

        # Add a table and edit grid cells.
        page.locator('.knowledge-visual-add-kind').select_option('table')
        page.get_by_role('button', name='Block hinzufügen', exact=True).click()
        tables = page.locator('table.knowledge-visual-table')
        expect(tables).to_have_count(2)
        tables.last.get_by_role('textbox', name='Zeile 2, Spalte 1').fill('Neuer Wert')
        assert 'Neuer Wert' in textarea.input_value()

        # Invalid link blocks form submission; switching can't silently lose it.
        page.locator('.knowledge-visual-add-kind').select_option('link')
        page.get_by_role('button', name='Block hinzufügen', exact=True).click()
        link = page.locator('.knowledge-visual-link').last
        link.get_by_role('textbox', name='Linktext').fill('Sicher')
        link.get_by_role('textbox', name='Linkadresse').fill('javascript:alert(1)')
        expect(page.locator('.knowledge-visual-status')).to_contain_text('sichere')
        page.get_by_role('button', name='Speichern', exact=True).click()
        assert page.evaluate('window.testSubmissions.length') == 0
        link.get_by_role('textbox', name='Linkadresse').fill('/wissen/raum/10')
        page.get_by_role('button', name='Speichern', exact=True).click()
        assert page.evaluate('window.testSubmissions.length') == 1
        assert '[Sicher](/wissen/raum/10)' in page.evaluate('window.testSubmissions[0]')
        assert '<custom-tag>Unbekannte Erweiterung</custom-tag>' in page.evaluate('window.testSubmissions[0]')

        # Tab back to raw Markdown and return without editing: no extra changes.
        before = textarea.input_value()
        page.get_by_role('button', name='Markdown-Quelltext', exact=True).click()
        assert textarea.input_value() == before
        page.get_by_role('button', name='Visuelle Ansicht', exact=True).click()
        assert textarea.input_value() == before

        # Mobile viewport, no unwanted global horizontal scroll.
        page.set_viewport_size({'width': 390, 'height': 844})
        page.emulate_media(color_scheme='dark', reduced_motion='reduce')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), (
            page.evaluate('document.documentElement.scrollWidth'), page.evaluate('innerWidth')
        )
        page.screenshot(path='/tmp/takt-knowledge-block-mobile.png', full_page=True)
        assert not page_errors, page_errors
        browser.close()
finally:
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=5)
print('Knowledge visual editor browser smoke passed: roundtrip, reorder, checklist, table, safe link, submit and mobile.')
