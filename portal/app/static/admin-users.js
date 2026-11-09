/* Progressive admin controls: lazy dialogs, deep-link accordions and native filters. */
(() => {
  "use strict";
  const root = document.querySelector(".admin-users-workspace");
  if (!root) return;

  function revealHash() {
    const id = decodeURIComponent(location.hash.slice(1));
    if (!id) return;
    const target = document.getElementById(id);
    if (!target) return;
    const details = target.closest("details");
    if (details) details.open = true;
    if (target.matches("details")) target.open = true;
  }
  window.addEventListener("hashchange", revealHash);
  revealHash();
  document.querySelectorAll('.admin-subnav a[href^="#"], .admin-welcome-actions a[href^="#"]').forEach(link => {
    link.addEventListener("click", () => {
      const target = document.getElementById(link.hash.slice(1));
      if (target?.matches("details")) target.open = true;
      target?.closest("details")?.setAttribute("open", "");
    });
  });

  // Only the chosen group's form and member options are fetched. At rest the
  // page renders O(visible users + groups), never O(groups × all users).
  let loading = false;
  document.addEventListener("click", async event => {
    const trigger = event.target.closest("[data-admin-group-editor]");
    if (!trigger || loading) return;
    event.preventDefault();
    loading = true;
    const original = trigger.innerHTML;
    trigger.disabled = true;
    trigger.setAttribute("aria-busy", "true");
    try {
      const gid = trigger.dataset.adminGroupEditor;
      if (!/^\d+$/.test(gid)) return;
      const response = await fetch("/admin/groups/editor/" + gid, {
        credentials: "same-origin", headers: {"Accept": "text/html"}
      });
      if (!response.ok) throw new Error("Gruppen-Editor konnte nicht geladen werden (" + response.status + ").");
      const holder = document.createElement("div");
      holder.innerHTML = await response.text();
      const modal = holder.querySelector("#admin-group-editor-modal");
      if (!modal) throw new Error("Ungültige Editor-Antwort.");
      document.body.appendChild(modal);
      if (window.TomSelect) modal.querySelectorAll("select.js-select").forEach(select => {
        if (!select.tomselect) new TomSelect(select, {
          allowEmptyOption: true, create: false,
          plugins: select.multiple ? ["remove_button"] : [],
          render: {no_results: () => '<div class="no-results">Keine Treffer</div>'}
        });
      });
      const instance = bootstrap.Modal.getOrCreateInstance(modal);
      modal.addEventListener("hidden.bs.modal", () => {
        modal.querySelectorAll("select.js-select").forEach(el => el.tomselect?.destroy());
        instance.dispose();
        modal.remove();
        trigger.focus();
      }, {once:true});
      instance.show();
    } catch (error) {
      let status = document.querySelector("[data-group-editor-error]");
      if (!status) {
        status = document.createElement("p");
        status.className = "alert alert-danger";
        status.setAttribute("role", "alert");
        status.dataset.groupEditorError = "";
        document.querySelector(".admin-groups-section")?.prepend(status);
      }
      status.textContent = error.message || "Gruppen-Editor konnte nicht geöffnet werden.";
    } finally {
      loading = false;
      trigger.disabled = false;
      trigger.removeAttribute("aria-busy");
      trigger.innerHTML = original;
    }
  });
})();
