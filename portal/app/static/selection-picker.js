/* Native checkboxes keep the form usable without JavaScript. All rights stay on the server. */
(() => {
  const fold = (value) =>
    value
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/ß/g, "ss")
      .toLocaleLowerCase()
      .trim();
  for (const root of document.querySelectorAll("[data-selection-picker]")) {
    const search = root.querySelector("[data-selection-search]"),
      kind = root.querySelector("[data-selection-kind]");
    const rows = [...root.querySelectorAll("[data-selection-option]")];
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
})();
