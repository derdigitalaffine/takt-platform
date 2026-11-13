/* Only reads owner-scoped OCR status; no document content is transmitted. */
(() => {
  "use strict";
  const pending = document.querySelector("[data-law-ocr-pending]");
  if (!pending) return;
  const id = pending.getAttribute("data-draft-id");
  if (!/^\d+$/.test(id || "")) return;

  const phase = pending.querySelector("[data-law-ocr-phase]");
  const hint = pending.querySelector("[data-law-ocr-hint]");
  const clock = pending.querySelector("[data-law-ocr-clock]");
  const retry = pending.querySelector("[data-law-ocr-retry]");
  let busy = false;
  let completed = false;
  let failures = 0;
  let timer = null;
  function next(ms) {
    if (!completed) timer = setTimeout(check, ms);
  }
  function update(data) {
    if (completed) return;
    if (data.ready === true) {
      completed = true;
      if (window.LawReviewUX?.deferRefresh?.()) return;
      window.location.reload();
      return;
    }
    const labels = {
      queued: "Warteschlange",
      processing: "Texterkennung läuft",
      finalizing: "Ergebnis wird geprüft",
      unknown: "OCR-Status unklar",
    };
    const name = labels[data.phase] || "Auftrag wird geprüft";
    if (phase) phase.textContent = name;
    if (hint) hint.textContent = typeof data.phase_message === "string" ?
      data.phase_message : "Die Bearbeitung dauert noch an.";
    const seconds = Number.isSafeInteger(data.elapsed_seconds)
      ? Math.max(0, data.elapsed_seconds) : 0;
    if (clock) clock.textContent = Math.floor(seconds / 60) + " Min. seit Beauftragung";
    if (retry) {
      retry.hidden = data.needs_attention !== true;
    }
  }
  async function check() {
    if (completed) return;
    if (busy || document.hidden) {
      next(4000);
      return;
    }
    busy = true;
    try {
      const response = await fetch("/laws-assistant/" + id + "/ocr/status", {
        credentials: "same-origin", cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("OCR-Status derzeit nicht verfügbar.");
      failures = 0;
      update(await response.json());
    } catch (_) {
      failures++;
      if (hint) {
        hint.textContent = "Verbindung zur OCR-Statusprüfung unterbrochen. " +
          "Der Auftrag bleibt erhalten; die Anzeige versucht es erneut.";
      }
      if (retry) retry.hidden = false;
    } finally {
      busy = false;
      if (!completed) next(Math.min(24000, failures ? 4000 * 2 ** Math.min(failures, 3) : 4500));
    }
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && !completed) {
      clearTimeout(timer);
      next(200);
    }
  });
  window.addEventListener("pagehide", () => clearTimeout(timer), { once: true });
  next(500);
})();
