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
  var temporary = form.dataset.aiTemporary === '1';
  var transientHistory = []; // Browser-memory only; never persisted by TAKT.
  if (temporary) {
    // A back/forward cache may otherwise retain the previous page's DOM and
    // JS heap. Explicitly erase both when the temporary chat is left.
    window.addEventListener('pagehide', function () {
      transientHistory.length = 0;
      if (messages) messages.replaceChildren();
      if (prompt) prompt.value = '';
      if (imageInput) imageInput.value = '';
    });
  }
  var startedAt = 0;
  var ticker = null;
  var baseStatus = '';
  var activeProgress = null;

  function updateStatus() {
    if (!controller || !activeProgress) return;
    var seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
    var progressLabel = activeProgress.querySelector('[data-ai-progress-label]');
    if (progressLabel) progressLabel.textContent = (baseStatus || 'TAKT überlegt …') + ' (' + seconds + ' s)';
  }

  var workspace = document.querySelector('[data-ai-workspace]');
  var conversations = document.querySelector('.ai-chat-conversations');
  function resizeWorkspace() {
    if (!workspace) return;
    var viewHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
    var available = Math.floor(viewHeight - workspace.getBoundingClientRect().top - 12);
    workspace.style.height = Math.max(260, available) + 'px';
  }
  if (conversations && window.matchMedia('(max-width: 1199.98px)').matches) {
    conversations.open = false;
  }
  resizeWorkspace();
  window.addEventListener('resize', resizeWorkspace);
  if (window.visualViewport) window.visualViewport.addEventListener('resize', resizeWorkspace);

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
    label.textContent = role === 'user' ? 'Du' : 'TAKT Agent';
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

  // Source IDs are only supplied after a message is persisted on the server.
  // The server rechecks ownership and current source permissions on every fork.
  function addForkAction(bubble, id) {
    if (!Number.isSafeInteger(id) || id <= 0 || !form.dataset.aiForkAction) return;
    var forkForm = document.createElement('form');
    forkForm.method = 'post';
    forkForm.action = form.dataset.aiForkAction;
    forkForm.className = 'ai-fork-action mt-2';
    var csrfSource = form.querySelector('input[name="csrf"]');
    if (!csrfSource) return;
    [['csrf', csrfSource.value], ['message_id', String(id)]].forEach(function (field) {
      var hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = field[0];
      hidden.value = field[1];
      forkForm.appendChild(hidden);
    });
    var button = document.createElement('button');
    button.type = 'submit';
    button.className = 'btn btn-sm btn-link text-secondary px-1 py-0';
    button.title = 'Neuen, unabhängigen Chat ab hier erstellen';
    button.textContent = 'Ab hier verzweigen';
    forkForm.appendChild(button);
    bubble.appendChild(forkForm);
  }

  function progressText(bubble) {
    var progress = document.createElement('div');
    progress.className = 'ai-message-progress';
    progress.setAttribute('role', 'status');
    progress.setAttribute('aria-live', 'polite');
    var label = document.createElement('span');
    label.setAttribute('data-ai-progress-label', '');
    label.textContent = 'Ich überlege kurz …';
    progress.appendChild(label);
    var dots = document.createElement('span');
    dots.className = 'ai-typing-dots';
    dots.setAttribute('aria-hidden', 'true');
    for (var index = 0; index < 3; index++) {
      dots.appendChild(document.createElement('span'));
    }
    progress.appendChild(dots);
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
        var url;
        try { url = new URL(source.url, window.location.origin); }
        catch (error) { return; }
        var external = source.kind === 'web';
        if (external) {
          // URLs are already checked by the backend; keep browser defence-in-depth.
          if (url.protocol !== 'https:' || url.username || url.password ||
              url.hostname === 'localhost' || url.hostname.endsWith('.localhost')) return;
        } else if (!source.url.startsWith('/') || source.url.startsWith('//') ||
                   url.origin !== window.location.origin) return;
        var item = document.createElement('li');
        var link = document.createElement('a');
        link.href = external ? url.href : url.pathname + url.search + url.hash;
        if (external) { link.target = '_blank'; link.rel = 'noopener noreferrer'; }
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
    // Enter sends; Shift+Enter inserts a newline. Keep IME composition intact.
    if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    if (controller || initiallyDisabled) return;
    if (typeof form.requestSubmit === 'function') form.requestSubmit(submit);
    else submit.click();
  });

  async function runAgent(question) {
    const body = new FormData(form);
    body.set('prompt', question);
    messages.querySelector('[data-ai-empty]')?.remove();
    const userBubble = messageBubble('user', question);
    const assistantBubble = messageBubble('assistant', '');
    const progress = progressText(assistantBubble.bubble);
    assistantBubble.item.classList.add('ai-message--streaming');
    controller = new AbortController();
    submit.disabled = true; stop.disabled = false; stop.hidden = false;
    status.textContent = 'Ich schaue mir deine Nachricht an …';
    hint.textContent = '';
    scrollToLatest();
    try {
      const response = await fetch('/agent/plan', {method: 'POST', body,
        credentials: 'same-origin', cache: 'no-store', signal: controller.signal, headers: {'Accept': 'application/json'}});
      const raw = await response.text();
      let data;
      try { data = JSON.parse(raw); } catch (_) {
        throw new Error(response.redirected ? 'Sitzung abgelaufen. Bitte erneut anmelden.' : 'Der Server hat keine gültige Agentenantwort geliefert (HTTP ' + response.status + '). Bitte erneut versuchen.');
      }
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Der Agent konnte den Auftrag nicht verarbeiten.');
      prompt.value = '';
      assistantBubble.content.textContent = data.message || '';
      if (typeof data.html === 'string') {
        assistantBubble.content.classList.add('ai-message-markdown');
        assistantBubble.content.innerHTML = data.html;
      }
      addAnswerMetadata(assistantBubble.bubble, data);
      const list = document.createElement('ul');
      for (const result of data.results || []) {
        if (!/^\/(?:(?:aufgaben|anliegen|forms|processes)\/\d+|dms\/r\/\d+|urlaub\/vorgang\/\d+|kalender\?ansicht=termine)$/.test(result.url || '')) continue;
        const li = document.createElement('li'); const link = document.createElement('a');
        link.href = result.url; link.textContent = result.title || result.name || 'TAKT-Bereich';
        li.appendChild(link); list.appendChild(li);
      }
      if (list.children.length) assistantBubble.bubble.appendChild(list);
      // A suggested destination is informational only. Navigating the
      // application requires the user's explicit click, never a model output.
      if (typeof data.open_url === 'string' &&
          /^\/(?:aufgaben|anliegen|forms|dms|kalender|processes|urlaub)(?:[/?#]|$)/.test(data.open_url) &&
          !data.open_url.startsWith('//') && !data.open_url.includes('\\')) {
        var actionBox = document.createElement('div');
        actionBox.className = 'ai-agent-destination';
        var explanation = document.createElement('span');
        explanation.textContent = data.proposals && data.proposals.length ?
          'Ich habe einen Vorschlag vorbereitet. Über den Link gelangst du zur Prüfung – gespeichert wird erst nach deiner Bestätigung.' :
          'Ich kann dich dorthin führen. Öffne den Bereich über diesen Link:';
        var link = document.createElement('a');
        link.className = 'btn btn-sm btn-primary';
        link.href = data.open_url;
        // A deliberate click opens the original TAKT page, not the tiny dock.
        if (window.self !== window.top) link.target = '_top';
        link.textContent = data.proposals && data.proposals.length ?
          'Vorschlag prüfen' : 'Bereich öffnen';
        actionBox.appendChild(explanation);
        actionBox.appendChild(link);
        assistantBubble.bubble.appendChild(actionBox);
      }
      progress.remove();
      assistantBubble.item.classList.remove('ai-message--streaming');
      status.textContent = data.open_url ? 'Link bereit – du entscheidest, wann du wechselst.' : 'Antwort bereit.';
      updateTitle(question); scrollToLatest();
    } catch (error) {
      progress.textContent = error.name === 'AbortError' ? 'Abgebrochen. Es wurde nichts geändert.' : error.message;
      assistantBubble.item.classList.remove('ai-message--streaming');
      assistantBubble.item.classList.add('ai-message--error');
      hint.textContent = progress.textContent;
    } finally {
      controller = null; submit.disabled = initiallyDisabled;
      stop.disabled = true; stop.hidden = true; prompt.focus({preventScroll: true});
    }
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    if (controller || initiallyDisabled) return;
    var question = prompt.value.trim();
    if (!question) { prompt.focus(); return; }
    if (!temporary && form.elements.use_agent?.checked && !(imageInput?.files?.length)) {
      await runAgent(question); return;
    }

    // FormData must be captured before clearing anything (including an image).
    var body = new FormData(form);
    if (temporary) body.set('history', JSON.stringify(transientHistory));
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
    startedAt = Date.now();
    baseStatus = 'Verbindung zum KI-Modell wird aufgebaut …';
    activeProgress = progress;
    updateStatus();
    ticker = window.setInterval(updateStatus, 1000);
    submit.disabled = true;
    stop.disabled = false;
    stop.hidden = false;
    status.textContent = 'Deine Nachricht wird gesendet …';
    hint.textContent = '';

    var accepted = false;
    var rejected = false;
    var finished = false;
    var doneData = null;
    var serverError = '';
    var receivedText = false;
    var rawTemporaryAnswer = '';

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
      // The server has saved the question before starting the stream. Clear it now
      // so a later provider error cannot accidentally resend the same message.
      prompt.value = '';
      if (imageInput) imageInput.value = '';
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
            baseStatus = String(eventData.value.message || 'Die KI arbeitet …');
            updateStatus();
            status.textContent = 'Ich denke darüber nach …';
          } else if (eventData.kind === 'delta') {
            var chunk = String(eventData.value.text || '');
            if (temporary) rawTemporaryAnswer += chunk;
            var follow = isAtBottom();
            // Raw deltas always remain inert. Only Markdown HTML generated
            // by the server's locked-down renderer may become markup.
            assistantBubble.content.appendChild(document.createTextNode(chunk));
            if (!receivedText) {
              receivedText = true;
              baseStatus = 'Antwort wird live übertragen …';
              updateStatus();
              status.textContent = 'Ich antworte …';
            }
            if (follow) scrollToLatest();
            else updateJump();
          } else if (eventData.kind === 'heartbeat') {
            baseStatus = 'Die KI arbeitet weiter …';
            updateStatus();
          } else if (eventData.kind === 'render') {
            if (typeof eventData.value.html === 'string') {
              var followRender = isAtBottom();
              assistantBubble.content.classList.add('ai-message-markdown');
              assistantBubble.content.innerHTML = eventData.value.html;
              if (followRender) scrollToLatest();
            }
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
      if (doneData && typeof doneData.html === 'string') {
        assistantBubble.content.classList.add('ai-message-markdown');
        assistantBubble.content.innerHTML = doneData.html;
      }
      progress.remove();
      addAnswerMetadata(assistantBubble.bubble, doneData);
      if (doneData) {
        addForkAction(userBubble.bubble, doneData.user_message_id);
        addForkAction(assistantBubble.bubble, doneData.assistant_message_id);
      }
      if (temporary) {
        // Persist neither the user prompt nor the model answer. Only the
        // current tab's JS memory supplies context on subsequent requests.
        if (rawTemporaryAnswer && rawTemporaryAnswer.length <= 8000) {
          transientHistory.push(
            {role: 'user', content: question},
            {role: 'assistant', content: rawTemporaryAnswer}
          );
          // Bound the context explicitly; omit oldest complete question/answer
          // pairs instead of fabricating a model summary.
          while (transientHistory.length > 12 ||
                 transientHistory.reduce(function (n, row) { return n + row.content.length; }, 0) > 16000) {
            transientHistory.splice(0, 2);
          }
          hint.textContent = '';
        } else {
          transientHistory.length = 0;
          hint.textContent = 'Die letzte Antwort ist für die temporäre Kontextübernahme zu lang. Frühere Nachrichten werden nicht erneut gesendet.';
        }
        status.textContent = 'Nur im Browser-Tab – nicht gespeichert.';
      } else {
        status.textContent = 'Antwort gespeichert.';
        hint.textContent = '';
      }
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
      if (ticker !== null) { window.clearInterval(ticker); ticker = null; }
      activeProgress = null;
      controller = null;
      submit.disabled = initiallyDisabled;
      stop.disabled = true;
      stop.hidden = true;
    }
  });

  form.dataset.aiReady = '1';

  stop.addEventListener('click', function () {
    if (controller) controller.abort();
  });
}());
