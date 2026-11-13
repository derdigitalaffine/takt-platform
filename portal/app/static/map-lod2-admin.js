/* Admin-only, opt-in local CityGML mesh management for TAKT Karten. */
(function () {
  'use strict';
  var advanced3d = document.getElementById('map-admin-3d');
  function revealDeepLink() {
    if (advanced3d && /^#(?:lod2-preview|dgm-preview|map-admin-3d)$/.test(location.hash)) {
      advanced3d.open = true;
    }
  }
  revealDeepLink();
  window.addEventListener('hashchange', revealDeepLink);
  var form = document.getElementById('lod2-import-form');
  var status = document.getElementById('lod2-admin-state');
  var submit = document.getElementById('lod2-import-submit');
  if (!form || !status || !submit) return;
  var pick = document.getElementById('lod2-gml-file');
  var limit = 4 * 1024 * 1024;

  function show(data) {
    if (!data.available) {
      status.textContent = 'Noch kein örtliches 3D-Modell installiert. Import nur nach expliziter Auswahl.';
      return;
    }
    status.textContent =
      'Modell aktiv · ' + data.roof_polygons + ' Dachflächen · ' +
      data.wall_polygons + ' Wandflächen · ' + data.triangles + ' Dreiecke · ' +
      data.skipped_polygons + ' ausgelassen · ' +
      'Import: ' + String(data.imported_at || '').slice(0, 19).replace('T', ' ') +
      ' UTC. Ohne DGM-Höhenabgleich.';
  }

  fetch('/maps/lod2/status', {credentials: 'same-origin'}).then(function (r) {
    if (!r.ok) throw Error('Status nicht abrufbar');
    return r.json();
  }).then(show).catch(function () { status.textContent = 'Modellstatus derzeit nicht verfügbar.'; });

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var file = pick.files && pick.files[0];
    if (!file || !/\.(gml|xml)$/i.test(file.name) || file.size === 0 ||
        file.size > limit) {
      status.textContent = 'Bitte eine CityGML-Datei (.gml oder .xml) bis 4 MiB auswählen.';
      return;
    }
    submit.disabled = true;
    status.textContent = 'Amtliche Dach- und Wandgeometrien werden geprüft und konvertiert …';
    fetch(form.action, {method: 'POST', credentials: 'same-origin', body: new FormData(form),
      headers: {'Accept': 'application/json'}}).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok || !data.ok) throw Error(data.detail || data.error || 'Import fehlgeschlagen');
        return data;
      });
    }).then(function (data) {
      show(data.status);
      form.reset();
    }).catch(function (error) {
      status.textContent = String(error.message || 'Import fehlgeschlagen').slice(0, 400);
    }).finally(function () { submit.disabled = false; });
  });
})();
