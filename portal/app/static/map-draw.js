/* Zeichnen und Messen auf MapLibre-Karten: Punkt, Linie, Fläche. Stützpunkte lassen sich verschieben,
   ein Klick auf eine Zeichnung wählt sie aus. Verwendet vom Kartenbrowser und von Formularfragen.

   var draw = MapDraw.create(map, { single: false, color: '#d62828', onChange: fn(features), onSketch: fn(info) });
   draw.start('line'|'polygon'|'point'), draw.finish(), draw.cancel(), draw.undo(), draw.features(),
   draw.setFeatures(list), draw.remove(id), draw.select(id), draw.update(id, props), draw.measure(feature) */
(function () {
  'use strict';
  var uid = function () { return Math.random().toString(16).slice(2, 10); };
  var COLORS = ['#d62828', '#1f5fa8', '#2a9d8f', '#e76f51', '#7b2cbf', '#f4a261', '#264653'];

  function measure(f) {
    var g = f.geometry, out = { length: 0, area: 0, points: 0 };
    if (!g) { return out; }
    var c = g.type === 'Polygon' ? g.coordinates[0].slice(0, -1) : g.type === 'LineString' ? g.coordinates : [g.coordinates];
    out.points = c.length;
    for (var i = 1; i < c.length; i++) { out.length += MapKit.haversine(c[i - 1], c[i]); }
    if (g.type === 'Polygon' && c.length > 2) {
      out.length += MapKit.haversine(c[c.length - 1], c[0]);
      out.area = Math.max(0, MapKit.ringArea(c) - g.coordinates.slice(1).reduce(function(sum,ring){return sum + MapKit.ringArea(ring.slice(0,-1));},0));
    }
    return out;
  }
  function describe(f) {
    var m = measure(f), g = f.geometry;
    if (!g) { return ''; }
    if (g.type === 'Point') { return g.coordinates[1].toFixed(6) + ', ' + g.coordinates[0].toFixed(6); }
    if (g.type === 'LineString') { return 'Länge ' + MapKit.fmtLen(m.length) + ' · ' + m.points + ' Punkte'; }
    return (f.properties && f.properties.shape === 'circle' ? 'Radius ' + MapKit.fmtLen(f.properties.radius_m) + ' · ' : '') + 'Fläche ' + MapKit.fmtArea(m.area) + ' · Umfang ' + MapKit.fmtLen(m.length);
  }
  function verticesOf(g) {
    return g.type === 'Polygon' ? g.coordinates[0].slice(0, -1) : g.type === 'LineString' ? g.coordinates : [g.coordinates];
  }
  function geometry(mode, pts) {
    if (mode === 'point' || mode === 'text') { return { type: 'Point', coordinates: pts[0] }; }
    if (mode === 'line') { return { type: 'LineString', coordinates: pts.slice() }; }
    if (mode === 'rectangle') {
      var a=pts[0], b=pts[pts.length-1];
      return {type:'Polygon',coordinates:[[a,[b[0],a[1]],b,[a[0],b[1]],a]]};
    }
    if (mode === 'circle') return circleGeometry(pts[0], MapKit.haversine(pts[0],pts[pts.length-1]));
    return { type: 'Polygon', coordinates: [pts.concat([pts[0]])] };
  }
  function circleGeometry(center, meters) {
    var radius=meters/6371008.8, ring=[];
    var lat=center[1]*Math.PI/180, lon=center[0]*Math.PI/180;
    for(var i=0;i<96;i++){
      var bearing=i/96*2*Math.PI;
      var phi=Math.asin(Math.sin(lat)*Math.cos(radius)+Math.cos(lat)*Math.sin(radius)*Math.cos(bearing));
      var lam=lon+Math.atan2(Math.sin(bearing)*Math.sin(radius)*Math.cos(lat),Math.cos(radius)-Math.sin(lat)*Math.sin(phi));
      ring.push([((lam*180/Math.PI+540)%360)-180,phi*180/Math.PI]);
    }
    ring.push(ring[0].slice());
    return {type:'Polygon',coordinates:[ring]};
  }
  function linesOf(g) {
    if (g.type==='Point') return [[g.coordinates]];
    if (g.type==='LineString') return [g.coordinates];
    if (g.type==='Polygon') return g.coordinates;
    if (g.type==='MultiPolygon') return g.coordinates.flat();
    return [];
  }
  var MIN = { point: 1, text:1, line: 2, polygon: 3, rectangle:2, circle:2 };

  function create(map, opts) {
    opts = opts || {};
    var feats = [], mode = null, pts = [], hover = null, selected = null, drag = null, lastClick = 0, lastPt = null;
    var history=['[]'], future=[], restoring=false, snapping=false, labelMarkers=[];
    function snap(p, screen) {
      if (!snapping) return p;
      var best=12, result=p, budget=8000;
      var candidates=feats.filter(function(f){return !drag || f.id!==selected;});
      if(opts.snapFeatures)candidates=candidates.concat(opts.snapFeatures());
      function check(point, coordinates) {
        var distance=Math.hypot(point.x-screen.x,point.y-screen.y);
        if(distance>=best)return;
        best=distance;
        result=coordinates ? coordinates.slice() : map.unproject([point.x,point.y]).toArray();
      }
      candidates.some(function(feature){
        if (!feature.geometry) return false;
        return linesOf(feature.geometry).some(function(line){
          var previous;
          return line.some(function(coordinates){
            if(budget--<=0)return true;
            var point=map.project(coordinates);
            check(point, coordinates);
            if(previous){
              var dx=point.x-previous.x, dy=point.y-previous.y, length2=dx*dx+dy*dy;
              if(length2){
                var t=Math.max(0,Math.min(1,((screen.x-previous.x)*dx+(screen.y-previous.y)*dy)/length2));
                check({x:previous.x+t*dx,y:previous.y+t*dy});
              }
            }
            previous=point;
            return false;
          });
        });
      });
      return result;
    }
    var src = 'draw-' + uid();
    var L = { fill: src + '-fill', line: src + '-line', pt: src + '-pt', vx: src + '-vx', sk: src + '-sk', skpt: src + '-skpt' };

    function fc(list) { return { type: 'FeatureCollection', features: list }; }
    function data() {
      return fc(feats.map(function (f) {
        return { type: 'Feature', id: f.id, geometry: f.geometry, properties: { id: f.id, color: f.properties.color || COLORS[0], sel: f.id === selected ? 1 : 0 } };
      }));
    }
    function sketchData() {
      var list = [], all = hover ? pts.concat([hover]) : pts;
      if (mode && all.length > 1) {
        list.push({ type: 'Feature', geometry: ((mode === 'polygon' && all.length > 2) || mode==='circle' || mode==='rectangle') ? geometry(mode, all) : { type: 'LineString', coordinates: all }, properties: {} });
      }
      pts.forEach(function (p, i) { list.push({ type: 'Feature', geometry: { type: 'Point', coordinates: p }, properties: { first: i === 0 ? 1 : 0 } }); });
      var f = selected && byId(selected);
      if (f && !mode && !(f.properties && f.properties.shape==='circle')) {
        verticesOf(f.geometry).forEach(function (p, i) { list.push({ type: 'Feature', geometry: { type: 'Point', coordinates: p }, properties: { vx: i, color: f.properties.color } }); });
      }
      return fc(list);
    }
    function byId(id) { return feats.filter(function (f) { return f.id === id; })[0]; }
    function ensure() {
      if (!map.getSource(src)) {
        map.addSource(src, { type: 'geojson', data: data() });
        map.addSource(src + '-s', { type: 'geojson', data: sketchData() });
        var color = ['get', 'color'];
        map.addLayer({ id: L.fill, type: 'fill', source: src, filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': color, 'fill-opacity': ['case', ['==', ['get', 'sel'], 1], 0.3, 0.18] } });
        map.addLayer({ id: L.line, type: 'line', source: src, filter: ['!=', ['geometry-type'], 'Point'], layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': color, 'line-width': ['case', ['==', ['get', 'sel'], 1], 4, 3] } });
        map.addLayer({ id: L.pt, type: 'circle', source: src, filter: ['==', ['geometry-type'], 'Point'],
          paint: { 'circle-radius': ['case', ['==', ['get', 'sel'], 1], 8, 6.5], 'circle-color': color, 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } });
        map.addLayer({ id: L.sk, type: 'line', source: src + '-s', filter: ['!=', ['geometry-type'], 'Point'], paint: { 'line-color': opts.color || '#1f5fa8', 'line-width': 2.5, 'line-dasharray': [2, 1] } });
        map.addLayer({ id: L.skpt, type: 'circle', source: src + '-s', filter: ['all', ['==', ['geometry-type'], 'Point'], ['!', ['has', 'vx']]],
          paint: { 'circle-radius': ['case', ['==', ['get', 'first'], 1], 7, 5], 'circle-color': '#fff', 'circle-stroke-color': opts.color || '#1f5fa8', 'circle-stroke-width': 2.5 } });
        map.addLayer({ id: L.vx, type: 'circle', source: src + '-s', filter: ['has', 'vx'],
          paint: { 'circle-radius': 6, 'circle-color': '#fff', 'circle-stroke-color': ['get', 'color'], 'circle-stroke-width': 3 } });
      }
    }
    function refresh() {
      if (!map.isStyleLoaded() && !map.getSource(src)) { return; }
      ensure();
      map.getSource(src).setData(data());
      map.getSource(src + '-s').setData(sketchData());
      labelMarkers.forEach(function(m){m.remove();});labelMarkers=[];
      if(opts.labels)feats.filter(function(f){return f.properties.name;}).slice(0,150).forEach(function(f){
        var el=document.createElement('span');el.className='map-drawing-label';el.textContent=f.properties.name;
        labelMarkers.push(new maplibregl.Marker({element:el,anchor:'bottom',offset:[0,-10]}).setLngLat(verticesOf(f.geometry)[0]).addTo(map));
      });
    }
    function changed() {
      if(!restoring){var snapshot=JSON.stringify(feats);if(snapshot!==history[history.length-1]){history.push(snapshot);if(history.length>60)history.shift();future=[];}}
      refresh(); if (opts.onChange) { opts.onChange(api.features()); }
    }
    function sketch() {
      refresh();
      if (!opts.onSketch) { return; }
      if (!mode) { opts.onSketch(null); return; }
      var all = hover ? pts.concat([hover]) : pts;
      var info = { mode: mode, count: pts.length, min: MIN[mode], text: '' };
      if (all.length >= 2 && mode !== 'point') { info.text = describe({ geometry: ((mode === 'polygon' && all.length > 2)||mode==='circle'||mode==='rectangle') ? geometry(mode, all) : { type: 'LineString', coordinates: all }, properties:mode==='circle'?{shape:'circle',radius_m:MapKit.haversine(all[0],all[all.length-1])}:{} }); }
      opts.onSketch(info);
    }

    if (map.isStyleLoaded()) { ensure(); }
    map.on('load', refresh);
    map.on('style.load', function () { refresh(); });   // nach Wechsel der Grundkarte neu anlegen

    function finish() {
      if (!mode) { return null; }
      var m = mode, done = null;
      if (pts.length >= MIN[m] && (opts.single||feats.length<500)) {
        if (opts.single) { feats = []; }
        done = { id: uid(), type: 'Feature', geometry: geometry(m, pts), properties: { name: m==='text'?'Beschriftung':'', color: opts.color || COLORS[feats.length % COLORS.length], kind: m==='text'?'point':(m==='circle'||m==='rectangle')?'polygon':m, shape:m } };
        if(m==='circle')done.properties.radius_m=MapKit.haversine(pts[0],pts[1]);
        feats.push(done);
        selected = done.id;
      }
      mode = null; pts = []; hover = null;
      map.getCanvas().style.cursor = '';
      map.doubleClickZoom.enable();
      changed(); sketch();
      if (opts.onFinish) { opts.onFinish(done); }
      return done;
    }

    map.on('click', function (ev) {
      if (drag && drag.moved) { return; }
      if (mode) {
        var now = Date.now(), p = snap([ev.lngLat.lng, ev.lngLat.lat],ev.point);
        var near = lastPt && Math.hypot(lastPt.x - ev.point.x, lastPt.y - ev.point.y) < 8;
        if (now - lastClick < 400 && near && pts.length >= MIN[mode]) { lastClick = 0; finish(); return; }   // Doppelklick beendet
        lastClick = now; lastPt = ev.point;
        // Klick auf den ersten Punkt schließt die Fläche
        if (mode === 'polygon' && pts.length >= 3) {
          var first = map.project(pts[0]);
          if (Math.hypot(first.x - ev.point.x, first.y - ev.point.y) < 12) { finish(); return; }
        }
        pts.push(p);
        if (mode === 'point' || mode==='text' || ((mode==='rectangle'||mode==='circle')&&pts.length===2)) { finish(); return; }
        sketch();
        return;
      }
      var hit = map.queryRenderedFeatures(ev.point, { layers: [L.pt, L.line, L.fill].filter(function (id) { return map.getLayer(id); }) });
      var id = hit.length ? hit[0].properties.id : null;
      if (id || selected) { api.select(id); }
    });
    map.on('mousemove', function (ev) {
      if (drag) { return; }
      if (mode) { hover = snap([ev.lngLat.lng, ev.lngLat.lat],ev.point); sketch(); return; }
      if (selected && map.getLayer(L.vx)) {
        var over = map.queryRenderedFeatures(ev.point, { layers: [L.vx] }).length;
        map.getCanvas().style.cursor = over ? 'move' : '';
      }
    });
    function startDrag(ev) {
      if (mode || !selected || !map.getLayer(L.vx) || (byId(selected).properties || {}).parcel) { return; }
      var hit = map.queryRenderedFeatures(ev.point, { layers: [L.vx] });
      if (!hit.length) { return; }
      ev.preventDefault();
      drag = { index: hit[0].properties.vx, moved: false };
      map.dragPan.disable();
    }
    function moveDrag(ev) {
      if (!drag) { return; }
      var f = byId(selected), p = snap([ev.lngLat.lng, ev.lngLat.lat],ev.point), g = f.geometry;
      if (f.properties.shape==='rectangle') delete f.properties.shape;
      drag.moved = true;
      if (g.type === 'Point') { g.coordinates = p; }
      else if (g.type === 'LineString') { g.coordinates[drag.index] = p; }
      else {
        g.coordinates[0][drag.index] = p;
        if (drag.index === 0) { g.coordinates[0][g.coordinates[0].length - 1] = p; }
      }
      refresh();
    }
    function endDrag() {
      if (!drag) { return; }
      var moved = drag.moved;
      map.dragPan.enable();
      setTimeout(function () { drag = null; }, 0);
      if (moved) { changed(); }
    }
    map.on('mousedown', startDrag);
    map.on('touchstart', function (ev) { if (ev.points && ev.points.length === 1) { startDrag(ev); } });
    map.on('mousemove', moveDrag);
    map.on('touchmove', moveDrag);
    map.on('mouseup', endDrag);
    map.on('touchend', endDrag);
    document.addEventListener('keydown', function (ev) {
      if (!mode || /INPUT|TEXTAREA|SELECT/.test((ev.target || {}).tagName || '')) { return; }
      if (ev.key === 'Escape') { api.cancel(); }
      if (ev.key === 'Enter') { finish(); }
      if (ev.key === 'Backspace') { ev.preventDefault(); api.undo(); }
    });

    var api = {
      start: function (m) {
        if(!MIN[m])return;
        api.cancel();
        mode = m; pts = []; hover = null; selected = null;
        map.getCanvas().style.cursor = 'crosshair';
        map.doubleClickZoom.disable();
        sketch(); refresh();
      },
      mode: function () { return mode; },
      finish: finish,
      cancel: function () {
        if (!mode) { return; }
        mode = null; pts = []; hover = null;
        map.getCanvas().style.cursor = '';
        map.doubleClickZoom.enable();
        sketch();
      },
      undo: function () { if(mode){if(pts.length)pts.pop();sketch();return;}if(history.length<2)return;future.push(history.pop());feats=JSON.parse(history[history.length-1]);selected=byId(selected)?selected:null;restoring=true;changed();restoring=false;sketch(); },
      redo: function () { if(mode||!future.length)return;var next=future.pop();history.push(next);feats=JSON.parse(next);selected=byId(selected)?selected:null;restoring=true;changed();restoring=false;sketch(); },
      canUndo: function(){return mode?pts.length>0:history.length>1;},
      canRedo: function(){return !mode&&future.length>0;},
      resetHistory:function(){history=[JSON.stringify(feats)];future=[];},
      setSnapping:function(value){snapping=!!value;},
      bufferPoint: function(id, meters) {
        var point=byId(id);
        if(!point || point.geometry.type!=='Point' || !Number.isFinite(meters) || meters<1 || meters>1000000 || feats.length>=500) return null;
        var zone={id:uid(),type:'Feature',geometry:circleGeometry(point.geometry.coordinates,meters),
          properties:{name:('Umkreis · '+(point.properties.name||'Punkt')).slice(0,200),color:point.properties.color||COLORS[0],kind:'polygon',shape:'circle',radius_m:meters}};
        feats.push(zone);selected=zone.id;changed();return zone.id;
      },
      duplicate:function(id){var f=byId(id);if(!f||feats.length>=500)return;var copy=JSON.parse(JSON.stringify(f));copy.id=uid();copy.properties.name=(copy.properties.name||'Zeichnung')+' (Kopie)';feats.push(copy);selected=copy.id;changed();return copy.id;},
      addPoint: function (lngLat) {   // z. B. aktueller GPS-Standort als nächster Stützpunkt
        if (!mode) { return; }
        pts.push(lngLat);
        if (mode === 'point'||mode==='text'||((mode==='rectangle'||mode==='circle')&&pts.length===2)) { finish(); } else { sketch(); }
      },
      features: function () { return feats.map(function (f) { return JSON.parse(JSON.stringify(f)); }); },
      setFeatures: function (list) {
        feats = (list || []).filter(function (f) { return f && f.geometry; }).map(function (f) {
          var c = JSON.parse(JSON.stringify(f));
          c.id = c.id || (c.properties && c.properties.id) || uid();
          c.type = 'Feature';
          c.properties = c.properties || {};
          return c;
        });
        selected = null;
        changed();
      },
      remove: function (id) { feats = feats.filter(function (f) { return f.id !== id; }); if (selected === id) { selected = null; } changed(); sketch(); },
      clear: function () { feats = []; selected = null; changed(); sketch(); },
      update: function (id, props) { var f = byId(id); if (f) { Object.assign(f.properties, props); changed(); } },
      select: function (id) {
        selected = id && byId(id) ? id : null;
        refresh();
        if (opts.onSelect) { opts.onSelect(selected); }
      },
      selected: function () { return selected; },
      zoomTo: function (id) {
        var f = byId(id);
        if (!f) { return; }
        var c = verticesOf(f.geometry);
        if (c.length === 1) { map.flyTo({ center: c[0], zoom: Math.max(map.getZoom(), 16) }); return; }
        var b = new maplibregl.LngLatBounds(c[0], c[0]);
        c.forEach(function (p) { b.extend(p); });
        map.fitBounds(b, { padding: 60, maxZoom: 18 });
      },
      layerIds: function () { return [L.fill, L.line, L.pt]; }
    };
    return api;
  }

  function validFeature(f){
    if(!f||!f.geometry)return false;
    var g=f.geometry,c=g.coordinates,count=0;
    function point(p){return Array.isArray(p)&&p.length>=2&&typeof p[0]==='number'&&typeof p[1]==='number'&&Number.isFinite(p[0])&&Number.isFinite(p[1])&&Math.abs(p[0])<=180&&Math.abs(p[1])<=85.051129;}
    function line(list,min){if(!Array.isArray(list)||list.length<min)return false;count+=list.length;return count<=5000&&list.every(point);}
    return g.type==='Point'?point(c):g.type==='LineString'?line(c,2):g.type==='Polygon'&&Array.isArray(c)&&c.length>0&&c.every(function(r){return line(r,4)&&r[0][0]===r[r.length-1][0]&&r[0][1]===r[r.length-1][1];});
  }
  window.MapDraw = { create: create, measure: measure, describe: describe, COLORS: COLORS, validFeature:validFeature };
})();
