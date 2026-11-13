/* TAKT Grundkartenvergleich: zwei synchronisierte MapLibre-Ansichten.
 * Eine zweite Karte wird ausschließlich nach Nutzeraktion angelegt.
 * Kein zusätzlicher GIS-Endpunkt, keine Übertragung personenbezogener Daten. */
(function () {
  'use strict';

  var initialized = false;

  function setup() {
    if (initialized || !window.MapWorkspace || !window.MapKit) return;
    initialized = true;

    var workspace = window.MapWorkspace;
    var map = workspace.map;
    var kit = workspace.kit;
    var button = document.getElementById('map-compare-toggle');
    var toolbar = document.getElementById('map-compare-toolbar');
    var overlay = document.getElementById('map-compare-layer');
    var divider = document.getElementById('map-compare-divider');
    var select = document.getElementById('map-compare-base');
    var slider = document.getElementById('map-compare-position');
    var close = document.getElementById('map-compare-close');
    var status = document.getElementById('map-compare-status');
    if (!button || !toolbar || !overlay || !divider || !select || !slider || !close) return;

    var bases = kit.bases.filter(function (l) {
      return l.kind === 'style' || !!l.tiles;
    });
    if (bases.length < 2) {
      button.disabled = true;
      button.title = 'Zum Grundkartenvergleich müssen mindestens zwei Grundkarten eingerichtet sein.';
      return;
    }

    bases.forEach(function (base) {
      var option = document.createElement('option');
      option.value = base.id;
      option.textContent = base.name;
      select.append(option);
    });

    var companion = null;
    function position() {
      var percent = Math.max(10, Math.min(90, Number(slider.value) || 50));
      overlay.style.clipPath = 'inset(0 0 0 ' + percent + '%)';
      divider.style.left = percent + '%';
      slider.setAttribute('aria-valuetext', percent + ' Prozent von links');
    }
    position();

    function synchronize() {
      if (!companion) return;
      var center = map.getCenter();
      companion.map.jumpTo({
        center: [center.lng, center.lat],
        zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch()
      });
    }
    function resize() {
      if (companion) {
        companion.map.resize();
        synchronize();
      }
    }
    map.on('move', synchronize);
    map.on('resize', resize);
    window.addEventListener('resize', resize);

    function stop() {
      if (companion) {
        companion.map.remove();
        companion = null;
      }
      overlay.hidden = true;
      divider.hidden = true;
      toolbar.hidden = true;
      button.setAttribute('aria-pressed', 'false');
      button.classList.remove('btn-primary');
      button.classList.add('btn-outline-secondary');
      if (status) status.textContent = '';
    }
    function start() {
      var alternative = bases.find(function (base) {
        return base.id !== kit.baseId;
      }) || bases[0];
      select.value = alternative.id;
      toolbar.hidden = false;
      overlay.hidden = false;
      divider.hidden = false;
      position();

      var center = map.getCenter();
      var state = {
        center: [center.lng, center.lat], zoom: map.getZoom(),
        bearing: map.getBearing(), pitch: map.getPitch(),
        base: select.value, layers: []
      };
      try {
        companion = MapKit.create('map-compare-canvas', {
          layers: bases.map(function (base) { return Object.assign({}, base); }),
          view: { center: state.center, zoom: state.zoom },
          state: state
        }, { hash: false, exportable: false });
        var other = companion.map;
        ['dragPan', 'dragRotate', 'scrollZoom', 'boxZoom', 'doubleClickZoom',
          'touchZoomRotate', 'keyboard'].forEach(function (name) {
          if (other[name] && typeof other[name].disable === 'function') {
            other[name].disable();
          }
        });
        synchronize();
        other.once('load', resize);
        button.setAttribute('aria-pressed', 'true');
        button.classList.add('btn-primary');
        button.classList.remove('btn-outline-secondary');
        if (status) status.textContent = 'Vergleich aktiv: links aktuelle Karte, rechts andere Grundkarte.';
      } catch (_) {
        stop();
        if (status) status.textContent = 'Der Kartenvergleich konnte nicht gestartet werden.';
      }
    }

    button.addEventListener('click', function () {
      if (companion) stop();
      else start();
    });
    close.addEventListener('click', stop);
    slider.addEventListener('input', position);
    select.addEventListener('change', function () {
      if (companion) companion.setBase(select.value);
      synchronize();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && companion && !document.querySelector('.modal.show')) {
        stop();
      }
    });
    // The right-hand view deliberately contains only the selected base map.
    // Overlay/symbol comparisons require separate per-layer clipping.
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }
  window.addEventListener('map-workbench-ready', setup);
})();
