/* Vertrauliche Fachablage: ausschließlich lokaler Filter, ohne Telemetrie oder Persistenz. */
(() => {
  "use strict";
  const table = document.getElementById("vb-review-table");
  const search = document.getElementById("vb-case-search");
  const site = document.getElementById("vb-case-site");
  const status = document.getElementById("vb-filter-count");
  const reset = document.getElementById("vb-filter-reset");
  const empty = document.getElementById("vb-filter-empty");
  if (!table || !search || !site || !status) return;
  const rows = [...table.querySelectorAll("[data-vb-case-row]")];
  const normalize = value => String(value || "").normalize("NFKC").toLocaleLowerCase("de").trim();
  function filter() {
    const term = normalize(search.value);
    const selectedSite = site.value;
    let shown = 0;
    for (const row of rows) {
      // Ausschließlich Aktenzeichen und Standort durchsuchen, keine Gesundheitsfelder.
      const fields = row.querySelectorAll("td");
      const searchable = normalize([fields[0]?.textContent, fields[2]?.textContent].join(" "));
      const matches = (!selectedSite || row.dataset.siteId === selectedSite) && (!term || searchable.includes(term));
      row.hidden = !matches;
      if (matches) shown++;
    }
    status.textContent = shown === 1 ? "1 Eintrag sichtbar" : `${shown} von ${rows.length} Einträgen sichtbar`;
    if (empty) empty.hidden = shown !== 0;
    if (reset) reset.hidden = !term && !selectedSite;
  }
  search.addEventListener("input", filter);
  site.addEventListener("change", filter);
  if (reset) reset.addEventListener("click", () => {
    search.value = "";
    site.value = "";
    filter();
    search.focus();
  });
  filter();
})();
