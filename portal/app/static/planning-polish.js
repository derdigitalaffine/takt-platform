/* Progressive enhancements shared by calendar and leave pages.
   Filtering is visual only; backend permissions and canonical data stay intact. */
(() => {
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

  const legendButton = root.querySelector("[data-planning-help]");
  legendButton?.addEventListener("click", () => {
    const detail = root.querySelector("#planning-help-detail");
    if (!detail) return;
    detail.hidden = !detail.hidden;
    legendButton.setAttribute("aria-expanded", String(!detail.hidden));
  });
})();
