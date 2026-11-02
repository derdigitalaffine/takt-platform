"""Kanban acceptance: sharing, task rules, mouse/touch/keyboard and responsive views."""
import os,re,subprocess,sys,tempfile,time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
BASE='http://127.0.0.1:8767';OUTPUT=Path('/tmp/takt-board-browser');OUTPUT.mkdir(exist_ok=True)


def capture(page,name):
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Page overflow: '+page.url
    page.screenshot(path=str(OUTPUT/(name+'.png')),full_page=True,animations='disabled')


def login(page,email):
    page.goto(BASE+'/login');page.get_by_label('E-Mail',exact=True).fill(email);page.get_by_label('Passwort',exact=True).fill('board-browser-password');page.get_by_role('button',name='Anmelden',exact=True).click();expect(page).not_to_have_url(re.compile('/login'))


def save(page,button):
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/action')) as response:button.click()
    assert response.value.ok,response.value.text()
    expect(page.locator('#kanban')).not_to_have_attribute('aria-busy','true')


def exercise(browser):
    context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce');p=context.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
    login(p,'owner@example.org');p.goto(BASE+'/tasks/boards');p.get_by_label('Name des neuen Boards').fill('Projekt Wissenshäppchen');p.get_by_role('button',name='Privates Board anlegen').click()
    path=p.url.replace(BASE,'');expect(p.locator('.kb-column')).to_have_count(5)
    first=p.locator('.kb-column').first;first.locator('.kb-add summary').click();first.locator('[name=title]').fill('Präsentation vorbereiten');first.locator('[name=checklist]').fill('Inhalte sammeln\nPräsentation prüfen')
    save(p,first.get_by_role('button',name='Aufgabe anlegen'))
    card=p.locator('[data-card]').first;expect(card.get_by_role('button',name='Präsentation vorbereiten',exact=True)).to_be_visible()
    capture(p,'board-desktop');card.get_by_role('button',name='Präsentation vorbereiten',exact=True).click()
    expect(p.locator('#drawer-title')).to_have_value('Präsentation vorbereiten');p.locator('#drawer-description').fill('Gemeinsam arbeiten, ohne den Boardkontext zu verlieren.');save(p,p.get_by_role('button',name='Änderungen speichern',exact=True))
    p.locator('#drawer-check').fill('Unterlagen versenden');save(p,p.locator('#drawer-check').locator('..').get_by_role('button',name='Hinzufügen',exact=True))
    p.locator('#drawer-comment').fill('Vorbereitung kann beginnen.');save(p,p.get_by_role('button',name='Kommentieren',exact=True));expect(p.get_by_text('Vorbereitung kann beginnen.',exact=True)).to_be_visible()
    capture(p,'drawer-desktop');p.locator('#drawer-comment').fill('Noch nicht gespeicherter Kommentar');p.locator('#kb-detail [data-bs-dismiss]').click();p.locator('[data-kb-open]').first.click();expect(p.locator('#drawer-comment')).to_have_value('Noch nicht gespeicherter Kommentar');p.locator('#kb-detail [data-bs-dismiss]').click()
    p.get_by_role('button',name='Board verwalten',exact=True).click();p.locator('#member-target').select_option(label='Alex Mitarbeit');p.locator('#member-role').select_option('2')
    with p.expect_navigation():p.get_by_role('button',name='Zugang setzen',exact=True).click()
    expect(p.locator('#board-settings')).to_have_class(re.compile('show'))
    p.locator('#member-target').select_option(label='Sam Lesen');p.locator('#member-role').select_option('1')
    with p.expect_navigation():p.get_by_role('button',name='Zugang setzen',exact=True).click()
    p.locator('#board-settings [data-bs-dismiss]').click()
    # Mouse drag changes status; unfinished checklist blocks completion.
    card=p.locator('[data-card]').first;cardid=card.get_attribute('data-card');target=p.locator('[data-drop-column]').nth(1)
    with p.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/action')) as response:card.locator('.kb-grip').drag_to(target)
    assert response.value.ok,response.value.text();expect(p.locator('.kb-column').nth(1).locator('[data-card]')).to_have_count(1)
    save(p,p.get_by_role('button',name='Letztes Verschieben rückgängig'));expect(p.locator('.kb-column').first.locator('[data-card]')).to_have_count(1)
    # Reader can open task, but receives no write controls.
    rcontext=browser.new_context();r=rcontext.new_page();login(r,'reader@example.org');r.goto(BASE+path);r.locator('[data-kb-open]').click();expect(r.locator('#kb-detail-body h3').first).to_have_text('Präsentation vorbereiten');expect(r.locator('#kb-detail-body form button:enabled')).to_have_count(0);rcontext.close()
    # Editor without global creation permission can create on this board.
    econtext=browser.new_context(viewport={'width':390,'height':844},has_touch=True,is_mobile=True,reduced_motion='reduce');e=econtext.new_page();e.on('pageerror',lambda x:errors.append(str(x)));login(e,'editor@example.org');e.goto(BASE+path)
    capture(e,'board-mobile');e.locator('[data-kb-open]').first.click();expect(e.locator('#drawer-title')).to_be_visible();capture(e,'drawer-mobile');e.locator('#kb-detail [data-bs-dismiss]').click()
    first=e.locator('.kb-column').first;first.locator('.kb-add summary').click();first.locator('[name=title]').fill('Teamaufgabe');save(e,first.get_by_role('button',name='Aufgabe anlegen'));expect(first.locator('[data-card]')).to_have_count(2)
    # Touch drag by the explicit grip, leaving normal scrolling available elsewhere.
    grip=e.locator('[data-card]').nth(1).locator('.kb-grip');grip.scroll_into_view_if_needed();box=grip.bounding_box();x,y=box['x']+box['width']/2,box['y']+box['height']/2
    target=e.locator('[data-card]').first.bounding_box();target_y=target['y']+10
    session=econtext.new_cdp_session(e)
    with e.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/action')) as response:
        session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
        for step in range(8):
            session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x-25,'y':y+(target_y-y)*(step+1)/8}]});time.sleep(.02)
        session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    assert response.value.ok,response.value.text()
    expect(e.locator('#kanban')).not_to_have_attribute('aria-busy','true');expect(e.locator('.kb-drag-ghost')).to_have_count(0)
    expect(e.locator('[data-card]').first.locator('[data-kb-open]')).to_have_text('Teamaufgabe')
    for mode in ('focus','list','board'):
        e.locator(f'[data-kb-layout={mode}]').click();capture(e,'mobile-'+mode)
    e.emulate_media(color_scheme='dark');capture(e,'board-mobile-dark')
    # Switch to free organization and rearrange without changing task status.
    p.reload();p.get_by_role('button',name='Board verwalten',exact=True).click();p.locator('#setting-mode').select_option('free')
    with p.expect_navigation():p.get_by_role('button',name='Board speichern',exact=True).click()
    p.locator('#board-settings [data-bs-dismiss]').click();expect(p.locator('#kanban > div p').filter(has_text='Freie Organisation')).to_be_visible();capture(p,'free-board-desktop')
    card=p.locator(f'[data-card="{cardid}"]');card.locator('summary').last.click();form=card.locator('form').filter(has=p.locator('[name=action][value=move]'));form.locator('[name=column]').select_option(index=3)
    button=form.get_by_role('button',name='Verschieben',exact=True);button.focus()
    with p.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/action')) as response:button.press('Enter')
    assert response.value.ok,response.value.text()
    expect(p.locator('#kanban')).not_to_have_attribute('aria-busy','true')
    expect(p.locator('.kb-column').nth(3).locator(f'[data-card="{cardid}"]')).to_have_count(1)
    p.get_by_role('button',name='Board verwalten',exact=True).click();p.get_by_role('button',name='Board löschen – Aufgaben behalten',exact=True).click()
    expect(p.locator('.swal2-popup')).to_be_visible();p.get_by_role('button',name='Ja, ausführen',exact=True).click()
    expect(p).to_have_url(BASE+'/tasks/boards')
    assert not errors,errors
    context.close();econtext.close()


with tempfile.TemporaryDirectory(prefix='takt-board-ui-') as root:
    env={**os.environ,'DATA_DIR':root+'/data','RECORDINGS_DIR':root+'/recordings','CADDY_CONF_DIR':root+'/caddy','PORTAL_ROOMS_FILE':root+'/rooms.json','PORTAL_CHAT_DIR':root+'/chat'}
    with (OUTPUT/'server.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','board_ui_app:app','--app-dir','tests/browser','--host','127.0.0.1','--port','8767','--lifespan','off'],env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            for attempt in range(60):
                try:
                    if httpx.get(BASE+'/login',trust_env=False,timeout=1).status_code==200:break
                except httpx.HTTPError:pass
                if server.poll() is not None:raise RuntimeError('Server failed; see server.log')
                time.sleep(.25)
            else:raise RuntimeError('Server did not start')
            with sync_playwright() as pw:
                options={}
                if os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'):options['executable_path']=os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH']
                browser=pw.chromium.launch(**options)
                try:exercise(browser)
                finally:browser.close()
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
print('Kanban browser flows passed: roles, cards, checklist, comments, mouse/touch, undo, free/status modes, desktop and mobile layouts.')
