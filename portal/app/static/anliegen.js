/* TAKT internal Anliegen: one-text AI draft or the fully manual disclosure.
 * No automatic submission, safe textContent, and no stale AI overwrites.
 */
(function () {
  'use strict';
  var form = document.getElementById('anliegen-create');
  if (!form) return;
  var prompt = document.getElementById('anliegen-description');
  var counter = document.getElementById('anliegen-prompt-counter');
  var details = document.getElementById('anliegen-review');
  var label = document.getElementById('anliegen-review-label');
  var subtitle = document.getElementById('anliegen-review-subtitle');
  var intro = document.getElementById('anliegen-review-intro');
  var title = document.getElementById('anliegen-title');
  var category = document.getElementById('anliegen-category');
  var finalBody = document.getElementById('anliegen-final-description');
  var secretNote = document.getElementById('anliegen-secret');
  var preview = document.getElementById('anliegen-recipient-preview');
  var ai = document.getElementById('anliegen-ai');
  var status = document.getElementById('anliegen-ai-status');
  var previewSequence = 0;
  var editVersion = 0;
  var controller = null;
  var busy = false;
  var generated = false;

  function isConfidential() {
    var option = category.selectedOptions[0];
    return !!(option && option.dataset.confidential === '1');
  }
  function setStatus(message, level) {
    if (!status) return;
    status.textContent = message || '';
    status.hidden = !message;
    status.dataset.state = level || '';
  }
  function refresh() {
    secretNote.hidden = !isConfidential();
    if (ai) {
      ai.disabled = busy || isConfidential();
      ai.setAttribute('aria-busy', String(busy));
    }
  }
  function manualEdit() {
    editVersion++;
    if (busy && controller) {
      controller.abort();
      setStatus('Der KI-Vorschlag wurde abgebrochen, weil Sie Angaben manuell bearbeiten.', '');
    }
    if (generated) subtitle.textContent = 'Ihre Änderungen werden erst nach dem Einreichen übernommen.';
  }
  async function previewRecipient() {
    if (!category.value || !window.fetch) return;
    var requestId = ++previewSequence;
    preview.textContent = 'Zuständigkeit wird geprüft …';
    preview.removeAttribute('data-ready');
    try {
      var response = await fetch('/anliegen/empfaenger-vorschau?category_id=' +
        encodeURIComponent(category.value), {
          credentials: 'same-origin', cache: 'no-store'
        });
      if (!response.ok) throw new Error('Empfänger nicht abrufbar');
      var data = await response.json();
      if (requestId !== previewSequence) return;
      preview.dataset.ready = String(!!data.ready);
      preview.textContent = data.ready ?
        'Zuständig: ' + data.recipient + ' · ' + data.message :
        'Noch keine eindeutige Zuständigkeit: ' + data.message;
    } catch (_error) {
      if (requestId === previewSequence) {
        preview.textContent = 'Zuständigkeit derzeit nicht abrufbar. Das Anliegen kann trotzdem eingereicht werden.';
      }
    }
  }

  title.addEventListener('input', manualEdit);
  finalBody.addEventListener('input', manualEdit);
  category.addEventListener('change', function () {
    manualEdit();
    refresh();
    previewRecipient();
  });
  details.addEventListener('toggle', function () {
    if (details.open && !generated && !finalBody.value.trim() && prompt.value.trim()) {
      finalBody.value = prompt.value.trim();
    }
    if (details.open && busy) manualEdit();
  });

  if (prompt && counter) {
    prompt.addEventListener('input', function () {
      editVersion++;
      counter.textContent = prompt.value.length.toLocaleString('de-DE') + ' Zeichen';
      if (busy && controller) {
        controller.abort();
        setStatus('Ihre Beschreibung wurde verändert. Der alte KI-Vorschlag wurde verworfen.', '');
      }
    });
  }
  refresh();
  if (details.open) previewRecipient();
  if (!ai || !window.fetch || !window.AbortController) return;

  ai.addEventListener('click', async function () {
    if (busy || isConfidential()) return;
    var input = prompt.value.trim();
    if (input.length < 8) {
      setStatus('Beschreiben Sie Ihr Anliegen mit mindestens 8 Zeichen.', 'error');
      prompt.focus();
      return;
    }
    if (input.length > 4000) {
      setStatus('Die KI kann höchstens 4.000 Zeichen verarbeiten. Nutzen Sie alternativ die manuelle Erfassung.', 'error');
      prompt.focus();
      return;
    }
    if ((title.value.trim() || finalBody.value.trim()) &&
        !window.confirm('Vorhandene manuelle Angaben durch einen neuen KI-Vorschlag ersetzen?')) return;

    var initialVersion = editVersion;
    var selectedCategory = category.value;
    controller = new AbortController();
    busy = true;
    refresh();
    setStatus('Die KI bereitet Ihr Anliegen auf …', '');
    try {
      var payload = new FormData();
      payload.append('csrf', form.querySelector('input[name="csrf"]').value);
      payload.append('category_id', selectedCategory);
      payload.append('text', input);
      var response = await fetch(ai.dataset.action, {
        method: 'POST', credentials: 'same-origin', body: payload,
        headers: {Accept: 'application/json'}, signal: controller.signal, cache: 'no-store'
      });
      if (!response.ok) throw new Error('Die KI ist nicht verfügbar (HTTP ' + response.status + '). Ihre Angaben bleiben erhalten.');
      var draft = await response.json();
      if (!draft || typeof draft.title !== 'string' || typeof draft.description !== 'string' ||
          draft.title.trim().length < 3 || draft.description.trim().length < 5) {
        throw new Error('Der KI-Dienst hat keinen verwendbaren Vorschlag geliefert.');
      }
      if (controller.signal.aborted || input !== prompt.value.trim() ||
          selectedCategory !== category.value || editVersion !== initialVersion || isConfidential()) {
        setStatus('Zwischenzeitlich bearbeitete Angaben bleiben unverändert. Der alte Vorschlag wurde nicht übernommen.', '');
        return;
      }
      title.value = draft.title.trim().slice(0, 200);
      finalBody.value = draft.description.trim().slice(0, 10000);
      var suggestedId = String(draft.category_id || '');
      if (/^[0-9]+$/.test(suggestedId)) {
        var chosen = Array.from(category.options).find(function (opt) {
          return opt.value === suggestedId && opt.dataset.confidential !== '1';
        });
        if (chosen) category.value = chosen.value;
      }
      generated = true;
      label.textContent = 'KI-Vorschlag prüfen und bearbeiten';
      subtitle.textContent = 'Titel, Kategorie und Beschreibung können Sie vollständig ändern.';
      intro.textContent = 'Vorschlag erstellt. Bitte prüfen Sie ihn – nichts wurde bisher eingereicht.';
      details.open = true;
      refresh();
      previewRecipient();
      setStatus('Vorschlag erstellt. Prüfen Sie unten die Angaben und reichen Sie Ihr Anliegen selbst ein.', 'success');
      details.scrollIntoView({behavior: 'smooth', block: 'start'});
      title.focus({preventScroll: true});
    } catch (error) {
      if (error && error.name !== 'AbortError') {
        setStatus(error.message || 'Die KI-Aufbereitung ist fehlgeschlagen.', 'error');
      }
    } finally {
      busy = false;
      controller = null;
      refresh();
    }
  });
  window.addEventListener('pagehide', function () {
    if (controller) controller.abort();
  });
}());