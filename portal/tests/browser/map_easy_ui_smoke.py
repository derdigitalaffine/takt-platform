"""Functional Chromium smoke for the progressive TAKT map UI (desktop, keyboard, touch).

Uses a representative extract of the actual map DOM plus a minimal MapKit
state adapter. No live geodata is downloaded. The actual map browser module
is covered by portal tests; these checks target DOM preservation and the
new task-oriented controls.
"""
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

PORTAL = Path(__file__).resolve().parents[2]
UI_JS = PORTAL / "app" / "static" / "map-easy-ui.js"
UI_CSS = PORTAL / "app" / "static" / "map-easy.css"
OUT = Path("/tmp/takt-board-browser")
OUT.mkdir(parents=True, exist_ok=True)

HTML = """<!doctype html><html lang="de" data-bs-theme="light"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bs-body-bg:#fff;--bs-body-color:#223;--bs-secondary-color:#667;
--bs-tertiary-bg:#f2f4f7;--bs-border-color:#dce0e5;--bs-primary:#2366ad;
--bs-primary-rgb:35,102,173;--bs-primary-text-emphasis:#1a528b;
--bs-primary-bg-subtle:#e9f2fd}
*{box-sizing:border-box}html,body{margin:0;padding:0;font:14px system-ui}
.map-shell{width:100vw;display:flex;height:90vh}
.map-panel{width:380px;max-width:100vw;border-right:1px solid var(--bs-border-color);
background:var(--bs-body-bg);display:flex;flex-direction:column}
.map-panel-body{padding:12px;overflow:auto;flex:1}
#map-layer-pane>*{margin-bottom:9px}.map-main{flex:1}
.form-select,.form-control{width:100%;padding:9px;border:1px solid var(--bs-border-color);border-radius:6px}
.map-discovery-shortcuts{display:flex;gap:5px;overflow:auto}
.map-discovery-filters{display:grid;gap:8px}
.map-discovery-header{display:flex;align-items:center;justify-content:space-between;gap:9px}
[hidden]{display:none!important}
@media(max-width:767px){.map-panel{width:100%}.map-main{display:none}}
</style>
</head><body>
<div class="map-shell" id="map-shell">
  <aside class="map-panel"><div class="map-panel-body">
    <div id="map-workbench">
      <div id="map-workbench-nav"></div>
      <div id="map-layer-pane">
        <label for="coord-input">Ort oder Koordinate finden</label>
        <form id="coord-search"><input id="coord-input" class="form-control"></form>
        <div id="place-results"></div>
        <div class="map-section-title">Grundkarte</div>
        <div id="base-list">
          <label><input type="radio" name="base" value="standard" checked>Standard</label>
          <label><input type="radio" name="base" value="luft">Luftbild</label>
          <label><input type="radio" name="base" value="">Ohne Grundkarte</label>
        </div>
        <div class="map-section-title">Fachebenen</div>
        <input id="layer-filter" class="form-control">
        <label><input type="checkbox" id="map-advanced">Erweiterte Optionen</label>
        <label><input type="checkbox" id="overlay-only-active">Nur aktive</label>
        <span id="overlay-count">1 aktiv</span>
        <div id="overlay-list">
          <div class="layer-row" data-id="flood">
            <input type="checkbox" data-toggle checked aria-label="Hochwasser anzeigen">
          </div>
          <div class="layer-row" data-id="soil">
            <input type="checkbox" data-toggle aria-label="Bodenschutz anzeigen">
          </div>
        </div>
        <section class="map-discovery" id="map-discovery">
          <div class="map-discovery-header"><div><h2 id="map-discovery-title">Geodaten entdecken</h2>
            <div class="small">Rheinland-Pfalz, Deutschland &amp; Open Data</div>
          </div><button id="map-discovery-reset">Alle</button></div>
          <div class="map-discovery-filters">
            <div><input type="search" id="map-discovery-search"></div>
            <div class="map-discovery-shortcuts">
              <button data-discovery-topic="" type="button">Alle</button>
              <button data-discovery-topic="3D-Gebäude" type="button">3D-Gebäude</button>
            </div>
            <div><select id="map-discovery-region"><option value="">Alle Gebiete</option>
              <option value="Rheinland-Pfalz">Rheinland-Pfalz</option></select>
              <select id="map-discovery-topic"><option value="">Alle Themen</option>
                <option value="Gelände">Gelände</option></select></div>
            <div><label><input type="checkbox" id="map-discovery-favorites-only">Nur Favoriten</label>
              <span id="map-discovery-count">60 Quellen</span></div>
          </div>
          <div id="map-discovery-status">Verzeichnis wird geladen</div>
          <div id="map-discovery-results"></div>
          <div id="map-discovery-preview" hidden></div>
        </section>
        <div class="map-compare-switch"><button id="map-compare-toggle">Karten vergleichen</button></div>
        <section class="map-lod2-panel" id="map-lod2-panel">
          <h3>Gebäudedächer</h3><button id="map-lod2-toggle">LoD2</button>
          <p>Lokale 3D-Vorschau, keine amtliche Höhenanalyse.</p>
        </section>
        <div class="map-view-switch"><button id="map-3d-view">Schrägansicht</button></div>
      </div>
      <div id="map-parcel-pane" hidden></div>
      <div id="map-workbench-actions"><button id="test-print">Drucken / PDF</button></div>
    </div>
  </div></aside><div class="map-main"></div>
</div>
<script>
  const listeners=[];
  window.__mapkit={
    bases:[{id:"standard",name:"Standardkarte"},{id:"luft",name:"Luftbild"}],
    overlays:[{id:"flood",name:"Hochwasser",visible:true},
              {id:"soil",name:"Bodenschutz",visible:false}],
    baseId:"standard",
    on(fn){listeners.push(fn)},
    emit(){listeners.forEach(fn=>fn())},
    setBase(id){this.baseId=id;this.emit()},
    setVisible(id,checked){this.overlays.find(l=>l.id===id).visible=checked;this.emit()}
  };
  window.MapWorkspace={kit:window.__mapkit,map:{resize() {}}};
  document.querySelector("#base-list").addEventListener("change",e=>{
    if(e.target.name==="base")window.__mapkit.setBase(e.target.value);
  });
  document.querySelector("#overlay-list").addEventListener("change",e=>{
    if(e.target.matches("[data-toggle]")){
      window.__mapkit.setVisible(e.target.closest("[data-id]").dataset.id,e.target.checked);
    }
  });
  document.querySelector("#map-discovery-topic").addEventListener("change",e=>{
    window.__selectedTopic=e.target.value;
  });
</script>
</body></html>"""

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.set_content(HTML)
    # Original controls work before enhancement; no Javascript-only duplicate logic.
    expect(page.locator("#base-list input")).to_have_count(3)
    expect(page.locator("#map-3d-view")).to_be_visible()
    page.add_style_tag(path=str(UI_CSS))
    page.add_script_tag(path=str(UI_JS))
    assert page.locator("#map-shell").evaluate("e=>e.classList.contains('map-easy-ready')")

    tabs = page.get_by_role("tablist", name="Karte gestalten")
    expect(tabs.get_by_role("tab")).to_have_count(3)
    expect(page.locator("#map-easy-overview")).to_be_visible()
    expect(page.locator("#map-easy-layers")).to_be_hidden()
    expect(page.locator("#map-easy-discover")).to_be_hidden()
    expect(page.locator("#map-easy-count")).to_have_text("1 aktiv")
    expect(page.get_by_role("button", name="Hochwasser ausblenden")).to_be_visible()
    expect(page.locator("#map-compare-toggle")).to_be_hidden()
    expect(page.locator("#test-print")).to_be_hidden()

    # A simple base-map select updates the original layer radio and MapKit.
    page.locator("#map-easy-base").select_option("luft")
    assert page.evaluate("window.__mapkit.baseId") == "luft"
    expect(page.locator('#base-list input[value="luft"]')).to_be_checked()
    # The existing checkbox is the single source of truth for active layers.
    page.get_by_role("button", name="Hochwasser ausblenden").click()
    expect(page.locator("#map-easy-count")).to_have_text("0 aktiv")
    expect(page.locator("#overlay-list [data-id=flood] [data-toggle]")).not_to_be_checked()

    page.get_by_role("button", name="Informationen auswählen oder ändern").click()
    expect(page.locator("#map-easy-layers")).to_be_visible()
    expect(page.locator("#base-list input")).to_have_count(3)
    expect(page.locator("#overlay-list [data-toggle]")).to_have_count(2)
    page.locator("#overlay-list [data-id=soil] [data-toggle]").check()
    assert page.evaluate("window.__mapkit.overlays[1].visible") is True
    tabs.get_by_role("tab", name="Meine Karte").click()
    expect(page.get_by_role("button", name="Bodenschutz ausblenden")).to_be_visible()

    # Keyboard-only operation follows the standard tab pattern.
    tab = tabs.get_by_role("tab", name="Meine Karte")
    tab.focus()
    tab.press("ArrowRight")
    expect(tabs.get_by_role("tab", name="Ebenen")).to_have_attribute("aria-selected", "true")
    tabs.get_by_role("tab", name="Ebenen").press("ArrowRight")
    expect(tabs.get_by_role("tab", name="Daten finden")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#map-discovery")).to_be_visible()
    expect(page.locator("#map-discovery-region")).to_be_hidden()
    page.locator(".map-easy-catalog-more summary").click()
    expect(page.locator("#map-discovery-region")).to_be_visible()
    page.get_by_role("button", name="Gelände", exact=True).click()
    assert page.evaluate("window.__selectedTopic") == "Gelände"
    # Everything remains in the DOM: existing JS IDs and controls are preserved.
    assert page.locator("#map-discovery-results").count() == 1
    tabs.get_by_role("tab", name="Daten finden").press("Home")
    expect(page.locator("#map-easy-overview")).to_be_visible()
    page.locator("#map-easy-special summary").click()
    expect(page.locator("#map-lod2-toggle")).to_be_visible()
    expect(page.locator("#map-3d-view")).to_be_visible()
    expect(page.locator("#map-compare-toggle")).to_be_visible()
    page.locator("#map-easy-export summary").click()
    expect(page.locator("#test-print")).to_be_visible()

    for width in (768, 390, 360):
        page.set_viewport_size({"width":width, "height":820})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
        assert page.locator("#map-easy-tabs").is_visible()
        assert page.get_by_role("tab", name="Meine Karte").bounding_box()["height"] >= 44
        assert page.locator("#map-easy-base").bounding_box()["height"] >= 40
        page.screenshot(path=str(OUT / f"map-easy-{width}.png"))
    assert not errors, errors
    browser.close()

print("TAKT Maps simplified UI: tabs, controls, original state, keyboard, responsive and 3D discovery passed.")
