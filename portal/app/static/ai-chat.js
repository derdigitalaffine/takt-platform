/* Progressive enhancement for TAKT: each SSE delta stays in the conversation.
 * Safe DOM text nodes, no third-party JS, no full-page reload after success.
 * The original form POST remains usable without JavaScript.
 */
(function () {
  'use strict';

  var form = document.querySelector('[data-ai-chat-form]');
  if (!form || !window.fetch || !window.ReadableStream || !window.AbortController) return;

  var messages = document.querySelector('[data-ai-messages]');
  var scroller = document.querySelector('[data-ai-scroll-area]');
  var jump = document.querySelector('[data-ai-jump]');
  var status = form.querySelector('[data-ai-status]');
  var hint = form.querySelector('[data-ai-hint]');
  var submit = form.querySelector('[data-ai-send]');
  var stop = form.querySelector('[data-ai-stop]');
  var prompt = form.querySelector('[name="message"]');
  var imageInput = form.querySelector('[name="image"]');
  if (!messages || !scroller || !jump || !status || !hint || !submit || !stop || !prompt) return;

  var controller = null;
  var initiallyDisabled = submit.disabled;

  function isAtBottom() {
    return scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 110;
  }

  function scrollToLatest() {
    scroller.scrollTop = scroller.scrollHeight;
    jump.hidden = true;
  }

  function updateJump() {
    jump.hidden = isAtBottom();
  }

  scroller.addEventListener('scroll', updateJump, {passive: true});
  jump.addEventListener('click', scrollToLatest);
  scrollToLatest();

  function messageBubble(role, text) {
    var item = document.createElement('li');
    item.className = 'ai-message ai-message--' + role;
    item.setAttribute('data-ai-message', '');

    var avatar = document.createElement('div');
    avatar.className = 'ai-message-avatar';
    avatar.setAttribute('aria-hidden', 'true');
    var icon = document.createElement('i');
    icon.className = 'fa-solid ' + (role === 'user' ? 'fa-user' : 'fa-brain');
    avatar.appendChild(icon);

    var bubble = document.createElement('div');
    bubble.className = 'ai-message-bubble';
    var label = document.createElement('div');
    label.className = 'ai-message-label';
    label.textContent = role === 'user' ? 'Sie' : 'KI-Assistent';
    var content = document.createElement('div');
    content.className = 'ai-message-text text-break';
    content.setAttribute('data-ai-message-text', '');
    content.textContent = text || '';
    bubble.appendChild(label);
    bubble.appendChild(content);
    item.appendChild(avatar);
    item.appendChild(bubble);
    messages.appendChild(item);
    return {item: item, bubble: bubble, content: content};
  }

  function progressText(bubble) {
    var progress = document.createElement('div');
    progress.className = 'ai-message-progress';
    progress.textContent = 'Verbindung zum KI-Modell wird aufgebaut …';
    bubble.appendChild(progress);
    return progress;
  }

  function addAnswerMetadata(bubble, data) {
    if (!data || typeof data !== 'object') return;
    if (Array.isArray(data.sources) && data.sources.length) {
      var block = document.createElement('div');
      block.className = 'ai-message-sources';
      var heading = document.createElement('strong');
      heading.className = 'small';
      heading.textContent = 'Verwendete interne Quellen';
      block.appendChild(heading);
      var list = document.createElement('ul');
      list.className = 'small mb-0';
      data.sources.forEach(function (source) {
        if (!source || typeof source.url !== 'string' || typeof source.title !== 'string') return;
        if (!source.url.startsWith('/') || source.url.startsWith('//')) return;
        var url;
        try { url = new URL(source.url, window.location.origin); }
        catch (error) { return; }
        if (url.origin !== window.location.origin) return;
        var item = document.createElement('li');
        var link = document.createElement('a');
        link.href = url.pathname + url.search + url.hash;
        link.textContent = source.title;
        item.appendChild(link);
        list.appendChild(item);
      });
      if (list.children.length) {
        block.appendChild(list);
        bubble.appendChild(block);
      }
    }
    if (typeof data.model === 'string' && data.model) {
      var model = document.createElement('div');
      model.className = 'ai-message-model';
      model.textContent = 'Modell: ' + data.model;
      bubble.appendChild(model);
    }
  }

  function eventFrame(frame) {
    var kind = 'message';
    var dataLines = [];
    frame.split('\n').forEach(function (line) {
      if (line.indexOf('event:') === 0) kind = line.slice(6).trim();
      if (line.indexOf('data:') === 0) dataLines.push(line.slice(5).trimStart());
    });
    if (!dataLines.length) return null;
    try { return {kind: kind, value: JSON.parse(dataLines.join('\n'))}; }
    catch (error) { throw new Error('Ungültige Antwort des KI-Dienstes.'); }
  }

  function updateTitle(value) {
    if (form.dataset.aiHasMessages === '1') return;
    form.dataset.aiHasMessages = '1';
    var title = value.slice(0, 100);
    var heading = document.querySelector('[data-ai-chat-title]');
    if (heading) heading.textContent = title;
    var sidebar = document.querySelector('[data-ai-current-link]');
    if (sidebar) sidebar.textContent = title;
    // The server uses the first question as the conversation title.
    var titleField = document.querySelector('input[name="title"]');
    if (titleField) titleField.value = title;
  }

  prompt.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.isComposing) {
      event.preventDefault();
      if (typeof form.requestSubmit === 'function') form.requestSubmit();
    }
  });

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    if (controller || initiallyDisabled) return;
    var question = prompt.value.trim();
    if (!question) { prompt.focus(); return; }

    // FormData must be captured before clearing anything (including an image).
    var body = new FormData(form);
    var hasImage = !!(imageInput && imageInput.files && imageInput.files.length);
    var empty = messages.querySelector('[data-ai-empty]');
    if (empty) empty.remove();

    var userText = question + (hasImage ? '\n[Bild für diese Anfrage verarbeitet; nicht gespeichert.]' : '');
    var userBubble = messageBubble('user', userText);
    var assistantBubble = messageBubble('assistant', '');
    var progress = progressText(assistantBubble.bubble);
    assistantBubble.item.classList.add('ai-message--streaming');
    scrollToLatest();

    controller = new AbortController();
    submit.disabled = true;
    stop.disabled = false;
    stop.hidden = false;
    status.textContent = 'KI-Anfrage wird gesendet …';
    hint.textContent = '';

    var accepted = false;
    var rejected = false;
    var finished = false;
    var doneData = null;
    var serverError = '';
    var receivedText = false;

    try {
      var response = await fetch(form.dataset.streamAction, {
        method: 'POST', body: body, credentials: 'same-origin',
        headers: {'Accept': 'text/event-stream'}, signal: controller.signal,
        cache: 'no-store'
      });
      if (!response.ok) {
        rejected = true;
        if (response.status === 403) throw new Error('Keine Berechtigung oder Sitzung abgelaufen.');
        if (response.status === 429) throw new Error('Zu viele Anfragen. Bitte versuchen Sie es später.');
        throw new Error('Der KI-Dienst konnte die Anfrage nicht annehmen (HTTP ' + response.status + ').');
      }
      accepted = true;
      updateTitle(question);
      if (!response.body) throw new Error('Streaming-Antwort wird vom Browser nicht unterstützt.');

      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';
      while (true) {
        var step = await reader.read();
        if (step.done) break;
        buffer += decoder.decode(step.value, {stream: true});
        // Normalize after buffering: CR and LF may arrive in different network chunks.
        buffer = buffer.replace(/\r\n/g, '\n');
        if (buffer.length > 160000) throw new Error('Die Antwort überschreitet die Größe des Chatfensters.');

        var end;
        while ((end = buffer.indexOf('\n\n')) !== -1) {
          var eventData = eventFrame(buffer.slice(0, end));
          buffer = buffer.slice(end + 2);
          if (!eventData) continue;

          if (eventData.kind === 'status') {
            progress.textContent = String(eventData.value.message || 'Die KI arbeitet …');
            status.textContent = 'KI verarbeitet die Anfrage …';
          } else if (eventData.kind === 'delta') {
            var chunk = String(eventData.value.text || '');
            var follow = isAtBottom();
            // No innerHTML: streamed model output must remain inert text.
            assistantBubble.content.appendChild(document.createTextNode(chunk));
            if (!receivedText) {
              receivedText = true;
              progress.textContent = 'Antwort wird live übertragen …';
              status.textContent = 'KI antwortet …';
            }
            if (follow) scrollToLatest();
            else updateJump();
          } else if (eventData.kind === 'error') {
            serverError = String(eventData.value.message || 'Die Anfrage ist fehlgeschlagen.');
          } else if (eventData.kind === 'done') {
            finished = true;
            doneData = eventData.value;
          }
        }
      }
      if (serverError) throw new Error(serverError);
      if (!finished) throw new Error('Die Verbindung wurde vor Ende der Antwort unterbrochen.');

      assistantBubble.item.classList.remove('ai-message--streaming');
      progress.remove();
      addAnswerMetadata(assistantBubble.bubble, doneData);
      // The server has persisted the user message and the complete answer.
      prompt.value = '';
      if (imageInput) imageInput.value = '';
      status.textContent = 'Antwort gespeichert.';
      hint.textContent = '';
      updateJump();
      prompt.focus({preventScroll: true});
    } catch (error) {
      assistantBubble.item.classList.remove('ai-message--streaming');
      if (rejected) {
        userBubble.item.remove();
        assistantBubble.item.remove();
        if (empty) messages.appendChild(empty);
      } else {
        assistantBubble.item.classList.add('ai-message--error');
        progress.textContent = 'Antwort abgebrochen oder fehlgeschlagen – Teilantwort nicht gespeichert.';
        if (!accepted) {
          progress.textContent = 'Verbindung fehlgeschlagen – gespeicherten Verlauf ggf. neu laden.';
        }
      }
      if (error && error.name === 'AbortError') {
        status.textContent = 'Antwort abgebrochen.';
        hint.textContent = 'Die Nachricht kann bereits gespeichert sein, die Teilantwort nicht.';
      } else {
        status.textContent = 'Antwort konnte nicht abgeschlossen werden.';
        hint.textContent = error instanceof Error ? error.message : 'Unbekannter Fehler.';
      }
      updateJump();
    } finally {
      controller = null;
      submit.disabled = initiallyDisabled;
      stop.disabled = true;
      stop.hidden = true;
    }
  });

  stop.addEventListener('click', function () {
    if (controller) controller.abort();
  });
}());
