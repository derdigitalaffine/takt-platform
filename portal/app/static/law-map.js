const bundle = JSON.parse(document.getElementById('map-bundle').textContent);
const kit = MapKit.create('law-area-map', bundle, {});
const field = document.getElementById('law-area-json');
const status = document.getElementById('law-area-status');
const draw = MapDraw.create(kit.map, {single:true, onChange(features) {
  field.value = features.length ? JSON.stringify(features[0].geometry) : '';
  field.dispatchEvent(new Event('input', {bubbles:true}));
}, onSketch(info) {status.textContent = info ? 'Eckpunkte setzen · Doppelklick oder „Fläche abschließen“ beendet.' : 'Fläche auswählen, um Stützpunkte zu verschieben.';}});
kit.map.addControl(new maplibregl.NavigationControl(), 'top-right');
try {const geometry = JSON.parse(field.value); if (geometry?.type==='Polygon') {draw.setFeatures([{geometry,properties:{color:'#1f5fa8'}}]);kit.map.once('load',()=>{const feature=draw.features()[0];if(feature)draw.zoomTo(feature.id);});}} catch (_) {}
document.getElementById('law-area-draw').onclick=()=>draw.start('polygon');
document.getElementById('law-area-finish').onclick=()=>draw.finish();
document.getElementById('law-area-cancel').onclick=()=>draw.cancel();
document.getElementById('law-area-clear').onclick=()=>draw.clear();
