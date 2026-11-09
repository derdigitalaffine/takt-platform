/* Progressive enhancement: live SSE chat, or asynchronous JSON-mode fallback.
 * No third-party JS, no HTML insertion of model output, no secrets in the DOM.
 */
(function () {
  'use strict';
  var form = document.querySelector('[data-ai-chat-form]');
  if (!form || !window.fetch || !window.ReadableStream || !window.AbortController) return;
  var panel = form.querySelector('[data-ai-live]');
  var status = form.querySelector('[data-ai-status]');
  var output = form.querySelector('[data-ai-output]');
  var hint = form.querySelector('[data-ai-hint]');
  var submit = form.querySelector('[data-ai-send]');
  var stop = form.querySelector('[data-ai-stop]');
  var controller = null;
  var startedAt = 0;
  var ticker = null;
  var baseStatus = "";

  function updateStatus() {
    if (!controller) return;
    var seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    status.textContent = (baseStatus || "KI arbeitet …") + " (" + seconds + " s)";
  }

  function eventFrame(frame) {
    var kind = 'message', payload = '';
    frame.split(/\r?\n/).forEach(function (line) {
      if (line.indexOf('event:') === 0) kind = line.slice(6).trim();
      if (line.indexOf('data:') === 0) payload += line.slice(5).trimStart();
    });
    if (!payload) return null;
    try { return {kind: kind, value: JSON.parse(payload)}; }
    catch (error) { throw new Error('Ungültige Antwort des KI-Dienstes.'); }
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    if (controller) return;
    controller = new AbortController();
    panel.hidden = false;
    output.textContent = '';
    startedAt = Date.now();
    baseStatus = 'Verbindung zum KI-Modell wird aufgebaut …';
    updateStatus();
    ticker = window.setInterval(updateStatus, 1000);
    hint.textContent = '';
    submit.disabled = true;
    stop.disabled = false;
    var finished = false;
    var serverError = '';
    try {
      var response = await fetch(form.dataset.streamAction, {
        method: 'POST', body: new FormData(form), credentials: 'same-origin',
        headers: {'Accept': 'text/event-stream'}, signal: controller.signal,
        cache: 'no-store'
      });
      if (!response.ok) {
        if (response.status === 403) throw new Error('Keine Berechtigung oder Sitzung abgelaufen.');
        if (response.status === 429) throw new Error('Zu viele Anfragen. Bitte versuchen Sie es später.');
        throw new Error('Der KI-Dienst konnte die Anfrage nicht annehmen (HTTP ' + response.status + ').');
      }
      if (!response.body) throw new Error('Streaming-Antwort wird vom Browser nicht unterstützt.');
      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';
      while (true) {
        var step = await reader.read();
        if (step.done) break;
        buffer += decoder.decode(step.value, {stream: true});
        buffer = buffer.replace(/\r\n/g, '\n');
        if (buffer.length > 160000) throw new Error('Die Antwort überschreitet die Größe des Chatfensters.');
        var end;
        while ((end = buffer.indexOf('\n\n')) !== -1) {
          var eventData = eventFrame(buffer.slice(0, end));
          buffer = buffer.slice(end + 2);
          if (!eventData) continue;
          if (eventData.kind === 'status') {
            baseStatus = String(eventData.value.message || 'Die KI arbeitet …');
            updateStatus();
          } else if (eventData.kind === 'delta') {
            // Never use innerHTML for model content.
            output.textContent += String(eventData.value.text || '');
            baseStatus = 'Antwort wird empfangen …';
            updateStatus();
          } else if (eventData.kind === 'heartbeat') {
            baseStatus = 'Die KI arbeitet weiter …';
            updateStatus();
          } else if (eventData.kind === 'error') {
            serverError = String(eventData.value.message || 'Die Anfrage ist fehlgeschlagen.');
          } else if (eventData.kind === 'done') {
            finished = true;
            baseStatus = 'Antwort vollständig gespeichert.';
            updateStatus();
          }
        }
      }
      if (serverError) throw new Error(serverError);
      if (!finished) throw new Error('Die Verbindung wurde vor Ende der Antwort unterbrochen.');
      // History, sources and access checks are rendered by the authenticated server.
      window.location.assign('/ki?chat=' + form.dataset.streamAction.split('/')[2]);
    } catch (error) {
      if (error && error.name === 'AbortError') {
        status.textContent = 'Antwort abgebrochen.';
        hint.textContent = 'Die Nachricht wurde bereits gespeichert, die Antwort nicht.';
      } else {
        status.textContent = 'Antwort konnte nicht abgeschlossen werden.';
        hint.textContent = error instanceof Error ? error.message : 'Unbekannter Fehler.';
      }
    } finally {
      if (ticker !== null) { window.clearInterval(ticker); ticker = null; }
      controller = null;
      submit.disabled = false;
      stop.disabled = true;
    }
  });
  stop.addEventListener('click', function () {
    if (controller) controller.abort();
  });
}());
