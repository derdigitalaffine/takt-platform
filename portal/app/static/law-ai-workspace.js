/* TAKT Ortsrecht workbench: client-only guidance, never stores source text. */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const mb = 25 * 1024 * 1024;

  // Accessible optional drop zone. Server-side type/size checks remain authoritative.
  const file = $("#law-ai-file");
  const drop = $("[data-law-upload-zone]");
  const feedback = $("[data-law-upload-feedback]");
  const uploadSubmit = $("[data-law-upload-submit]");
  function fileFeedback() {
    const selected = file?.files?.[0];
    if (!selected) {
      if (feedback) feedback.textContent = "PDF, Word, Bild oder Textdatei hier ablegen oder auswählen.";
      if (uploadSubmit) uploadSubmit.disabled = false;
      return;
    }
    const tooLarge = selected.size > mb;
    if (feedback) {
      feedback.textContent = selected.name + " · " +
        (selected.size / 1024 / 1024).toLocaleString("de-DE", { maximumFractionDigits: 1 }) +
        " MB" + (tooLarge ? " – maximale Größe: 25 MB" : " · bereit zum Import");
      feedback.classList.toggle("text-danger", tooLarge);
    }
    if (uploadSubmit) uploadSubmit.disabled = tooLarge;
  }
  if (file) file.addEventListener("change", fileFeedback);
  if (drop && file) {
    ["dragenter", "dragover"].forEach((name) => drop.addEventListener(name, (event) => {
      if (!event.dataTransfer?.types?.includes("Files")) return;
      event.preventDefault();
      drop.classList.add("is-over");
    }));
    ["dragleave", "drop"].forEach((name) => drop.addEventListener(name, () => {
      drop.classList.remove("is-over");
    }));
    drop.addEventListener("drop", (event) => {
      if (!event.dataTransfer?.files?.length) return;
      event.preventDefault();
      try {
        file.files = event.dataTransfer.files;
        fileFeedback();
      } catch (_) {
        if (feedback) feedback.textContent = "Bitte die Datei über „Auswählen“ öffnen.";
      }
    });
  }

  // Filter only the user's visible draft list (max 40, already ACL-filtered).
  const search = $("[data-law-drafts-search]");
  const status = $("[data-law-drafts-filter]");
  const drafts = $$("[data-law-draft]");
  function updateDrafts() {
    if (!drafts.length) return;
    const query = (search?.value || "").trim().toLocaleLowerCase("de");
    const filter = status?.value || "all";
    let count = 0;
    drafts.forEach((draft) => {
      const state = draft.getAttribute("data-law-draft-status") || "";
      const name = (draft.getAttribute("data-law-draft-name") || "").toLocaleLowerCase("de");
      const statusMatches = filter === "all" ||
        (filter === "accepted" && state === "accepted") ||
        (filter === "processing" && state === "ocr_queued") ||
        (filter === "review" && state !== "accepted" && state !== "ocr_queued");
      const visible = name.includes(query) && statusMatches;
      draft.hidden = !visible;
      const row = draft.closest(".law-draft-item");
      if (row) row.hidden = !visible;
      if (visible) count += 1;
    });
    const counter = $("[data-law-drafts-count]");
    if (counter) counter.textContent = count + " von " + drafts.length + " Entwürfen angezeigt";
    const empty = $("[data-law-drafts-empty]");
    if (empty) empty.hidden = count !== 0;
  }
  search?.addEventListener("input", updateDrafts);
  status?.addEventListener("change", updateDrafts);

  // Display the model traffic cost before the user consents to sending data.
  const analyzeForm = $("[data-law-analysis-form]");
  if (analyzeForm) {
    const budget = $("[data-law-analysis-budget]");
    const advancedCalls = Number(budget?.getAttribute("data-law-advanced-calls") || 0);
    const showBudget = () => {
      const mode = $('input[name="mode"]:checked', analyzeForm)?.value;
      if (!budget) return;
      const stage = $('[data-law-stage-select]', analyzeForm)?.value || "all";
      const stageCount = stage === "all" ? 3 : 1;
      const calls = mode === "advanced" ? Math.floor(advancedCalls / 3) * stageCount : stageCount;
      budget.textContent = (mode === "advanced" ? "Gesamter Text" : "Schnellcheck") +
        ": " + calls + " reguläre Modellaufrufe, bei begrenzten Wiederholungsversuchen höchstens " +
        (calls * 3) + ". " + (stageCount === 1 ? "Ein Agent ausgewählt." : "Drei Agenten ausgewählt.") +
        (mode === "simple" ? " Lange Texte werden nur auszugsweise geprüft." : " Vollständige Abschnittsabdeckung.");
    };
    $('input[name="mode"]', analyzeForm).forEach((input) =>
      input.addEventListener("change", showBudget));
    $("[data-law-stage-select]", analyzeForm)?.addEventListener("change", showBudget);
    showBudget();
  }

  const review = $("[data-law-review-form]");
  const editor = $("#law-ai-body");
  let navigationAllowed = false;
  let dirty = false;

  const fields = review
    ? $$("input[name], select[name], textarea[name]", review)
        .filter((input) => input.name !== "csrf" && input.name !== "confirmed")
    : [];
  // Never store private legal content in localStorage/sessionStorage or logs.
  const initial = new Map(fields.map((input) => [input, input.value]));

  function updateDirty() {
    dirty = fields.some((input) => input.value !== initial.get(input));
    const warning = $("[data-law-editor-dirty]");
    if (warning) warning.hidden = !dirty;
    const sourceNotice = $("[data-law-ai-source-warning]");
    if (sourceNotice) sourceNotice.hidden = !dirty;
  }

  const stats = $("[data-law-editor-count]");
  const outline = $("[data-law-editor-outline]");
  let outlineTimeout = null;

  // Build navigation with DOM text nodes only. Never render OCR/LLM HTML.
  function renderOutline() {
    if (!editor || !outline) return;
    const text = editor.value;
    outline.replaceChildren();
    let offset = 0;
    let total = 0;
    for (const line of text.split("\n")) {
      const match = /^(?:\s{0,3}(#{1,5})\s+(.+)|\s{0,3}(§\s*\d+[a-zA-Z]*\b.{0,85})|\s{0,3}((?:Artikel|Art\.)\s+\d+[a-zA-Z]*\b.{0,85}))$/u.exec(line);
      if (match && total < 65) {
        const label = (match[2] || match[3] || match[4] || "").trim();
        const depth = match[1] ? match[1].length : 2;
        if (label) {
          const button = document.createElement("button");
          button.type = "button";
          button.dataset.depth = String(depth);
          button.textContent = label.slice(0, 110);
          const start = offset;
          button.addEventListener("click", () => {
            editor.focus();
            editor.setSelectionRange(start, Math.min(start + line.length, editor.value.length));
            editor.scrollIntoView({ block: "center", behavior: "smooth" });
          });
          outline.append(button);
          total++;
        }
      }
      offset += line.length + 1;
    }
    if (!total) {
      const p = document.createElement("p");
      p.className = "text-secondary small mb-0 p-2";
      p.textContent = "Noch keine Überschriften oder Paragraphen gefunden.";
      outline.append(p);
    }
    if (total >= 65) {
      const p = document.createElement("p");
      p.className = "text-secondary small p-2 mb-0";
      p.textContent = "Weitere Überschriften im Text vorhanden.";
      outline.append(p);
    }
  }

  function updateEditorMetrics() {
    if (!editor) return;
    if (stats) {
      const lines = editor.value.split("\n").length;
      const chars = Array.from(editor.value).length;
      stats.textContent = chars.toLocaleString("de-DE") + " Zeichen · " +
        lines.toLocaleString("de-DE") + " Zeilen";
    }
    renderOutline();
  }

  const scheduleMetrics = () => {
    if (outlineTimeout !== null) window.clearTimeout(outlineTimeout);
    outlineTimeout = window.setTimeout(updateEditorMetrics, 280);
  };
  if (review) {
    fields.forEach((input) => {
      input.addEventListener("input", () => {
        updateDirty();
        if (input === editor) scheduleMetrics();
      });
      input.addEventListener("change", updateDirty);
    });
    review.addEventListener("submit", () => {
      // The explicit and required legal confirmation is validated by the
      // browser; a successful submit is a deliberate handoff.
      navigationAllowed = true;
    });
    analyzeForm?.addEventListener("submit", (event) => {
      if (dirty && !window.confirm(
        "Du hast ungespeicherte Änderungen im redaktionellen Formular. " +
        "Die KI bewertet ausschließlich die importierte Textversion. " +
        "Beim Start gehen die ungespeicherten Eingaben verloren. Trotzdem starten?"
      )) {
        event.preventDefault();
        return;
      }
      navigationAllowed = true;
    });
    $("[data-law-discard-form]")?.addEventListener("submit", () => {
      navigationAllowed = true;
    });
    window.addEventListener("beforeunload", (event) => {
      if (!dirty || navigationAllowed) return;
      event.preventDefault();
      event.returnValue = "";
    });
    updateEditorMetrics();
  }

  // Long-running OCR/LLM jobs may finish while a reviewer is typing. Never
  // reload the page and silently throw away unsaved legal corrections.
  let finishedBannerShown = false;
  function deferRefresh() {
    if (!dirty) return false;
    if (finishedBannerShown) return true;
    finishedBannerShown = true;
    const container = $("[data-law-ai-analysis-pending]") || $("[data-law-ocr-pending]") || review;
    if (!container) return true;
    const message = document.createElement("div");
    message.className = "alert alert-success mt-2";
    message.setAttribute("role", "status");
    const heading = document.createElement("strong");
    heading.textContent = "Prüfauftrag abgeschlossen – deine aktuellen Eingaben bleiben erhalten.";
    const p = document.createElement("p");
    p.className = "small mb-2";
    p.textContent = "Die neuen Ergebnisse werden nach dem Neuladen angezeigt. " +
      "Ungespeicherte Änderungen können dabei verloren gehen.";
    const reload = document.createElement("button");
    reload.type = "button";
    reload.className = "btn btn-sm btn-outline-primary";
    reload.textContent = "Ergebnisse laden und ungespeicherte Änderungen verwerfen";
    reload.addEventListener("click", () => {
      navigationAllowed = true;
      window.location.reload();
    });
    message.append(heading, p, reload);
    container.prepend(message);
    return true;
  }
  window.LawReviewUX = {
    hasUnsavedChanges: () => dirty,
    deferRefresh,
  };
})();
