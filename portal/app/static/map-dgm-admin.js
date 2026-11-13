/* Admin-only optional LVermGeo DGM XYZ import (no remote GIS downloads). */
(function () {
  'use strict';
  var form = document.getElementById('dgm-import-form');
  var status = document.getElementById('dgm-admin-state');
  var submit = document.getElementById('dgm-import-submit');
  var input = document.getElementById('dgm-xyz-file');
  var confirm = document.getElementById('dgm-confirm-height');
  if (!form || !status || !submit || !input || !confirm) return;
  var max = 12 * 1024 * 1024;
  function show(data) {
    if (!data.available) {
      status.textContent = 'Kein passendes Geländemodell vorhanden. Bitte zuerst LoD2 importieren und den Höhenbezug prüfen.';
      return;
    }
    status.textContent = 'DGM verfügbar: ' + data.sample_count + ' Höhenpunkte · ' +
      data.triangles + ' Geländedreiecke · Rasterweite ' + data.grid_spacing_m + ' m · ' +
      data.skipped_cells + ' unvollständige Rasterzellen ausgelassen · ' +
      'Import ' + String(data.imported_at || '').slice(0, 16).replace('T', ' ') + ' UTC. ' +
      'Mit aktueller LoD2-Gebäudevorschau verknüpft.';
  }
  fetch('/maps/dgm/status', {credentials:'same-origin'}).then(function (r) {
    if (!r.ok) throw Error();
    return r.json();
  }).then(show).catch(function () {
    status.textContent = 'DGM-Status konnte nicht geladen werden.';
  });
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var file = input.files && input.files[0];
    if (!file || !/\.(xyz|txt|asc)$/i.test(file.name) || !file.size || file.size > max) {
      status.textContent = 'Bitte eine DGM-XYZ-Datei (max. 12 MiB) auswählen.';
      return;
    }
    if (!confirm.checked) {
      status.textContent = 'Zunächst den gemeinsamen amtlichen Höhenbezug ausdrücklich bestätigen.';
      return;
    }
    submit.disabled = true;
    status.textContent = 'DGM wird geprüft und als begrenztes 3D-Gelände aufbereitet …';
    fetch(form.action, {method:'POST', body:new FormData(form),
      credentials:'same-origin', headers:{Accept:'application/json'}})
      .then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok || !data.ok) throw Error(data.detail || data.error || 'DGM-Import fehlgeschlagen.');
          return data;
        });
      }).then(function (data) {
        show(data.status);
        form.reset();
      }).catch(function (error) {
        status.textContent = String(error.message || 'DGM-Import fehlgeschlagen.').slice(0, 400);
      }).finally(function () { submit.disabled = false; });
  });
})();
