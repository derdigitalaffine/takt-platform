/* Poll only a status endpoint; it cannot change or publish a legal text. */
(() => {
  "use strict";
  const pending = document.querySelector("[data-law-ocr-pending]");
  if (!pending) return;
  const id = pending.getAttribute("data-draft-id");
  if (!/^\d+$/.test(id || "")) return;
  let running = false;
  const check = async () => {
    if (running || document.hidden) return;
    running = true;
    try {
      const response = await fetch("/laws-assistant/" + id + "/ocr/status", {
        credentials: "same-origin", cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Statusabfrage fehlgeschlagen.");
      const data = await response.json();
      if (data.ready === true) {
        window.location.reload();
      }
    } catch (_error) {
      pending.append(document.createTextNode(
        " Automatische Statusabfrage nicht verfügbar; bitte die Seite manuell aktualisieren."
      ));
      clearInterval(timer);
    } finally {
      running = false;
    }
  };
  const timer = setInterval(check, 7000);
})();
