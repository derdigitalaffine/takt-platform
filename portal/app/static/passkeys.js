/* Native WebAuthn; zero third-party scripts and no credentials stored in browser storage. */
(() => {
  "use strict";
  const login = document.querySelector("[data-passkey-login]");
  const enroll = document.querySelector("[data-passkey-enroll]");
  if (!login && !enroll) return;

  const available = !!(window.PublicKeyCredential && navigator.credentials &&
                        window.isSecureContext && typeof navigator.credentials.create === "function");
  const csrf = document.querySelector('meta[name="csrf"]')?.content ||
               document.querySelector('input[name="csrf"]')?.value || "";

  function bytes(value) {
    const base = value.replace(/-/g, "+").replace(/_/g, "/");
    const decoded = atob(base.padEnd(Math.ceil(base.length / 4) * 4, "="));
    return Uint8Array.from(decoded, char => char.charCodeAt(0));
  }
  function b64(value) {
    if (value === null || value === undefined) return null;
    const arr = new Uint8Array(value);
    let binary = "";
    for (const v of arr) binary += String.fromCharCode(v);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function normalizePublicKey(data) {
    const options = {...data, challenge: bytes(data.challenge)};
    if (data.user) options.user = {...data.user, id: bytes(data.user.id)};
    for (const list of ["excludeCredentials", "allowCredentials"]) {
      if (data[list]) options[list] = data[list].map(item => ({...item, id: bytes(item.id)}));
    }
    return options;
  }
  function serialize(credential) {
    const response = credential.response;
    const result = {
      id: credential.id, rawId: b64(credential.rawId), type: "public-key",
      clientExtensionResults: credential.getClientExtensionResults?.() || {},
      response: {clientDataJSON: b64(response.clientDataJSON)},
    };
    if (credential.authenticatorAttachment) result.authenticatorAttachment = credential.authenticatorAttachment;
    if (response.attestationObject) {
      result.response.attestationObject = b64(response.attestationObject);
      result.response.transports = response.getTransports?.() || [];
    } else {
      result.response.authenticatorData = b64(response.authenticatorData);
      result.response.signature = b64(response.signature);
      result.response.userHandle = b64(response.userHandle);
    }
    return result;
  }
  async function post(url, payload) {
    const response = await fetch(url, {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: {"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify(payload),
    });
    const json = await response.json();
    if (!response.ok) {
      throw new Error(typeof json.detail === "string" ? json.detail :
        "Passkey-Vorgang fehlgeschlagen. Bitte erneut versuchen.");
    }
    return json;
  }
  function statusFor(button) {
    return button.closest("[data-passkey-panel]")?.querySelector("[data-passkey-status]");
  }
  async function run(button, kind) {
    const status = statusFor(button);
    const original = button.textContent;
    const name = enroll?.closest("[data-passkey-panel]")?.querySelector("[data-passkey-name]")?.value || "Mein Passkey";
    const password = enroll?.closest("[data-passkey-panel]")?.querySelector("[data-passkey-password]")?.value || "";
    button.disabled = true;
    if (status) { status.textContent = "Passkey-Anfrage wird vorbereitet …"; status.classList.remove("text-danger"); }
    try {
      const prefix = kind === "create" ? "/profile/passkeys" : "/auth/passkeys/login";
      const options = await post(prefix + "/options", kind === "create" ? {password} : {});
      if (status) status.textContent = "Bitte im Browser das Gerät bzw. den Passkey bestätigen …";
      const credential = kind === "create"
        ? await navigator.credentials.create({publicKey: normalizePublicKey(options)})
        : await navigator.credentials.get({publicKey: normalizePublicKey(options)});
      if (!credential) throw new Error("Kein Passkey ausgewählt.");
      const verified = await post(prefix + "/verify", {
        credential: serialize(credential),
        ...(kind === "create" ? {name} : {next: document.querySelector('input[name="next"]')?.value || "/"}),
      });
      if (status) status.textContent = "Passkey bestätigt. Anmeldung wird abgeschlossen …";
      window.location.assign(verified.redirect || (kind === "create" ? "/profile/security#passkeys" : "/"));
    } catch (error) {
      if (status) {
        status.classList.add("text-danger");
        status.textContent = error?.name === "NotAllowedError"
          ? "Abgebrochen oder keine Bestätigung vom Gerät erhalten."
          : (error?.message || "Passkey-Vorgang fehlgeschlagen.");
      }
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  for (const [button, kind] of [[login, "get"], [enroll, "create"]]) {
    if (!button) continue;
    if (!available) {
      button.disabled = true;
      const status = statusFor(button);
      if (status) status.textContent =
        "Passkeys benötigen einen aktuellen Browser und eine sichere HTTPS-Verbindung.";
      continue;
    }
    button.addEventListener("click", () => run(button, kind));
  }
})();
