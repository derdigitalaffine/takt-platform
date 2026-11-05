"""Exercise real leave and calendar forms with isolated organizational fixtures."""
import os,subprocess,sys,tempfile,time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
base='http://127.0.0.1:8769'
with tempfile.TemporaryDirectory(prefix='takt-leave-') as root:
    env={**os.environ,'DATA_DIR':root+'/data','RECORDINGS_DIR':root+'/recordings','CADDY_CONF_DIR':root+'/caddy','PORTAL_ROOMS_FILE':root+'/rooms.json','PORTAL_CHAT_DIR':root+'/chat'}
    logpath=Path('/tmp/takt-leave-browser.log')
    with logpath.open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','organization_ui_app:app','--app-dir','tests/browser','--host','127.0.0.1','--port','8769','--lifespan','off'],env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(80):
                try:
                    if httpx.get(base+'/login',trust_env=False).status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.25)
            else:raise AssertionError(logpath.read_text())
            with sync_playwright() as pw:
                browser=pw.chromium.launch();p=browser.new_page(viewport={'width':1440,'height':1000});errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
                p.goto(base+'/login');p.get_by_label('E-Mail',exact=True).fill('planner@example.org');p.get_by_label('Passwort',exact=True).fill('browser-test-password');p.get_by_role('button',name='Anmelden',exact=True).click()
                p.goto(base+'/urlaub');p.get_by_label('Organisationseinheit',exact=True).select_option(label='Finanzen');p.get_by_role('button',name='Anzeigen',exact=True).click()
                p.locator('#leave-starts_on-display').fill('07.12.2026');p.locator('#leave-ends_on-display').fill('09.12.2026');p.get_by_role('button',name='Als geplant speichern',exact=True).click()
                expect(p.locator('article')).to_contain_text('Geplant')
                p.get_by_role('button',name='Verbindlich markieren',exact=True).click();expect(p.locator('article > p').first).to_contain_text('Verbindlich')
                p.get_by_role('button',name='Zeitraum bearbeiten',exact=True).click()
                p.locator('#leave-starts_on-display').fill('14.12.2026');p.locator('#leave-ends_on-display').fill('16.12.2026')
                p.get_by_role('button',name='Konflikte prüfen',exact=True).click();expect(p.locator('#leave-preview')).to_be_visible()
                p.get_by_role('button',name='Änderung als Entwurf speichern',exact=True).click()
                expect(p.locator('article')).to_contain_text('Bisheriger verbindlicher Zeitraum')
                p.get_by_role('button',name='Verbindlich markieren',exact=True).click()
                p.set_viewport_size({'width':390,'height':844});p.screenshot(path='/tmp/takt-leave-mobile.png',full_page=True);assert p.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),p.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+2&&getComputedStyle(e).position!=='absolute').slice(0,20).map(e=>[e.tagName,e.className,Math.round(e.getBoundingClientRect().width)])")
                p.screenshot(path='/tmp/takt-leave-mobile.png',full_page=True);p.set_viewport_size({'width':1440,'height':1000})
                p.goto(base+'/kalender');p.locator('summary').filter(has_text='Kalender anlegen').click()
                p.get_by_label('Name',exact=True).fill('Gemeinsame Jahrestermine');p.get_by_role('button',name='Kalender anlegen',exact=True).click()
                expect(p.get_by_label('Gemeinsame Jahrestermine',exact=True)).to_be_visible()
                p.locator('#event-editor summary').click();form=p.locator('#calendar-event-form');form.get_by_label('Titel',exact=True).fill('Jahresauftakt');form.get_by_label('Ganztägig',exact=True).check()
                form.locator('#calendar-start-display').fill('01.12.2026');form.locator('#calendar-end-display').fill('02.12.2026');form.get_by_role('button',name='Termin speichern',exact=True).click()
                expect(form.get_by_label('Titel',exact=True)).to_have_value('');expect(p.locator('#event-error')).to_have_text('')
                assert not errors,errors
                browser.close()
        finally:server.terminate();server.wait(timeout=10)
print('Leave and calendar browser form checks passed')
