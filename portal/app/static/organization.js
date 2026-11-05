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
  search.addEventListener("input", () => {
    const query = search.value.toLocaleLowerCase().trim();
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
    document.querySelector("[data-org-empty]").hidden = visible.size > 0;
  });
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
  window.addEventListener("hashchange", openHash);
  openHash();
})();
