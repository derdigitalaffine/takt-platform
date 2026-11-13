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

  document.querySelectorAll("[data-law-ai-apply-heading]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!editor) return;
      const quote = (button.getAttribute("data-law-ai-apply-heading") || "").trim();
      const level = Number(button.getAttribute("data-law-ai-heading-level"));
      if (!quote || !Number.isInteger(level) || level < 1 || level > 5) return;
      const normalized = (line) => line.trim();
      const lines = editor.value.split("\n");
      const matching = lines.map((line, index) => normalized(line) === quote ? index : -1)
        .filter((index) => index >= 0);
      if (matching.length !== 1) {
        button.textContent = "Fundstelle nicht eindeutig – bitte manuell prüfen";
        return;
      }
      const line = lines[matching[0]];
      const inner = line.trim().replace(/^#{1,5}\s+/, "");
      lines[matching[0]] = "#".repeat(level) + " " + inner;
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
      const index = editor.value.indexOf(quote);
      if (index < 0 || !quote) {
        button.textContent = "Fundstelle nicht mehr vorhanden";
        return;
      }
      editor.focus();
      editor.setSelectionRange(index, index + quote.length);
      editor.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });

  const panel = document.querySelector("[data-law-ai-analysis-pending]");
  const id = panel?.getAttribute("data-draft-id");
  if (!panel || !/^\d+$/.test(id || "")) return;
  let running = false;
  const status = panel.querySelector('[role="status"]');
  const labels = {
    waiting: "wartet auf Bearbeitung",
    preparing: "Quellenprüfung",
    law_structure: "1/3 · Gliederungsagent",
    law_metadata: "2/3 · Stammdatenagent",
    law_verify: "3/3 · Texttreueagent",
  };
  const poll = async () => {
    if (running || document.hidden) return;
    running = true;
    try {
      const response = await fetch("/laws-assistant/" + id + "/agents/status", {
        credentials: "same-origin", cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Statusabruf nicht möglich.");
      const value = await response.json();
      if (value.ready === true) {
        window.location.reload();
        return;
      }
      if (status) status.textContent = "KI-Auswertung: " + (labels[value.step] || "In Bearbeitung");
    } catch (_) {
      clearInterval(timer);
      if (status) status.textContent = "Status nicht abrufbar – bitte manuell aktualisieren.";
    } finally {
      running = false;
    }
  };
  const timer = setInterval(poll, 5000);
})();
