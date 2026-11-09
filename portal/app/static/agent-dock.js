(() => {
  'use strict';
  const root = document.querySelector('[data-agent-dock]');
  if (!root || window.self !== window.top) return;
  const button = root.querySelector('[data-agent-open]');
  const panel = root.querySelector('#agent-dock-panel');
  const frame = root.querySelector('[data-agent-frame]');
  function close() { panel.hidden = true; button.setAttribute('aria-expanded', 'false'); button.focus(); }
  function place() {
    const header = document.querySelector('.app-topbar, header, .navbar');
    const bottom = header ? Math.max(0, header.getBoundingClientRect().bottom) : 0;
    root.style.setProperty('--agent-top', Math.min(bottom + 8, 120) + 'px');
  }
  button.addEventListener('click', () => {
    if (!panel.hidden) return close();
    place(); panel.hidden = false; button.setAttribute('aria-expanded', 'true');
    if (frame.getAttribute('src') === 'about:blank') frame.src = '/agent?panel=1';
    root.querySelector('[data-agent-close]').focus();
  });
  root.querySelector('[data-agent-close]').addEventListener('click', close);
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !panel.hidden) close(); });
  frame.addEventListener('load', () => {
    try {
      const doc = frame.contentDocument;
      if (!doc || !/^\/(agent|ki)$/.test(frame.contentWindow.location.pathname)) return;
      doc.documentElement.dataset.agentEmbedded = 'true';
      const url = new URL(frame.contentWindow.location.href);
      const chatId = url.searchParams.get('chat');
      root.querySelector('[data-agent-detach]').href = '/agent' + (chatId && /^\d+$/.test(chatId) ? '?chat=' + chatId : '');
      const workspace = doc.querySelector('[data-ai-workspace]');
      if (workspace && !doc.querySelector('.agent-embedded-tools')) {
        const tools = doc.createElement('div'); tools.className = 'agent-embedded-tools';
        const choice = doc.createElement('select'); choice.className = 'form-select form-select-sm'; choice.setAttribute('aria-label', 'Unterhaltung wählen');
        const placeholder = doc.createElement('option'); placeholder.value = ''; placeholder.textContent = 'Unterhaltungen'; choice.append(placeholder);
        for (const link of doc.querySelectorAll('.ai-chat-sidebar a[href]')) {
          const href = link.getAttribute('href');
          if (!/^\/agent\?chat=\d+$/.test(href)) continue;
          const option = doc.createElement('option'); option.value = href; option.textContent = link.textContent.trim(); option.selected = link.hasAttribute('aria-current'); choice.append(option);
        }
        choice.addEventListener('change', () => { if (/^\/agent\?chat=\d+$/.test(choice.value)) frame.contentWindow.location.assign(choice.value); });
        tools.append(choice);
        const newChat = doc.querySelector('form[action="/agent/new"]');
        if (newChat) tools.append(newChat.cloneNode(true));
        workspace.before(tools);
      }
      frame.contentWindow.dispatchEvent(new Event('resize'));
      frame.contentWindow.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
    } catch (_) { /* Expired sessions retain the ordinary login boundary. */ }
  });
  window.addEventListener('resize', place);
})();
