/* TAKT Karten: task-first UI without replacing MapLibre, Mantine or layer logic.
 * Existing controls are MOVED, not duplicated: original listeners and IDs survive.
 * If this enhancement fails, the original complete map controls remain usable. */
(function () {
  'use strict';

  var pane = document.getElementById('map-layer-pane');
  var discovery = document.getElementById('map-discovery');
  var searchResults = document.getElementById('place-results');
  var baseList = document.getElementById('base-list');
  var overlayList = document.getElementById('overlay-list');
  var host = document.getElementById('map-workbench');
  if (!pane || !discovery || !searchResults || !baseList || !overlayList || !host
      || document.getElementById('map-easy-tabs')) return;

  function el(tag, className, html) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (html !== undefined) node.innerHTML = html;
    return node;
  }

  var originalChildren = Array.from(pane.children);
  var searchIndex = originalChildren.indexOf(searchResults);
  var discoveryIndex = originalChildren.indexOf(discovery);
  if (searchIndex < 0 || discoveryIndex <= searchIndex) return;
  var layers = originalChildren.slice(searchIndex + 1, discoveryIndex);
  var extras = originalChildren.slice(discoveryIndex + 1);

  var tabs = el('nav', 'map-easy-tabs');
  tabs.id = 'map-easy-tabs';
  tabs.setAttribute('role', 'tablist');
  tabs.setAttribute('aria-label', 'Karte gestalten');
  var captions = [
    ['overview', 'Meine Karte', 'fa-map'],
    ['layers', 'Ebenen', 'fa-layer-group'],
    ['discover', 'Daten finden', 'fa-compass']
  ];
  captions.forEach(function (data, index) {
    var btn = el('button', 'map-easy-tab' + (index === 0 ? ' is-active' : ''));
    btn.type = 'button';
    btn.id = 'map-tab-' + data[0];
    btn.dataset.mapTab = data[0];
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-controls', 'map-easy-' + data[0]);
    btn.setAttribute('aria-selected', index === 0 ? 'true' : 'false');
    btn.tabIndex = index === 0 ? 0 : -1;
    btn.innerHTML = '<i class="fa-solid ' + data[2] +
      '" aria-hidden="true"></i><span>' + data[1] + '</span>';
    tabs.appendChild(btn);
  });

  var overview = el('section', 'map-easy-pane');
  overview.id = 'map-easy-overview';
  overview.setAttribute('role', 'tabpanel');
  overview.setAttribute('aria-labelledby', 'map-tab-overview');
  overview.innerHTML =
    '<div class="map-easy-intro"><span class="map-easy-eyebrow">Dein Kartenausschnitt</span>' +
      '<h2 class="map-easy-heading">Was möchtest du sehen?</h2>' +
      '<p>Wähle deine Grundkarte. Zusätzliche Informationen kannst du jederzeit einblenden.</p></div>' +
    '<div class="map-easy-block"><label for="map-easy-base" class="map-easy-label">' +
      '<i class="fa-solid fa-map me-1" aria-hidden="true"></i>Grundkarte</label>' +
      '<select id="map-easy-base" class="form-select" aria-describedby="map-easy-base-help">' +
        '<option value="">Karten werden geladen …</option></select>' +
      '<p id="map-easy-base-help" class="map-easy-hint">Das Hintergrundbild deiner Karte.</p></div>' +
    '<div class="map-easy-block"><div class="map-easy-row">' +
      '<h2 class="map-easy-label mb-0">Sichtbare Informationen</h2>' +
      '<span id="map-easy-count" class="map-easy-count" role="status">0 aktiv</span></div>' +
      '<div id="map-easy-active" class="map-easy-active" aria-live="polite"></div>' +
      '<button type="button" class="map-easy-action" data-map-go="layers">' +
        '<i class="fa-solid fa-plus" aria-hidden="true"></i>' +
        '<span>Informationen auswählen oder ändern</span>' +
        '<i class="fa-solid fa-arrow-right ms-auto" aria-hidden="true"></i></button></div>' +
    '<button type="button" class="map-easy-discover-link" data-map-go="discover">' +
      '<span class="map-easy-link-icon"><i class="fa-solid fa-compass" aria-hidden="true"></i></span>' +
      '<span><strong>Weitere Karten entdecken</strong>' +
      '<small>Luftbilder, Kataster, Hochwasser, Bahn und mehr</small></span>' +
      '<i class="fa-solid fa-chevron-right ms-auto" aria-hidden="true"></i></button>' +
    '<details class="map-easy-details" id="map-easy-special">' +
      '<summary><span><i class="fa-solid fa-cubes-stacked me-2" aria-hidden="true"></i>' +
      '3D und Kartenvergleich</span>' +
      '<i class="fa-solid fa-chevron-down map-easy-chevron" aria-hidden="true"></i></summary>' +
      '<div class="map-easy-details-body" id="map-easy-special-body">' +
      '<p class="map-easy-hint">Zusätzliche Ansichten, wenn du sie benötigst.</p></div></details>';

  var layersPane = el('section', 'map-easy-pane');
  layersPane.id = 'map-easy-layers';
  layersPane.hidden = true;
  layersPane.setAttribute('role', 'tabpanel');
  layersPane.setAttribute('aria-labelledby', 'map-tab-layers');
  layersPane.innerHTML = '<div class="map-easy-pane-head">' +
    '<h2 class="h6 mb-1">Informationen einblenden</h2>' +
    '<p>Wähle per Häkchen, welche Ebenen auf deiner Karte erscheinen.</p></div>';

  var discoverPane = el('section', 'map-easy-pane');
  discoverPane.id = 'map-easy-discover';
  discoverPane.hidden = true;
  discoverPane.setAttribute('role', 'tabpanel');
  discoverPane.setAttribute('aria-labelledby', 'map-tab-discover');
  discoverPane.innerHTML = '<div class="map-easy-pane-head">' +
    '<h2 class="h6 mb-1">Neue Karten und Daten finden</h2>' +
    '<p>Suche nach einem Thema. Erst deine Auswahl fragt den Kartendienst ab.</p></div>';

  // Move the ORIGINAL DOM nodes. Existing layer toggles, discovery search,
  // extrusion, legends, comparison and model controls retain their handlers.
  layers.forEach(function (child) { layersPane.appendChild(child); });
  discoverPane.appendChild(discovery);
  extras.forEach(function (child) {
    overview.querySelector('#map-easy-special-body').appendChild(child);
  });
  searchResults.after(tabs, overview, layersPane, discoverPane);

  var searchLabel = pane.querySelector('label[for="coord-input"]');
  if (searchLabel) searchLabel.textContent = 'Ort oder Adresse finden';
  var search = document.getElementById('coord-input');
  if (search) search.placeholder = 'Ort, Adresse oder Koordinaten …';

  var catalogHeading = document.getElementById('map-discovery-title');
  if (catalogHeading) catalogHeading.textContent = 'Datenquellen';
  var catalogSubtitle = discovery.querySelector('.map-discovery-header .small');
  if (catalogSubtitle) catalogSubtitle.textContent = 'Amtliche Karten und offene Daten';

  // Rarely used discovery settings are still fully available with one click.
  var filters = discovery.querySelector('.map-discovery-filters');
  if (filters && filters.children.length >= 4) {
    var advanced = el('details', 'map-easy-catalog-more');
    advanced.innerHTML = '<summary>Region, Thema und Favoriten filtern ' +
      '<i class="fa-solid fa-chevron-down" aria-hidden="true"></i></summary>';
    var body = el('div', 'map-easy-catalog-more-body');
    Array.from(filters.children).slice(2).forEach(function (node) { body.appendChild(node); });
    advanced.appendChild(body);
    filters.appendChild(advanced);
    // A result count belongs to the compact top line, not hidden filters.
    var count = document.getElementById('map-discovery-count');
    var header = discovery.querySelector('.map-discovery-header');
    if (count && header) {
      count.classList.add('map-easy-source-count');
      header.insertBefore(count, header.lastElementChild);
    }
  }

  // Keep the existing source catalog browsing feature intact. A single
  // optional chip adds the official DGM terrain download category.
  var shortcuts = discovery.querySelector('.map-discovery-shortcuts');
  var terrainChip;
  if (shortcuts && !shortcuts.querySelector('[data-discovery-topic="Gelände"]')) {
    terrainChip = el('button', 'btn btn-sm btn-outline-secondary');
    terrainChip.type = 'button';
    terrainChip.dataset.discoveryTopic = 'Gelände';
    terrainChip.setAttribute('aria-pressed', 'false');
    terrainChip.textContent = 'Gelände';
    shortcuts.appendChild(terrainChip);
    terrainChip.addEventListener('click', function () {
      var select = document.getElementById('map-discovery-topic');
      if (!select) return;
      select.value = select.value === 'Gelände' ? '' : 'Gelände';
      select.dispatchEvent(new Event('change', {bubbles: true}));
    });
  }

  // Print/PDF is available to all viewers, but no longer occupies permanent
  // space below *every* toolbox pane.
  var actions = document.getElementById('map-workbench-actions');
  if (actions) {
    var exportDetails = el('details', 'map-easy-details map-easy-export');
    exportDetails.id = 'map-easy-export';
    exportDetails.innerHTML = '<summary><span><i class="fa-solid fa-print me-2" aria-hidden="true">' +
      '</i>Drucken und exportieren</span>' +
      '<i class="fa-solid fa-chevron-down map-easy-chevron" aria-hidden="true"></i></summary>';
    actions.before(exportDetails);
    exportDetails.appendChild(actions);
  }

  // Technical explanation is intentionally optional; users always see a
  // concise warning that this 3D overlay is not a certified height model.
  var lod2 = document.getElementById('map-lod2-panel');
  if (lod2) {
    var explanation = lod2.querySelector('p');
    if (explanation) {
      var help = el('details', 'map-easy-help');
      help.innerHTML = '<summary>Was sind LoD2 und DGM?</summary>';
      explanation.before(help);
      help.appendChild(explanation);
    }
  }

  var easyBase = document.getElementById('map-easy-base');
  var easyActive = document.getElementById('map-easy-active');
  var easyCount = document.getElementById('map-easy-count');
  var api = null;
  function showTab(name, focus) {
    if (!captions.some(function (c) { return c[0] === name; })) return;
    captions.forEach(function (c) {
      var selected = c[0] === name;
      var btn = document.getElementById('map-tab-' + c[0]);
      var panel = document.getElementById('map-easy-' + c[0]);
      btn.classList.toggle('is-active', selected);
      btn.setAttribute('aria-selected', String(selected));
      btn.tabIndex = selected ? 0 : -1;
      panel.hidden = !selected;
      if (selected && focus) btn.focus();
    });
    var scrollbox = pane.closest('.map-panel-body');
    if (scrollbox && focus) scrollbox.scrollTop = 0;
    if (api && api.map && api.map.resize) api.map.resize();
  }
  tabs.addEventListener('click', function (event) {
    var tab = event.target.closest('[data-map-tab]');
    if (tab) showTab(tab.dataset.mapTab, false);
  });
  tabs.addEventListener('keydown', function (event) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    var buttons = Array.from(tabs.querySelectorAll('[data-map-tab]'));
    var index = buttons.indexOf(document.activeElement);
    if (index < 0) return;
    event.preventDefault();
    var next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
      : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
    showTab(buttons[next].dataset.mapTab, true);
  });
  overview.addEventListener('click', function (event) {
    var btn = event.target.closest('[data-map-go]');
    if (btn) showTab(btn.dataset.mapGo, true);
    var hide = event.target.closest('[data-map-hide]');
    if (hide && api) {
      // Change the original checkbox, so all MapKit state and the underlying
      // full layer list remain synchronised by the existing event handler.
      var input = Array.from(overlayList.querySelectorAll('[data-toggle]')).find(function (node) {
        return node.closest('[data-id]')?.dataset.id === hide.dataset.mapHide;
      });
      if (input && input.checked) {
        input.checked = false;
        input.dispatchEvent(new Event('change', {bubbles: true}));
        update();
      }
    }
  });
  easyBase.addEventListener('change', function () {
    if (!api) return;
    var radio = Array.from(baseList.querySelectorAll('input[name="base"]')).find(function (node) {
      return node.value === easyBase.value;
    });
    if (radio) {
      radio.checked = true;
      radio.dispatchEvent(new Event('change', {bubbles: true}));
    }
    update();
  });

  function update() {
    if (!api || !api.kit) return;
    var kit = api.kit;
    var currentOptions = Array.from(easyBase.options).map(function (o) { return o.value; });
    var expectedOptions = kit.bases.map(function (b) { return b.id; }).concat(['']);
    if (currentOptions.join('|') !== expectedOptions.join('|')) {
      easyBase.replaceChildren();
      kit.bases.forEach(function (base) {
        var option = document.createElement('option');
        option.value = base.id;
        option.textContent = base.name;
        easyBase.appendChild(option);
      });
      var none = document.createElement('option');
      none.value = '';
      none.textContent = 'Ohne Grundkarte';
      easyBase.appendChild(none);
    }
    easyBase.value = kit.baseId || '';
    var visible = kit.overlays.filter(function (l) { return l.visible; });
    easyCount.textContent = visible.length + ' aktiv';
    easyActive.replaceChildren();
    if (!visible.length) {
      var empty = el('p', 'map-easy-empty');
      empty.textContent = 'Noch keine zusätzlichen Informationen eingeblendet.';
      easyActive.appendChild(empty);
    } else {
      visible.slice(0, 12).forEach(function (layer) {
        var button = el('button', 'map-easy-active-item');
        button.type = 'button';
        button.dataset.mapHide = layer.id;
        button.setAttribute('aria-label', layer.name + ' ausblenden');
        var label = el('span');
        label.textContent = layer.name;
        var x = el('i', 'fa-solid fa-xmark');
        x.setAttribute('aria-hidden', 'true');
        button.append(label, x);
        easyActive.appendChild(button);
      });
      if (visible.length > 12) {
        var hint = el('p', 'map-easy-hint');
        hint.textContent = '+' + (visible.length - 12) + ' weitere Ebenen – über „Ebenen“ verwalten.';
        easyActive.appendChild(hint);
      }
    }
  }

  function ready() {
    if (api || !window.MapWorkspace?.kit) return;
    api = window.MapWorkspace;
    api.kit.on(update);
    update();
  }
  window.addEventListener('map-workbench-ready', ready);
  ready();
  // Keep the initial overview even when a different toolkit tab was opened
  // previously; this is a visual enhancement, not persistent map state.
  document.getElementById('map-shell')?.classList.add('map-easy-ready');
})();
