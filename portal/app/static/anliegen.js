/* TAKT Interne Anliegen – description first, optional AI draft, editable final fields.
   Uses the existing authenticated /anliegen/ki-entwurf endpoint; never submits the form. */
(function () {
  'use strict';

  var form = document.getElementById('anliegen-create');
  if (!form) return;

  var category = document.getElementById('anliegen-category');
  var title = document.getElementById('anliegen-title');
  var description = document.getElementById('anliegen-description');
  var finalDescription = document.getElementById('anliegen-final-description');
  var counter = document.getElementById('anliegen-character-count');
  var confidentialNote = document.getElementById('anliegen-secret');
  var aiButton = document.getElementById('anliegen-ai');
  var aiLabel = aiButton && aiButton.querySelector('[data-ai-button-label]');
  var aiStatus = document.getElementById('anliegen-ai-status');
  var reviewNote = document.getElementById('anliegen-review-notice');
  var copy = document.getElementById('anliegen-copy');
  var controller = null;
  var busy = false;
  var generated = false;
  var inputRevision = 0;
  var preview = document.getElementById('anliegen-recipient-preview');
  var previewSeq = 0;
  async function previewRecipient() {
    if (!preview || !category.value) return;
    var seq = ++previewSeq;
    preview.textContent = 'Zuständigkeit wird geprüft …';
    try {
      var response = await fetch('/anliegen/empfaenger-vorschau?category_id=' +
        encodeURIComponent(category.value), {credentials:'same-origin', cache:'no-store'});
      if (!response.ok) throw new Error('Empfängerprüfung fehlgeschlagen');
      var data = await response.json();
      if (seq !== previewSeq) return;
      preview.classList.toggle('alert-success', !!data.ready);
      preview.classList.toggle('alert-warning', !data.ready);
      preview.textContent = data.ready ?
        'Wird weitergeleitet an: ' + data.recipient + ' (' + data.message + ')' :
        'Weiterleitung zunächst offen: ' + data.message;
    } catch (_err) {
      if (seq === previewSeq) {
        preview.textContent = 'Die Zuständigkeit kann gerade nicht geprüft werden. Die Meldung kann weiterhin eingereicht werden.';
      }
    }
  }


  function confidential() {
    var selected = category.selectedOptions[0];
    return !!(selected && selected.dataset.confidential === '1');
  }

  function setStatus(message, state) {
    if (!aiStatus) return;
    aiStatus.hidden = !message;
    aiStatus.textContent = message || '';
    aiStatus.dataset.state = state || '';
  }

  function setReview(message, state) {
    reviewNote.textContent = message;
    reviewNote.dataset.state = state || '';
  }

  function refresh() {
    var secret = confidential();
    confidentialNote.hidden = !secret;
    if (aiButton) {
      aiButton.disabled = secret || busy;
      aiButton.setAttribute('aria-disabled', String(secret || busy));
      aiButton.setAttribute('aria-busy', String(busy));
    }
    if (aiLabel) aiLabel.textContent = busy ? 'KI erstellt den Vorschlag …' : 'Mit KI aufbereiten';
  }

  function manualChange() {
    inputRevision += 1;
    if (generated) {
      setReview('Sie bearbeiten den Vorschlag selbst. Nur Ihre geprüften Angaben werden eingereicht.', 'changed');
    }
  }

  description.addEventListener('input', function () {
    inputRevision += 1;
    if (counter) counter.textContent = description.value.length.toLocaleString('de-DE') + ' / 10.000';
  });
  title.addEventListener('input', manualChange);
  finalDescription.addEventListener('input', manualChange);
  category.addEventListener('change', function () {
    if (confidential() && controller) {
      controller.abort();
      setStatus('KI-Aufbereitung abgebrochen: vertrauliche Anliegen werden nicht an die KI übermittelt.', 'error');
    } else if (confidential()) {
      setStatus('', '');
    }
    refresh();
    manualChange();
    previewRecipient();
  });

  copy.addEventListener('click', function () {
    finalDescription.value = description.value;
    generated = false;
    setReview('Originaltext zur Bearbeitung übernommen. Sie können ihn rechts weiter anpassen.', 'ready');
    finalDescription.focus();
  });

  refresh();
  previewRecipient();
  if (!aiButton || !window.fetch || !window.AbortController) return;

  aiButton.addEventListener('click', async function () {
    if (busy || confidential()) return;
    var raw = description.value.trim();
    var selectedCategory = category.value;
    var revision = inputRevision;
    if (raw.length < 8) {
      setStatus('Bitte beschreiben Sie Ihr Anliegen zunächst mit mindestens 8 Zeichen.', 'error');
      description.focus();
      return;
    }
    if (raw.length > 4000) {
      setStatus('Die KI kann maximal 4.000 Zeichen aufbereiten. Die manuelle Einreichung ist weiterhin möglich.', 'error');
      description.focus();
      return;
    }
    if ((title.value.trim() || finalDescription.value.trim()) &&
        !window.confirm('Vorhandene Angaben rechts durch einen neuen KI-Vorschlag ersetzen?')) {
      return;
    }

    controller = new AbortController();
    busy = true;
    refresh();
    setStatus('Die KI bereitet den Text auf. Ihre Originalbeschreibung bleibt unverändert …', '');

    try {
      var payload = new FormData();
      payload.append('csrf', form.querySelector('[name="csrf"]').value);
      payload.append('category_id', category.value);
      payload.append('text', raw);

      var response = await fetch(aiButton.dataset.action, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
        body: payload,
        signal: controller.signal,
        cache: 'no-store'
      });
      if (!response.ok) {
        throw new Error('Die KI ist derzeit nicht verfügbar (HTTP ' + response.status + '). Ihre Eingaben bleiben erhalten.');
      }
      var proposal = await response.json();
      if (typeof proposal.title !== 'string' || typeof proposal.description !== 'string' ||
          !proposal.title.trim() || !proposal.description.trim()) {
        throw new Error('Der KI-Dienst hat keinen auswertbaren Vorschlag geliefert.');
      }

      // Do not overwrite fields if the user edited the original during inference
      // or switched to a confidential category.
      if (controller.signal.aborted || confidential() || category.value !== selectedCategory ||
          description.value.trim() !== raw || inputRevision !== revision) {
        setStatus('Die ursprüngliche Beschreibung oder Kategorie wurde geändert. Der alte KI-Vorschlag wurde nicht übernommen.', 'error');
        return;
      }

      title.value = proposal.title.trim().slice(0, 200);
      finalDescription.value = proposal.description.trim().slice(0, 10000);

      var suggestedId = String(proposal.category_id || '');
      if (/^\d+$/.test(suggestedId)) {
        var proposedCategory = Array.from(category.options).find(function (option) {
          return option.value === suggestedId && option.dataset.confidential !== '1';
        });
        if (proposedCategory) category.value = proposedCategory.value;
      }

      generated = true;
      previewRecipient();
      setStatus('Vorschlag erstellt. Bitte rechts Titel, Kategorie und Beschreibung prüfen.', 'success');
      setReview('KI-Vorschlag bereit – prüfen und korrigieren Sie die Angaben vor dem Einreichen.', 'ready');
      title.focus();
    } catch (error) {
      if (error && error.name === 'AbortError') return;
      setStatus(error && error.message ? error.message : 'Die KI-Aufbereitung ist fehlgeschlagen.', 'error');
    } finally {
      controller = null;
      busy = false;
      refresh();
    }
  });

  window.addEventListener('pagehide', function () {
    if (controller) controller.abort();
  });
}());