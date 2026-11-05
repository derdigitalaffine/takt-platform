/* One rights-checked person editor, reused in organization and user administration. */
(() => {
  "use strict";
  let drawer;
  function ensureDrawer() {
    if (drawer) return drawer;
    drawer = document.createElement("div");
    drawer.id = "org-person-drawer";
    drawer.className = "offcanvas offcanvas-end org-person-drawer";
    drawer.tabIndex = -1;
    drawer.setAttribute("aria-labelledby", "org-panel-title");
    drawer.innerHTML = '<div class="offcanvas-body" data-org-person-content></div>';
    document.body.append(drawer);
    return drawer;
  }
  async function openEditor(button) {
    const query = new URLSearchParams({
      origin: button.dataset.origin || "organization",
    });
    if (button.dataset.unit) query.set("unit", button.dataset.unit);
    const url = "/admin/organization/person/" +
      encodeURIComponent(button.dataset.person) + "?" + query;
    if (!window.bootstrap?.Offcanvas) {
      // Preserve a usable form when the drawer library cannot be loaded.
      location.assign(url);
      return;
    }
    const el = ensureDrawer();
    const content = el.querySelector("[data-org-person-content]");
    content.replaceChildren();
    const status = document.createElement("p");
    status.className = "text-secondary";
    status.textContent = "Organisationszuordnungen werden geladen …";
    content.append(status);
    window.bootstrap.Offcanvas.getOrCreateInstance(el).show();
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) {
      status.textContent = "Editor konnte nicht geöffnet werden (" + response.status + ").";
      return;
    }
    content.innerHTML = await response.text();
    const form = content.querySelector("[data-org-person-form]");
    const note = content.querySelector("[data-org-person-preview]");
    if (!form || !note) return;

    const controls = [...form.querySelectorAll(".org-editor-unit input[name], .org-editor-unit select[name]")];
    const initial = new WeakMap(controls.map((input) => [
      input, input.type === "checkbox" || input.type === "radio" ? input.checked : input.value,
    ]));

    function describe(input) {
      const name = input.name;
      if (name.startsWith("member_"))
        return input.checked ? "Organisationszuordnung hinzufügen" : "Organisationszuordnung entfernen";
      if (name === "primary_unit")
        return input.checked ? "Neue Hauptzuordnung" : "Bisherige Hauptzuordnung ändern";
      if (name.startsWith("staff_")) return "Besetzungswirkung: " + input.value;
      if (name.startsWith("capacity_")) return "Einsatzanteil: " + input.value + " %";
      if (name.startsWith("role_")) {
        const label = input.closest(".org-role-choice")?.querySelector(".form-check-label")?.textContent.trim() || input.value;
        return "Rolle " + label + (input.checked ? " vergeben" : " entziehen");
      }
      if (name.startsWith("child_")) {
        const label = input.closest(".org-role-choice")?.querySelector(".form-check-label")?.textContent.trim() || "Bereichsrolle";
        return "Geltung " + label + (input.checked ? " einschließlich Untereinheiten" : " nur diese Einheit");
      }
      return "Einstellung ändern";
    }

    function renderPreview() {
      const affected = [];
      for (const entry of form.querySelectorAll(".org-editor-unit")) {
        const changes = [];
        for (const input of entry.querySelectorAll("input[name],select[name]")) {
          if (!initial.has(input)) continue;
          const value = input.type === "checkbox" || input.type === "radio" ? input.checked : input.value;
          if (initial.get(input) === value) continue;
          if (input.name.startsWith("child_")) {
            // An unselected role has no subtree scope, so its checkbox does
            // not represent a saved change.
            const match = input.name.match(/^child_(\d+)_(\w+)$/);
            const role = match && entry.querySelector('input[name="role_' + match[1] + '"][value="' + match[2] + '"]');
            if (!role?.checked) continue;
          }
          changes.push(describe(input));
        }
        if (changes.length) {
          const unit = entry.querySelector("summary .fw-semibold")?.textContent.trim() || "Organisationseinheit";
          affected.push({ unit, changes });
        }
      }
      note.replaceChildren();
      const header = document.createElement("strong");
      header.textContent = affected.length
        ? "Änderungen für " + affected.length + " Organisationseinheiten prüfen:"
        : "Noch keine Änderungen. Nicht bearbeitete Zuordnungen und Rollen bleiben erhalten.";
      note.append(header);
      if (!affected.length) return;
      const list = document.createElement("ul");
      list.className = "mt-2 mb-0";
      for (const item of affected) {
        const li = document.createElement("li");
        const title = document.createElement("strong");
        title.textContent = item.unit + ": ";
        li.append(title, document.createTextNode(item.changes.join("; ")));
        list.append(li);
      }
      note.append(list);
    }
    form.addEventListener("change", renderPreview);
    renderPreview();
  }
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-org-person-editor]");
    if (!button) return;
    event.preventDefault();
    openEditor(button).catch((error) => {
      const content = ensureDrawer().querySelector("[data-org-person-content]");
      content.textContent = "Der Editor konnte nicht geladen werden. Bitte Seite erneut öffnen.";
      console.error(error);
    });
  });
})();
