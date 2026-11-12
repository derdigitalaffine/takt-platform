/* A single portal-wide person picker, progressively enhanced from native <select>.
   Only fields semantically selecting portal users are touched. Existing names,
   values, 'multiple' and required/disabled semantics remain unchanged. */
(() => {
  'use strict';
  const metaNode = document.querySelector('#takt-person-picker-meta');
  let metadata = {people: {}, organizations: []};
  try { if (metaNode) metadata = JSON.parse(metaNode.textContent); } catch (_) {}
  const people = metadata.people || {};
  const orgs = Array.isArray(metadata.organizations) ? metadata.organizations : [];
  const collator = new Intl.Collator('de', {sensitivity: 'base', numeric: true});
  const fields = /^(?:(?:user|users|person|persons|employee|employees|staff|assignee|creator|owner|recipient|recipients|participant|participants|member|members|caretaker|caretakers|teacher|teachers|lecturer|lecturers|approver|delegate|deputy|substitute|reviewer|editor|responsible|manager|supervisor|representative|colleague)(?:_ids?|s)?|condition_(?:creator_id|assignee_id)|(?:user|person|member|employee)\[\])$/i;
  const handled = new WeakSet();
  const normal = value => String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('de-DE').trim();
  function surname(label) {
    const name = String(label || '')
      .split(/\s+[·•]\s+/)[0]
      .replace(/\s*\((?:ich|me|selbst)\)\s*$/i, '')
      .replace(/\s*\([^)]*@[^)]*\)\s*$/, '')
      .replace(/\s*<[^>]*>\s*$/, '').trim();
    if (name.includes(',')) {
      const [family, first] = name.split(',', 2);
      return [normal(family), normal(first)];
    }
    const parts = name.split(/\s+/);
    return [normal(parts.pop() || ''), normal(parts.join(' '))];
  }
  function isPerson(select) {
    if (select.dataset.personPicker === 'off') return false;
    if (select.closest('[data-picker]') || select.closest('[data-no-person-picker]')) return false;
    if (select.dataset.personPicker === '1') return true;
    if (!fields.test(select.name || '')) return false;
    const items = [...select.querySelectorAll('option')].filter(o => o.value !== '' && o.value !== '0');
    if (!items.length || items.length > 5000) return false;
    // Avoid turning role, category, group, status or staff-count selections into people.
    if (items.some(o => !/^\d+$/.test(o.value))) return false;
    return true;
  }
  function reorder(select) {
    const parents = [...select.querySelectorAll('optgroup')];
    if (!parents.length) parents.push(select);
    for (const parent of parents) {
      const opts = [...parent.children].filter(o => o.tagName === 'OPTION');
      const placeholders = opts.filter(o => !o.value || o.value === '0');
      const sorted = opts.filter(o => !!o.value && o.value !== '0').sort((a, b) => {
        const aKey = surname(a.textContent), bKey = surname(b.textContent);
        return collator.compare(aKey[0], bKey[0]) || collator.compare(aKey[1], bKey[1])
          || collator.compare(a.textContent, b.textContent);
      });
      for (const option of [...placeholders, ...sorted]) parent.appendChild(option);
    }
  }
  let uid = 0;
  function enhance(select) {
    if (handled.has(select) || !isPerson(select) || typeof window.TomSelect !== 'function') return;
    if (select.tomselect) return; // Respect a module's specialized picker.
    handled.add(select);
    reorder(select);
    const id = 'pp-org-' + (++uid);
    let orgFilter = '';
    const search = query => normal(query);
    const control = new window.TomSelect(select, {
      create: false,
      allowEmptyOption: true,
      maxOptions: 250,
      searchField: ['text', 'value'],
      sortField: [{field: '$order', direction: 'asc'}],
      plugins: select.multiple ? ['remove_button'] : [],
      placeholder: select.multiple ? 'Personen auswählen oder suchen …' : 'Person suchen oder auswählen …',
      score: function(query) {
        const needle = search(query);
        return function(option) {
          const match = people[String(option.value)];
          if (orgFilter === '__without__' && match && match.orgs.length) return 0;
          if (orgFilter && orgFilter !== '__without__'
              && (!match || !match.orgs.includes(Number(orgFilter)))) return 0;
          const haystack = search((option.text || '') + ' ' + (option.value || ''));
          return needle && !haystack.includes(needle) ? 0 : 1;
        };
      },
      render: {
        option: function(item, escape) {
          return '<div>' + escape(item.text || '') + '</div>';
        },
        no_results: () => '<div class="no-results p-2">Keine passenden Personen</div>'
      }
    });
    control.wrapper.classList.add('pp-person-control');
    control.wrapper.dataset.personPicker = '1';
    if (orgs.length && [...select.options].some(option => people[option.value]?.orgs.length)) {
      const box = document.createElement('div');
      box.className = 'pp-org-filter';
      const label = document.createElement('label');
      label.htmlFor = id;
      label.textContent = 'Organisationseinheit';
      const filter = document.createElement('select');
      filter.id = id;
      filter.className = 'form-select form-select-sm';
      filter.dataset.personPicker = 'off';
      const all = document.createElement('option');
      all.value = ''; all.textContent = 'Alle Organisationseinheiten';
      filter.appendChild(all);
      const present = new Set([...select.options].flatMap(option => people[option.value]?.orgs || []));
      for (const org of orgs) {
        if (!present.has(org.id)) continue;
        const option = document.createElement('option');
        option.value = String(org.id);
        option.textContent = org.path || org.name;
        filter.appendChild(option);
      }
      const without = document.createElement('option');
      without.value = '__without__'; without.textContent = 'Ohne Organisationszuordnung';
      filter.appendChild(without);
      label.appendChild(filter);
      box.appendChild(label);
      control.wrapper.insertAdjacentElement('beforebegin', box);
      filter.addEventListener('change', () => {
        orgFilter = filter.value;
        // Filter suggestions, not already chosen option values. Disabling
        // selected native options would silently omit them from form submission.
        control.refreshOptions(false);
      });
    }
  }
  function scan(root) {
    if (root instanceof HTMLSelectElement) enhance(root);
    if (root.querySelectorAll) root.querySelectorAll('select').forEach(enhance);
  }
  scan(document);
  // Offcanvas/modal HTMX-style content can add selects after the initial page.
  const observer = new MutationObserver(records => {
    const added = records.flatMap(record => [...record.addedNodes]).filter(n => n.nodeType === 1);
    for (const node of added) scan(node);
  });
  if (document.body) observer.observe(document.body, {childList: true, subtree: true});
  window.TaktPersonPicker = {enhance: scan, sortKey: surname};
})();
