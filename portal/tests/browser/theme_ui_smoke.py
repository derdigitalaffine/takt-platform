"""Personal theme selection, persistence, live OS and tab updates."""
import os, subprocess, sys, tempfile, time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect
BASE='http://127.0.0.1:8766'
with tempfile.TemporaryDirectory(prefix='takt-theme-') as root:
    env={**os.environ,'DATA_DIR':root+'/data','RECORDINGS_DIR':root+'/recordings','CADDY_CONF_DIR':root+'/caddy','PORTAL_ROOMS_FILE':root+'/rooms.json','PORTAL_CHAT_DIR':root+'/chat'}
    with open(root+'/server.log','w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','seminar_ui_app:app','--app-dir','tests/browser','--host','127.0.0.1','--port','8766','--lifespan','off'],env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(80):
                try:
                    if httpx.get(BASE+'/login',trust_env=False).status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.25)
            else:raise AssertionError(Path(root+'/server.log').read_text())
            with sync_playwright() as pw:
                config={}
                if os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'):config['executable_path']=os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH']
                browser=pw.chromium.launch(**config)
                context=browser.new_context(color_scheme='light',viewport={'width':390,'height':844})
                page=context.new_page();page.goto(BASE+'/login')
                def choose(mode):
                    page.get_by_role('button',name='Farbschema',exact=True).click()
                    page.locator('[data-theme-set="'+mode+'"]').click()
                choose('dark');expect(page.locator('html')).to_have_attribute('data-bs-theme','dark')
                page.reload();expect(page.locator('html')).to_have_attribute('data-bs-theme','dark')
                page.emulate_media(color_scheme='light');expect(page.locator('html')).to_have_attribute('data-bs-theme','dark')
                choose('light');page.emulate_media(color_scheme='dark');expect(page.locator('html')).to_have_attribute('data-bs-theme','light')
                choose('auto');expect(page.locator('html')).to_have_attribute('data-bs-theme','dark')
                page.emulate_media(color_scheme='light');expect(page.locator('html')).to_have_attribute('data-bs-theme','light')
                expect(page.locator('[data-theme-set="auto"]')).to_have_attribute('aria-pressed','true')
                other=context.new_page();other.goto(BASE+'/login');choose('dark')
                expect(other.locator('html')).to_have_attribute('data-bs-theme','dark')
                page.evaluate("localStorage.setItem('theme','garbage')")
                page.reload();expect(page.locator('html')).not_to_have_attribute('data-bs-theme','garbage')
                context.close();browser.close()
        finally:
            server.terminate();server.wait(timeout=10)
print('Theme browser tests passed: manual, persistence, OS changes, cross-tab and invalid preferences.')
