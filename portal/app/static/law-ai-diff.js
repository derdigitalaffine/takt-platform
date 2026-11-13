/* Source-vs-editor legal-text comparison. No persistence or HTML from documents. */
(() => {
  "use strict";
  const editor = document.getElementById("law-ai-body");
  const host = document.getElementById("law-original-diff");
  if (!editor || !host) return;
  const baseline = editor.value;
  const output = host.querySelector("[data-law-diff-result]");
  const compare = host.querySelector("[data-law-diff-run]");
  if (!output || !compare) return;

  const textNode = (tag, content, className) => {
    const el = document.createElement(tag);
    el.textContent = content;
    if (className) el.className = className;
    return el;
  };
  function diff() {
    const before = baseline.split("\n");
    const after = editor.value.split("\n");
    const limit = Math.min(Math.max(before.length, after.length), 40000);
    let prefix = 0;
    while (prefix < limit && prefix < before.length &&
           prefix < after.length && before[prefix] === after[prefix]) prefix++;
    let suffix = 0;
    while (suffix < limit - prefix && suffix < before.length - prefix &&
           suffix < after.length - prefix &&
           before[before.length - 1 - suffix] === after[after.length - 1 - suffix]) suffix++;
    const removed = before.slice(prefix, before.length - suffix);
    const added = after.slice(prefix, after.length - suffix);
    output.replaceChildren();
    if (!removed.length && !added.length) {
      output.append(textNode("p", "Keine Veränderungen gegenüber dem importierten Text.", "text-success mb-0"));
      return;
    }
    output.append(textNode("p",
      "Unveränderte Anfangszeilen: " + prefix + " · Unveränderte Endzeilen: " +
      suffix + " · betroffene Originalzeilen: " + removed.length +
      " · betroffene Entwurfszeilen: " + added.length +
      ". Der Vergleich zeigt zusammenhängende Änderungsbereiche und ist keine juristische Bewertung.",
      "small text-secondary"));
    const grid = document.createElement("div");
    grid.className = "law-diff-grid";
    for (const [label, lines, style] of [
      ["Importierter Originaltext (Zeilen " + (prefix + 1) + " ff.)", removed, "law-diff-old"],
      ["Aktueller Arbeitsentwurf (Zeilen " + (prefix + 1) + " ff.)", added, "law-diff-new"]
    ]) {
      const col = document.createElement("section");
      const heading = textNode("h4", label, "h6");
      const pre = textNode("pre", lines.slice(0, 300).join("\n") ||
        "(keine Zeilen)", style);
      pre.setAttribute("tabindex", "0");
      col.append(heading, pre);
      if (lines.length > 300) {
        col.append(textNode("p", "Nur die ersten 300 geänderten Zeilen angezeigt; " +
          "für einen vollständigen Vergleich den gesamten Dokumenttext prüfen.", "small text-warning"));
      }
      grid.append(col);
    }
    output.append(grid);
  }
  compare.addEventListener("click", diff);
  editor.addEventListener("input", () => {
    output.replaceChildren(textNode("p",
      "Entwurf seit dem letzten Vergleich verändert. Erneut vergleichen.",
      "small text-secondary mb-0"));
  });
})();
