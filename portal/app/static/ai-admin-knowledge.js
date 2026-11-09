/* TAKT KI-Wissensverwaltung: Live-Status und lokale Listenfilterung. */
(function () {
  'use strict';
  var lawFilter = document.querySelector('[data-ai-filter-laws]');
  if (lawFilter) {
    var lawEntries = Array.prototype.slice.call(document.querySelectorAll('[data-ai-law-entry]'));
    lawFilter.addEventListener('input', function () {
      var term = lawFilter.value.trim().toLocaleLowerCase('de');
      lawEntries.forEach(function (entry) {
        entry.hidden = !!term && !entry.textContent.toLocaleLowerCase('de').includes(term);
        // Bootstrap grid/list styles may override [hidden].
        entry.style.display = entry.hidden ? 'none' : '';
      });
    });
  }

  var overview = document.querySelector('[data-ai-index-overview]');
  if (!overview) return;

  var button = overview.querySelector('[data-ai-index-refresh]');
  var loading = false;
  var numberFields = {
    '[data-ai-index-ready]': 'ready',
    '[data-ai-index-total]': 'total',
    '[data-ai-index-missing]': 'missing',
    '[data-ai-index-vectors]': 'vectors',
    '[data-ai-index-qdrant]': 'qdrant',
    '[data-ai-index-chunks-ready]': 'chunks_ready',
    '[data-ai-index-chunks-total]': 'chunks_total'
  };

  function refresh() {
    if (loading || document.hidden) return;
    loading = true;
    if (button) button.disabled = true;
    fetch('/admin/ai/index/status', { credentials: 'same-origin', cache: 'no-store' })
      .then(function (response) {
        if (!response.ok) throw new Error('Status konnte nicht aktualisiert werden');
        return response.json();
      })
      .then(function (data) {
        Object.keys(numberFields).forEach(function (selector) {
          var el = document.querySelector(selector);
          if (el && data[numberFields[selector]] !== undefined) {
            el.textContent = String(data[numberFields[selector]]);
          }
        });
        var model = document.querySelector('[data-ai-index-model]');
        if (model) model.textContent = data.active ?
          data.provider + ' · ' + data.model : 'Nicht konfiguriert';
        [['pending', 'pending'], ['running', 'running'], ['failed', 'failed']].forEach(function (pair) {
          var el = document.querySelector('[data-ai-index-' + pair[0] + ']');
          if (el && data.jobs) el.textContent = String(data.jobs[pair[1]] || 0);
        });
        var progress = Number(data.percent);
        progress = Number.isFinite(progress) ? Math.max(0, Math.min(100, Math.round(progress))) : 0;
        var progressLabel = document.querySelector('[data-ai-index-percent]');
        var progressBar = document.querySelector('[data-ai-index-progressbar]');
        var progressFill = document.querySelector('[data-ai-index-progress-fill]');
        if (progressLabel) progressLabel.textContent = progress + ' %';
        if (progressBar) progressBar.setAttribute('aria-valuenow', String(progress));
        if (progressFill) progressFill.style.width = progress + '%';
        var lastCheck = document.querySelector('[data-ai-index-last-check]');
        if (lastCheck) lastCheck.textContent = 'Stand ' + new Date().toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
        var refreshError = document.querySelector('[data-ai-index-refresh-error]');
        if (refreshError) refreshError.textContent = '';
        if (data.documents && typeof data.documents === 'object') {
          document.querySelectorAll('[data-ai-index-doc]').forEach(function (el) {
            var value = data.documents[el.getAttribute('data-ai-index-doc')];
            if (!value || typeof value.label !== 'string') return;
            el.textContent = value.label;
            var allowed = ['success', 'secondary', 'warning', 'danger'];
            el.className = 'badge text-bg-' +
              (allowed.indexOf(value.color) !== -1 ? value.color : 'secondary') + ' ms-1';
          });
          document.querySelectorAll('[data-ai-index-doc-progress]').forEach(function (el) {
            var value = data.documents[el.getAttribute('data-ai-index-doc-progress')];
            if (value && Number.isFinite(Number(value.percent))) {
              el.textContent = Math.max(0, Math.min(100, Math.round(Number(value.percent)))) + ' %';
            }
          });
        }
      })
      .catch(function () {
        // Keep the last verified server-rendered status; never claim success.
        if (button) button.title = 'Status aktuell nicht abrufbar';
        var refreshError = document.querySelector('[data-ai-index-refresh-error]');
        if (refreshError) refreshError.textContent = 'Status derzeit nicht abrufbar. Die letzten bekannten Zahlen bleiben sichtbar.';
      })
      .finally(function () {
        loading = false;
        if (button) button.disabled = false;
      });
  }

  if (button) button.addEventListener('click', refresh);
  window.setInterval(refresh, 20000);

  // Real model diagnostics: only an explicit click sends synthetic/user-supplied
  // text to the chosen provider. Never put provider data into HTML markup.
  document.querySelectorAll('[data-ai-diagnostic]').forEach(function (testForm) {
    testForm.addEventListener('submit', async function (event) {
      event.preventDefault();
      if (!testForm.reportValidity()) return;
      var kind = testForm.getAttribute('data-ai-diagnostic');
      var result = document.querySelector('[data-ai-diagnostic-result="' + kind + '"]');
      var submit = testForm.querySelector('button[type="submit"]');
      if (!result || !submit || submit.disabled) return;
      submit.disabled = true;
      result.className = 'small mt-3 text-secondary';
      result.textContent = kind === 'llm' ? 'LLM-Anfrage läuft …' : 'Embedding-Anfrage läuft …';
      try {
        var response = await fetch(testForm.action, {
          method: 'POST', body: new FormData(testForm),
          credentials: 'same-origin', cache: 'no-store',
          headers: {Accept: 'application/json'}
        });
        var value = await response.json();
        if (!response.ok || !value.ok) {
          throw new Error(typeof value.detail === 'string' ?
            value.detail : 'Modelltest fehlgeschlagen (HTTP ' + response.status + ').');
        }
        var duration = Number.isFinite(Number(value.duration_ms)) ?
          Math.round(Number(value.duration_ms)) + ' ms' : 'nicht verfügbar';
        if (kind === 'llm') {
          result.textContent = 'Erfolgreich · ' + value.provider + ' · ' +
            value.model + ' · ' + duration + '\nAntwort: ' + value.reply;
        } else {
          result.textContent = 'Embedding-Verbindung erfolgreich · ' + value.provider +
            ' · ' + value.model + ' · ' + duration + ' · ' +
            value.dimensions + ' Dimensionen';
        }
        result.style.whiteSpace = 'pre-wrap';
        result.className = 'small mt-3 text-success';
      } catch (error) {
        result.textContent = error instanceof Error ? error.message :
          'Der Modelltest konnte nicht abgeschlossen werden.';
        result.className = 'small mt-3 text-danger';
      } finally {
        submit.disabled = false;
      }
    });
  });
}());
