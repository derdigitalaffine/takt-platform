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
    '[data-ai-index-qdrant]': 'qdrant'
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
        if (data.documents && typeof data.documents === 'object') {
          document.querySelectorAll('[data-ai-index-doc]').forEach(function (el) {
            var value = data.documents[el.getAttribute('data-ai-index-doc')];
            if (!value || typeof value.label !== 'string') return;
            el.textContent = value.label;
            var allowed = ['success', 'secondary', 'warning', 'danger'];
            el.className = 'badge text-bg-' +
              (allowed.indexOf(value.color) !== -1 ? value.color : 'secondary') + ' ms-1';
          });
        }
      })
      .catch(function () {
        // Keep the last verified server-rendered status; never claim success.
        if (button) button.title = 'Status aktuell nicht abrufbar';
      })
      .finally(function () {
        loading = false;
        if (button) button.disabled = false;
      });
  }

  if (button) button.addEventListener('click', refresh);
  window.setInterval(refresh, 20000);
}());
