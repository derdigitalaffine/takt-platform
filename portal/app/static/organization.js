/* Discovery only; permissions and transactions remain on the server. */
(() => {
  const search = document.querySelector("[data-org-search]");
  if (!search) return;
  const tree = document.querySelector(".org-tree"),
    active = tree?.querySelector("[aria-current]");
  if (active)
    tree.scrollTop +=
      active.getBoundingClientRect().top -
      tree.getBoundingClientRect().top -
      tree.clientHeight / 2;
  const rows = [...document.querySelectorAll("[data-org-row]")],
    byId = new Map(rows.map((row) => [row.dataset.id, row]));
  const tableSearch = document.querySelector("[data-org-table-search]");
  const tableRows = [...document.querySelectorAll("[data-org-table-row]")];
  function filterOrganizations(input) {
    const query = input.value.toLocaleLowerCase().trim();
    if (input !== search) search.value = input.value;
    if (tableSearch && input !== tableSearch) tableSearch.value = input.value;
    const visible = new Set();
    for (const row of rows) {
      if (!row.dataset.name.includes(query)) continue;
      let current = row;
      while (current && !visible.has(current)) {
        visible.add(current);
        current = byId.get(current.dataset.parent);
      }
    }
    rows.forEach((row) => (row.hidden = !visible.has(row)));
    tableRows.forEach((row) => (row.hidden = !row.dataset.name.includes(query)));
    document.querySelector("[data-org-empty]").hidden = visible.size > 0;
  }
  search.addEventListener("input", () => filterOrganizations(search));
  tableSearch?.addEventListener("input", () => filterOrganizations(tableSearch));
  function openHash() {
    const target = location.hash
      ? document.getElementById(location.hash.slice(1))
      : null;
    if (target?.tagName === "DETAILS") target.open = true;
  }
  document.querySelectorAll("[data-org-open]").forEach((link) =>
    link.addEventListener("click", () => {
      const target = document.getElementById(link.hash.slice(1));
      if (target) target.open = true;
    }),
  );
  const batch = document.querySelector("[data-org-role-batch]");
  if (batch) {
    const preview = batch.querySelector("[data-org-batch-preview]");
    const renderPreview = () => {
      const recipients = [...batch.querySelectorAll('input[name="targets"]:checked')]
        .map((input) => input.closest("label")?.querySelector("[data-selection-title]")?.textContent.trim() || input.value);
      const roles = [...batch.querySelectorAll('input[name="roles"]:checked')]
        .map((input) => {
          const card = input.closest(".org-role-choice");
          const label = card.querySelector(".form-check-label")?.textContent.trim() || input.value;
          const subtree = card.querySelector('input[name^="children_"]')?.checked;
          return label + (subtree ? " (mit Untereinheiten)" : " (nur diese Einheit)");
        });
      preview.replaceChildren();
      const header = document.createElement("strong");
      header.textContent = roles.length + " Rollen für " + recipients.length + " ausgewählte Personen/Gruppen ergänzen";
      preview.append(header);
      if (!recipients.length || !roles.length) {
        preview.append(document.createTextNode(" · Bitte Empfänger und Rollen wählen."));
        return;
      }
      const list = document.createElement("ul");
      list.className = "mt-2 mb-0";
      for (const recipient of recipients) {
        const li = document.createElement("li");
        li.textContent = recipient + ": " + roles.join(", ");
        list.append(li);
      }

      preview.append(list);
    };
    batch.addEventListener("change", renderPreview);
    batch.addEventListener("click", (event) => {
      if (event.target.closest("[data-selection-all], [data-selection-clear]"))
        requestAnimationFrame(renderPreview);
    });
    batch.addEventListener("submit", (event) => {
      if (!batch.querySelector('input[name="roles"]:checked') ||
          !batch.querySelector('input[name="targets"]:checked')) {
        event.preventDefault();
        preview.textContent = "Mindestens eine Rolle und eine Person/Gruppe auswählen.";
        preview.focus();
      }
    });
    preview.tabIndex = -1;
    renderPreview();
  }
  // Large departments remain navigable: keep the first 30 people visible,
  // search through all records and reveal the next batch on demand. Without JS
  // every row remains visible and forms keep working unchanged.
  const memberSearch = document.querySelector("[data-org-member-search]");
  const memberList = document.querySelector("[data-org-member-list]");
  const members = [...document.querySelectorAll("[data-org-member-row]")];
  const memberCounter = document.querySelector("[data-org-member-count]");
  if (memberSearch && memberList) {
    let batchSize = 30;
    const more = document.createElement("button");
    more.type = "button";
    more.className = "btn btn-outline-secondary btn-sm mb-3";
    more.textContent = "Weitere Personen anzeigen";
    more.setAttribute("aria-label", "Weitere Personen dieser Organisationseinheit anzeigen");
    memberList.insertAdjacentElement("afterend", more);
    const showMembers = () => {
      const value = memberSearch.value.toLocaleLowerCase().trim();
      const matches = members.filter(row => (row.dataset.name || "").includes(value));
      members.forEach(row => { row.hidden = !matches.includes(row) || matches.indexOf(row) >= batchSize; });
      more.hidden = matches.length <= batchSize;
      memberCounter.textContent = matches.length + " passende Zuordnungen" +
        (matches.length > batchSize ? " · " + batchSize + " angezeigt" : "");
    };
    memberSearch.addEventListener("input", () => { batchSize = 30; showMembers(); });
    more.addEventListener("click", () => { batchSize += 30; showMembers(); });
    showMembers();
  }
  const roleSearch = document.querySelector("[data-org-role-search]");
  const roleEntries = [...document.querySelectorAll("[data-org-role-entry]")];
  const roleCounter = document.querySelector("[data-org-role-count]");
  if (roleSearch && roleCounter) {
    const showRoles = () => {
      const query = roleSearch.value.toLocaleLowerCase().trim();
      let matches = 0;
      roleEntries.forEach(row => {
        const show = (row.dataset.name || "").includes(query);
        row.hidden = !show;
        if (show) matches++;
      });
      roleCounter.textContent = matches + " passende Rollenempfänger";
    };
    roleSearch.addEventListener("input", showRoles);
    showRoles();
  }
  window.addEventListener("hashchange", openHash);
  openHash();
})();
