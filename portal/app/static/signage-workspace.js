(() => {
  'use strict';
  const search = document.querySelector('[data-sg-screen-search]');
  if (search) {
    const cards = [...document.querySelectorAll('[data-sg-screen-item]')];
    search.addEventListener('input', () => {
      const q = search.value.trim().toLocaleLowerCase('de-DE');
      for (const card of cards) card.hidden = !!q && !card.textContent.toLocaleLowerCase('de-DE').includes(q);
    });
  }
  const treeSearch = document.querySelector('[data-sg-tree-search]');
  if (treeSearch) {
    const root = document.querySelector('.sg-tree-root');
    const count = document.querySelector('[data-sg-tree-count]');
    if (root) {
      const links = [...root.querySelectorAll('.sg-tree-link')];
      const groups = [...root.querySelectorAll('.sg-tree-group')];
      const originallyOpen = new Map(groups.map(group => [group, group.open]));
      const parentFilter = () => {
        for (const select of document.querySelectorAll('select[name="parent_id"],select[name="part_id"]')) {
          const form = select.closest('form');
          const building = form?.querySelector('[name="building_id"]')?.value;
          if (!building) continue;
          for (const option of select.options) {
            if (!option.value) continue;
            const visible = option.dataset.sgBuilding === building;
            option.disabled = !visible; option.hidden = !visible;
          }
          if (select.selectedOptions[0]?.disabled) select.value = '';
        }
      };
      document.querySelectorAll('.sg-add-group form [name="building_id"]').forEach(
        field => field.addEventListener('change', parentFilter));
      parentFilter();
      treeSearch.addEventListener('input', () => {
        const q = treeSearch.value.trim().toLocaleLowerCase('de-DE');
        let countVisible = 0;
        for (const link of links) {
          const show = !q || link.textContent.toLocaleLowerCase('de-DE').includes(q);
          link.parentElement.hidden = !show;
          if (show && q) countVisible++;
        }
        for (const group of groups.slice().reverse()) {
          if (!q) {
            group.hidden = false;
            group.open = originallyOpen.get(group);
            continue;
          }
          const summaryMatch = (group.querySelector(':scope > summary')?.textContent || '')
            .toLocaleLowerCase('de-DE').includes(q);
          const descendants = [...group.querySelectorAll('.sg-tree-link')];
          const childGroups = [...group.querySelectorAll('.sg-tree-group')];
          const hasMatches = summaryMatch
            || descendants.some(link => !link.parentElement.hidden)
            || childGroups.some(child => !child.hidden);
          group.hidden = !hasMatches;
          group.open = hasMatches;
          if (summaryMatch) {
            for (const link of descendants) link.parentElement.hidden = false;
            for (const child of childGroups) { child.hidden = false; child.open = true; }
          }
        }
        if (count) count.textContent = q
          ? (countVisible ? countVisible + ' passende Einträge' : 'Keine passenden Einträge')
          : '';
      });
    }
  }
})();
