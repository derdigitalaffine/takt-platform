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
      budget.textContent = mode === "advanced"
        ? "Gesamter Text: " + advancedCalls + " reguläre Anfragen, bei Nachprüfung höchstens " +
          (advancedCalls * 3) + ". Mehr Laufzeit und mögliche API-Kosten."
        : "Schnellcheck: 3 reguläre Anfragen, bei Nachprüfung höchstens 9. Lange Texte nur auszugsweise.";
    };
    $$('input[name="mode"]', analyzeForm).forEach((input) =>
      input.addEventListener("change", showBudget));
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

  // Explicit, editor-only structural aids; they do not invent normative words.
  // No source text is persisted until the reviewer confirms legal acceptance.
  const snippets = {
    title: "# Titel der Satzung\n",
    group: "## Erster Teil – Allgemeines\n",
    norm: "### § 1 Geltungsbereich\n",
    paragraph: "(1) ",
    appendix: "## Anlage 1 – Bezeichnung\n",
    reference: "[[§ 1]]",
    table: "| Spalte 1 | Spalte 2 |\n| --- | --- |\n| Inhalt | Inhalt |\n",
  };
  $("[data-law-insert]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!editor) return;
      const key = button.getAttribute("data-law-insert");
      if (!Object.prototype.hasOwnProperty.call(snippets, key)) return;
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      const selectedText = editor.value.slice(start, end);
      let insert = snippets[key];
      if (selectedText && ["title", "group", "norm", "appendix"].includes(key) &&
          !selectedText.includes("\n")) {
        const prefix = snippets[key].match(/^#+ /)?.[0] || "";
        insert = prefix + selectedText + "\n";
      }
      if (!["paragraph", "reference"].includes(key) &&
          start > 0 && editor.value[start - 1] !== "\n") {
        insert = "\n" + insert;
      }
      editor.setRangeText(insert, start, end, "end");
      editor.dispatchEvent(new Event("input", { bubbles: true }));
      editor.focus();
    });
  });

  const canonicalButton = $("[data-law-canonical-preview]");
  const canonicalPanel = $("[data-law-canonical-panel]");
  const canonicalCount = $("[data-law-canonical-count]");
  const canonicalList = $("[data-law-canonical-changes]");
  const canonicalText = $("[data-law-canonical-text]");
  const canonicalWarnings = $("[data-law-canonical-warnings]");
  const canonicalApply = $("[data-law-canonical-apply]");
  const canonicalConfirm = $("[data-law-canonical-confirm]");
  let canonicalResult = null;
  let canonicalBusy = false;
  if (review && editor && canonicalButton && canonicalPanel) {
    canonicalButton.addEventListener("click", async () => {
      if (canonicalBusy) return;
      const url = review.getAttribute("data-law-canonical-url") || "";
      if (!/^\/laws-assistant\/\d+\/markdown\/preview$/.test(url)) return;
      canonicalBusy = true;
      canonicalButton.disabled = true;
      canonicalResult = null;
      canonicalPanel.hidden = false;
      if (canonicalApply) canonicalApply.disabled = true;
      if (canonicalConfirm) canonicalConfirm.checked = false;
      if (canonicalCount) canonicalCount.textContent = "Gliederung wird erkannt …";
      if (canonicalList) canonicalList.replaceChildren();
      if (canonicalText) canonicalText.value = "";
      if (canonicalWarnings) canonicalWarnings.textContent = "";
      try {
        const payload = new FormData();
        payload.set("csrf", $('input[name="csrf"]', review)?.value || "");
        const response = await fetch(url, {
          method: "POST", body: payload,
          credentials: "same-origin", cache: "no-store",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) throw new Error(
          response.status === 422
            ? "Die Quelle ist für eine sichere vollständige Vorschau zu groß oder leer."
            : "Die strukturierte Markdown-Vorschau ist nicht verfügbar."
        );
        const result = await response.json();
        if (result.source_preserved !== true || typeof result.markdown !== "string"
            || result.markdown.length > 150_000) {
          throw new Error("Die Quelltexttreue konnte nicht nachgewiesen werden.");
        }
        canonicalResult = result;
        if (canonicalCount) canonicalCount.textContent =
          (result.suggested_changes || 0) + " Formateinfügungen · " +
          (result.paragraphs || 0) + " Einzelvorschriften · " +
          (result.groups || 0) + " Gruppen";
        if (canonicalText) canonicalText.value = result.markdown;
        if (canonicalWarnings) {
          canonicalWarnings.textContent = (Array.isArray(result.warnings)
            ? result.warnings.join(" ") + " " : "") + (result.note || "");
        }
        if (canonicalList && Array.isArray(result.changes)) {
          for (const change of result.changes.slice(0, 60)) {
            if (!change || typeof change.suggested_heading !== "string") continue;
            const line = document.createElement("div");
            line.className = "law-canonical-change";
            const label = document.createElement("span");
            label.className = "small text-secondary";
            label.textContent = "Zeile " + change.line;
            const suggestion = document.createElement("code");
            suggestion.textContent = change.suggested_heading;
            line.append(label, suggestion);
            canonicalList.append(line);
          }
          if (result.changes.length > 60) {
            const hint = document.createElement("p");
            hint.className = "small text-secondary mt-2";
            hint.textContent = "Weitere Vorschläge sind in der vollständigen Markdown-Vorschau enthalten.";
            canonicalList.append(hint);
          }
        }
        if (canonicalApply) canonicalApply.disabled = !canonicalConfirm?.checked;
      } catch (error) {
        if (canonicalCount) canonicalCount.textContent =
          error.message || "Gliederungsvorschau fehlgeschlagen.";
      } finally {
        canonicalBusy = false;
        canonicalButton.disabled = false;
      }
    });
    canonicalConfirm?.addEventListener("change", () => {
      if (canonicalApply) canonicalApply.disabled =
        !canonicalConfirm.checked || !canonicalResult;
    });
    canonicalApply?.addEventListener("click", () => {
      if (!canonicalResult || !canonicalConfirm?.checked) return;
      if (dirty && !window.confirm(
        "Die Markdown-Vorschau verwendet den ursprünglichen Importstand. " +
        "Deine bisherigen Änderungen im Editor werden dadurch ersetzt. Fortfahren?"
      )) return;
      editor.value = canonicalResult.markdown;
      editor.dispatchEvent(new Event("input", { bubbles: true }));
      editor.focus();
      editor.scrollIntoView({ block: "center", behavior: "smooth" });
      if (canonicalCount) canonicalCount.textContent =
        "Formatierung in den Editor geladen – bitte Wortlaut und Gliederung prüfen.";
      if (canonicalConfirm) canonicalConfirm.checked = false;
      canonicalApply.disabled = true;
    });
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
