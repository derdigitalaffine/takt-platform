(() => {
  'use strict';
  const search = document.querySelector('[data-seminar-search]');
  if (!search) return;
  search.addEventListener('input', () => {
    const query = search.value.trim().toLocaleLowerCase('de');
    for (const card of document.querySelectorAll('[data-seminar-person]')) {
      card.hidden = !card.textContent.toLocaleLowerCase('de').includes(query);
    }
  });
})();
