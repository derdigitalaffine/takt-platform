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
    const el = ensureDrawer();
    const content = el.querySelector("[data-org-person-content]");
    content.replaceChildren();
    const status = document.createElement("p");
    status.className = "text-secondary";
    status.textContent = "Organisationszuordnungen werden geladen …";
    content.append(status);
    if (window.bootstrap?.Offcanvas)
      window.bootstrap.Offcanvas.getOrCreateInstance(el).show();
    const query = new URLSearchParams({
      origin: button.dataset.origin || "organization",
    });
    if (button.dataset.unit) query.set("unit", button.dataset.unit);
    const response = await fetch(
      "/admin/organization/person/" + encodeURIComponent(button.dataset.person) + "?" + query,
      { credentials: "same-origin" },
    );
    if (!response.ok) {
      status.textContent = "Editor konnte nicht geöffnet werden (" + response.status + ").";
      return;
    }
    content.innerHTML = await response.text();
    const form = content.querySelector("[data-org-person-form]");
    const note = content.querySelector("[data-org-person-preview]");
    if (form && note) {
      form.addEventListener("change", () => {
        const changes = [];
        for (const entry of form.querySelectorAll(".org-editor-unit")) {
          const count = entry.querySelectorAll('input[name^="role_"]:checked').length;
          const assigned = entry.querySelector('input[name^="member_"]');
          if (count || assigned?.checked) changes.push(entry.querySelector("summary")?.textContent.trim().replace(/\s+/g, " "));
        }
        note.textContent = "Gemeinsame Transaktion für " + changes.length +
          " zugeordnete bzw. rollenführende Einheiten. Änderungen werden vollständig geprüft.";
      });
    }
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
