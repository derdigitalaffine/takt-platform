/* Kartenbrowser: Ebenenliste, Transparenz, Zeit (WMS-T), Legende, Sachinformation, Messen, Export,
   Koordinatensuche, eigene Layer (WMS/WFS/WMTS) und Speichern. */
(function () {
  'use strict';
  var bundle = JSON.parse(document.getElementById('map-bundle').textContent);
  var publicGeocoder = true;
  GeoSearch.policy.then(function(d){publicGeocoder=d.public_only;var hint=document.createElement('div');hint.className='small text-secondary';hint.textContent=publicGeocoder?'Öffentliche Orte: neue Suche mit Enter, gespeicherte Treffer beim Tippen.':'Adresse suchen – Live-Suche gemäß Einstellungen.';document.getElementById('coord-search').append(hint);}).catch(function(){});
  var meta = JSON.parse(document.getElementById('map-meta').textContent);
  var csrf = (document.querySelector('meta[name="csrf"]') || {}).content || '';
  var esc = MapKit.esc;
  var params = new URLSearchParams(location.search);

  // Ebenen und Grundkarte aus dem Link (?base=s1&layers=s3,s4)
  if (params.has('base')) {
    bundle.state.base = params.get('base');
    bundle.state.noBase = bundle.state.base === '';
  }
  if (params.has('layers')) {
    var wanted = params.get('layers').split(',');
    bundle.state.layers = bundle.layers.filter(function (l) { return l.role !== 'base'; }).map(function (l) {
      return { id: l.id, visible: wanted.indexOf(l.id) >= 0, opacity: l.opacity };
    });
  }
  var kit = MapKit.create('map', bundle, { hash: true, exportable: true });
  var map = kit.map;
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
  map.addControl(new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: false }), 'top-right');
  map.addControl(new maplibregl.FullscreenControl({ container: document.getElementById('map-shell') }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');

  var infoPanel=document.getElementById('map-info'),parcelInfo=document.getElementById('map-info-parcel'),otherInfo=document.getElementById('map-info-other'),infoRevision=0;
  function showInfo(){infoPanel.hidden=false;shell.classList.remove('panel-hidden');setTimeout(function(){map.resize();infoPanel.scrollIntoView({block:'nearest',behavior:'smooth'});},50);}
  /* --- Seitenleiste ------------------------------------------------------------------ */
  var shell = document.getElementById('map-shell');
  document.getElementById('panel-close').addEventListener('click', function () { shell.classList.add('panel-hidden'); setTimeout(function () { map.resize(); }, 50); });
  document.getElementById('panel-open').addEventListener('click', function () { shell.classList.remove('panel-hidden'); setTimeout(function () { map.resize(); }, 50); });
  document.getElementById('panel-expand').addEventListener('click',function(){if(shell.classList.contains('panel-expanded')){shell.classList.remove('panel-expanded','panel-half');}else if(shell.classList.contains('panel-half')){shell.classList.remove('panel-half');shell.classList.add('panel-expanded');}else{shell.classList.add('panel-half');}this.setAttribute('aria-label',shell.classList.contains('panel-expanded')?'Seitenleiste verkleinern':'Seitenleiste vergrößern');map.resize();});
  document.getElementById('map-info-close').addEventListener('click',function(){infoRevision++;infoPanel.hidden=true;parcelKit.cancelInspect();});
  if (window.innerWidth < 768) { shell.classList.add('panel-hidden'); }

  function renderBases() {
    var box = document.getElementById('base-list');
    box.innerHTML = kit.bases.map(function (b) {
      return '<label class="base-option"><input class="form-check-input mt-0" type="radio" name="base" value="' + esc(b.id) + '"' + (b.id === kit.baseId ? ' checked' : '') + '>' +
        '<span class="flex-grow-1">' + esc(b.name) + '</span>' + (b.description ? '<i class="fa-regular fa-circle-question text-secondary" title="' + esc(b.description) + '"></i>' : '') + '</label>';
    }).join('') + '<label class="base-option"><input class="form-check-input mt-0" type="radio" name="base" value=""' + (!kit.baseId ? ' checked' : '') + '><span class="text-secondary">ohne Grundkarte</span></label>';
  }
  document.getElementById('base-list').addEventListener('change', function (ev) { if (ev.target.name === 'base') { kit.setBase(ev.target.value); } });

  var filterText = '';
  function renderOverlays() {
    var box = document.getElementById('overlay-list');
    var cats = [], byCat = {};
    var activeOnly = document.getElementById('overlay-only-active').checked;
    kit.overlays.forEach(function (l) {
      if (activeOnly && !l.visible) { return; }
      if (filterText && (l.name + ' ' + (l.category || '') + ' ' + (l.description || '')).toLowerCase().indexOf(filterText) < 0) { return; }
      var c = l.category || 'Fachdaten';
      if (!byCat[c]) { byCat[c] = []; cats.push(c); }
      byCat[c].push(l);
    });
    document.getElementById('overlay-count').textContent =
      kit.overlays.filter(function (layer) { return layer.visible; }).length +
      ' aktiv · ' + kit.overlays.length + ' verfügbar';
    var empty = document.getElementById('overlay-empty');
    empty.hidden = cats.length > 0;
    empty.textContent = filterText ? 'Keine passenden Ebenen. Ändern Sie den Suchbegriff.' : 'Keine Ebenen verfügbar.';
    box.innerHTML = cats.map(function (c) {
      return '<div class="layer-cat">' + esc(c) + '</div><div class="layer-group" data-cat="' + esc(c) + '">' + byCat[c].map(rowHtml).join('') + '</div>';
    }).join('');
    if (window.Sortable) {
      box.querySelectorAll('.layer-group').forEach(function (g) {
        Sortable.create(g, { handle: '.drag', animation: 150, onEnd: function () {
          var ids = Array.prototype.map.call(box.querySelectorAll('.layer-row'), function (r) { return r.dataset.id; });
          kit.reorder(ids);
        } });
      });
    }
  }
  function rowHtml(l) {
    var swatch = (l.kind === 'wfs' || l.kind === 'geojson') ? '<span class="layer-swatch" style="background:' + esc(l.color) + '"></span>' : '';
    var times = l.times && l.times.length ? '<div class="d-flex align-items-center gap-2 mt-1"><i class="fa-regular fa-clock text-secondary small" title="Zeit (WMS-T)"></i>' +
      '<input type="range" class="form-range flex-grow-1" data-time-range min="0" max="' + (l.times.length - 1) + '" value="' + Math.max(0, l.times.indexOf(l.time)) + '" aria-label="Zeitpunkt">' +
      '<span class="small text-nowrap" data-time-label>' + esc(l.time) + '</span></div>' : '';
    return '<div class="layer-row' + (l.visible ? ' is-on' : '') + '" data-id="' + esc(l.id) + '">' +
      '<div class="layer-head"><i class="fa-solid fa-grip-vertical drag small" title="Reihenfolge ändern"></i>' +
      '<input class="form-check-input mt-0" type="checkbox" data-toggle' + (l.visible ? ' checked' : '') + ' aria-label="' + esc(l.name) + ' anzeigen">' + swatch +
      '<span class="layer-name" title="' + esc(l.description || l.name) + '">' + esc(l.name) + '</span>' +
      (l.legend ? '<button class="btn-icon" type="button" data-legend title="Legende"><i class="fa-solid fa-list-ul"></i></button>' : '') +
      (l.custom ? '<button class="btn-icon" type="button" data-remove title="Entfernen"><i class="fa-solid fa-xmark"></i></button>' : '') + '</div>' +
      '<div class="layer-tools"><div class="d-flex align-items-center gap-2"><i class="fa-solid fa-circle-half-stroke text-secondary small" title="Deckkraft"></i>' +
      '<input type="range" class="form-range flex-grow-1" min="0" max="100" value="' + Math.round(l.opacity * 100) + '" data-opacity aria-label="Deckkraft">' +
      '<span class="small text-nowrap" style="width:2.6rem" data-opacity-label>' + Math.round(l.opacity * 100) + ' %</span></div>' + times +
      (l.attribution ? '<div class="small text-secondary mt-1 text-truncate">' + esc(l.attribution.replace(/<[^>]*>/g, '')) + '</div>' : '') + '</div></div>';
  }
  var list = document.getElementById('overlay-list');
  list.addEventListener('change', function (ev) {
    var row = ev.target.closest('.layer-row');
    if (!row) { return; }
    if (ev.target.hasAttribute('data-toggle')) {
      kit.setVisible(row.dataset.id, ev.target.checked);
      renderOverlays();
    }
    if (ev.target.hasAttribute('data-time-range')) {
      var l = kit.overlays.find(function (x) { return x.id === row.dataset.id; });
      kit.setTime(l.id, l.times[parseInt(ev.target.value, 10)]);
    }
  });
  list.addEventListener('input', function (ev) {
    var row = ev.target.closest('.layer-row');
    if (!row) { return; }
    if (ev.target.hasAttribute('data-opacity')) {
      kit.setOpacity(row.dataset.id, ev.target.value / 100);
      row.querySelector('[data-opacity-label]').textContent = ev.target.value + ' %';
    }
    if (ev.target.hasAttribute('data-time-range')) {
      var l = kit.overlays.find(function (x) { return x.id === row.dataset.id; });
      row.querySelector('[data-time-label]').textContent = l.times[parseInt(ev.target.value, 10)];
    }
  });
  list.addEventListener('click', function (ev) {
    var row = ev.target.closest('.layer-row');
    if (!row) { return; }
    var l = kit.overlays.find(function (x) { return x.id === row.dataset.id; });
    if (ev.target.closest('[data-legend]')) {
      document.getElementById('legend-title').textContent = 'Legende: ' + l.name;
      document.getElementById('legend-body').innerHTML = '<img src="' + esc(l.legend) + '" alt="Legende ' + esc(l.name) + '" style="max-width:100%">';
      bootstrap.Modal.getOrCreateInstance(document.getElementById('legend-modal')).show();
    }
    if (ev.target.closest('[data-remove]')) { kit.removeOverlay(l.id); renderOverlays(); }
  });
  document.getElementById('layer-filter').addEventListener('input', function (ev) { filterText = ev.target.value.trim().toLowerCase(); renderOverlays(); });
  document.getElementById('overlay-only-active').addEventListener('change', renderOverlays);
  renderBases();
  renderOverlays();

  /* --- Koordinaten anzeigen und suchen ---------------------------------------------- */
  var coords = document.getElementById('map-coords');
  map.on('mousemove', function (ev) {
    var u = MapKit.toUtm32(ev.lngLat.lng, ev.lngLat.lat);
    coords.textContent = MapKit.fmtLatLon(ev.lngLat) + '  ·  UTM 32: ' + Math.round(u[0]) + ' ' + Math.round(u[1]);
  });
  var searchBox = document.getElementById('place-results'), searchMarker = null;
  function jump(lngLat, label, bbox) {
    if (bbox && bbox.length === 4) {
      map.fitBounds([[parseFloat(bbox[2]), parseFloat(bbox[0])], [parseFloat(bbox[3]), parseFloat(bbox[1])]], { padding: 40, maxZoom: 18 });
    } else { map.flyTo({ center: lngLat, zoom: Math.max(map.getZoom(), 16) }); }
    if (searchMarker) { searchMarker.remove(); }
    searchMarker = new maplibregl.Marker({ color: '#1f5fa8' }).setLngLat(lngLat)
      .setPopup(new maplibregl.Popup({ offset: 24 }).setText(label)).addTo(map);
    searchMarker.togglePopup();
    if (window.innerWidth < 768) { shell.classList.add('panel-hidden'); setTimeout(function () { map.resize(); }, 50); }
  }
  function coordsFrom(text) {
    var t = text.replace(/utm\s*32[nN]?/i, '').trim();
    if (/[a-zäöüß]{3,}/i.test(t)) { return null; }   // enthält Wörter → Ortssuche
    var nums = t.match(/-?\d+(?:[.,]\d+)?/g);
    if (!nums || nums.length !== 2) { return null; }
    var a = parseFloat(nums[0].replace(',', '.')), b = parseFloat(nums[1].replace(',', '.'));
    if (Math.abs(a) > 1000 || Math.abs(b) > 1000) { return utmToLngLat(a, b); }
    if (Math.abs(a) <= 90) { return (a < 20 && b > 40) ? [a, b] : [b, a]; }   // üblich: Breite, Länge
    return [a, b];
  }
  var searchInput=document.getElementById('coord-input');
  function mapResults(res,live) {
      if (!res.length) { searchBox.innerHTML = live ? '' : '<div class="small text-secondary py-1">Nichts gefunden.</div>'; return; }
      searchBox.replaceChildren();res.filter(function(r){return r.lat!=null&&r.lon!=null;}).forEach(function(r){var b=document.createElement('button');b.type='button';b.className='list-group-item list-group-item-action small';b.textContent=r.label;b.onclick=function(){jump([r.lon,r.lat],r.label,r.type==='house'?null:r.bbox);};searchBox.append(b);});
      if(!live&&res.length===1&&res[0].lat!=null&&res[0].lon!=null){jump([res[0].lon,res[0].lat],res[0].label,res[0].type==='house'?null:res[0].bbox);}
  }
  var runMapSearch=GeoSearch.bind(searchInput,mapResults,function(){searchBox.textContent='Suche gerade nicht möglich.';});
  document.getElementById('coord-search').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var text = document.getElementById('coord-input').value.trim();
    if (!text) { return; }
    var lngLat = coordsFrom(text);
    if (lngLat) { searchBox.innerHTML = ''; jump(lngLat, lngLat[1].toFixed(6) + ', ' + lngLat[0].toFixed(6)); return; }
    runMapSearch();
  });
  /* UTM 32N → WGS84 (Näherung ausreichend für die Suche) */
  function utmToLngLat(e, n) {
    var a = 6378137, f = 1 / 298.257222101, k0 = 0.9996, e2 = f * (2 - f), ep2 = e2 / (1 - e2);
    var e1 = (1 - Math.sqrt(1 - e2)) / (1 + Math.sqrt(1 - e2)), x = e - 500000, M = n / k0;
    var mu = M / (a * (1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2 * e2 * e2 / 256));
    var p1 = mu + (3 * e1 / 2 - 27 * Math.pow(e1, 3) / 32) * Math.sin(2 * mu) + (21 * e1 * e1 / 16 - 55 * Math.pow(e1, 4) / 32) * Math.sin(4 * mu) + (151 * Math.pow(e1, 3) / 96) * Math.sin(6 * mu);
    var N1 = a / Math.sqrt(1 - e2 * Math.sin(p1) * Math.sin(p1)), T1 = Math.tan(p1) * Math.tan(p1), C1 = ep2 * Math.cos(p1) * Math.cos(p1);
    var R1 = a * (1 - e2) / Math.pow(1 - e2 * Math.sin(p1) * Math.sin(p1), 1.5), D = x / (N1 * k0);
    var lat = p1 - (N1 * Math.tan(p1) / R1) * (D * D / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 * C1 - 9 * ep2) * Math.pow(D, 4) / 24);
    var lon = 9 * Math.PI / 180 + (D - (1 + 2 * T1 + C1) * Math.pow(D, 3) / 6) / Math.cos(p1);
    return [lon * 180 / Math.PI, lat * 180 / Math.PI];
  }

  var parcelKit=MapParcels.create(map,document.getElementById('parcel-browser'),{browserMode:true,onChange:function(){publishWorkspace();},infoHost:parcelInfo,initial:bundle.state.parcels||[],isDrawing:function(){return draw&&draw.mode();},show:showInfo,onActive:function(f){if(f)showInfo();},onMode:function(enabled){if(!enabled)parcelInfo.replaceChildren();},onStyle:function(style){kit.setParcelStyle(style);},onPreset:function(){
    if(!meta.canEdit){toast('Eigene Ebenen können angemeldete Portalnutzer ergänzen.',true);return;}
    document.getElementById('map-catalog').value='parcels';bootstrap.Modal.getOrCreateInstance(document.getElementById('add-layer')).show();document.getElementById('map-catalog-load').click();
  }});
  var advanced = document.getElementById('map-advanced');
  try { advanced.checked = localStorage.getItem('map-advanced') === '1'; } catch (_) {}
  function updateLayerOptions() {
    shell.classList.toggle('is-advanced', advanced.checked);
    try { localStorage.setItem('map-advanced', advanced.checked ? '1' : '0'); } catch (_) {}
  }
  advanced.addEventListener('change', updateLayerOptions);
  updateLayerOptions();
  map.on('map-service-error',function(e){document.getElementById('map-service-status').textContent=e.message;});
  map.on('error',function(e){if(e.sourceId)document.getElementById('map-service-status').textContent='Ein Kartendienst konnte nicht geladen werden. Quelle und Layerauswahl prüfen.';});
  /* --- Klick: Sachinformation (WMS) und Objekte (WFS/GeoJSON) ----------------------- */
  map.on('click', function (ev) {
    if (draw.mode()) { return; }
    var mine = draw.layerIds().filter(function (id) { return map.getLayer(id); });
    if (mine.length && map.queryRenderedFeatures(ev.point, { layers: mine }).length) { return; }   // Klick wählt eine Zeichnung
    var revision=++infoRevision;otherInfo.replaceChildren();parcelKit.clearActive();showInfo();
    var feats = map.queryRenderedFeatures(ev.point, { layers: kit.vectorLayerIds() });
    var seen={};
    feats.forEach(function(f){var signature=(f.source||'')+':'+JSON.stringify(f.properties||{});if(seen[signature])return;seen[signature]=true;
      var section=document.createElement('details'),head=document.createElement('summary');var layer=kit.overlays.find(function(l){return 'src-'+l.id===f.source;});head.textContent=layer?layer.name:'Kartenobjekt';section.append(head);
      var table=document.createElement('table');table.className='table table-sm small';Object.keys(f.properties||{}).slice(0,30).forEach(function(k){var row=table.insertRow(),key=document.createElement('th'),value=document.createElement('td');key.textContent=k;value.textContent=f.properties[k];row.append(key,value);});section.append(table);otherInfo.append(section);
    });
    var loading=document.createElement('p');loading.className='small text-secondary mt-2';loading.textContent='Weitere Karteninformationen werden geladen …';otherInfo.append(loading);
    kit.featureInfo(ev.point).then(function(rows){if(revision!==infoRevision)return;loading.remove();
      rows.forEach(function(r){var section=document.createElement('details'),head=document.createElement('summary');head.textContent=r.layer.name+(r.error?' · nicht verfügbar':'');section.append(head);
        var frame=document.createElement('iframe');frame.setAttribute('sandbox','');frame.title='Sachinformation '+r.layer.name;frame.srcdoc='<base target="_blank"><style>body{font:14px system-ui;margin:6px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px}img{max-width:100%}</style>'+r.html;section.append(frame);otherInfo.append(section);
      });
      if(!rows.length&&!feats.length){var empty=document.createElement('p');empty.className='small text-secondary mt-2';empty.textContent=parcelKit.activeMode()?'Keine weiteren Ebeneninformationen an dieser Stelle.':'Keine Objektinformationen an dieser Stelle. Zum Prüfen eines Flurstücks den Bereich „Flurstücke“ öffnen.';otherInfo.append(empty);}
    });

  });

  /* --- Zeichnen und Messen ------------------------------------------------------------- */
  var measureBox = document.getElementById('map-measure');
  var sketchInfo=null;
  var KIND = { point: ['Punkt', 'fa-location-dot'], text:['Text','fa-font'], rectangle:['Rechteck','fa-vector-square'],circle:['Kreis','fa-circle'],line: ['Linie', 'fa-route'], polygon: ['Fläche', 'fa-draw-polygon'] };
  var draw = MapDraw.create(map, {
    labels:true,
    snapFeatures:function(){return parcelKit.features().concat(bundle.plan?.geometry?[{geometry:bundle.plan.geometry}]:[]);},
    onChange: publishWorkspace,
    onSelect: function (id) {
      publishWorkspace();
      if (!id) return;
      shell.classList.remove('panel-hidden');
      map.resize();
      window.dispatchEvent(new CustomEvent('map-workbench-selection'));
    },
    onSketch: function (info) {
      sketchInfo=info;publishWorkspace();
      if (!info) { measureBox.hidden = true; return; }
      measureBox.hidden = false;
      var hint = (info.mode === 'point'||info.mode==='text') ? 'In die Karte klicken' : (info.mode==='rectangle'||info.mode==='circle') ? (info.count?'Zweiten Punkt für Größe setzen':'Ersten Punkt setzen') :
        info.count < info.min ? (info.mode === 'polygon' ? 'Eckpunkte setzen (mind. 3)' : 'Punkte setzen (mind. 2)') :
        (info.mode === 'polygon' ? 'Ersten Punkt oder doppelt klicken zum Schließen' : 'Doppelklick oder „Fertig“ beendet');
      measureBox.innerHTML = '<i class="fa-solid ' + KIND[info.mode][1] + ' me-1"></i>' + (info.text ? '<strong>' + esc(info.text) + '</strong> · ' : '') + esc(hint) +
        '<span class="ms-2 text-nowrap">' + (info.count >= info.min && info.mode !== 'point' ? '<button class="btn btn-sm btn-primary py-0" type="button" data-sk="finish">Fertig</button> ' : '') +
        (info.count ? '<button class="btn btn-sm btn-outline-secondary py-0" type="button" data-sk="undo" title="Letzten Punkt entfernen (Rücktaste)"><i class="fa-solid fa-rotate-left"></i></button> ' : '') +
        '<button class="btn btn-sm btn-outline-secondary py-0" type="button" data-sk="cancel">Abbrechen</button></span>';
    }
  });
  measureBox.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-sk]');
    if (b) { draw[b.dataset.sk](); }
  });
  function exportDrawings() {
    var data = { type: 'FeatureCollection', features: draw.features().map(function (f) {
      var m = MapDraw.measure(f);
      return { type: 'Feature', geometry: f.geometry, properties: { shape:f.properties.shape||'',radius_m:f.properties.radius_m||0, name: f.properties.name || '', farbe: f.properties.color, laenge_m: Math.round(m.length * 10) / 10, flaeche_m2: Math.round(m.area) } };
    }) };
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/geo+json' }));
    a.download = 'zeichnungen.geojson';
    a.click();
    setTimeout(function(){URL.revokeObjectURL(a.href);},1000);
  }
  document.getElementById('draw-import').addEventListener('change', function (ev) {
    var file = ev.target.files[0];
    if (!file) { return; }
    if(file.size>5000000){toast('Die Datei darf höchstens 5 MB groß sein.',true);ev.target.value='';return;}
    file.text().then(function (text) {
      if(text.length>5000000)throw new Error('Datei zu groß');
      var data = JSON.parse(text), list = data.type === 'FeatureCollection' ? data.features : [data];
      if(!Array.isArray(list))throw new Error('Keine Objektliste');
      var ok = list.filter(function (f) { return MapDraw.validFeature(f); }).slice(0, Math.max(0,500-draw.features().length)).map(function (f, i) {
        var p = f.properties || {};
        return { type: 'Feature', geometry: f.geometry, properties: { shape: /^(circle|rectangle|text)$/.test(p.shape||'')?p.shape:'', radius_m: Number.isFinite(p.radius_m)?p.radius_m:0, name: String(p.name || p.bezeichnung || '').slice(0, 200), color: /^#[0-9a-f]{6}$/i.test(p.farbe || p.color || '') ? (p.farbe || p.color) : MapDraw.COLORS[i % MapDraw.COLORS.length] } };
      });
      draw.setFeatures(draw.features().concat(ok));
      if (ok.length) { draw.zoomTo(draw.features()[draw.features().length - 1].id); }
      toast(ok.length + ' Objekt(e) übernommen', !ok.length);
    }).catch(function () { toast('Die Datei ist kein gültiges GeoJSON.', true); });
    ev.target.value = '';
  });
  draw.setFeatures((bundle.state && bundle.state.drawings) || []);
  draw.resetHistory();

  /* --- Export und Link ------------------------------------------------------------------ */
  function toast(text, error) {
    if (window.Swal) { Swal.fire({ toast: true, position: 'top-end', timer: error ? 5000 : 2200, showConfirmButton: false, icon: error ? 'error' : 'success', title: text }); }
  }
  document.getElementById('btn-export').addEventListener('click', function () {
    map.once('render', function () {
      try {
        var a = document.createElement('a');
        a.download = 'karte.png';
        a.href = window.MapPrint.capture(window.MapWorkspace);
        a.click();
      } catch (e) { toast('Bild nicht möglich: Ein direkt geladener Dienst erlaubt keinen Export.', true); }
    });
    map.triggerRepaint();
  });
  document.getElementById('btn-link').addEventListener('click', function () {
    var on = kit.overlays.filter(function (l) { return l.visible && !l.custom; }).map(function (l) { return l.id; });
    var link = new URL(location.href);
    link.searchParams.set('base', kit.baseId || '');
    link.searchParams.set('layers', on.join(','));
    var url = link.href;
    (navigator.clipboard && window.isSecureContext ? navigator.clipboard.writeText(url) : Promise.reject()).then(function () { toast('Link kopiert'); })
      .catch(function () { window.prompt('Link zu diesem Ausschnitt:', url); });
  });

  function fingerprint(){var state=kit.state();return JSON.stringify({drawings:draw.features(),base:state.base,layers:state.layers,custom:state.custom,parcels:parcelKit.features()});}
  var baseline=fingerprint();
  kit.on(publishWorkspace);
  function publishWorkspace(){if(!draw)return;window.dispatchEvent(new CustomEvent('map-workbench-change'));}
  function getWorkspace(){return {features:draw.features(),selected:draw.selected(),sketch:sketchInfo,canUndo:draw.canUndo(),canRedo:draw.canRedo(),canSave:meta.canEdit,plan:bundle.plan||null,dirty:fingerprint()!==baseline};}
  window.MapWorkspace={snapshot:getWorkspace,draw:draw,map:map,kit:kit,click:function(id){var el=document.getElementById(id);if(el)el.click();},
    start:function(mode){parcelKit.cancelInspect();draw.start(mode);if(innerWidth<768){shell.classList.add('panel-hidden');map.resize();}},
    download:exportDrawings};
  window.addEventListener('beforeunload',function(ev){if(getWorkspace().dirty){ev.preventDefault();ev.returnValue='';}});
  window.dispatchEvent(new CustomEvent('map-workbench-ready'));
  document.addEventListener('keydown',function(ev){if(/INPUT|TEXTAREA|SELECT/.test((ev.target||{}).tagName||'')||ev.target.isContentEditable)return;if((ev.ctrlKey||ev.metaKey)&&ev.key.toLowerCase()==='z'){ev.preventDefault();if(ev.shiftKey)draw.redo();else draw.undo();}});
  if(bundle.plan){
    var plan=bundle.plan;
    function showPlan(){
      if(!plan.geometry)return;
      if(!map.getSource('law-boundary')){map.addSource('law-boundary',{type:'geojson',data:{type:'Feature',geometry:plan.geometry,properties:{}}});map.addLayer({id:'law-boundary-fill',type:'fill',source:'law-boundary',paint:{'fill-color':'#7950f2','fill-opacity':0.13}});map.addLayer({id:'law-boundary-line',type:'line',source:'law-boundary',paint:{'line-color':'#7950f2','line-width':3,'line-dasharray':[3,2]}});}
    }
    map.on('load',function(){showPlan();if(plan.geometry&&!/^#\d+(?:\.\d+)?\/-?\d+(?:\.\d+)?\/-?\d/.test(location.hash)){var bounds=new maplibregl.LngLatBounds();plan.geometry.coordinates[0].forEach(function(p){bounds.extend(p);});map.fitBounds(bounds,{padding:50,maxZoom:17});}});
    map.on('style.load',showPlan);
  }

  /* --- Geodaten entdecken -----------------------------------------------------------
   * Metadata are public and fetched once. Only a deliberate click triggers
   * GetCapabilities; private signed proxy URLs are never exposed to guests.
   * Favorites contain source keys only, no location or saved-map contents.
   */
  var discovery=document.getElementById('map-discovery'), catalogEntries={},
      catalogSelected=null, catalogCaps=null, sourceFavorites=[];
  var catalogStatus=document.getElementById('map-discovery-status'),
      catalogResults=document.getElementById('map-discovery-results'),
      catalogPreview=document.getElementById('map-discovery-preview'),
      catalogChoices=document.getElementById('map-discovery-choices'),
      catalogActivation=document.getElementById('map-discovery-activation-status');
  try{
    var favoriteJson=JSON.parse(localStorage.getItem('map-source-favorites-v1')||'[]');
    if(Array.isArray(favoriteJson))sourceFavorites=favoriteJson.filter(function(k){return typeof k==='string';}).slice(0,100);
  }catch(_){}
  function cleanSearch(value){return String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('de');}
  function currentCatalog(){
    var q=cleanSearch(document.getElementById('map-discovery-search').value.trim()).split(/\s+/).filter(Boolean),
        region=document.getElementById('map-discovery-region').value,
        topic=document.getElementById('map-discovery-topic').value,
        favOnly=document.getElementById('map-discovery-favorites-only').checked;
    return Object.keys(catalogEntries).filter(function(key){
      var d=catalogEntries[key];
      return (!region||d.region===region)&&(!topic||d.topic===topic)&&
        (!favOnly||sourceFavorites.indexOf(key)>=0)&&
        q.every(function(word){return cleanSearch([d.name,d.topic,d.region,d.provider,d.note].join(' ')).indexOf(word)>=0;});
    }).sort(function(a,b){
      var aa=catalogEntries[a],bb=catalogEntries[b];
      var af=sourceFavorites.indexOf(a)>=0?0:1,bf=sourceFavorites.indexOf(b)>=0?0:1;
      return af-bf || (aa.region==='Rheinland-Pfalz'?0:1)-(bb.region==='Rheinland-Pfalz'?0:1)
        || aa.name.localeCompare(bb.name,'de');
    });
  }
  function renderCatalog(){
    var keys=currentCatalog();
    document.getElementById('map-discovery-count').textContent=keys.length+' Quellen';
    catalogStatus.textContent=keys.length?'Quelle wählen, um verfügbare Layer zu prüfen.':'Keine Treffer. Such- oder Themenfilter anpassen.';
    catalogResults.innerHTML=keys.map(function(key){
      var d=catalogEntries[key],fav=sourceFavorites.indexOf(key)>=0;
      var isData=d.kind==='download',title=isData?'Download & Hinweise':'Ebenen auswählen';
      return '<article class="map-source-row" data-source="'+esc(key)+'">'+
        '<div class="source-main"><button type="button" class="source-title" data-source-open="'+esc(key)+'" title="'+esc(title)+'">'+esc(d.name)+'</button>'+
        '<div class="source-meta">'+esc(d.region)+' · '+esc(d.topic)+' · '+esc(d.provider)+'</div>'+
        '<div class="d-flex flex-wrap gap-1 mt-1"><span class="source-tag">'+esc(isData?d.format||'Download':d.kind.toUpperCase())+'</span>'+
        '<span class="source-tag">'+esc(d.license)+'</span></div></div>'+
        '<button class="source-fav" type="button" data-source-favorite="'+esc(key)+'" aria-pressed="'+(fav?'true':'false')+'" aria-label="'+(fav?'Favorit entfernen: ':'Als Favorit speichern: ')+esc(d.name)+'">'+
        '<i class="'+(fav?'fa-solid':'fa-regular')+' fa-star" aria-hidden="true"></i></button></article>';
    }).join('');
    catalogResults.hidden=false;
    catalogPreview.hidden=true;
  }
  function fillCatalogFilters(regions,topics){
    [['map-discovery-region',regions],['map-discovery-topic',topics]].forEach(function(item){
      var field=document.getElementById(item[0]);
      (item[1]||[]).forEach(function(v){
        var option=document.createElement('option');option.value=v;option.textContent=v;field.append(option);
      });
    });
  }
  fetch('/maps/library',{credentials:'same-origin'}).then(function(r){if(!r.ok)throw Error('Quellenverzeichnis nicht verfügbar');return r.json();}).then(function(d){
    catalogEntries=Object.assign({},d.services||{},d.datasets||{});
    fillCatalogFilters(d.regions,d.topics);
    renderCatalog();
  }).catch(function(){catalogStatus.textContent='Geodatenverzeichnis momentan nicht verfügbar. Vorhandene Ebenen können weiterhin genutzt werden.';});
  ['map-discovery-search','map-discovery-region','map-discovery-topic','map-discovery-favorites-only'].forEach(function(id){
    document.getElementById(id).addEventListener(id==='map-discovery-search'?'input':'change',renderCatalog);
  });
  document.getElementById('map-discovery-reset').addEventListener('click',function(){
    ['map-discovery-search','map-discovery-region','map-discovery-topic'].forEach(function(id){document.getElementById(id).value='';});
    document.getElementById('map-discovery-favorites-only').checked=false;
    renderCatalog();
  });
  document.getElementById('map-discovery-back').addEventListener('click',function(){
    catalogPreview.hidden=true;catalogResults.hidden=false;catalogActivation.textContent='';
  });
  catalogResults.addEventListener('click',function(ev){
    var star=ev.target.closest('[data-source-favorite]');
    if(star){
      var key=star.dataset.sourceFavorite,ix=sourceFavorites.indexOf(key);
      if(ix>=0)sourceFavorites.splice(ix,1);else sourceFavorites.unshift(key);
      sourceFavorites=sourceFavorites.slice(0,100);
      try{localStorage.setItem('map-source-favorites-v1',JSON.stringify(sourceFavorites));}catch(_){}
      renderCatalog();return;
    }
    var button=ev.target.closest('[data-source-open]');
    if(!button)return;
    openCatalogSource(button.dataset.sourceOpen);
  });
  function discoveryPost(url,fields){
    var body=new FormData();body.append('csrf',csrf);
    Object.keys(fields||{}).forEach(function(key){body.append(key,fields[key]);});
    return fetch(url,{method:'POST',body:body,credentials:'same-origin',headers:{'Accept':'application/json'}}).then(function(r){
      return r.json().then(function(d){if(!r.ok||!d.ok)throw Error(d.error||'Dienst nicht erreichbar');return d;});
    });
  }
  function openCatalogSource(key){
    var spec=catalogEntries[key];if(!spec)return;
    catalogSelected={key:key,spec:spec};catalogCaps=null;
    document.getElementById('map-discovery-preview-title').textContent=spec.name;
    document.getElementById('map-discovery-preview-info').textContent=spec.provider+' · '+spec.license+
      (spec.note?' · '+spec.note:'');
    catalogResults.hidden=true;catalogPreview.hidden=false;
    catalogActivation.textContent='';
    var button=document.getElementById('map-discovery-activate');
    button.disabled=!meta.canEdit||spec.kind==='download';
    if(spec.kind==='download'){
      catalogChoices.innerHTML='<p class="small mb-2">'+esc(spec.note||'')+'</p>'+
        '<div class="d-grid gap-2"><a class="btn btn-sm btn-outline-primary" href="'+esc(spec.download_url)+'" target="_blank" rel="noopener noreferrer">Amtliche Daten beziehen <i class="fa-solid fa-arrow-up-right-from-square ms-1" aria-hidden="true"></i></a>'+
        '<a class="btn btn-sm btn-outline-secondary" href="'+esc(spec.source_url)+'" target="_blank" rel="noopener noreferrer">Produkt- und Lizenzinformationen</a>'+
        (spec.viewer_url?'<a class="btn btn-sm btn-outline-success" href="'+esc(spec.viewer_url)+'" target="_blank" rel="noopener noreferrer">Rheinland-Pfalz in 3D ansehen <i class="fa-solid fa-arrow-up-right-from-square ms-1" aria-hidden="true"></i></a>':'')+'</div>';
      return;
    }
    if(!meta.canEdit){
      catalogChoices.innerHTML='<p class="small">Zum Einblenden zusätzlicher Ebenen bitte im Portal anmelden. Die Karte und die bereits freigegebenen öffentlichen Ebenen bleiben ohne Anmeldung nutzbar.</p>';
      return;
    }
    catalogChoices.textContent='Verfügbare Ebenen werden beim Anbieter geprüft …';
    discoveryPost('/maps/library/'+encodeURIComponent(key)+'/layers',{}).then(function(data){
      if(!catalogSelected||catalogSelected.key!==key)return;
      catalogCaps=data;
      var layers=(data.layers||[]).filter(function(l){return l.name&&l.supported!==false;});
      if(!layers.length){catalogChoices.textContent='Keine kompatiblen Kartenebenen gefunden.';return;}
      catalogChoices.innerHTML='<label class="visually-hidden" for="map-discovery-layer-filter">Ebenen filtern</label>'+
        '<input id="map-discovery-layer-filter" class="form-control form-control-sm mb-2" type="search" placeholder="In dieser Quelle suchen …">'+
        '<div data-discovery-options>'+layers.slice(0,180).map(function(l,i){
          return '<label class="map-discovery-choice" data-name="'+esc(cleanSearch((l.title||l.name)+' '+l.name))+'">'+
            '<input class="form-check-input" type="checkbox" data-layer-idx="'+i+'"'+(layers.length===1?' checked':'')+'>'+
            '<span class="small"><strong>'+esc(l.title||l.name)+'</strong><span class="d-block text-secondary">'+esc(l.name)+'</span>'+
              (l.abstract?'<span class="d-block text-secondary">'+esc(l.abstract).slice(0,300)+'</span>':'')+
            '</span></label>';
        }).join('')+'</div>'+
        (layers.length>180?'<div class="small text-secondary mt-1">Die ersten 180 Ebenen werden angeboten. Für weitere Ebenen bitte den erweiterten Diensteditor verwenden.</div>':'');
      catalogCaps.supported=layers.slice(0,180);
      var filter=document.getElementById('map-discovery-layer-filter');
      filter.addEventListener('input',function(){
        var words=cleanSearch(filter.value).split(/\s+/).filter(Boolean);
        catalogChoices.querySelectorAll('[data-name]').forEach(function(row){
          row.hidden=!words.every(function(w){return row.dataset.name.indexOf(w)>=0;});
        });
      });
    }).catch(function(e){
      if(catalogSelected&&catalogSelected.key===key){
        catalogChoices.textContent=e.message||'Quelle derzeit nicht verfügbar. Bitte später erneut versuchen.';
      }
    });
  }
  document.getElementById('map-discovery-activate').addEventListener('click',function(){
    if(!catalogSelected||!catalogCaps||!meta.canEdit)return;
    var spec=catalogSelected.spec,cap=catalogCaps;
    var chosen=Array.prototype.map.call(catalogChoices.querySelectorAll('[data-layer-idx]:checked'),function(input){
      return cap.supported[Number(input.dataset.layerIdx)];
    }).filter(Boolean);
    if(!chosen.length){catalogActivation.textContent='Bitte mindestens eine Ebene auswählen.';return;}
    if(chosen.length>12){catalogActivation.textContent='Höchstens zwölf Ebenen gleichzeitig hinzufügen.';return;}
    var button=this;button.disabled=true;catalogActivation.textContent='Ebenen werden zur Karte hinzugefügt …';
    var defs=chosen.map(function(l){
      var category=spec.topic+' · '+spec.region;
      if(cap.type==='xyz')return {kind:'xyz',url:l.template,name:l.title,
        category:category,service:{tile_size:spec.tile_size||256},
        attribution:spec.attribution};
      if(cap.type==='wmts')return {kind:'wmts',url:l.template,layers:l.name,
        name:l.title,category:category,styles:l.styles||'',format:l.format||'image/png',
        service:l.service||{},attribution:spec.attribution};
      return {kind:cap.type,url:cap.url,layers:l.name,name:l.title,
        category:category,version:cap.version||'',service:l.service||{},
        times:l.times||[],time:l.time||'',attribution:spec.attribution};
    });
    var added=0,skipped=0,failed=0;
    Promise.all(defs.map(function(def){
      var exists=kit.overlays.some(function(l){
        return l.custom&&l.custom.kind===def.kind&&l.custom.url===def.url&&
          (l.custom.layers||'')===(def.layers||'');
      });
      if(exists){skipped++;return Promise.resolve();}
      return discoveryPost('/maps/sign',{layer:JSON.stringify(def)}).then(function(result){
        kit.addOverlay(result.layer);added++;
      }).catch(function(){failed++;});
    })).then(function(){
      renderOverlays();
      catalogActivation.textContent=added+' hinzugefügt'+(skipped?', '+skipped+' bereits vorhanden':'')+
        (failed?', '+failed+' fehlgeschlagen':'')+'.';
      if(added){toast(added+' Kartenebene(n) aktiviert');}
      button.disabled=false;
    });
  });
  var perspective=document.getElementById('map-3d-view');
  function syncPerspective(){var active=map.getPitch()>10;perspective.setAttribute('aria-pressed',active?'true':'false');
    perspective.classList.toggle('btn-primary',active);perspective.classList.toggle('btn-outline-secondary',!active);}
  perspective.addEventListener('click',function(){map.easeTo({pitch:map.getPitch()>10?0:55,duration:500});});
  map.on('pitchend',syncPerspective);
  syncPerspective();

  if (!meta.canEdit) { return; }

  /* --- Eigene Layer hinzufügen ---------------------------------------------------------- */
  function post(url, fields) {
    var body = new FormData();
    body.append('csrf', csrf);
    Object.keys(fields).forEach(function (k) { body.append(k, fields[k]); });
    return fetch(url, { method: 'POST', body: body, headers: { 'X-Requested-With': 'fetch', 'Accept':'application/json' }, credentials: 'same-origin' }).then(function (r) { return r.json(); });
  }
  var result = document.getElementById('al-result'), status = document.getElementById('al-status'), caps = null;
  ['al-url','al-kind'].forEach(function(id){document.getElementById(id).addEventListener('input',function(){caps=null;result.replaceChildren();});});
  document.getElementById('map-catalog-load').addEventListener('click',function(){
    var key=document.getElementById('map-catalog').value;status.textContent='Amtliche Quelle wird geprüft …';
    post('/maps/catalog/'+key,{}).then(function(d){if(!d.ok){status.textContent=d.error;return;}document.getElementById('al-url').value=d.url;document.getElementById('al-kind').value=d.type==='wmts'?'xyz':d.type;showCaps(d,d.url);}).catch(function(){status.textContent='Quelle derzeit nicht erreichbar. Bitte später erneut versuchen.';});
  });
  document.getElementById('al-query').addEventListener('click', function () {
    var url = document.getElementById('al-url').value.trim(), kind = document.getElementById('al-kind').value;
    status.textContent = 'Frage Dienst ab …';
    result.innerHTML = '';
    post('/maps/capabilities', { url: url, kind: kind }).then(function (d) {
      showCaps(d,url);
    }).catch(function () { status.textContent = 'Abfrage fehlgeschlagen.'; });
  });
  function showCaps(d,url) {
      if (!d.ok) { status.textContent = ''; result.innerHTML = '<div class="alert alert-danger py-2">' + esc(d.error) + '</div>'; return; }
      caps = d;
      caps.url = d.url || url;
      status.textContent = (d.title || 'Dienst') + ' · ' + d.layers.length + ' Layer';
      result.innerHTML = d.layers.length ? '<input class="form-control form-control-sm mb-2" id="al-filter" placeholder="Layer filtern …">' +
        '<div class="list-group" style="max-height:22rem;overflow:auto">' + d.layers.map(function (l, i) {
          return '<label class="list-group-item d-flex gap-2" style="padding-left:' + (0.75 + (l.depth || 0) * 0.8) + 'rem" data-name="' + esc((l.title + ' ' + l.name).toLowerCase()) + '">' +
            '<input class="form-check-input flex-none" type="checkbox" value="' + i + '"' + (l.supported === false ? ' disabled' : '') + '>' +
            '<span><span class="fw-semibold">' + esc(l.title) + '</span> <code class="small">' + esc(l.name) + '</code>' +
            (l.times && l.times.length ? ' <span class="badge text-bg-info">Zeit: ' + l.times.length + ' Werte</span>' : '') +
            (l.supported === false ? ' <span class="badge text-bg-secondary">nicht in Web-Mercator</span>' : '') +
            (l.abstract ? '<div class="small text-secondary">' + esc(l.abstract) + '</div>' : '') + '</span></label>';
        }).join('') + '</div>' : '<div class="text-secondary">Der Dienst enthält keine abrufbaren Layer.</div>';
      var f = document.getElementById('al-filter');
      if (f) { f.addEventListener('input', function () { var q = f.value.toLowerCase(); result.querySelectorAll('[data-name]').forEach(function (r) { r.classList.toggle('d-none', r.dataset.name.indexOf(q) < 0); }); }); }
  }
  document.getElementById('al-add').addEventListener('click', function () {
    var defs = [];
    var kind = document.getElementById('al-kind').value, url = document.getElementById('al-url').value.trim();
    var chosen = result.querySelectorAll('input[type=checkbox]:checked');
    if (caps && chosen.length) {
      chosen.forEach(function (c) {
        var l = caps.layers[parseInt(c.value, 10)];
        if (caps.type === 'wmts') { defs.push({kind:'wmts',url:l.template,layers:l.name,name:l.title,styles:l.styles,format:l.format,service:l.service,attribution:l.attribution||caps.attribution||''}); }
        else if (caps.type === 'xyz') { defs.push({ kind: 'xyz', url: l.template, name: l.title }); }
        else { defs.push({ kind: caps.type, url: caps.url, layers: l.name, name: l.title, version: caps.version, times: l.times || [], time: l.time || '', service:l.service || {},attribution:l.attribution||caps.attribution||'' }); }
      });
    } else if (kind === 'xyz' && url.indexOf('{z}') >= 0) {
      defs.push({ kind: 'xyz', url: url, name: 'Kacheln: ' + url.split('/')[2] });
    } else { status.textContent = 'Bitte zuerst „Dienst abfragen“ und Layer auswählen.'; return; }
    var done = 0;
    defs.forEach(function (def) {
      post('/maps/sign', { layer: JSON.stringify(def) }).then(function (d) {
        if (d.ok) { kit.addOverlay(d.layer); renderOverlays(); done++; status.textContent = done + ' Layer hinzugefügt'; }
        else { status.textContent = d.error; }
      });
    });
  });

  /* --- Speichern -------------------------------------------------------------------------- */
  var saving=false;
  function save(asNew) {
    if(saving)return;
    var title = document.getElementById('sm-title').value.trim();
    var out = document.getElementById('sm-result');
    if (!title) { out.innerHTML = '<div class="text-danger small">Bitte einen Titel angeben.</div>'; return; }
    saving=true;out.textContent='Karte wird gespeichert …';
    var savedFingerprint=fingerprint();
    post('/maps/save', { id: asNew ? '' : (meta.mapId || ''), title: title, description: document.getElementById('sm-desc').value,
      public: document.getElementById('sm-public').checked ? '1' : '0', state: JSON.stringify(Object.assign(kit.state(), { drawings: draw.features(), parcels:parcelKit.features() })) }).then(function (d) {
      if (!d.ok) { out.innerHTML = '<div class="text-danger small">' + esc(d.error) + '</div>'; return; }
      meta.mapId = d.id; baseline=savedFingerprint;publishWorkspace();
      var pub = d.public ? location.origin + d.public : '';
      out.innerHTML = '<div class="alert alert-success small mb-0"><i class="fa-solid fa-check me-1"></i>Gespeichert. <a href="' + esc(d.link) + '">Karte öffnen</a>' +
        (pub ? '<div class="mt-2">Öffentlicher Link:<input class="form-control form-control-sm mt-1" readonly value="' + esc(pub) + '"></div>' +
          '<div class="mt-2">Einbetten:<textarea class="form-control form-control-sm font-monospace mt-1" rows="3" readonly>' +
          esc('<iframe src="' + location.origin + d.public.replace('/karte/', '/karte-embed/') + '" title="Karte" style="width:100%;height:600px;border:0" allow="geolocation; fullscreen" loading="lazy"></iframe>') + '</textarea></div>' : '') + '</div>';
    }).catch(function(){out.textContent='Karte konnte nicht gespeichert werden. Bitte erneut versuchen.';}).finally(function(){saving=false;});
  }
  document.getElementById('sm-save').addEventListener('click', function () { save(false); });
  var copyBtn = document.getElementById('sm-copy');
  if (copyBtn) { copyBtn.addEventListener('click', function () { save(true); }); }
})();
