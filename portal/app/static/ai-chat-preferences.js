/* Display-only preference: this stores a font size, never chat content. */
(function () {
  'use strict';
  var workspace = document.querySelector('[data-ai-workspace]');
  var select = document.querySelector('[data-ai-font-size]');
  if (!workspace || !select) return;

  var allowed = ['14', '16', '18', '20'];
  var key = 'takt-ai-reading-size';
  var fallback = window.self !== window.top ? '14' : '16';
  function apply(value) {
    var safe = allowed.indexOf(String(value)) === -1 ? fallback : String(value);
    select.value = safe;
    workspace.style.setProperty('--ai-reading-size', safe + 'px');
    // The embedded dock shares the setting through same-origin storage.
    return safe;
  }
  try {
    apply(window.localStorage.getItem(key));
  } catch (_) {
    apply(fallback);
  }
  select.addEventListener('change', function () {
    var safe = apply(select.value);
    try { window.localStorage.setItem(key, safe); } catch (_) {
      // Disabled storage must not break the chat or font-size control.
    }
  });
  window.addEventListener('storage', function (event) {
    if (event.key === key) apply(event.newValue);
  });
}());
