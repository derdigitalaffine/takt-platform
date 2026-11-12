/* Native checkboxes keep the form usable without JavaScript. All rights stay on the server. */
window.taktInitSelectionPicker = () => {
  const fold = (value) =>
    value
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/ß/g, "ss")
      .toLocaleLowerCase()
      .trim();
  let pickerMeta = {people:{}, organizations:[]};
  try {
    const node = document.querySelector('#takt-person-picker-meta');
    if (node) pickerMeta = JSON.parse(node.textContent);
  } catch (_) {}
  const personMap = pickerMeta.people || {};
  const organizations = pickerMeta.organizations || [];
  for (const root of document.querySelectorAll("[data-selection-picker]")) {
    const search = root.querySelector("[data-selection-search]"),
      kind = root.querySelector("[data-selection-kind]");
    const rows = [...root.querySelectorAll("[data-selection-option]")];
    const surnames = window.TaktPersonPicker?.sortKey;
    if (surnames) {
      const collator = new Intl.Collator('de', {sensitivity:'base', numeric:true});
      const parent = root.querySelector('.selection-options');
      const placeholder = root.querySelector('[data-selection-empty]');
      rows.sort((a,b) => {
        if (a.dataset.kind !== b.dataset.kind) return a.dataset.kind === 'person' ? -1 : 1;
        if (a.dataset.kind !== 'person') return 0;
        const nameA = surnames(a.querySelector('[data-selection-title]')?.textContent);
        const nameB = surnames(b.querySelector('[data-selection-title]')?.textContent);
        return collator.compare(nameA[0],nameB[0]) || collator.compare(nameA[1],nameB[1]);
      }).forEach(row => parent.insertBefore(row, placeholder));
    }
    // This picker intentionally retains its checkbox and group semantics.
    // Organizational filtering only applies to users the server already
    // exposed on the current page; never retrieve an unrestricted directory.
    let orgFilter = null;
    const availableOrgs = new Set();
    for (const row of rows) {
      if (row.dataset.kind !== 'person') continue;
      const id = row.querySelector('[data-selection-check]')?.value.replace(/^user:/, '');
      for (const orgId of personMap[id]?.orgs || []) availableOrgs.add(orgId);
    }
    if (availableOrgs.size) {
      const control = document.createElement('select');
      control.className = 'form-select w-auto';
      control.dataset.selectionOrg = '1';
      control.setAttribute('aria-label', 'Organisationseinheit filtern');
      control.add(new Option('Alle Organisationseinheiten', ''));
      for (const org of organizations) {
        if (availableOrgs.has(org.id)) control.add(new Option(org.path || org.name, String(org.id)));
      }
      const bar = search.closest('.d-flex');
      bar?.append(control);
      orgFilter = control;
    }
    const checks = rows.map((row) =>
      row.querySelector("[data-selection-check]"),
    );
    const error = root.querySelector("[data-selection-error]");
    const max = Number(root.dataset.max) || 500;
    const selected = () => checks.filter((c) => c.checked && !c.disabled);
    function render() {
      const terms = fold(search.value).split(/\s+/).filter(Boolean);
      let visible = 0;
      for (const row of rows) {
        row.hidden =
          (!!kind?.value && row.dataset.kind !== kind.value) ||
          (!!orgFilter?.value && (row.dataset.kind !== 'person' ||
            !(personMap[row.querySelector('[data-selection-check]').value.replace(/^user:/, '')]?.orgs || [])
              .includes(Number(orgFilter.value)))) ||
          !terms.every((term) => fold(row.dataset.search).includes(term));
        if (!row.hidden) visible++;
      }
      root.querySelector("[data-selection-empty]").hidden = visible > 0;
      root.querySelector("[data-selection-all]").disabled = !rows.some(
        (row, i) => !row.hidden && !checks[i].disabled && !checks[i].checked,
      );
      const chosen = selected();
      root.querySelector("[data-selection-count]").textContent =
        `${chosen.length} ausgewählt · ${visible} Treffer`;
      const chips = root.querySelector("[data-selection-chips]");
      chips.replaceChildren();
      for (const input of chosen.slice(0, 8)) {
        const title = input
          .closest("[data-selection-option]")
          .querySelector("[data-selection-title]").textContent;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "selection-chip";
        button.textContent = title + " ×";
        button.setAttribute("aria-label", title + " aus Auswahl entfernen");
        button.addEventListener("click", () => {
          input.checked = false;
          render();
          search.focus();
        });
        chips.append(button);
      }
      if (chosen.length > 8) {
        const rest = document.createElement("span");
        rest.className = "small align-self-center";
        rest.textContent = `+ ${chosen.length - 8} weitere`;
        chips.append(rest);
      }
      root
        .closest("form")
        ?.querySelectorAll("[data-selection-submit]")
        .forEach((button) => (button.disabled = !chosen.length));
    }
    search.addEventListener("input", render);
    kind?.addEventListener("change", render);
    orgFilter?.addEventListener("change", render);
    search.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        search.value = "";
        render();
      }
      if (event.key === "Enter") {
        event.preventDefault();
        const available = rows.filter(
          (row, i) => !row.hidden && !checks[i].disabled,
        );
        if (available.length === 1) {
          const input = available[0].querySelector("input");
          if (!input.checked && selected().length >= max) {
            error.textContent = `Höchstens ${max} Einträge auswählen.`;
            return;
          }
          input.checked = true;
          search.value = "";
          render();
        } else available[0]?.querySelector("input").focus();
      }
    });
    root.addEventListener("change", (event) => {
      if (event.target.matches("[data-selection-check]")) {
        if (selected().length > max) {
          event.target.checked = false;
          error.textContent = `Höchstens ${max} Einträge auswählen.`;
        } else error.textContent = "";
        render();
      }
    });
    root.querySelector("[data-selection-all]").addEventListener("click", () => {
      const additions = rows.filter(
        (row, i) => !row.hidden && !checks[i].disabled && !checks[i].checked,
      );
      if (selected().length + additions.length > max) {
        error.textContent = `Höchstens ${max} Einträge auswählen. Bitte Suche einschränken.`;
        return;
      }
      for (const row of additions) row.querySelector("input").checked = true;
      error.textContent = "";
      render();
    });
    root
      .querySelector("[data-selection-clear]")
      .addEventListener("click", () => {
        checks.forEach((input) => (input.checked = false));
        error.textContent = "";
        render();
      });
    root.closest("form")?.addEventListener("submit", (event) => {
      if (!selected().length) {
        event.preventDefault();
        error.textContent = "Mindestens einen Eintrag auswählen.";
        search.focus();
      }
    });
    render();
  }
};
window.taktInitSelectionPicker();
