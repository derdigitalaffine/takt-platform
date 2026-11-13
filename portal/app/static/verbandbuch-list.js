/* Confidential case list: in-memory filtering only; no telemetry, network requests or persistence. */
(() => {
  "use strict";
  const table = document.getElementById("vb-review-table");
  const search = document.getElementById("vb-case-search");
  const site = document.getElementById("vb-case-site");
  const status = document.getElementById("vb-filter-count");
  if (!table || !search || !site || !status) return;
  const rows = [...table.querySelectorAll("[data-vb-case-row]")];
  function filter() {
    const term = search.value.trim().toLocaleLowerCase("de");
    let shown = 0;
    for (const row of rows) {
      const matches = (!site.value || row.dataset.siteId === site.value)
        && (!term || row.textContent.toLocaleLowerCase("de").includes(term));
      row.hidden = !matches;
      if (matches) shown++;
    }
    status.textContent = `${shown} von ${rows.length} Einträgen sichtbar`;
  }
  search.addEventListener("input", filter);
  site.addEventListener("change", filter);
  filter();
})();
