(() => {
  'use strict';
  function updateClock() {
    const now = new Date();
    const label = new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' }).format(now);
    const date = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Berlin' }).format(now);
    document.querySelectorAll('[data-sg-time]').forEach(el => { el.textContent = label; });
    document.querySelectorAll('[data-sg-date]').forEach(el => { el.textContent = date; });
  }
  updateClock();
  setInterval(updateClock, 15000);
})();
