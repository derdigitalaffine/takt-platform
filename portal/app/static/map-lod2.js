/* Opt-in native LoD2 geometry for TAKT Maps.
 * WebGL custom layer draws triangulated roof and wall faces from a bounded
 * locally imported CityGML excerpt. No upstream requests or third-party JS.
 * This is a local flat-terrain PREVIEW, not a nationwide DGM/3D Tiles viewer. */
(function () {
  'use strict';
  var started = false;
  function boot() {
    if (started || !window.MapWorkspace || !window.maplibregl) return;
    started = true;
    var map = window.MapWorkspace.map;
    var button = document.getElementById('map-lod2-toggle');
    var info = document.getElementById('map-lod2-info');
    if (!button || !info) return;
    var active = false, mesh = null, loading = false;
    var layerId = 'takt-lod2-preview-mesh';

    function say(message) { info.textContent = message; }
    function hasLayer() { return !!map.getLayer(layerId); }
    function remove() {
      active = false;
      if (hasLayer()) map.removeLayer(layerId);
      button.setAttribute('aria-pressed', 'false');
      button.classList.remove('btn-primary');
      button.classList.add('btn-outline-secondary');
      say('3D-Dachmodell ausgeblendet. Die Kartenebenen bleiben unverändert.');
    }

    function meshLayer(data) {
      return {
        id: layerId, type: 'custom', renderingMode: '3d',
        onAdd: function (_, gl) {
          var vertexSource = [
            'precision highp float;',
            'attribute vec3 a_position;', 'attribute float a_kind;',
            'uniform mat4 u_matrix;', 'varying float v_kind;',
            'void main() { v_kind = a_kind; gl_Position = u_matrix * vec4(a_position, 1.0); }'
          ].join('\n');
          var fragmentSource = [
            'precision mediump float;', 'varying float v_kind;',
            'void main() {',
            '  vec3 roof = vec3(0.75, 0.26, 0.18);',
            '  vec3 wall = vec3(0.76, 0.78, 0.79);',
            '  gl_FragColor = vec4(mix(wall, roof, step(0.5, v_kind)), 0.95);',
            '}'
          ].join('\n');

          function shader(type, source) {
            var result = gl.createShader(type);
            gl.shaderSource(result, source);
            gl.compileShader(result);
            if (!gl.getShaderParameter(result, gl.COMPILE_STATUS)) {
              var message = gl.getShaderInfoLog(result);
              gl.deleteShader(result);
              throw Error('3D-Shader nicht verfügbar: ' + message);
            }
            return result;
          }
          var vert = shader(gl.VERTEX_SHADER, vertexSource);
          var frag = shader(gl.FRAGMENT_SHADER, fragmentSource);
          var program = gl.createProgram();
          gl.attachShader(program, vert);
          gl.attachShader(program, frag);
          gl.linkProgram(program);
          gl.deleteShader(vert);
          gl.deleteShader(frag);
          if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
            var message = gl.getProgramInfoLog(program);
            gl.deleteProgram(program);
            throw Error('3D-Shader-Verknüpfung fehlgeschlagen: ' + message);
          }
          this.program = program;
          this.posAttr = gl.getAttribLocation(program, 'a_position');
          this.kindAttr = gl.getAttribLocation(program, 'a_kind');
          this.matrixUniform = gl.getUniformLocation(program, 'u_matrix');
          var positions = new Float32Array(data.vertices.length * 4);
          data.vertices.forEach(function (v, i) {
            var m = maplibregl.MercatorCoordinate.fromLngLat(
              {lng: v[0], lat: v[1]}, v[2]);
            positions.set([m.x, m.y, m.z, v[3]], i * 4);
          });
          this.count = data.vertices.length;
          this.buffer = gl.createBuffer();
          gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
          gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
        },
        render: function (gl, args) {
          if (!this.program || !this.buffer) return;
          // Standard Mercator matrix: this simple preview does not support
          // globe projection or a terrain height correction.
          var projection = args && args.defaultProjectionData;
          if (!projection || !projection.mainMatrix) return;
          gl.useProgram(this.program);
          gl.uniformMatrix4fv(this.matrixUniform, false, projection.mainMatrix);
          gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
          gl.enableVertexAttribArray(this.posAttr);
          gl.vertexAttribPointer(this.posAttr, 3, gl.FLOAT, false, 16, 0);
          gl.enableVertexAttribArray(this.kindAttr);
          gl.vertexAttribPointer(this.kindAttr, 1, gl.FLOAT, false, 16, 12);
          gl.enable(gl.DEPTH_TEST);
          gl.enable(gl.BLEND);
          gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
          gl.drawArrays(gl.TRIANGLES, 0, this.count);
        },
        onRemove: function (_, gl) {
          if (this.buffer) gl.deleteBuffer(this.buffer);
          if (this.program) gl.deleteProgram(this.program);
          this.buffer = null;
          this.program = null;
        }
      };
    }

    function validate(data) {
      if (!data || data.format !== 'takt-lod2-mesh/1'
          || !Array.isArray(data.vertices)
          || data.vertices.length === 0
          || data.vertices.length > 48000
          || data.vertices.length % 3) return false;
      return data.vertices.every(function (v) {
        return Array.isArray(v) && v.length === 4
          && v.every(Number.isFinite)
          && v[0] >= -180 && v[0] <= 180
          && v[1] >= -85 && v[1] <= 85
          && v[2] >= 0 && v[2] <= 2100
          && (v[3] === 0 || v[3] === 1);
      });
    }

    function add() {
      if (!active || !mesh || hasLayer()) return;
      try {
        if (map.isStyleLoaded()) map.addLayer(meshLayer(mesh));
      } catch (_) {
        active = false;
        say('3D-Renderer konnte nicht gestartet werden. Bitte die Karte neu laden.');
        button.setAttribute('aria-pressed', 'false');
      }
    }
    map.on('style.load', add);

    function turnOn() {
      if (loading) return;
      loading = true;
      button.disabled = true;
      say('Gebäudedächer werden geladen …');
      var promise = mesh ? Promise.resolve(mesh) : fetch('/maps/lod2/mesh', {
        credentials: 'same-origin', headers: {Accept: 'application/json'}
      }).then(function (response) {
        if (!response.ok) throw Error('Das LoD2-Modell ist derzeit nicht verfügbar.');
        return response.json();
      });
      promise.then(function (data) {
        if (!validate(data)) throw Error('Die importierten 3D-Geometrien sind ungültig.');
        mesh = data;
        active = true;
        if (typeof map.setProjection === 'function') map.setProjection({type:'mercator'});
        add();
        if (!hasLayer() && map.isStyleLoaded())
          throw Error('3D-Schicht konnte nicht aufgebaut werden.');
        button.classList.remove('btn-outline-secondary');
        button.classList.add('btn-primary');
        button.setAttribute('aria-pressed', 'true');
        if (Array.isArray(data.bbox) && data.bbox.length === 4
            && data.bbox.every(Number.isFinite)) {
          map.fitBounds([[data.bbox[0], data.bbox[1]],
                         [data.bbox[2], data.bbox[3]]], {
            padding: 70, maxZoom: 18, duration: 650
          });
        }
        if (map.getPitch() < 15) map.easeTo({pitch:55, duration:500});
        say(data.roof_polygons + ' Dachflächen · '
            + data.wall_polygons + ' Wandflächen · '
            + data.skipped_polygons + ' ausgelassen. '
            + 'Lokale Vorschau ohne DGM-Höhenabgleich.');
      }).catch(function (error) {
        active = false;
        say(error.message || '3D-Gebäude konnten nicht geladen werden.');
      }).finally(function () {
        loading = false;
        button.disabled = false;
      });
    }

    button.addEventListener('click', function () {
      if (active) remove();
      else turnOn();
    });
    fetch('/maps/lod2/status', {credentials:'same-origin'}).then(function (r) {
      if (!r.ok) throw Error();
      return r.json();
    }).then(function (data) {
      if (!data.available) {
        button.disabled = true;
        say('Noch kein örtlicher LoD2-CityGML-Ausschnitt importiert.');
        return;
      }
      button.disabled = false;
      say('Amtliches LoD2-Modell verfügbar: '
          + data.roof_polygons + ' Dachflächen. '
          + 'Import vom ' + String(data.imported_at || '').slice(0,10)
          + '. Manuelle 3D-Vorschau, keine amtliche Höhenanalyse.');
    }).catch(function () {
      button.disabled = true;
      say('3D-Modellstatus derzeit nicht verfügbar.');
    });
  }

  window.addEventListener('map-workbench-ready', boot);
  if (document.readyState !== 'loading') boot();
  else document.addEventListener('DOMContentLoaded', boot);
})();
