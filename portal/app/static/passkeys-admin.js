/* User-management passkey revocation; no credential material in HTML. */
(() => {
  "use strict";
  const form = document.querySelector("[data-passkey-admin-form]");
  if (!form) return;
  form.addEventListener("submit", event => {
    const target = form.querySelector("#passkey-admin-user")?.value || "";
    if (!/^\d+$/.test(target)) {
      event.preventDefault();
      form.querySelector("#passkey-admin-user")?.focus();
      return;
    }
    form.action = "/admin/users/" + target + "/passkeys/revoke";
  });
})();
