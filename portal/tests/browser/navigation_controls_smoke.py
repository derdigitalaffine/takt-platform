"""Navigation discovery, preferences, responsive layout and no-JS fallback."""
import os, subprocess, sys, tempfile, time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect
BASE='http://127.0.0.1:8766'
OUTPUT=Path('/tmp/takt-navigation-controls');OUTPUT.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='takt-navigation-') as root:
    env={**os.environ,'DATA_DIR':root+'/data','RECORDINGS_DIR':root+'/recordings','CADDY_CONF_DIR':root+'/caddy','PORTAL_ROOMS_FILE':root+'/rooms.json','PORTAL_CHAT_DIR':root+'/chat'}
    with open(OUTPUT/'server.log','w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','navigation_controls_app:app','--app-dir','tests/browser','--host','127.0.0.1','--port','8766','--lifespan','off'],env=env,stdout=log,stderr=subprocess.STDOUT)
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
                p=ctx.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
                p.goto(BASE+'/login');p.get_by_label('E-Mail',exact=True).fill('planner@example.org');p.get_by_label('Passwort',exact=True).fill('browser-test-password');p.get_by_role('button',name='Anmelden',exact=True).click()
                samples=[]
                pages=[('/forms','Formularstatus'),('/umfragen','Umfragestatus'),('/seminare','Seminarübersichten'),('/resources','Ressourcen'),('/maps','Kartenansicht'),('/umlaeufe','Umlaufansichten'),('/dms','Ablagestatus')]
                for index,(route,label) in enumerate(pages):
                    assert p.goto(BASE+route).status==200,route
                    nav=p.get_by_label(label,exact=True)
                    expect(nav).to_have_class(__import__('re').compile(r'ds-nav'))
                    selected=nav.locator('a[aria-current="page"],a.active').first
                    expect(selected).to_be_visible()
                    style=selected.evaluate("e=>{const s=getComputedStyle(e);return {height:s.minHeight,radius:s.borderRadius,color:s.color,background:s.backgroundColor,weight:s.fontWeight}}")
                    samples.append((route,style))
                    selected.focus()
                    assert selected.evaluate("e=>getComputedStyle(e).outlineStyle")!='none'
                    p.screenshot(path=str(OUTPUT/(str(index)+'-desktop.png')),full_page=True)
                    for width in [360,768]:
                        p.set_viewport_size({'width':width,'height':900});p.emulate_media(color_scheme='dark')
                        assert p.evaluate('document.documentElement.scrollWidth<=innerWidth'),route
                        assert nav.locator('a').first.bounding_box()['height']>=44,route
                    p.screenshot(path=str(OUTPUT/(str(index)+'-mobile-dark.png')),full_page=True)
                    p.set_viewport_size({'width':1440,'height':1000});p.emulate_media(color_scheme='light')
                assert all(style==samples[0][1] for _,style in samples),samples
                # Server-side active state survives reload and has no JavaScript dependency.
                p.goto(BASE+'/seminare?tab=mine&period=past')
                expect(p.get_by_label('Buchungshistorie').locator('[aria-current="page"]')).to_have_text('Vergangen / beendet')
                p.goto(BASE+'/resources')
                expect(p.get_by_label('Modulnavigation',exact=True)).to_have_count(0)
                p.goto(BASE+'/resources/1/edit')
                tab=p.get_by_role('tab',name='Zeiten & Regeln',exact=True);tab.click()
                expect(tab).to_have_attribute('aria-selected','true')
                expect(p.locator('#zeiten')).to_be_visible()
                tab.press('ArrowRight')
                expect(p.get_by_role('tab',name='Räume & Preise',exact=True)).to_have_attribute('aria-selected','true')
                p.goto(BASE+'/seminare/1/participants')
                expect(p.get_by_label('Seminarbereiche').locator('[aria-current="page"]')).to_have_text('Teilnehmer & Durchführung')
                p.goto(BASE+'/seminare/1/organisation')
                expect(p.get_by_label('Seminarbereiche').locator('[aria-current="page"]')).to_have_text('Organisation & Vorlagen')
                assert not errors,errors
                ctx.close();browser.close()
        finally:
            server.terminate();server.wait(timeout=10)
print('Navigation controls passed: common geometry, active states, focus, mobile, Bootstrap tabs and seminar subpages.')
