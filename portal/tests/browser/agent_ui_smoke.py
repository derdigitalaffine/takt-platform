"""Exercise real agent preview, cancel, reset, execution and mobile layout."""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

BASE = 'http://127.0.0.1:8765'
OUTPUT = Path('browser-artifacts')
OUTPUT.mkdir(exist_ok=True)


def exercise(page):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(BASE + '/login')
    page.get_by_label('E-Mail', exact=True).fill('browser@example.org')
    page.get_by_label('Passwort', exact=True).fill('browser-test-password')
    page.get_by_role('button', name='Anmelden', exact=True).click()
    expect(page).not_to_have_url(re.compile('/login'))
    page.goto(BASE + '/agent')
    page.get_by_role('button', name='Neuer Chat', exact=True).click()
    chat_url = page.url
    expect(page.locator('[name="use_agent"]')).to_be_checked()
    command = 'Termin am 12.11.2026 von 9 bis 10 Uhr in Raum 1 zur Projektbesprechung mit Tagesordnung prüfen; Projektformular kopieren und Projektwissen in Projektablage verschieben.'
    page.locator('#ai-prompt').fill(command)
    page.get_by_role('button', name='Nachricht senden', exact=True).click()
    expect(page).to_have_url(re.compile(r'/kalender\?ansicht=termine&agent_plan='))
    expect(page.locator('[data-agent-draft]')).to_contain_text('Die Fachmaske ist ausgefüllt')
    form = page.locator('#calendar-event-form')
    expect(form.locator('[name="title"]')).to_have_value('Projektbesprechung')
    expect(form.locator('[name="location"]')).to_have_value('Raum 1')
    expect(form.locator('[name="description"]')).to_have_value('Tagesordnung prüfen')
    expect(form.locator('[name="repeat"]')).to_be_disabled()
    form.locator('[name="title"]').fill('Von mir geprüfte Projektbesprechung')
    page.screenshot(path=str(OUTPUT / 'agent-desktop-native.png'), full_page=True)
    page.set_viewport_size(dict(width=390, height=844))
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(OUTPUT / 'agent-mobile-native.png'), full_page=True)
    page.get_by_role('button', name='Vorschlag prüfen', exact=True).click()
    expect(page.locator('[data-agent-final-preview]')).to_contain_text('Von mir geprüfte Projektbesprechung')
    page.get_by_role('button', name='Diesen Schritt verbindlich speichern', exact=True).click()
    expect(page).to_have_url(re.compile(r'/forms/[0-9]+\?agent_plan='))
    expect(page.locator('[data-agent-draft]')).to_contain_text('geschlossenen Entwurf kopieren')
    page.get_by_role('button', name='Vorschlag prüfen', exact=True).click()
    page.get_by_role('button', name='Diesen Schritt verbindlich speichern', exact=True).click()
    expect(page).to_have_url(re.compile(r'/dms/r/[0-9]+\?agent_plan='))
    expect(page.locator('[data-agent-draft]')).to_contain_text('Projektablage')
    expect(page.locator('form[action="/agent/draft/review"] [name="area_id"] option:checked')).to_have_text(re.compile('Projektablage'))
    page.get_by_role('button', name='Vorschlag prüfen', exact=True).click()
    page.get_by_role('button', name='Diesen Schritt verbindlich speichern', exact=True).click()
    expect(page).to_have_url(re.compile(r'/dms/r/[0-9]+$'))
    page.goto(chat_url)
    expect(page.locator('[data-ai-messages]')).to_contain_text(re.compile('Drei Schritte zur Prüfung|Wissensrechte ausgeblendet'))
    def handoff(command, expected_path, field=None, value=None):
        page.goto(chat_url)
        page.locator('#ai-prompt').fill(command)
        page.get_by_role('button', name='Nachricht senden', exact=True).click()
        expect(page).to_have_url(re.compile(expected_path))
        expect(page.locator('[data-agent-draft]')).to_contain_text('Die Fachmaske ist ausgefüllt')
        if field:
            expect(page.locator('form[action="/agent/draft/review"] [name="' + field + '"]')).to_have_value(value)
        page.get_by_role('button', name='Vorschlag prüfen', exact=True).click()
        expect(page.locator('[data-agent-final-preview]')).to_be_visible()
        page.get_by_role('button', name='Diesen Schritt verbindlich speichern', exact=True).click()
        expect(page.locator('[data-agent-final-preview]')).to_have_count(0)
    handoff('Internes Anliegen: Zwei Bürostühle für Raum 1 prüfen', r'/anliegen/neu\?agent_plan=', 'title', 'Browser Anliegen')
    handoff('Anliegen bearbeiten: Browser Anliegen starten', r'/anliegen/[0-9]+\?agent_plan=', 'status', 'in_progress')
    handoff('Anliegen zuweisen: Browser Anliegen an Alex Agent', r'/anliegen/[0-9]+\?agent_plan=')
    handoff('Routing ändern: Agent IT Anliegen an Alex Agent ohne bestehende Vorgänge umzuweisen', r'/anliegen/kategorien\?agent_plan=', 'title', 'Agent IT Anliegen Team')
    handoff('Aufgabe vorbereiten: Browser Aufgabe mit Unterlagen prüfen', r'/aufgaben/neu\?agent_plan=', 'title', 'Browser Aufgabe')
    handoff('Aufgabe zuweisen: Browser Aufgabe an Alex Agent', r'/aufgaben/[0-9]+/bearbeiten\?agent_plan=')
    handoff('Aufgabe priorisieren: Browser Aufgabe hoch', r'/aufgaben/[0-9]+/bearbeiten\?agent_plan=', 'priority', 'high')
    handoff('Aufgabe starten: Browser Aufgabe in Bearbeitung', r'/aufgaben/[0-9]+\?agent_plan=')
    page.goto(chat_url)
    page.locator('#ai-prompt').fill('Vertrauliche Beschwerde wegen Mobbing bitte manuell erfassen')
    page.get_by_role('button', name='Nachricht senden', exact=True).click()
    expect(page).to_have_url(re.compile(r'/anliegen/neu\?agent_private='))
    expect(page.locator('#anliegen-review')).to_have_attribute('open', '')
    expect(page.locator('#anliegen-final-description')).to_have_value(re.compile('Mobbing'))
    expect(page.locator('#anliegen-ai')).to_have_count(0)
    page.goto(BASE + '/urlaub/planer')
    unit_id = page.locator('select[name="unit"] option').filter(has_text='Agent Urlaubsbereich').first.get_attribute('value')
    page.goto(BASE + '/urlaub/planer?unit=' + unit_id)
    deletion = page.get_by_role('link', name='Urlaubsabwesenheit löschen', exact=True)
    expect(deletion).to_have_count(1)
    deletion.click()
    expect(page.get_by_role('heading', name='Eingetragene Abwesenheit löschen')).to_be_visible()
    page.locator('[name="reason"]').fill('Fehlerhafte Testeintragung korrigieren')
    page.locator('[name="confirm"]').check()
    page.screenshot(path=str(OUTPUT / 'leave-admin-delete-mobile.png'), full_page=True)
    page.get_by_role('button', name='Abwesenheit jetzt löschen', exact=True).click()
    expect(page.locator('.alert').filter(has_text='Abwesenheit aus der aktiven Planung gelöscht')).to_be_visible()
    page.goto(BASE + '/urlaub/planer?unit=' + unit_id)
    expect(page.get_by_role('link', name='Urlaubsabwesenheit löschen', exact=True)).to_have_count(0)
    assert not errors, errors


with tempfile.TemporaryDirectory(prefix='takt-agent-browser-') as root:
    env = {**os.environ, 'DATA_DIR': root + '/data', 'RECORDINGS_DIR': root + '/recordings',
           'CADDY_CONF_DIR': root + '/caddy'}
    with (OUTPUT / 'agent-server.log').open('w') as log:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'agent_ui_app:app', '--app-dir', 'tests/browser',
                                   '--host', '127.0.0.1', '--port', '8765', '--lifespan', 'off'],
                                  env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(80):
                try:
                    if httpx.get(BASE + '/login', timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if server.poll() is not None:
                    raise RuntimeError('Agent fixture failed; see agent-server.log')
                time.sleep(.25)
            else:
                raise RuntimeError('Agent fixture startup timed out')
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page(viewport=dict(width=1440, height=1000))
                    exercise(page)
                finally:
                    browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill(); server.wait(timeout=5)
print('Central agent browser flows passed: edited native forms, sequential confirmation, history, protected manual intake and mobile layout.')
