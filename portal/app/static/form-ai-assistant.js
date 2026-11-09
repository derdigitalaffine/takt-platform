/* KI-Formularassistent: Vorschläge bleiben bis zur bewussten Übernahme rein lokal. */
(function () {
  'use strict';
  var panel = document.getElementById('form-ai-panel');
  var builder = window.TaktFormBuilderAI;
  if (!panel || !builder) { return; }
  var prompt = document.getElementById('form-ai-prompt');
  var mode = document.getElementById('form-ai-mode');
  var provider = document.getElementById('form-ai-provider');
  var generate = document.getElementById('form-ai-generate');
  var progress = document.getElementById('form-ai-progress');
  var error = document.getElementById('form-ai-error');
  var preview = document.getElementById('form-ai-preview');
  var apply = document.getElementById('form-ai-apply');
  var cancel = document.getElementById('form-ai-cancel');
  var dismiss = document.getElementById('form-ai-dismiss');
  var currentController = null;
  var proposal = null;
  var proposalSnapshot = '';
  var proposalMode = '';

  function setError(message) {
    error.textContent = message || '';
    error.hidden = !message;
  }
  function setBusy(busy) {
    progress.hidden = !busy;
    generate.disabled = busy;
    prompt.readOnly = busy;
    mode.disabled = busy;
    provider.disabled = busy;
  }
  function clearPreview() {
    proposal = null;
    proposalSnapshot = '';
    preview.hidden = true;
  }
  function appendText(tag, content, parent) {
    var el = document.createElement(tag);
    el.textContent = content || '';
    parent.appendChild(el);
    return el;
  }
  function renderPreview(data) {
    var names = builder.types();
    document.getElementById('form-ai-preview-title').textContent = data.title || 'Formularentwurf';
    document.getElementById('form-ai-preview-description').textContent = data.description || '';
    document.getElementById('form-ai-preview-count').textContent =
      data.items.length + ' Bausteine · ' + data.question_count + ' Fragen';
    var list = document.getElementById('form-ai-preview-items');
    list.replaceChildren();
    data.items.forEach(function (item) {
      var li = document.createElement('li');
      var name = names[item.type] ? names[item.type][0] : item.type;
      appendText('span', name, li).className = 'small text-secondary d-block';
      appendText('strong', item.title || name, li);
      if (item.description) {
        appendText('span', item.description, li).className = 'small text-secondary d-block';
      }
      if (item.required) {
        appendText('span', 'Pflichtangabe', li).className = 'badge text-bg-light border ms-2';
      }
      list.appendChild(li);
    });
    var notes = document.getElementById('form-ai-preview-notes');
    notes.replaceChildren();
    (data.notes || []).forEach(function (note) { appendText('li', note, notes); });
    notes.hidden = !notes.children.length;
    var sources = document.getElementById('form-ai-preview-sources');
    sources.replaceChildren();
    (data.sources || []).forEach(function (source) {
      if (typeof source.url !== 'string' || !source.url.startsWith('/') || source.url.startsWith('//')) { return; }
      var link = document.createElement('a');
      link.href = source.url;
      link.textContent = source.title;
      link.className = 'me-2';
      sources.appendChild(link);
    });
    if (sources.children.length) { sources.prepend(document.createTextNode('Berücksichtigtes TAKT-Wissen: ')); }
    sources.hidden = !sources.children.length;
    preview.hidden = false;
  }

  panel.querySelectorAll('[data-form-ai-example]').forEach(function (button) {
    button.addEventListener('click', function () {
      prompt.value = button.dataset.formAiExample;
      prompt.focus();
    });
  });
  generate.addEventListener('click', async function () {
    setError('');
    clearPreview();
    if (!prompt.value.trim()) {
      setError('Beschreiben Sie zuerst das gewünschte Formular.');
      prompt.focus();
      return;
    }
    var snapshot = builder.snapshot();
    proposalSnapshot = JSON.stringify(snapshot);
    proposalMode = mode.value;
    var body = new FormData();
    body.set('csrf', document.querySelector('#builder-form [name="csrf"]').value);
    body.set('prompt', prompt.value.trim());
    body.set('mode', proposalMode);
    body.set('provider_id', provider.value);
    body.set('current_json', JSON.stringify(snapshot.items));
    body.set('form_title', snapshot.title);
    body.set('form_description', snapshot.description);
    var knowledge = document.getElementById('form-ai-knowledge');
    body.set('include_knowledge', knowledge && knowledge.checked ? '1' : '0');
    var controller = new AbortController();
    currentController = controller;
    setBusy(true);
    try {
      var response = await fetch(panel.dataset.endpoint, {
        method: 'POST', body: body, credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }, signal: controller.signal
      });
      var data = await response.json();
      if (!response.ok) {
        var message = data && data.detail;
        throw new Error(typeof message === 'string' ? message : 'Der Formularvorschlag konnte nicht erstellt werden.');
      }
      if (!data || !Array.isArray(data.items) || !data.items.length) {
        throw new Error('Die KI hat keinen verwendbaren Formularvorschlag zurückgegeben.');
      }
      proposal = data;
      renderPreview(data);
      preview.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (exc) {
      if (exc.name !== 'AbortError') {
        clearPreview();
        setError(exc.message || 'KI momentan nicht verfügbar.');
      }
    } finally {
      if (currentController === controller) { currentController = null; setBusy(false); }
    }
  });
  cancel.addEventListener('click', function () {
    if (currentController) { currentController.abort(); currentController = null; setBusy(false); }
  });
  dismiss.addEventListener('click', function () { clearPreview(); setError(''); });
  apply.addEventListener('click', function () {
    if (!proposal) { return; }
    if (JSON.stringify(builder.snapshot()) !== proposalSnapshot) {
      setError('Das Formular hat sich seit dem KI-Vorschlag geändert. Erstellen Sie bitte einen neuen Vorschlag, damit keine Änderungen verloren gehen.');
      return;
    }
    if (proposalMode === 'replace' && builder.snapshot().items.length &&
        !window.confirm('Den bisherigen Formularaufbau durch den KI-Entwurf ersetzen? Ungespeicherte Änderungen am Aufbau gehen dabei verloren.')) {
      return;
    }
    builder.apply(proposal, proposalMode);
    clearPreview();
    setError('');
    document.getElementById('builder-state').textContent = 'KI-Entwurf übernommen – bitte prüfen und speichern';
    document.getElementById('builder-items').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
})();
