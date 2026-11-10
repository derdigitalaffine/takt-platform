"""Kanban acceptance: sharing, task rules, mouse/touch/keyboard and responsive views."""
import os,re,subprocess,sys,tempfile,time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
BASE='http://127.0.0.1:8767';OUTPUT=Path('/tmp/takt-board-browser');OUTPUT.mkdir(exist_ok=True)


def capture(page,name):
    if not page.evaluate('document.documentElement.scrollWidth <= innerWidth'):
        print(page.evaluate("({w:innerWidth,scroll:document.documentElement.scrollWidth,body:document.body.scrollWidth,x:scrollX,drawers:[...document.querySelectorAll('.kb-drawer')].map(e=>({id:e.id,cls:e.className,d:getComputedStyle(e).display,v:getComputedStyle(e).visibility,w:e.scrollWidth,rect:e.getBoundingClientRect().toJSON()})),outside:[...document.querySelectorAll('body *')].filter(e=>!e.closest('#kb-columns')&&getComputedStyle(e).display!=='none'&&getComputedStyle(e).visibility!=='hidden'&&e.getBoundingClientRect().right>innerWidth+1).slice(0,20).map(e=>({tag:e.tagName,cls:e.className,rect:e.getBoundingClientRect().toJSON()}))})"))
        page.screenshot(path=str(OUTPUT/'overflow-debug.png'),full_page=True)
        raise AssertionError(str(page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1 && getComputedStyle(e).position!=='fixed').slice(0,16).map(e=>({tag:e.tagName,cls:e.className,w:e.getBoundingClientRect().width,x:e.getBoundingClientRect().x,scroll:e.scrollWidth}))")))
    page.screenshot(path=str(OUTPUT/(name+'.png')),full_page=True,animations='disabled')


def login(page,email):
    page.goto(BASE+'/login');page.get_by_label('E-Mail',exact=True).fill(email);page.get_by_label('Passwort',exact=True).fill('board-browser-password');page.get_by_role('button',name='Anmelden',exact=True).click();expect(page).not_to_have_url(re.compile('/login'))


def save(page,button):
    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/action')) as response:button.click()
    assert response.value.ok,response.value.text()
    expect(page.locator('#kanban')).not_to_have_attribute('aria-busy','true')


def exercise(browser):
    context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
    p=context.new_page();errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
    login(p,'owner@example.org');p.goto(BASE+'/tasks/boards')
    p.get_by_role('button',name='Neues Board',exact=True).click()
    p.get_by_label('Boardname',exact=True).fill('Projekt Wissenshäppchen')
    p.get_by_role('button',name='Privates Board anlegen').click()
    path=p.url.replace(BASE,'');expect(p.locator('.kb-column')).to_have_count(5)
    # Native column editor, keyboard, dirty guard and neutral status.
    first=p.locator('.kb-column').first;header=first.locator('.kb-column-heading')
    header.hover();expect(first.locator('.kb-column-gear')).to_have_css('opacity','1')
    header.focus();header.press('Enter');first.locator('[data-column-form] [name=title]').fill('Eingang')
    first.locator('[data-column-form] [name=status]').select_option('')
    save(p,first.get_by_role('button',name='Spalte speichern',exact=True))
    header.click();first.locator('[data-column-form] [name=title]').fill('Entwurf')
    p.get_by_role('button',name='Aktualisieren',exact=True).click()
    expect(first.locator('[data-column-form] [name=title]')).to_have_value('Entwurf')
    first.locator('[data-column-form] [name=title]').press('Escape')
    first.locator('.kb-add summary').click();first.locator('.kb-add [name=title]').fill('Präsentation vorbereiten')
    first.locator('[name=checklist]').fill('Inhalte sammeln\nPräsentation prüfen')
    first.locator('[name=card_type]').select_option('checklist')
    save(p,first.get_by_role('button',name='Aufgabe anlegen'))
    card=p.locator('[data-card]').first
    expect(card.locator('.kb-card-title')).to_have_text('Präsentation vorbereiten')
    assert card.bounding_box()['height']<150
    expect(card.locator('select')).to_have_count(0)
    # Clicking title edits in place; refresh cannot discard the draft. Escape cancels.
    card.locator('.kb-card-title').click();quick=p.get_by_label('Titel schnell bearbeiten')
    quick.fill('Lokaler Entwurf');p.get_by_role('button',name='Aktualisieren',exact=True).click()
    expect(quick).to_have_value('Lokaler Entwurf');quick.press('Escape')
    expect(card.locator('.kb-card-title')).to_have_text('Präsentation vorbereiten')
    card.locator('.kb-card-title').click();p.get_by_label('Titel schnell bearbeiten').fill('Präsentation im Team')
    save(p,card.get_by_role('button',name='Speichern',exact=True))
    expect(card.locator('.kb-card-title')).to_have_text('Präsentation im Team')
    # A badge opens just the corresponding modal; closing returns to the badge.
    badge=card.get_by_role('button',name=re.compile('Checkliste:'))
    badge.click();modal=p.get_by_role('dialog');expect(modal).to_be_visible()
    expect(modal).to_contain_text('Inhalte sammeln');capture(p,'checklist-modal-desktop')
    p.get_by_role('button',name='Vorschau schließen').click();expect(badge).to_be_focused()
    # Pencil opens a bottom Mantine sheet, preserving task rules and board position.
    card.locator('.kb-pencil').click();drawer=p.get_by_role('dialog');expect(p.locator('#drawer-title')).to_have_value('Präsentation im Team')
    box=drawer.bounding_box();assert box['width']>1200 and abs(box['x'])<2 and box['y']>0 and abs(box['y']+box['height']-1000)<3
    p.locator('#drawer-description').fill('Gemeinsam arbeiten, ohne den Boardkontext zu verlieren.')
    p.get_by_role('dialog').get_by_label('Kartentyp',exact=True).select_option('idea');p.get_by_label('Farbstreifen').select_option('grape')
    p.locator('#drawer-tags').fill('Planung, Team')
    save(p,p.get_by_role('button',name='Änderungen speichern',exact=True))
    expect(p.locator('#drawer-title')).to_be_visible()
    p.locator('#drawer-status').select_option('in_progress');save(p,p.get_by_role('button',name='Status ändern',exact=True))
    expect(first.locator('[data-card]')).to_have_count(1)
    p.locator('#drawer-status').select_option('done')
    with p.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/action')) as response:p.get_by_role('button',name='Status ändern',exact=True).click()
    assert response.value.status==422
    expect(p.get_by_role('dialog')).to_contain_text('Ihre Eingaben bleiben erhalten')
    expect(p.locator('#kb-message')).to_contain_text('Checkliste')
    p.locator('#drawer-comment').fill('Vorbereitung kann beginnen.')
    save(p,p.get_by_role('button',name='Kommentieren',exact=True))
    expect(p.get_by_role('dialog')).to_contain_text('Vorbereitung kann beginnen.')
    p.locator('#drawer-files').set_input_files({'name':'plan.txt','mimeType':'text/plain','buffer':b'Synthetic board attachment'})
    save(p,p.get_by_role('button',name='Dateien hochladen',exact=True))
    expect(p.get_by_role('dialog').get_by_role('link',name='plan.txt')).to_be_visible()
    capture(p,'bottom-editor-desktop')
    p.locator('#drawer-comment').fill('Noch nicht gespeicherter Kommentar')
    p.get_by_role('button',name='Kartendetails schließen').click();card.locator('.kb-pencil').click()
    expect(p.locator('#drawer-comment')).to_have_value('Noch nicht gespeicherter Kommentar')
    p.get_by_role('button',name='Kartendetails schließen').click()
    expect(card.locator('.kb-cover-grape')).to_be_visible()
    for badge_name,content in [('Kommentare:','Vorbereitung kann beginnen.'),('Anhänge:','plan.txt'),('Beschreibung','Gemeinsam arbeiten')]:
        card.get_by_role('button',name=re.compile(badge_name)).click()
        expect(p.get_by_role('dialog')).to_contain_text(content)
        if badge_name=='Anhänge:':capture(p,'attachments-modal-desktop')
        p.get_by_role('button',name='Vorschau schließen').click()
    # Linked sources use the same compact card and detail sheet, with an original link.
    p.get_by_role('button',name='Inhalte hinzufügen',exact=True).click()
    p.locator('[data-kb-library-search]').fill('Teamentscheidung')
    p.locator('.kb-library-results button').filter(has_text='Teamentscheidung').click()
    save(p,p.locator('#kb-library').get_by_role('button',name='Karte hinzufügen',exact=True))
    source=p.locator('[data-kind=source]');source.locator('.kb-pencil').click()
    expect(p.get_by_role('dialog')).to_contain_text('Fachmodul')
    expect(p.get_by_role('dialog').get_by_role('link',name=re.compile('Original öffnen'))).to_be_visible()
    save(p,p.get_by_role('button',name='Nur aus diesem Board entfernen',exact=True))
    expect(source).to_have_count(0)
    # Sharing remains in board settings; readers have no write controls.
    p.get_by_role('button',name='Board verwalten',exact=True).click()
    for person,role in [('Alex Mitarbeit','2'),('Sam Lesen','1')]:
        p.locator('#member-target').select_option(label=person);p.locator('#member-role').select_option(role)
        with p.expect_navigation():p.get_by_role('button',name='Zugang setzen',exact=True).click()
    p.locator('#board-settings [data-bs-dismiss]').click()
    rc=browser.new_context();r=rc.new_page();login(r,'reader@example.org');r.goto(BASE+path)
    expect(r.locator('[data-column-editor]')).to_have_count(0)
    r.locator('.kb-card-title').click();expect(r.get_by_role('dialog')).to_contain_text('Präsentation im Team')
    expect(r.get_by_role('dialog').get_by_role('button',name='Änderungen speichern')).to_have_count(0)
    rc.close()
    # Mouse drag, undo, then neutral -> linked status column.
    card=p.locator('[data-card]').first;card.hover()
    with p.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/action')) as response:card.locator('.kb-grip').drag_to(p.locator('[data-drop-column]').nth(1))
    assert response.value.ok,response.value.text()
    expect(p.locator('.kb-column').nth(1).locator('[data-card]')).to_have_count(1)
    save(p,p.get_by_role('button',name='Letztes Verschieben rückgängig'))
    expect(first.locator('[data-card]')).to_have_count(1)
    # Mobile, touch targets, title quick edit, modal, drawer, layouts and dark mode.
    ec=browser.new_context(viewport={'width':390,'height':844},has_touch=True,is_mobile=True,reduced_motion='reduce')
    e=ec.new_page();e.on('pageerror',lambda x:errors.append(str(x)));login(e,'editor@example.org');e.goto(BASE+path)
    capture(e,'compact-board-mobile')
    e.locator('.kb-card .kb-pencil').first.tap();expect(e.locator('#drawer-title')).to_be_visible();capture(e,'bottom-editor-mobile')
    e.get_by_role('button',name='Kartendetails schließen').click()
    e.get_by_role('button',name=re.compile('Kommentare:')).tap();expect(e.get_by_role('dialog')).to_contain_text('Vorbereitung kann beginnen.')
    capture(e,'comments-modal-mobile');e.get_by_role('button',name='Vorschau schließen').click()
    first_e=e.locator('.kb-column').first;first_e.locator('.kb-add summary').click()
    first_e.locator('.kb-add [name=title]').fill('Teamaufgabe');save(e,first_e.get_by_role('button',name='Aufgabe anlegen'))
    grip=first_e.locator('[data-card]').nth(1).locator('.kb-grip');grip.scroll_into_view_if_needed();box=grip.bounding_box();x,y=box['x']+box['width']/2,box['y']+box['height']/2
    target_y=first_e.locator('[data-drop-column]').bounding_box()['y']+10;session=ec.new_cdp_session(e)
    with e.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/action')) as response:
        session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
        for step in range(16):
            session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x-20,'y':y+(target_y-y)*(step+1)/16}]});time.sleep(.02)
        session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    assert response.value.ok,response.value.text()
    expect(first_e.locator('.kb-card-title').first).to_have_text('Teamaufgabe')
    for mode in ('focus','list','board'):
        e.locator(f'[data-kb-layout={mode}]').click();capture(e,'mobile-'+mode)
    e.locator('[aria-label="Darstellung wählen"]').count()  # Theme is inherited from the shell.
    e.evaluate("document.documentElement.dataset.bsTheme='dark'");capture(e,'compact-board-dark')
    # Many-card fixture: compact cards fit without whole-page overflow.
    p.goto(BASE+'/tasks/boards')
    p.get_by_role('link',name=re.compile('Dichtes Teamboard')).click()
    expect(p.locator('[data-card]')).to_have_count(48)
    assert max(p.locator('[data-card]').evaluate_all('(cards)=>cards.map(c=>c.getBoundingClientRect().height)'))<160
    capture(p,'dense-board-desktop')
    # Non-JavaScript navigation and column editing remain usable.
    plain=browser.new_context(storage_state=context.storage_state(),java_script_enabled=False)
    fallback=plain.new_page();fallback.goto(BASE+path);fallback.locator('.kb-column-heading').first.click()
    fallback.locator('[data-column-form] [name=title]').first.fill('Eingang ohne JavaScript')
    fallback.get_by_role('button',name='Spalte speichern',exact=True).first.click()
    expect(fallback.locator('.kb-column-name').first).to_have_text('Eingang ohne JavaScript')
    expect(fallback.locator('.kb-card-title').first).to_have_attribute('href',re.compile('/aufgaben/'))
    plain.close();ec.close();context.close()
    assert not errors,errors


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
