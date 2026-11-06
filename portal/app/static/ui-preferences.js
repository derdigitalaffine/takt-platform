/* Lightweight account-backed presentation preferences; no permission changes. */
window.taktInitUiPreferences = () => {
  "use strict";
  window.taktDisposeUiPreferences?.();
  const lifecycle = new AbortController();
  window.taktDisposeUiPreferences = () => lifecycle.abort();
  const root = document.querySelector("[data-ui-preferences]");
  if (!root) return;
  const csrf = root.dataset.csrf;
  let state = { density: "comfortable", org_view: "explorer", last_org_unit: null };
  function apply() {
    const density = state.density === "compact" ? "compact" : "comfortable";
    document.documentElement.dataset.density = density;
    for (const button of document.querySelectorAll("[data-ui-density]")) {
      const active = button.dataset.uiDensity === density;
      button.setAttribute("aria-pressed", String(active));
      button.classList.toggle("active", active);
    }
    const workspace = document.querySelector("[data-org-workspace]");
    if (workspace) {
      const view = state.org_view === "table" ? "table" : "explorer";
      workspace.dataset.view = view;
      const table = workspace.querySelector("[data-org-table]");
      if (table) table.hidden = view !== "table";
      for (const button of document.querySelectorAll("[data-org-view]")) {
        const active = button.dataset.orgView === view;
        button.setAttribute("aria-pressed", String(active));
        button.classList.toggle("active", active);
      }
    }
  }
  async function write(patch) {
    const body = new URLSearchParams({ ...patch, csrf });
    const response = await fetch("/ui/preferences", {
      method: "POST", credentials: "same-origin", body,
    });
    if (!response.ok) throw Error("Darstellung konnte nicht gespeichert werden.");
  }
  fetch("/ui/preferences", { credentials: "same-origin" })
    .then((response) => response.ok ? response.json() : state)
    .then((prefs) => { if (lifecycle.signal.aborted) return; state = { ...state, ...prefs }; apply(); })
    .catch(() => { if (!lifecycle.signal.aborted) apply(); });
  document.addEventListener("click", async (event) => {
    const density = event.target.closest("[data-ui-density]");
    if (density) {
      const next = density.dataset.uiDensity;
      if (!["compact", "comfortable"].includes(next)) return;
      try { await write({ density: next }); state.density = next; apply(); }
      catch (_) { density.title = "Einstellung konnte nicht gespeichert werden"; }
      return;
    }
    const mode = event.target.closest("[data-org-view]");
    if (mode) {
      const next = mode.dataset.orgView;
      if (!["explorer", "table"].includes(next)) return;
      try { await write({ org_view: next }); state.org_view = next; apply(); }
      catch (_) { mode.title = "Ansicht konnte nicht gespeichert werden"; }
      return;
    }
    const link = event.target.closest("a[data-org-unit-link]");
    if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
      event.preventDefault();
      try { await write({ last_org_unit: link.dataset.orgUnitLink }); }
      catch (_) { /* Navigation is still possible without saving preference. */ }
      location.assign(link.href);
    }
  }, { signal: lifecycle.signal });
  const selector = root.querySelector("select[data-org-context]");
  if (selector?.form) {
    selector.form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try { await write({ last_org_unit: selector.value }); }
      catch (_) { /* Never block a valid form submission for a UI preference. */ }
      HTMLFormElement.prototype.submit.call(selector.form);
    });
  }
};
window.taktInitUiPreferences();
