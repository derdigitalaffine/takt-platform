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
      frame.contentWindow.dispatchEvent(new Event('resize'));
      frame.contentWindow.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
    } catch (_) { /* Expired sessions retain the ordinary login boundary. */ }
  });
  window.addEventListener('resize', place);
})();
