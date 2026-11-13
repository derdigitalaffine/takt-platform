/* User-management passkey revocation; no credential material in HTML. */
(() => {
  "use strict";
  const form = document.querySelector("[data-passkey-admin-form]");
  if (!form) return;
  const select = form.querySelector("#passkey-admin-user");
  const updateTarget = () => {
    const target = select?.value || "";
    form.action = /^\d+$/.test(target) ? "/admin/users/" + target + "/passkeys/revoke" : "";
  };
  select?.addEventListener("change", updateTarget);
  form.addEventListener("submit", event => {
    const target = select?.value || "";
    updateTarget();
    if (!/^\d+$/.test(target)) {
      event.preventDefault();
      form.querySelector("#passkey-admin-user")?.focus();
      return;
    }
    form.action = "/admin/users/" + target + "/passkeys/revoke";
  });
})();
