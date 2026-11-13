/* Shared Ortsrecht formatting review: client-controlled, no automatic rewriting. */
(() => {
  "use strict";
  const editor = document.getElementById("law-ai-body") || document.getElementById("body_md");
  const toolbar = document.getElementById("law-md-quality");
  if (!editor || !toolbar) return;

  const button = toolbar.querySelector("[data-law-md-check]");
  const status = toolbar.querySelector("[data-law-md-status]");
  const form = editor.closest("form");
  const csrf = form && form.querySelector('input[name="csrf"]');
  if (!button || !status || !csrf) return;

  const action = document.createElement("button");
  action.type = "button";
  action.className = "btn btn-sm btn-outline-primary";
  action.textContent = "Vorgeschlagene Gliederung anwenden";
  action.hidden = true;
  toolbar.append(action);

  let proposed = null;
  let checkedSource = null;
  const reset = () => { proposed = null; checkedSource = null; action.hidden = true; };
  editor.addEventListener("input", reset);
  function show(message, danger) {
    status.textContent = message;
    status.classList.toggle("text-danger", !!danger);
  }
  button.addEventListener("click", async () => {
    reset();
    button.disabled = true;
    show("TAKT-Gliederung wird geprüft …");
    const source = editor.value;
    const payload = new FormData();
    payload.append("csrf", csrf.value);
    payload.append("body_md", source);
    try {
      const response = await fetch("/laws-assistant/markdown/review", {
        method: "POST", body: payload, credentials: "same-origin",
        headers: { Accept: "application/json" }, cache: "no-store",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(
        typeof data.detail === "string" ? data.detail : "Prüfung fehlgeschlagen");
      const issues = (data.diagnostics || []).slice(0, 5).join(" · ");
      show(data.norms + " Einzelvorschriften, " + data.groups +
        " Gliederungseinträge erkannt. " +
        (data.changed ? data.suggestion_count + " Überschriften als Vorschlag erkannt. " :
          "Keine eindeutigen neuen Überschriften zu formatieren. ") +
        (issues ? "Prüfhinweise: " + issues : "Keine weiteren Prüfhinweise aus dem Parser."));
      if (data.changed) {
        proposed = data.proposed_md;
        checkedSource = source;
        action.hidden = false;
      }
    } catch (error) {
      show(error && error.message ? error.message : "Formatprüfung nicht verfügbar.", true);
    } finally {
      button.disabled = false;
    }
  });
  action.addEventListener("click", () => {
    if (proposed === null || editor.value !== checkedSource) {
      show("Der Text wurde verändert. Bitte erneut prüfen.", true);
      reset();
      return;
    }
    if (!window.confirm("Nur die vorgeschlagenen Markdown-Überschriften setzen? " +
        "Prüfe anschließend die vollständige Gliederung und den Wortlaut anhand des Originals.")) return;
    const next = proposed;
    reset();
    editor.value = next;
    editor.dispatchEvent(new Event("input", { bubbles: true }));
    show("Formatvorschlag in den ungespeicherten Editor übernommen. Bitte kontrollieren.");
    editor.focus();
  });
})();
