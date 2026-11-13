/* Fast, dependency-free client regression for the opt-in LoD2 + DGM renderer.
   Run with: node tests/test_map_dgm_client.js */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(
  path.join(__dirname, '../app/static/map-lod2.js'), 'utf8');

function environment(stale) {
  const elements = {};
  const layers = {};
  const listeners = {};
  const meshes = [];
  let removed = 0;

  function element(id) {
    return (elements[id] ||= {
      id, disabled: true, checked: false, textContent: '',
      attrs: {}, handlers: {},
      setAttribute(k, v) { this.attrs[k] = v; },
      addEventListener(k, fn) { this.handlers[k] = fn; },
      classList: {add() {}, remove() {}}
    });
  }

  const gl = {
    VERTEX_SHADER: 1, FRAGMENT_SHADER: 2, COMPILE_STATUS: 3, LINK_STATUS: 4,
    ARRAY_BUFFER: 5, STATIC_DRAW: 6, FLOAT: 7, DEPTH_TEST: 8, BLEND: 9,
    SRC_ALPHA: 10, ONE_MINUS_SRC_ALPHA: 11, TRIANGLES: 12,
    createShader() { return {}; }, shaderSource() {}, compileShader() {},
    getShaderParameter() { return true; }, getShaderInfoLog() { return ''; },
    deleteShader() {}, createProgram() { return {}; }, attachShader() {},
    linkProgram() {}, getProgramParameter() { return true; },
    getProgramInfoLog() { return ''; }, deleteProgram() {}, useProgram() {},
    getAttribLocation(_, name) { return name === 'a_position' ? 0 : 1; },
    getUniformLocation() { return {}; }, uniformMatrix4fv() {},
    createBuffer() { return {}; }, bindBuffer() {},
    bufferData(_, positions) { meshes.push(Array.from(positions)); },
    enableVertexAttribArray() {}, vertexAttribPointer() {},
    enable() {}, blendFunc() {}, drawArrays() {},
    deleteBuffer() {}
  };
  const map = {
    getLayer(id) { return layers[id]; },
    addLayer(layer) { layers[layer.id] = layer; layer.onAdd(map, gl); },
    removeLayer(id) { const layer = layers[id]; if (layer) layer.onRemove(map, gl); delete layers[id]; removed++; },
    isStyleLoaded() { return true; },
    on(name, fn) { listeners[name] = fn; },
    getPitch() { return 0; }, setProjection() {}, fitBounds() {}, easeTo() {}
  };
  const sha = 'a'.repeat(64);
  const model = {
    format:'takt-lod2-mesh/1',
    vertices:[[7.70,49.50,0,1], [7.71,49.50,4,1], [7.70,49.51,4,1]],
    sha256:sha, height_origin_m:104, roof_polygons:1, wall_polygons:1,
    skipped_polygons:0, bbox:[7.70,49.50,7.71,49.51]
  };
  const dgm = {
    format:'takt-dgm-mesh/1',
    vertices:[[7.70,49.50,-1,2], [7.71,49.50,2,2], [7.70,49.51,0,2]],
    loD2_sha256:stale ? 'b'.repeat(64) : sha,
    height_origin_m:104, min_height_relative_m:-1,
    triangles:1, grid_spacing_m:5, skipped_cells:0
  };
  const urls = [];
  async function fetchMock(url) {
    urls.push(url);
    return {
      ok: true, async json() {
        if (url === '/maps/lod2/status') return {available:true, roof_polygons:1, imported_at:'2026-11-13'};
        if (url === '/maps/dgm/status') return {available:true, grid_spacing_m:5, triangles:1};
        if (url === '/maps/lod2/mesh') return model;
        if (url === '/maps/dgm/mesh') return dgm;
        throw Error('Unexpected network request: '+url);
      }
    };
  }
  const maplibregl = {
    MercatorCoordinate: {
      fromLngLat(point, height=0) {
        return {x: (point.lng+180)/360, y: (90-point.lat)/180, z: height/40075016.69};
      }
    }
  };
  const win = {
    MapWorkspace:{map}, maplibregl, addEventListener() {}
  };
  const doc = {
    readyState:'complete', getElementById:element, addEventListener() {}
  };
  vm.runInNewContext(script, {
    window:win, document:doc, maplibregl, fetch:fetchMock,
    Promise, Number, Float32Array
  }, {filename:'map-lod2.js'});
  return {layers, elements, element, listeners, meshes, urls, removedCount:()=>removed};
}

async function settle() {
  for (let i=0; i<24; i++) await Promise.resolve();
}

(async function run() {
  const t = environment(false);
  await settle();
  const building = t.element('map-lod2-toggle');
  const toggle = t.element('map-dgm-toggle');
  assert.equal(building.disabled, false);
  assert.equal(toggle.disabled, true, 'Terrain requires explicit LoD2 activation.');
  assert.deepEqual(t.urls.sort(), ['/maps/dgm/status','/maps/lod2/status']);
  building.handlers.click();
  await settle();
  assert.deepEqual(Object.keys(t.layers), ['takt-lod2-preview-mesh']);
  assert.equal(toggle.disabled, false);
  assert.equal(building.attrs['aria-pressed'], 'true');
  toggle.checked = true;
  toggle.handlers.change();
  await settle();
  assert.deepEqual(Object.keys(t.layers), ['takt-dgm-relief-mesh','takt-lod2-preview-mesh']);
  assert.equal(t.element('map-dgm-info').textContent.includes('Geländedreiecke'), true);
  assert.equal(t.meshes.length >= 3, true);
  // After terrain appears, both buildings and terrain are lifted together
  // if the negative DGM relative height would be hidden under the base raster.
  const terrainPositions = t.meshes[t.meshes.length - 2];
  const buildingPositions = t.meshes[t.meshes.length - 1];
  assert.equal(terrainPositions[2] > 0, true);
  assert.equal(buildingPositions[2] > terrainPositions[2], true);
  toggle.checked = false;
  toggle.handlers.change();
  assert.deepEqual(Object.keys(t.layers), ['takt-lod2-preview-mesh']);
  building.handlers.click();
  assert.deepEqual(Object.keys(t.layers), []);
  assert.equal(toggle.disabled, true);

  const stale = environment(true);
  await settle();
  stale.element('map-lod2-toggle').handlers.click();
  await settle();
  const wrong = stale.element('map-dgm-toggle');
  wrong.checked = true;
  wrong.handlers.change();
  await settle();
  assert.equal(wrong.checked, false);
  assert.equal(Object.keys(stale.layers).length, 1);
  assert.equal(stale.element('map-dgm-info').textContent.includes('gehören nicht'), true);
  console.log('MapLibre LoD2 and DGM client lifecycle, relative relief and stale hash protection passed.');
})().catch(error => {console.error(error);process.exitCode=1;});
