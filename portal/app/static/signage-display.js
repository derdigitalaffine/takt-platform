(() => {
  'use strict';
  function updateClock() {
    const now = new Date();
    const label = new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' }).format(now);
    const date = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Berlin' }).format(now);
    document.querySelectorAll('[data-sg-time]').forEach(el => { el.textContent = label; });
    document.querySelectorAll('[data-sg-date]').forEach(el => { el.textContent = date; });
  }
  document.querySelectorAll('[data-sg-search]').forEach(input => {
    const section = input.closest('section');
    const entries = [...section.querySelectorAll('[data-sg-entry]')];
    const status = document.createElement('p');
    status.className = 'sd-search-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    input.parentElement.insertAdjacentElement('afterend', status);
    function filter() {
      const query = input.value.toLocaleLowerCase('de-DE').trim();
      let count = 0;
      entries.forEach(entry => {
        const match = !query || entry.textContent.toLocaleLowerCase('de-DE').includes(query);
        entry.hidden = !match;
        if (match) count++;
      });
      status.textContent = query ? count + (count === 1 ? ' Treffer' : ' Treffer') : '';
    }
    input.addEventListener('input', filter);
  });
  updateClock();
  setInterval(updateClock, 15000);
})();
