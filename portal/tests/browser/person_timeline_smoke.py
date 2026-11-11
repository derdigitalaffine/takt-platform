"""Exercise the custom view with the actual vendored FullCalendar bundle."""
import os, subprocess, sys, time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect
base='http://127.0.0.1:8770'
server=subprocess.Popen([sys.executable,'-m','http.server','8770','--bind','127.0.0.1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(80):
        try:
            if httpx.get(base+'/tests/browser/person_timeline_fixture.html',trust_env=False).status_code==200:break
        except httpx.HTTPError:pass
        time.sleep(.1)
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1280,'height':900})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/tests/browser/person_timeline_fixture.html')
        expect(page.get_by_role('button',name='Zeitraum für Ada Beispiel eintragen')).to_be_visible()
        expect(page.get_by_role('button',name='Zeitraum für Ben Muster eintragen')).to_have_count(0)
        expect(page.get_by_role('button',name='Ada Beispiel: Urlaub',exact=False)).to_be_visible()
        assert page.locator('.pt-event img').count()==0
        page.get_by_role('button',name='Zeitraum für Ada Beispiel eintragen').click()
        dialog=page.get_by_role('dialog');expect(dialog).to_be_visible()
        dialog.get_by_label('Beginn',exact=True).fill('2026-03-29')
        dialog.get_by_label('Ende einschließlich',exact=True).fill('2026-03-30')
        dialog.get_by_label('Tagesabschnitt').first.select_option('pm')
        dialog.get_by_label('Tagesabschnitt').last.select_option('am')
        dialog.get_by_role('button',name='Zeitraum prüfen').click()
        expect(dialog).to_have_count(0)
        assert page.evaluate('proposals[0].startHalf')=='pm' and page.evaluate('proposals[0].endHalf')=='am'
        assert page.evaluate('proposals[0].endExclusive')=='2026-03-31'
        page.get_by_role('button',name='Ada Beispiel: Urlaub',exact=False).click()
        expect(page.get_by_role('dialog')).to_be_visible();page.get_by_role('dialog').get_by_role('button',name='Schließen').click()
        page.locator('.fc-next-button').click();expect(page.locator('.pt-table')).to_be_visible()
        page.locator('.fc-prev-button').click()
        page.get_by_role('searchbox',name='Person suchen').fill('Ben')
        expect(page.get_by_role('rowheader',name='Ada Beispiel')).to_have_count(0)
        expect(page.get_by_role('rowheader',name='Ben Muster')).to_be_visible()
        search = page.get_by_role('searchbox', name='Person suchen')
        search.press('ControlOrMeta+A')
        search.press('Backspace')
        expect(page.get_by_role('rowheader', name='Ada Beispiel')).to_be_visible()
        page.get_by_role('button',name='Jahr',exact=True).click()
        expect(page.locator('.pt-table')).to_be_visible()
        expect(page.locator('.pt-lane')).to_have_count(2)
        assert page.locator('.pt-nonwork').count()<250
        page.get_by_role('button',name='Monat',exact=True).click()
        page.set_viewport_size({'width':360,'height':800});page.emulate_media(color_scheme='dark')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert not errors,errors
        page.screenshot(path='/tmp/takt-person-timeline-mobile.png',full_page=True)
        page.set_viewport_size({'width':1440,'height':900})
        elapsed=page.evaluate('''() => { const start=performance.now(); timeline.setPeople(Array.from({length:150},(_,i)=>({id:String(i+1),name:'Mitarbeitende '+(i+1),group:'Bereich '+Math.floor(i/25),canSelect:i===0}))); calendar.changeView('taktPeopleYear'); return performance.now()-start; }''')
        expect(page.locator('.pt-lane')).to_have_count(150)
        assert page.locator('.pt-nonwork').count()<16000
        assert elapsed<5000, f'150-person annual view took {elapsed:.0f} ms'
        print(f'150-person annual render: {elapsed:.0f} ms')
        browser.close()
finally:
    server.terminate();server.wait(timeout=10)
print('Person timeline browser checks passed')
