/* Global TAKT Agent: progressive, safe text-only UI with explicit write approval. */
(function () {
  'use strict';
  const root = document.querySelector('[data-takt-agent]');
  if (!root || !window.fetch) return;
  const launch = root.querySelector('[data-agent-open]');
  const shade = root.querySelector('[data-agent-shade]');
  const panel = root.querySelector('[data-agent-panel]') || root.querySelector('.takt-agent-panel');
  const close = root.querySelector('[data-agent-close]');
  const messages = root.querySelector('[data-agent-messages]');
  const form = root.querySelector('[data-agent-form]');
  const input = root.querySelector('#takt-agent-input');
  const send = root.querySelector('[data-agent-send]');
  const status = root.querySelector('[data-agent-status]');
  const confirm = root.querySelector('[data-agent-confirm]');
  const proposals = root.querySelector('[data-agent-proposals]');
  const approve = root.querySelector('[data-agent-approve]');
  const reject = root.querySelector('[data-agent-reject]');
  if (![launch, shade, panel, close, messages, form, input, send, status, confirm, proposals, approve, reject].every(Boolean)) return;
  const csrf = document.querySelector('meta[name="csrf"]')?.content || '';
  let pending = '';
  let busy = false;

  function open() {
    shade.hidden = false;
    panel.hidden = false;
    panel.setAttribute('aria-hidden', 'false');
    launch.setAttribute('aria-expanded', 'true');
    document.body.classList.add('takt-agent-open');
    input.focus();
  }
  function hide() {
    shade.hidden = true;
    panel.hidden = true;
    panel.setAttribute('aria-hidden', 'true');
    launch.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('takt-agent-open');
    launch.focus();
  }
  function setBusy(value, label) {
    busy = value;
    send.disabled = value;
    approve.disabled = value;
    input.disabled = value;
    if (label) status.textContent = label;
    else status.textContent = 'Enter senden · Shift+Enter Zeilenumbruch';
  }
  function bubble(text, kind) {
    const el = document.createElement('div');
    el.className = 'takt-agent-message is-' + (kind || 'agent');
    el.textContent = String(text || '');
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
    return el;
  }
  function list(items, max) {
    if (!Array.isArray(items) || !items.length) return;
    const el = document.createElement('ul');
    el.className = 'takt-agent-links';
    items.slice(0, max || 12).forEach(function (item) {
      if (!item || !/^\/(?:aufgaben|anliegen)\/\d+$/.test(item.url || '')) return;
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = item.url;
      a.textContent = item.title || item.label || (item.type + ' #' + item.id);
      li.appendChild(a);
      if (item.status) {
        const label = document.createElement('span');
        label.className = 'small text-secondary';
        label.textContent = ' · ' + item.status;
        li.appendChild(label);
      }
      el.appendChild(li);
    });
    if (items.length > (max || 12)) {
      const remaining = document.createElement('li');
      remaining.textContent = 'Weitere Treffer: ' + (items.length - (max || 12));
      el.appendChild(remaining);
    }
    if (el.children.length) messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }
  async function post(url, params) {
    const data = new FormData();
    data.set('csrf', csrf);
    Object.keys(params).forEach(function (key) { data.set(key, params[key]); });
    const response = await fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Accept': 'application/json'}, body: data
    });
    let json = {};
    try { json = await response.json(); } catch (_) { /* Non-JSON errors are generic. */ }
    if (!response.ok) {
      const detail = json.detail;
      throw new Error(typeof detail === 'string' ? detail : 'Die Anfrage konnte nicht verarbeitet werden (' + response.status + ').');
    }
    return json;
  }
  function clearProposal() {
    pending = '';
    proposals.replaceChildren();
    confirm.hidden = true;
  }
  async function submit() {
    const text = input.value.trim();
    if (busy || text.length < 3) return;
    const oldPlan = pending;
    clearProposal();
    bubble(text, 'user');
    input.value = '';
    const progress = bubble('Ich prüfe die verfügbaren Funktionen und suche nach passenden Vorgängen …', 'agent');
    setBusy(true, 'TAKT Agent plant …');
    try {
      if (oldPlan) await post('/agent/cancel', {plan_id: oldPlan});
      const data = await post('/agent/plan', {prompt: text});
      progress.textContent = data.message || 'Ergebnis';
      if (Array.isArray(data.steps)) data.steps.forEach(function (step) {
        bubble(step.label + ': ' + step.count + ' Treffer', 'step');
      });
      list(data.results, 12);
      if (data.plan_id && Array.isArray(data.proposals) && data.proposals.length) {
        pending = data.plan_id;
        data.proposals.forEach(function (label) {
          const li = document.createElement('li');
          li.textContent = label;
          proposals.appendChild(li);
        });
        confirm.hidden = false;
        bubble('Bitte bestätigen Sie die vorbereiteten Änderungen oder verwerfen Sie sie.', 'agent');
      }
    } catch (error) {
      progress.classList.add('is-error');
      progress.textContent = error.message || 'Der Arbeitsplan konnte nicht erstellt werden.';
    } finally {
      setBusy(false);
      messages.scrollTop = messages.scrollHeight;
    }
  }
  async function execute() {
    if (busy || !pending) return;
    const token = pending;
    clearProposal(); // Confirmation is single-use even if the request fails.
    setBusy(true, 'TAKT speichert die freigegebenen Änderungen …');
    const progress = bubble('Ich führe die bestätigten Schritte aus …', 'agent');
    try {
      const data = await post('/agent/execute', {plan_id: token});
      progress.textContent = data.message || 'Änderungen gespeichert.';
      list(data.applied, 12);
    } catch (error) {
      progress.classList.add('is-error');
      progress.textContent = error.message || 'Die Änderungen konnten nicht gespeichert werden.';
    } finally {
      setBusy(false);
    }
  }
  launch.addEventListener('click', open);
  shade.addEventListener('click', hide);
  close.addEventListener('click', hide);
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && !panel.hidden) hide();
  });
  root.querySelectorAll('[data-agent-sample]').forEach(function (button) {
    button.addEventListener('click', function () {
      input.value = button.dataset.agentSample;
      input.focus();
    });
  });
  form.addEventListener('submit', function (event) { event.preventDefault(); submit(); });
  input.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      submit();
    }
  });
  approve.addEventListener('click', execute);
  reject.addEventListener('click', async function () {
    if (busy || !pending) return;
    const token = pending;
    clearProposal();
    setBusy(true, 'Vorschlag wird verworfen …');
    try {
      await post('/agent/cancel', {plan_id: token});
      bubble('Vorschlag verworfen. Es wurde nichts verändert.', 'agent');
    } catch (error) {
      bubble(error.message || 'Vorschlag lokal verworfen. Laden Sie die Seite neu.', 'error');
    } finally { setBusy(false); }
  });
})();
