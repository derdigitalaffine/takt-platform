/* Poll the admin-only fleet API without replacing user-selected filters or focus. */
(() => {
  'use strict';
  const root = document.querySelector('.sg-fleet');
  if (!root) return;
  const search = root.querySelector('[data-fleet-search]');
  const items = [...root.querySelectorAll('[data-fleet-item]')];
  const message = root.querySelector('[data-fleet-message]');
  function filter() {
    const q = (search?.value || '').trim().toLocaleLowerCase('de-DE');
    let count = 0;
    for (const row of items) {
      const matches = !q || row.textContent.toLocaleLowerCase('de-DE').includes(q);
      row.hidden = !matches;
      if (matches) count++;
    }
    if (message && q) message.textContent = count + ' von ' + items.length + ' Geräten';
  }
  search?.addEventListener('input', filter);
  let controller;
  async function refresh() {
    if (document.hidden) return;
    controller?.abort();
    controller = new AbortController();
    try {
      const response = await fetch('/signage/fleet/status', {
        cache: 'no-store', credentials: 'same-origin', signal: controller.signal,
        headers: { Accept: 'application/json' }
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const feed = await response.json();
      if (!feed || !Array.isArray(feed.devices) || !feed.counts) throw new Error('Invalid fleet response');
      for (const [kind, value] of Object.entries(feed.counts)) {
        const counter = root.querySelector('[data-fleet-count="' + kind + '"]');
        if (counter && Number.isSafeInteger(value)) counter.textContent = String(value);
      }
      const byId = new Map(feed.devices.map(device => [String(device.id), device]));
      for (const row of items) {
        const device = byId.get(row.dataset.deviceId);
        if (!device) continue;
        const badge = row.querySelector('[data-fleet-health]');
        const age = row.querySelector('[data-fleet-age]');
        if (badge) {
          badge.className = 'sg-fleet-state state-' + device.status;
          badge.textContent = device.status_label;
          badge.setAttribute('aria-label', 'Zustand ' + device.status_label);
        }
        if (age) age.textContent = device.age_seconds === null
          ? 'Kein aktuelles Signal'
          : 'Letztes Signal vor ' + Math.floor(device.age_seconds / 60) + ' Min.';
      }
      if (message && !search?.value) message.textContent = 'Status aktuell – Abgleich alle 60 Sekunden';
    } catch (error) {
      if (error.name !== 'AbortError' && message) {
        message.textContent = 'Status momentan nicht abrufbar. Angezeigte Werte können veraltet sein.';
      }
    }
  }
  window.setInterval(refresh, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  // Server-rendered snapshot is accurate on first paint. Do not request immediately.
})();
