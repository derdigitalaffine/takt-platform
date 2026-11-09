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
    page.locator('[data-agent-open]').click()
    expect(page.locator('#takt-agent-input')).to_be_focused()
    assert page.locator('[data-agent-panel]').evaluate("el => el.parentElement === document.body")
    assert page.locator('[data-agent-shade]').evaluate("el => el.parentElement === document.body")
    assert page.locator('[data-agent-panel]').evaluate("el => { const r=el.getBoundingClientRect(); return r.top===0 && r.height===innerHeight && r.right===innerWidth; }")
    page.locator('[data-agent-close]').focus()
    page.keyboard.press('Shift+Tab')
    expect(page.locator('[data-agent-send]')).to_be_focused()
    page.keyboard.press('Tab')
    expect(page.locator('[data-agent-close]')).to_be_focused()
    command = 'Termin am 12.11.2026 von 9 bis 10 Uhr in Raum 1 zur Projektbesprechung mit Tagesordnung prüfen; Projektformular kopieren und Projektwissen in Projektablage verschieben.'
    page.locator('#takt-agent-input').fill(command)
    page.locator('#takt-agent-input').press('Enter')
    expect(page.locator('[data-agent-confirm]')).to_be_visible()
    expect(page.locator('[data-agent-proposals] li')).to_have_count(3)
    expect(page.locator('[data-agent-proposals]')).to_contain_text('Tagesordnung prüfen')
    expect(page.locator('[data-agent-proposals]')).to_contain_text('2026-11-12T09:00:00+01:00')
    expect(page.locator('[data-agent-proposals]')).to_contain_text('Projektablage')
    expect(page.locator('[data-agent-messages] a[href="/kalender?ansicht=termine"]')).to_have_count(1)
    expect(page.locator('[data-agent-messages] a[href^="/forms/"]')).to_have_count(1)
    page.screenshot(path=str(OUTPUT / 'agent-desktop-preview.png'))
    page.set_viewport_size(dict(width=390, height=844))
    assert page.locator('[data-agent-panel]').evaluate("el => {const r=el.getBoundingClientRect(); return r.top===0 && r.height===innerHeight && r.width===innerWidth;}")
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(OUTPUT / 'agent-mobile-preview.png'))
    page.locator('[data-agent-reject]').click()
    expect(page.locator('[data-agent-confirm]')).to_be_hidden()
    expect(page.locator('[data-agent-messages]')).to_contain_text('Vorschlag verworfen')
    page.locator('[data-agent-reset]').click()
    expect(page.locator('[data-agent-messages]')).to_contain_text('Neuer Auftrag')
    expect(page.locator('[data-agent-messages] a')).to_have_count(0)
    page.locator('#takt-agent-input').fill(command)
    page.locator('#takt-agent-input').press('Enter')
    expect(page.locator('[data-agent-confirm]')).to_be_visible()
    page.locator('[data-agent-approve]').click()
    expect(page.locator('[data-agent-confirm]')).to_be_hidden()
    expect(page.locator('[data-agent-messages]')).to_contain_text('Die freigegebenen Änderungen wurden gespeichert.')
    expect(page.locator('[data-agent-messages] a[href^="/forms/"]')).to_have_count(2)
    page.keyboard.press('Escape')
    expect(page.locator('#takt-agent-panel')).to_be_hidden()
    expect(page.locator('[data-agent-open]')).to_be_focused()
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
print('Agent browser flows passed: preview, links, cancel, reset, confirmation, mobile and keyboard.')
