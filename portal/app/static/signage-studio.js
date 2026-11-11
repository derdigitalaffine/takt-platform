/* Progressive enhancement; the backend works without JavaScript. */
(() => {
  'use strict';
  const form = document.getElementById('sg-design-form');
  if (!form) {
    const copy = document.querySelector('[data-copy-secret]');
    if (copy) copy.addEventListener('click', () => {
      const value = document.getElementById('sg-secret')?.textContent || '';
      navigator.clipboard?.writeText(value).then(() => {
        copy.textContent = 'Kopiert';
      }).catch(() => { copy.textContent = 'Bitte manuell kopieren'; });
    });
    return;
  }
  const frame = document.getElementById('sg-live-frame');
  const previewStatus = document.getElementById('sg-live-status');
  let refreshTimer = null;
  let controller = null;
  const previewEndpoint = form.action.replace(/save$/, 'preview-live');
  function queueLivePreview() {
    if (!frame || !previewStatus) return;
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(async () => {
      if (controller) controller.abort();
      controller = new AbortController();
      previewStatus.textContent = 'Vorschau wird aktualisiert …';
      try {
        const response = await fetch(previewEndpoint, {
          method: 'POST', body: new FormData(form),
          headers: { 'Accept': 'text/html' },
          credentials: 'same-origin', signal: controller.signal,
        });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const html = await response.text();
        frame.srcdoc = html;
        previewStatus.textContent = 'Aktuelle Vorschau, noch nicht gespeichert';
      } catch (err) {
        if (err.name !== 'AbortError') {
          previewStatus.textContent = 'Vorschau momentan nicht erreichbar. Gespeichertes Design bleibt verfügbar.';
        }
      }
    }, 650);
  }
  form.addEventListener('input', queueLivePreview);
  form.addEventListener('change', queueLivePreview);
    const list = document.getElementById('sg-widget-list');
  const hidden = document.getElementById('sg-layout-json');
  let initial = [];
  try { initial = JSON.parse(hidden.value); } catch (_) { /* defaults remain */ }
  if (Array.isArray(initial)) {
    const ordered = initial.map(key => [...list.children].find(item => item.dataset.widget === key)).filter(Boolean);
    ordered.forEach(item => list.appendChild(item));
  }
  function sync() {
    hidden.value = JSON.stringify([...list.querySelectorAll('.sg-widget-choice')]
      .filter(item => item.querySelector('input').checked).map(item => item.dataset.widget));
    queueLivePreview();
  }
  list.addEventListener('change', sync);
  list.addEventListener('click', event => {
    const btn = event.target.closest('.sg-widget-up,.sg-widget-down');
    if (!btn) return;
    const item = btn.closest('.sg-widget-choice');
    if (btn.classList.contains('sg-widget-up') && item.previousElementSibling) {
      list.insertBefore(item, item.previousElementSibling);
    } else if (btn.classList.contains('sg-widget-down') && item.nextElementSibling) {
      list.insertBefore(item.nextElementSibling, item);
    }
    sync();
    btn.focus();
  });
  let dragging = null;
  list.addEventListener('dragstart', event => {
    const item = event.target.closest('.sg-widget-choice');
    if (!item) return;
    dragging = item;
    item.classList.add('is-dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', item.dataset.widget);
  });
  list.addEventListener('dragover', event => {
    if (!dragging) return;
    event.preventDefault();
    const over = event.target.closest('.sg-widget-choice');
    if (over && over !== dragging) {
      const top = over.getBoundingClientRect().top + over.offsetHeight / 2;
      list.insertBefore(dragging, event.clientY > top ? over.nextSibling : over);
    }
  });
  list.addEventListener('drop', event => { event.preventDefault(); sync(); });
  list.addEventListener('dragend', () => {
    if (dragging) dragging.classList.remove('is-dragging');
    dragging = null;
    sync();
  });
  const shell = document.getElementById('sg-preview-shell');
  document.querySelectorAll('[data-aspect]').forEach(btn => btn.addEventListener('click', () => {
    const portrait = btn.dataset.aspect === 'portrait';
    shell.classList.toggle('is-portrait', portrait);
    document.querySelectorAll('[data-aspect]').forEach(other => {
      other.classList.toggle('is-active', other === btn);
      other.setAttribute('aria-pressed', String(other === btn));
    });
  }));
  const colors = [...form.querySelectorAll('input[type=color]')];
  const contrastMessage = document.getElementById('sg-contrast-alert');
  function luminance(hex) {
    const rgb = [1,3,5].map(i => parseInt(hex.slice(i, i+2), 16)/255)
      .map(n => n <= .04045 ? n/12.92 : Math.pow((n+.055)/1.055,2.4));
    return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];
  }
  function applyColors() {
    const selected = Object.fromEntries(colors.map(color => [color.name, color.value]));
    if (frame.contentDocument) {
      const style = frame.contentDocument.body.style;
      style.setProperty('--sg-bg', selected.background);
      style.setProperty('--sg-fg', selected.foreground);
      style.setProperty('--sg-accent', selected.accent);
    }
    const l1 = luminance(selected.background), l2 = luminance(selected.foreground);
    const contrast = (Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);
    contrastMessage.textContent = contrast < 4.5
      ? 'Kontrastwarnung: Text und Hintergrund sind schwer lesbar ('+contrast.toFixed(1)+':1).'
      : 'Textkontrast '+contrast.toFixed(1)+':1 – gut lesbar.';
  }
  colors.forEach(color => color.addEventListener('input', applyColors));
  frame?.addEventListener('load', applyColors);
  applyColors();
  form.addEventListener('submit', sync);
  sync();
})();
