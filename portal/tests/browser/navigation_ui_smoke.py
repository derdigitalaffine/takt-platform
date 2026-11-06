"""Navigation discovery, preferences, responsive layout and no-JS fallback."""
import os, subprocess, sys, tempfile, time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect
BASE='http://127.0.0.1:8766'
OUTPUT=Path('/tmp/takt-navigation-browser');OUTPUT.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='takt-navigation-') as root:
    env={**os.environ,'DATA_DIR':root+'/data','RECORDINGS_DIR':root+'/recordings','CADDY_CONF_DIR':root+'/caddy','PORTAL_ROOMS_FILE':root+'/rooms.json','PORTAL_CHAT_DIR':root+'/chat'}
    with open(OUTPUT/'server.log','w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','seminar_ui_app:app','--app-dir','tests/browser','--host','127.0.0.1','--port','8766','--lifespan','off'],env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(80):
                try:
                    if httpx.get(BASE+'/login',trust_env=False).status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.25)
            else:raise AssertionError((OUTPUT/'server.log').read_text())
            with sync_playwright() as pw:
                browser=pw.chromium.launch()
                ctx=browser.new_context(viewport={'width':1440,'height':1000})
                p=ctx.new_page();errors=[];p.on('pageerror',lambda error:errors.append(str(error)))
                p.goto(BASE+'/login');p.get_by_label('E-Mail',exact=True).fill('planner@example.org');p.get_by_label('Passwort',exact=True).fill('browser-test-password');p.get_by_role('button',name='Anmelden',exact=True).click()
                p.get_by_role('link',name='Module entdecken',exact=True).click()
                expect(p.get_by_role('heading',name='Ihre Module')).to_be_visible()
                expect(p.locator('.module-hub-hero')).to_be_visible()
                expect(p.locator('.module-hub-filters')).to_be_visible()
                expect(p.locator('.module-hub-group')).not_to_have_count(0)
                p.get_by_label('Modul oder Tätigkeit suchen').fill('Besprechung')
                p.get_by_role('button',name='Suchen',exact=True).click()
                expect(p.locator('.module-catalog article')).to_have_count(1)
                p.goto(BASE+'/module')
                p.locator('a.module-hub-category[href*="category=schedule"]').click()
                expect(p.locator('.module-hub-group')).to_have_count(1)
                expect(p.locator('#module-category')).to_have_value('schedule')
                p.goto(BASE+'/module?q=Besprechung&category=schedule&sort=favorites')
                p.get_by_role('button',name='Meetings: Als Favorit merken',exact=True).click()
                expect(p.get_by_role('button',name='Meetings: Favorit entfernen',exact=True)).to_be_visible()
                assert 'category=schedule' in p.url and 'sort=favorites' in p.url
                expect(p.locator('.module-hub-favorite-list')).to_contain_text('Meetings')
                p.goto(BASE+'/module')
                p.locator('#module-sort').select_option('az')
                p.get_by_role('button',name='Suchen',exact=True).click()
                expect(p.locator('#module-sort')).to_have_value('az')
                p.goto(BASE+'/profile/menu');p.locator('#pm-g-schedule').uncheck();p.get_by_role('button',name='Speichern',exact=True).click()
                p.goto(BASE+'/');p.locator('#nav-search').fill('Besprechung')
                expect(p.locator('#app-nav a[href="/meetings/plan"]')).to_be_visible()
                p.locator('#app-nav a[href="/meetings/plan"]').click()
                expect(p.get_by_label('Ende',exact=True)).to_be_visible()
                p.goto(BASE+'/module')
                for width,theme in [(1440,'light'),(768,'dark'),(360,'dark')]:
                    p.set_viewport_size({'width':width,'height':900});p.emulate_media(color_scheme=theme)
                    assert p.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                    assert p.locator('.module-hub-card-open').first.bounding_box()['height'] >= 40
                    p.locator('.module-hub-card-open').first.focus()
                    assert p.locator('.module-hub-card-open').first.evaluate("el=>getComputedStyle(el).outlineStyle") != 'none'
                    p.screenshot(path=str(OUTPUT/f'modules-{width}-{theme}.png'),full_page=True)
                fallback=browser.new_context(storage_state=ctx.storage_state(),java_script_enabled=False,viewport={'width':390,'height':844})
                f=fallback.new_page();f.goto(BASE+'/module');f.get_by_label('Modul oder Tätigkeit suchen').fill('DMS');f.get_by_role('button',name='Suchen',exact=True).click()
                expect(f.get_by_role('heading',name='Dokumentenablage')).not_to_be_visible() # planner has no DMS access
                expect(f.get_by_text('Keine passenden Module gefunden')).to_be_visible()
                assert not errors, errors
                fallback.close();ctx.close();browser.close()
        finally:
            server.terminate();server.wait(timeout=10)
print('Navigation browser tests passed.')
