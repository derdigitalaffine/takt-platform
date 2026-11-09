/* Optional TAKT AI drafting: never submits an Anliegen without the user clicking Einreichen. */
(function () {
  'use strict';
  var form = document.getElementById('anliegen-create');
  if (!form) return;
  var category = document.getElementById('anliegen-category');
  var title = document.getElementById('anliegen-title');
  var body = document.getElementById('anliegen-description');
  var alert = document.getElementById('anliegen-secret');
  var ai = document.getElementById('anliegen-ai');
  var status = document.getElementById('anliegen-ai-status');
  var busy = false;
  function confidential() {
    var selected = category.selectedOptions[0];
    return !!(selected && selected.dataset.confidential === '1');
  }
  function refresh() {
    alert.hidden = !confidential();
    if (ai) ai.disabled = confidential() || busy;
    if (status && confidential()) status.textContent = '';
  }
  category.addEventListener('change', refresh);
  refresh();
  if (!ai || !window.fetch) return;
  ai.addEventListener('click', async function () {
    if (busy || confidential()) return;
    var input = body.value.trim();
    if (input.length < 8) { status.textContent = 'Bitte beschreiben Sie zuerst Ihr Anliegen.'; body.focus(); return; }
    busy = true; refresh();
    status.textContent = 'Die KI erstellt einen unverbindlichen Textvorschlag …';
    try {
      var data = new FormData();
      data.append('csrf', form.querySelector('[name="csrf"]').value);
      data.append('category_id', category.value);
      data.append('text', input);
      var response = await fetch(ai.dataset.action, {
        method: 'POST', credentials: 'same-origin',
        headers: {'Accept': 'application/json'}, body: data, cache: 'no-store'
      });
      if (!response.ok) throw new Error('Der KI-Entwurf ist derzeit nicht verfügbar (HTTP ' + response.status + ').');
      var draft = await response.json();
      if (typeof draft.title !== 'string' || typeof draft.description !== 'string') {
        throw new Error('Der KI-Dienst hat keinen brauchbaren Entwurf geliefert.');
      }
      title.value = draft.title.slice(0, 200);
      body.value = draft.description.slice(0, 4000);
      var suggested = category.querySelector('option[value="' + String(draft.category_id).replace(/[^0-9]/g, '') + '"]');
      if (suggested && suggested.dataset.confidential !== '1') category.value = suggested.value;
      status.textContent = 'Entwurf übernommen. Bitte prüfen und erst danach einreichen.';
      title.focus();
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : 'Die KI-Hilfe ist nicht verfügbar.';
    } finally {
      busy = false; refresh();
    }
  });
}());
