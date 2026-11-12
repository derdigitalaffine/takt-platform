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
    const orgPathCache = new Map();
    const orgPathFor = value => {
      const key = String(value);
      if (orgPathCache.has(key)) return orgPathCache.get(key);
      const ids = new Set(people[key]?.orgs || []);
      const path = orgs.filter(org => ids.has(org.id))
        .sort((a, b) => (b.path || '').length - (a.path || '').length)[0]?.path || '';
      orgPathCache.set(key, path);
      return path;
    };
    const fullLabel = value => String(value || '').replace(/\s*\([^)]*@[^)]*\)\s*$/, '').trim();
    const initials = label => {
      const chunks = fullLabel(label).split(/[\s,]+/).filter(Boolean);
      return (chunks.length > 1 ? chunks[0][0] + chunks[chunks.length - 1][0]
        : (chunks[0] || '?').slice(0, 2)).toLocaleUpperCase('de-DE');
    };
    const control = new window.TomSelect(select, {
      create: false,
      allowEmptyOption: true,
      maxOptions: 120,
      // Prevent results from covering the submit button after selection.
      // The picker is immediately reusable and the selected chips persist.
      closeAfterSelect: true,
      clearAfterSelect: true,
      searchField: ['text', 'value'],
      sortField: [{field: '$order', direction: 'asc'}],
      plugins: select.multiple ? ['remove_button'] : [],
      placeholder: select.multiple ? 'Personen auswählen oder suchen …' : 'Person suchen oder auswählen …',
      score: function(query) {
        const needle = search(query);
        return function(option) {
          const haystack = search((option.text || '') + ' ' + orgPathFor(option.value));
          return needle && !haystack.includes(needle) ? 0 : 1;
        };
      },
      render: {
        option: function(item, escape) {
          const name = fullLabel(item.text || '');
          const details = orgPathFor(item.value);
          return '<div class="pp-person-result">'
            + '<span class="pp-person-avatar" aria-hidden="true">' + escape(initials(name)) + '</span>'
            + '<span class="pp-person-lines"><strong>' + escape(name) + '</strong>'
            + (details ? '<small>' + escape(details) + '</small>' : '') + '</span>'
            + '</div>';
        },
        item: function(item, escape) {
          return '<div class="pp-selected-item">' + escape(fullLabel(item.text || '')) + '</div>';
        },
        no_results: () => '<div class="pp-empty">Keine passenden Personen. Bitte Namen oder Organisation prüfen.</div>'
      }
    });
    // Tom Select's Sifter may treat an empty query as 'all results',
    // skipping custom score filters. Filter the returned result set instead:
    // this works with empty/nonempty searches and every dropdown refresh.
    // Never remove or disable options: selected values must survive a
    // cross-organization multi-select without changing form submission.
    const baseSearch = control.search.bind(control);
    const selectedUsers = new Set([...select.options].map(option => option.value)
      .filter(value => value && value !== '0'));
    function inOrg(value) {
      if (!orgFilter) return true;
      const memberships = people[String(value)]?.orgs || [];
      if (orgFilter === '__without__') return !memberships.length;
      return memberships.includes(Number(orgFilter));
    }
    control.search = function(query) {
      const response = baseSearch(query);
      if (!orgFilter) return response;
      const filtered = response.items.filter(row => inOrg(String(row.id)));
      return {...response, items: filtered, total: filtered.length};
    };
    control.wrapper.classList.add('pp-person-control');
    control.wrapper.dataset.personPicker = '1';
    control.wrapper.classList.toggle('pp-multiple', select.multiple);
    const actions = document.createElement('div');
    actions.className = 'pp-picker-actions';
    const selectionStatus = document.createElement('span');
    selectionStatus.className = 'pp-picker-count';
    selectionStatus.setAttribute('role', 'status');
    selectionStatus.setAttribute('aria-live', 'polite');
    actions.append(selectionStatus);
    if (select.multiple) {
      const clearButton = document.createElement('button');
      clearButton.type = 'button';
      clearButton.className = 'pp-picker-clear';
      clearButton.textContent = 'Auswahl aufheben';
      clearButton.addEventListener('click', () => {
        control.clear();
        control.focus();
      });
      actions.append(clearButton);
    }
    control.wrapper.insertAdjacentElement('afterend', actions);
    function updateSelection() {
      const count = control.items.length;
      selectionStatus.textContent = select.multiple
        ? (count ? count + ' Personen ausgewählt' : 'Noch keine Person ausgewählt')
        : (count ? 'Person ausgewählt' : 'Person auswählen');
      const clearButton = actions.querySelector('button');
      if (clearButton) clearButton.hidden = count === 0;
    }
    control.on('change', updateSelection);
    updateSelection();
    // Organization browsing is part of the SAME picker dropdown. A separate
    // select made the UI confusing and did not reliably refresh blank searches.
    // Controls are siblings of the Tom Select listbox, never interactive
    // descendants of listbox options (ARIA APG).
    if (orgs.length && [...selectedUsers].some(value => people[value]?.orgs.length)) {
      const relevant = [...select.options].filter(option => selectedUsers.has(option.value));
      const allowed = new Set(relevant.flatMap(option => people[option.value]?.orgs || []));
      const available = orgs.filter(org => allowed.has(org.id));
      const orgById = new Map(available.map(org => [org.id, org]));
      const children = new Map();
      for (const org of available) {
        const parent = orgById.has(org.parent_id) ? org.parent_id : 0;
        if (!children.has(parent)) children.set(parent, []);
        children.get(parent).push(org);
      }
      // Precompute subtree counts once instead of rescanning every person
      // for every organization (important for large municipal directories).
      const counts = new Map();
      let unassigned = 0;
      for (const option of relevant) {
        const memberships = people[option.value]?.orgs || [];
        if (!memberships.length) unassigned++;
        for (const oid of memberships) counts.set(oid, (counts.get(oid) || 0) + 1);
      }
      const countFor = id => id === '__without__' ? unassigned : (counts.get(Number(id)) || 0);
      const toolbar = document.createElement('div');
      toolbar.className = 'pp-integrated-toolbar';
      toolbar.setAttribute('aria-label', 'Organisationseinheiten filtern');
      const top = document.createElement('div');
      top.className = 'pp-integrated-top';
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'pp-org-toggle';
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-controls', id);
      toggle.textContent = 'Alle Organisationseinheiten';
      const count = document.createElement('span');
      count.className = 'pp-visible-count';
      count.setAttribute('role', 'status');
      count.setAttribute('aria-live', 'polite');
      top.append(toggle, count);
      const panel = document.createElement('div');
      panel.className = 'pp-org-panel';
      panel.id = id;
      panel.hidden = true;
      const hint = document.createElement('p');
      hint.className = 'pp-org-hint';
      hint.textContent = 'Bereich auswählen · Untereinheiten sind eingeschlossen';
      const all = document.createElement('button');
      all.type = 'button';
      all.className = 'pp-org-choice';
      all.dataset.ppOrgId = '';
      all.textContent = 'Alle Organisationseinheiten';
      panel.append(hint, all);
      const tree = document.createElement('ul');
      tree.className = 'pp-org-tree';
      tree.setAttribute('aria-label', 'Organisationseinheiten');
      function branch(org) {
        const li = document.createElement('li');
        li.className = 'pp-org-node';
        const line = document.createElement('div');
        line.className = 'pp-org-line';
        const choice = document.createElement('button');
        choice.type = 'button';
        choice.className = 'pp-org-choice';
        choice.dataset.ppOrgId = String(org.id);
        choice.title = org.path || org.name;
        const name = document.createElement('span');
        name.className = 'pp-org-name';
        name.textContent = org.name;
        const peopleCount = document.createElement('span');
        peopleCount.className = 'pp-org-count';
        const total = countFor(org.id);
        peopleCount.textContent = String(total);
        peopleCount.setAttribute('aria-label', total + ' verfügbare Personen');
        choice.append(name, peopleCount);
        line.append(choice);
        const suborgs = children.get(org.id) || [];
        if (suborgs.length) {
          const expand = document.createElement('button');
          expand.type = 'button';
          expand.className = 'pp-org-expand';
          expand.textContent = '▸';
          expand.setAttribute('aria-label', 'Untereinheiten von ' + org.name + ' anzeigen');
          const sub = document.createElement('ul');
          sub.className = 'pp-org-subtree';
          sub.hidden = true;
          suborgs.forEach(child => sub.append(branch(child)));
          expand.setAttribute('aria-expanded', 'false');
          expand.addEventListener('click', () => {
            sub.hidden = !sub.hidden;
            expand.setAttribute('aria-expanded', String(!sub.hidden));
            expand.textContent = sub.hidden ? '▸' : '▾';
          });
          line.insertBefore(expand, choice);
          li.append(line, sub);
        } else {
          const space = document.createElement('span');
          space.className = 'pp-org-expand-placeholder';
          space.setAttribute('aria-hidden', 'true');
          line.insertBefore(space, choice);
          li.append(line);
        }
        return li;
      }
      (children.get(0) || []).forEach(org => tree.append(branch(org)));
      panel.append(tree);
      if (relevant.some(option => !(people[option.value]?.orgs || []).length)) {
        const noOrg = document.createElement('button');
        noOrg.type = 'button';
        noOrg.className = 'pp-org-choice pp-org-no-assignment';
        noOrg.dataset.ppOrgId = '__without__';
        noOrg.textContent = 'Ohne Organisationszuordnung';
        panel.append(noOrg);
      }
      toolbar.append(top, panel);
      control.dropdown.insertBefore(toolbar, control.dropdown_content);

      // Pointer interactions must not blur Tom Select and close the dropdown
      // before the organization filter can be activated.
      toolbar.addEventListener('mousedown', event => {
        if (event.target.closest('button')) event.preventDefault();
      });
      // Tom Select normally closes on input blur. Keep it open when keyboard
      // navigation moves into our sibling filter toolbar, then close normally
      // when leaving the entire picker. This keeps filters keyboard-accessible.
      const baseBlur = control.onBlur.bind(control);
      control.onBlur = event => {
        if (event?.relatedTarget && toolbar.contains(event.relatedTarget)) return;
        return baseBlur(event);
      };
      toolbar.addEventListener('focusout', event => {
        const next = event.relatedTarget;
        if (!next || (!control.wrapper.contains(next) && !control.dropdown.contains(next))) {
          control.close();
        }
      });
      // Discoverable keyboard shortcut from the one search field. The
      // organization buttons remain normal keyboard-operable buttons.
      control.control_input.addEventListener('keydown', event => {
        if ((event.altKey && event.key === 'ArrowDown') || event.key === 'F4') {
          event.preventDefault();
          event.stopPropagation();
          control.open();
          panel.hidden = false;
          toggle.setAttribute('aria-expanded', 'true');
          toggle.focus();
        }
      });
      function updateFilter(openAfter = true) {
        const current = orgById.get(Number(orgFilter));
        toggle.textContent = orgFilter === '__without__'
          ? 'Ohne Organisation' : current ? current.name : 'Alle Organisationseinheiten';
        toggle.classList.toggle('pp-org-filter-active', !!orgFilter);
        const amount = relevant.filter(option => inOrg(option.value)).length;
        count.textContent = amount + (amount === 1 ? ' Person' : ' Personen');
        panel.querySelectorAll('[data-pp-org-id]').forEach(button => {
          const selected = button.dataset.ppOrgId === orgFilter;
          button.classList.toggle('is-selected', selected);
          button.setAttribute('aria-pressed', String(selected));
        });
        // Tom Select caches result sets by the search string. The search
        // override applies scope *after* scoring, including empty queries.
        control.refreshOptions(false);
        if (openAfter) {
          control.open();
          control.positionDropdown();
        }
      }
      panel.addEventListener('click', event => {
        const choice = event.target.closest('.pp-org-choice');
        if (!choice) return;
        orgFilter = choice.dataset.ppOrgId;
        panel.hidden = true;
        toggle.setAttribute('aria-expanded', 'false');
        updateFilter();
        control.focus();
      });
      toggle.addEventListener('click', () => {
        panel.hidden = !panel.hidden;
        toggle.setAttribute('aria-expanded', String(!panel.hidden));
        control.open();
        control.positionDropdown();
      });
      toolbar.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !panel.hidden) {
          panel.hidden = true;
          toggle.setAttribute('aria-expanded', 'false');
          control.focus();
          event.stopPropagation();
          event.preventDefault();
        }
      });
      control.on('dropdown_close', () => {
        panel.hidden = true;
        toggle.setAttribute('aria-expanded', 'false');
      });
      updateFilter(false);
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
