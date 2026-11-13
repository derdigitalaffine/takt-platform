/* Ortsrecht LLM review is advisory only. No autosave, tool calls or publication. */
(() => {
  "use strict";

  const fields = {
    title: "law-ai-title",
    short_title: "law-ai-short-title",
    doc_type: "law-ai-type",
    version_note: "law-ai-version-note",
    issued_on: "law-ai-issued",
    valid_from: "law-ai-valid-from",
    valid_until: "law-ai-valid-until",
    level: "law-ai-level",
  };

  document.querySelectorAll("[data-law-ai-apply-field]").forEach((button) => {
    button.addEventListener("click", () => {
      const field = button.getAttribute("data-law-ai-apply-field");
      const value = button.getAttribute("data-law-ai-value") || "";
      const id = fields[field];
      if (!id) return;
      const control = document.getElementById(id);
      if (!control) return;
      if (control.tagName === "SELECT") {
        let candidate = Array.from(control.options).find((opt) =>
          opt.value === value ||
          (field === "level" && opt.textContent.trim().toLowerCase() === value.toLowerCase())
        );
        if (!candidate) {
          button.textContent = "Bitte passende Auswahl manuell prüfen";
          return;
        }
        control.value = candidate.value;
      } else {
        if (value.length > (control.maxLength > 0 ? control.maxLength : 400)) return;
        if (control.type === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(value)) return;
        control.value = value;
      }
      control.dispatchEvent(new Event("change", { bubbles: true }));
      button.textContent = "Übertragen – bitte prüfen";
      control.focus();
    });
  });

  const editor = document.getElementById("law-ai-body");

  // Python source offsets count Unicode code points. Browser textareas use
  // UTF-16 offsets; correctly handle supplementary characters in OCR text.
  function toTextAreaOffset(text, codePointOffset) {
    if (!Number.isSafeInteger(codePointOffset) || codePointOffset < 0) return -1;
    let position = 0;
    let codePoints = 0;
    for (const character of text) {
      if (codePoints === codePointOffset) return position;
      position += character.length;
      codePoints += 1;
    }
    return codePoints === codePointOffset ? position : -1;
  }

  document.querySelectorAll("[data-law-ai-apply-heading]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!editor) return;
      const quote = (button.getAttribute("data-law-ai-apply-heading") || "").trim();
      const level = Number(button.getAttribute("data-law-ai-heading-level"));
      if (!quote || !Number.isInteger(level) || level < 1 || level > 5) return;
      const normalized = (line) => line.trim();
      const lines = editor.value.split("\n");
      const rawOffset = button.getAttribute("data-law-ai-offset") || "";
      const offset = /^\d+$/.test(rawOffset)
        ? toTextAreaOffset(editor.value, Number(rawOffset)) : -1;
      const targetLine = (offset >= 0 &&
                          editor.value.slice(offset, offset + quote.length).trim() === quote)
        ? editor.value.slice(0, offset).split("\n").length - 1 : -1;
      const matches = lines.map((line, index) => normalized(line) === quote ? index : -1)
        .filter((index) => index >= 0);
      const chosen = targetLine >= 0 && normalized(lines[targetLine]) === quote
        ? targetLine : matches.length === 1 ? matches[0] : -1;
      if (chosen < 0) {
        button.textContent = "Fundstelle nicht eindeutig – bitte manuell prüfen";
        return;
      }
      const line = lines[chosen];
      const inner = line.trim().replace(/^#{1,5}\s+/, "");
      lines[chosen] = "#".repeat(level) + " " + inner;
      editor.value = lines.join("\n");
      editor.dispatchEvent(new Event("input", { bubbles: true }));
      button.textContent = "Im Entwurf formatiert – vor Übernahme prüfen";
      editor.focus();
    });
  });

  document.querySelectorAll("[data-law-ai-locate]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!editor) return;
      const quote = button.getAttribute("data-law-ai-locate") || "";
      const rawOffset = button.getAttribute("data-law-ai-offset") || "";
      const offset = /^\d+$/.test(rawOffset)
        ? toTextAreaOffset(editor.value, Number(rawOffset)) : -1;
      const exact = offset >= 0 && editor.value.slice(offset, offset + quote.length) === quote;
      const first = editor.value.indexOf(quote);
      const ambiguous = first >= 0 && editor.value.indexOf(quote, first + quote.length) >= 0;
      const index = exact ? offset : !ambiguous ? first : -1;
      if (index < 0 || !quote) {
        button.textContent = "Fundstelle verändert oder mehrdeutig – bitte manuell suchen";
        return;
      }
      editor.focus();
      editor.setSelectionRange(index, index + quote.length);
      editor.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });

  const panel = document.querySelector("[data-law-ai-analysis-pending]");
  const id = panel?.getAttribute("data-draft-id");
  const jobId = panel?.getAttribute("data-job-id");
  if (!panel || !/^\d+$/.test(id || "") || !/^\d+$/.test(jobId || "")) return;

  const status = panel.querySelector("[data-law-ai-stage]");
  const badge = panel.querySelector("[data-law-ai-stream-badge]");
  const calls = panel.querySelector("[data-law-ai-call-count]");
  const stats = panel.querySelector("[data-law-ai-stream-stats]");
  const validated = panel.querySelector("[data-law-ai-validated]");
  const retries = panel.querySelector("[data-law-ai-retries]");
  const bar = panel.querySelector("[data-law-ai-progress]");
  const fill = panel.querySelector("[data-law-ai-progress-bar]");
  const names = {
    law_structure: "Gliederungsagent (1/3)",
    law_metadata: "Stammdatenagent (2/3)",
    law_verify: "Texttreueagent (3/3)",
    waiting: "Warteschlange",
    preparing: "Quellen- und Berechtigungsprüfung",
  };
  const statusUrl = "/laws-assistant/" + id + "/agents/status";
  const eventsUrl = "/laws-assistant/" + id + "/agents/" + jobId + "/events";
  let source = null;
  let pollTimer = null;
  let polling = false;
  let finished = false;

  function render(value) {
    if (!value || typeof value !== "object" || finished) return;
    if (value.ready === true) {
      finished = true;
      source?.close();
      if (pollTimer !== null) clearInterval(pollTimer);
      window.location.reload();
      return;
    }
    const match = /^(law_structure|law_metadata|law_verify):(\d+)\/(\d+)$/.exec(value.step || "");
    if (status) {
      status.textContent = match
        ? names[match[1]] + " · Abschnitt " + match[2] + " von " + match[3]
        : names[value.step] || "KI-Auftrag wird vorbereitet";
    }
    const total = Number.isSafeInteger(value.progress_total) && value.progress_total > 0
      ? value.progress_total : 0;
    const done = Number.isSafeInteger(value.progress_done) && value.progress_done >= 0
      ? Math.min(value.progress_done, total) : 0;
    if (calls) calls.textContent = done + " von " + (total || "…") + " Prüfabschnitten abgeschlossen";
    const percent = total ? Math.min(100, Math.round(done / total * 100)) : 0;
    if (bar) bar.setAttribute("aria-valuenow", String(percent));
    if (fill) fill.style.width = percent + "%";
    if (validated) {
      const items = Number.isSafeInteger(value.validated_items)
        ? Math.max(0, value.validated_items) : 0;
      validated.textContent = items + " fundstellengeprüfte Vorschläge";
    }
    if (value.stream_active === true) {
      const chars = Number.isSafeInteger(value.stream_characters)
        ? Math.max(0, value.stream_characters) : 0;
      const chunks = Number.isSafeInteger(value.stream_chunks)
        ? Math.max(0, value.stream_chunks) : 0;
      if (badge) badge.textContent = "Streaming aktiv";
      if (stats) stats.textContent = chars.toLocaleString("de-DE") +
        " Zeichen · " + chunks + " Antwortteile empfangen (noch ungeprüft)";
    } else {
      if (badge) badge.textContent = "Modell verarbeitet";
      if (stats) stats.textContent = "Warte auf Antwort oder prüfe Fundstellen …";
    }
  }

  async function poll() {
    if (polling || finished || document.hidden) return;
    polling = true;
    try {
      const response = await fetch(statusUrl, {
        credentials: "same-origin", cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Status nicht verfügbar.");
      render(await response.json());
    } catch (_) {
      if (status) status.textContent =
        "Live-Status ist nicht abrufbar. Bitte Seite manuell aktualisieren.";
    } finally {
      polling = false;
    }
  }
  function usePolling() {
    source?.close();
    source = null;
    if (pollTimer !== null) return;
    poll();
    pollTimer = setInterval(poll, 3500);
  }

  if (typeof EventSource === "function") {
    try {
      source = new EventSource(eventsUrl);
      source.onmessage = (event) => {
        try {
          render(JSON.parse(event.data));
        } catch (_) {
          usePolling();
        }
      };
      source.addEventListener("access-lost", () => {
        source?.close();
        source = null;
        if (status) status.textContent = "Berechtigung beendet – bitte Seite neu laden.";
      });
      source.onerror = () => {
        if (!finished) usePolling();
      };
    } catch (_) {
      usePolling();
    }
  } else {
    usePolling();
  }
  window.addEventListener("pagehide", () => {
    source?.close();
    if (pollTimer !== null) clearInterval(pollTimer);
  }, { once: true });
})();
