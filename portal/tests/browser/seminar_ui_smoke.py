"""Real-browser seminar flows. Run from portal; optionally set PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH."""
import json, os, re, subprocess, sys, tempfile, time
from pathlib import Path
import httpx
from playwright.sync_api import expect, sync_playwright
BASE='http://127.0.0.1:8766'
OUTPUT=Path(os.environ.get('SEMINAR_BROWSER_ARTIFACTS','/tmp/takt-seminar-browser'));OUTPUT.mkdir(parents=True,exist_ok=True)


def capture(page,name):
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Horizontal overflow: '+page.url
    page.screenshot(path=str(OUTPUT/(name+'.png')),full_page=True,animations='disabled')


def login(page,email):
    page.goto(BASE+'/login');page.get_by_label('E-Mail',exact=True).fill(email);page.get_by_label('Passwort',exact=True).fill('browser-test-password')
    page.get_by_role('button',name='Anmelden',exact=True).click();expect(page).not_to_have_url(re.compile('/login'))


def exercise(browser,f):
    errors=[]
    staff=browser.new_context(viewport={'width':1440,'height':1000},color_scheme='light',reduced_motion='reduce')
    p=staff.new_page();p.on('pageerror',lambda error:errors.append(str(error)));login(p,'planner@example.org')
    sid,tid=f['sid'],f['tid']
    anonymous=browser.new_context(viewport={'width':390,'height':844})
    gate=anonymous.new_page()
    assert gate.goto(BASE+f'/seminare/{sid}').status==401
    expect(gate.get_by_role('heading',name='Dieser Bereich erfordert eine Anmeldung')).to_be_visible()
    capture(gate,'login-required-mobile')
    gate.get_by_role('link',name='Anmelden und Seminar öffnen').click()
    gate.get_by_label('E-Mail',exact=True).fill('member@example.org')
    gate.get_by_label('Passwort',exact=True).fill('browser-test-password')
    gate.get_by_role('button',name='Anmelden',exact=True).click()
    expect(gate).to_have_url(BASE+f'/seminare/{sid}')
    anonymous.close()
    for suffix,name in [('/organisation','organisation'),('/mail','mail'),(f'/durchfuehrung/{tid}','conduct'),('/planen','planner'),('/participants','participants')]:
        assert p.goto(BASE+f'/seminare/{sid}'+suffix).status==200
        capture(p,name+'-desktop');p.set_viewport_size({'width':390,'height':844});capture(p,name+'-mobile')
        p.emulate_media(color_scheme='dark');capture(p,name+'-mobile-dark');p.emulate_media(color_scheme='light');p.set_viewport_size({'width':1440,'height':1000})
    for url in ('/seminare',f'/seminare/{sid}'):
        p.goto(BASE+url)
        if url=='/seminare':capture(p,'overview-polished-collapsed')
        if url=='/seminare':p.locator('.sem-card-participants').filter(has=p.locator(f'[data-term-id="{tid}"]')).locator(':scope > summary').click()
        preview=p.locator(f'details[data-participant-preview][data-term-id="{tid}"]')
        expect(preview).not_to_have_attribute('open','')
        expect(preview.locator('li')).not_to_be_visible()
        preview.locator('summary').click()
        expect(preview.locator('li')).to_have_text(['Alex Teilnahme'])
        expect(preview.locator('li')).to_be_visible()
        expect(preview.locator('a')).to_have_attribute('href',f'/seminare/{sid}/participants?tid={tid}')
        p.set_viewport_size({'width':390,'height':844});capture(p,'term-participants-'+('overview' if url=='/seminare' else 'detail'))
        preview.locator('summary').click();expect(preview.locator('li')).not_to_be_visible()
        p.set_viewport_size({'width':1440,'height':1000})
    p.goto(BASE+f'/seminare/{sid}/mail');p.locator('#mail-kind').select_option('notice');p.locator('#mail-distributors').fill('Hausverteiler;alle@example.org')
    p.get_by_role('button',name='Vorschau & Empfänger prüfen').click();expect(p.get_by_role('heading',name='Versand prüfen')).to_be_visible();capture(p,'mail-preview-desktop')
    p.set_viewport_size({'width':390,'height':844});capture(p,'mail-preview-mobile');p.get_by_role('button',name='1 Nachrichten einreihen').click()
    expect(p.get_by_text('1 Nachrichten in die Versandwarteschlange aufgenommen.')).to_be_visible()
    p.goto(BASE+f'/seminare/{sid}/durchfuehrung/{tid}');checkin=p.get_by_role('link',name='Check-in öffnen',exact=True).get_attribute('href')
    p.locator('#attendance-search').fill('unbekannte person');expect(p.locator('[data-seminar-person]:visible')).to_have_count(0)
    p.locator('#attendance-search').fill('Alex');expect(p.locator('[data-seminar-person]:visible')).to_have_count(1)
    member=browser.new_context(viewport={'width':390,'height':844},color_scheme='light',reduced_motion='reduce')
    m=member.new_page();m.on('pageerror',lambda error:errors.append(str(error)));login(m,'member@example.org')
    m.goto(BASE+f'/seminare/{sid}');capture(m,'series-mobile');m.get_by_role('button',name='Als Favorit merken').click();expect(m.get_by_role('button',name='Aus Favoriten entfernen')).to_be_visible()
    m.goto(BASE+f'/seminare/{sid}');m.locator(f'input[name="sessions"][value="{f["future"]}"]').check();m.get_by_role('button',name='Anmelden',exact=True).click();expect(m).to_have_url(re.compile('/seminare/p/'));capture(m,'booking-mobile')
    m.goto(BASE+f'/seminare/{sid}');m.get_by_role('button',name='Reihe abonnieren',exact=True).click();m.get_by_role('button',name='Ausdrücklich dauerhaft anmelden').click();expect(m.get_by_text('Daueranmeldung aktiv',exact=True)).to_be_visible();capture(m,'subscription-mobile')
    m.goto(checkin);m.get_by_role('button',name='Ich bin anwesend').click();expect(m.get_by_text('Ihre Anwesenheit wurde bestätigt.')).to_be_visible()
    p.goto(BASE+f'/seminare/{sid}/durchfuehrung/{tid}');expect(p.get_by_text('Selbst-Check-in ·',exact=False).last).to_be_visible();capture(p,'attendance-self-mobile')
    m.goto(BASE+f'/seminare/{f["single"]}');capture(m,'single-event-mobile');m.locator('input[name="sessions"]').check();m.get_by_role('button',name='Anmelden',exact=True).click();expect(m).to_have_url(re.compile('/seminare/p/'))
    guest=browser.new_context(viewport={'width':390,'height':844},reduced_motion='reduce')
    g=guest.new_page();g.on('pageerror',lambda error:errors.append(str(error)));g.goto(BASE+f['teacher']);capture(g,'guest-teacher-mobile')
    g.get_by_label('Titel',exact=True).fill('Präsentation zum Wissenshäppchen');g.locator('#guest-file').set_input_files({'name':'praesentation.pdf','mimeType':'application/pdf','buffer':b'%PDF-1.4\n%%EOF'})
    g.locator('#guest-mode').select_option('scheduled');g.locator('#guest-release-display').fill('15.01.2027, 12:00');g.locator('#guest-release-display').press('Tab');g.get_by_role('button',name='Zur Freigabe einreichen').click()
    expect(g.get_by_text('Freigabe durch Planung ausstehend',exact=False)).to_be_visible();capture(g,'guest-upload-mobile')
    p.goto(BASE+f'/seminare/{sid}/materials?tid={tid}');expect(p.get_by_text('Dozentenunterlage – Freigabe ausstehend',exact=False)).to_be_visible();capture(p,'material-review-mobile')
    p.goto(BASE+f'/seminare/{sid}/organisation')
    with p.expect_download() as download_info:
        p.get_by_role('link',name='Seminarreihe als JSON herunterladen').click()
    exported=Path(download_info.value.path()).read_bytes()
    assert json.loads(exported)['format']=='takt.seminar-series'
    p.goto(BASE+'/seminare/importieren');capture(p,'json-import-mobile')
    p.locator('#seminar-json').set_input_files({'name':'seminarreihe.json','mimeType':'application/json','buffer':exported})
    p.get_by_role('button',name='Als neuen Entwurf importieren').click()
    expect(p).to_have_url(re.compile(r'/seminare/\d+/planen$'));capture(p,'json-imported-planner-mobile')
    # Assign multiple planners through the real UI; a member gains only this series.
    p.goto(BASE+f'/seminare/{sid}/planen')
    p.locator('#sp-planners').select_option(label=['Mara Planung','Alex Teilnahme'])
    with p.expect_navigation():
        p.get_by_role('button',name='Änderungen speichern',exact=True).click()
    expect(p.locator('#sp-planners option:checked')).to_have_count(2)
    assert m.goto(BASE+f'/seminare/{sid}/planen').status==200
    capture(m,'assigned-planner-mobile')
    assert m.goto(BASE+f'/seminare/{f["single"]}/planen').status==404
    assert m.goto(BASE+'/seminare/planen').status==403
    assert not errors,errors
    staff.close();member.close();guest.close()


with tempfile.TemporaryDirectory(prefix='takt-seminar-ui-') as root:
    env={**os.environ,'DATA_DIR':root+'/data','RECORDINGS_DIR':root+'/recordings','CADDY_CONF_DIR':root+'/caddy','PORTAL_ROOMS_FILE':root+'/rooms.json','PORTAL_CHAT_DIR':root+'/chat'}
    with (OUTPUT/'server.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','seminar_ui_app:app','--app-dir','tests/browser','--host','127.0.0.1','--port','8766','--lifespan','off'],env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            for attempt in range(60):
                try:
                    if httpx.get(BASE+'/login',timeout=1,trust_env=False).status_code==200:break
                except httpx.HTTPError:pass
                if server.poll() is not None:raise RuntimeError('Server failed; see '+str(OUTPUT/'server.log'))
                time.sleep(.25)
            else:raise RuntimeError('Server not ready')
            fixture=json.loads(Path(root,'data','browser-fixture.json').read_text())
            with sync_playwright() as playwright:
                config={}
                if os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'):config['executable_path']=os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH']
                browser=playwright.chromium.launch(**config)
                try:exercise(browser,fixture)
                finally:browser.close()
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
print('Seminar browser flows passed: planning, messaging, booking, favorites, standing consent, check-in, guest uploads, desktop/mobile and themes.')
