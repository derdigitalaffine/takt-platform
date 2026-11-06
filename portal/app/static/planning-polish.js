/* Progressive enhancements shared by calendar and leave pages.
   Filtering is visual only; backend permissions and canonical data stay intact. */
window.taktInitPlanningPolish = () => {
  "use strict";
  const root = document.querySelector(".planning-workspace");
  if (!root) return;
  const sourceList = root.querySelector("#calendar-source-list");
  const search = root.querySelector("#calendar-source-search");
  const empty = root.querySelector("#calendar-source-empty");
  const matchCount = root.querySelector("#calendar-source-match-count");
  const checkboxes = sourceList
    ? [...sourceList.querySelectorAll('input[type="checkbox"][data-calendar]')]
    : [];
  const inlineSources = sourceList
    ? [...sourceList.querySelectorAll("form[data-inline-source]")]
    : [];

  function filterSources() {
    if (!sourceList || !search) return;
    const query = search.value.trim().toLocaleLowerCase("de");
    let visible = 0;
    sourceList.querySelectorAll("[data-calendar-source]").forEach((item) => {
      const text = item.textContent.trim().toLocaleLowerCase("de");
      item.hidden = !text.includes(query);
      if (!item.hidden) visible += 1;
    });
    if (empty) empty.hidden = visible !== 0;
    if (matchCount) matchCount.textContent = visible + " von " +
      sourceList.querySelectorAll("[data-calendar-source]").length + " Kalendern";
  }
  search?.addEventListener("input", filterSources);
  filterSources();

  root.querySelectorAll("[data-calendar-choose]").forEach((button) => {
    button.addEventListener("click", () => {
      const selected = button.dataset.calendarChoose === "all";
      // Native clicks preserve the existing FullCalendar source listeners.
      for (const input of checkboxes) {
        if (input.checked !== selected) input.click();
      }
      for (const form of inlineSources) {
        const button = form.querySelector("button[aria-pressed]");
        if (button && (button.getAttribute("aria-pressed") === "true") !== selected)
          form.requestSubmit();
      }
      const live = root.querySelector("#calendar-source-feedback");
      if (live) live.textContent = selected
        ? "Alle verfügbaren Kalender sind eingeblendet."
        : "Alle Kalender sind ausgeblendet. Die Auswahl kann einzeln geändert werden.";
    });
  });
  root.querySelectorAll("[data-planning-open-editor]").forEach((button) => {
    button.addEventListener("click", () => {
      const selector = button.dataset.planningOpenEditor;
      if (selector !== "#event-editor") return;
      const editor = root.querySelector(selector);
      if (!editor || editor.hidden) return;
      editor.open = true;
      const focusTarget = editor.querySelector('input[name="title"]') ||
        editor.querySelector("summary");
      editor.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant" : "smooth",
        block: "start",
      });
      focusTarget?.focus({ preventScroll: true });
    });
  });

  const requestSearch = root.querySelector("#leave-request-search");
  const statusFilter = root.querySelector("#leave-status-filter");
  const filteredCount = root.querySelector("#leave-request-filter-count");
  const emptyResults = root.querySelector("#leave-request-no-matches");
  const requestCards = [...root.querySelectorAll("#leave-request-list .leave-request-card")];
  function filterRequests() {
    if (!requestSearch || !statusFilter) return;
    const term = requestSearch.value.trim().toLocaleLowerCase("de");
    const status = statusFilter.value;
    let count = 0;
    for (const card of requestCards) {
      const searchText = card.querySelector("h3, h2")?.textContent
        .toLocaleLowerCase("de") || "";
      card.hidden = !(searchText.includes(term) &&
        (!status || card.dataset.status === status));
      if (!card.hidden) count += 1;
    }
    if (filteredCount) filteredCount.textContent = count + " von " +
      requestCards.length + " Einträgen";
    if (emptyResults) emptyResults.hidden = count !== 0 || requestCards.length === 0;
  }
  requestSearch?.addEventListener("input", filterRequests);
  statusFilter?.addEventListener("change", filterRequests);
  filterRequests();

  const legendButton = root.querySelector("[data-planning-help]");
  legendButton?.addEventListener("click", () => {
    const detail = root.querySelector("#planning-help-detail");
    if (!detail) return;
    detail.hidden = !detail.hidden;
    legendButton.setAttribute("aria-expanded", String(!detail.hidden));
  });
}};
window.taktInitPlanningPolish();
