/* TAKT AI model task picker; provider data is untrusted and always text-only. */
(() => {
  "use strict";
  const forms = document.querySelectorAll("[data-ai-task-form]");
  if (!forms.length) return;

  // The same provider is often used for all eight agent profiles. Share the
  // in-flight request and loaded catalog to avoid unnecessary API traffic.
  const catalogRequests = new Map();
  async function catalog(providerId) {
    if (!catalogRequests.has(providerId)) {
      const request = fetch("/admin/ai/provider/" + encodeURIComponent(providerId) + "/models", {
        credentials: "same-origin", cache: "no-store",
        headers: { Accept: "application/json" },
      }).then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(
          typeof data.detail === "string" ? data.detail : "Modellkatalog nicht erreichbar"
        );
        return Array.isArray(data.models) ? data.models : [];
      }).catch((error) => {
        catalogRequests.delete(providerId);
        throw error;
      });
      catalogRequests.set(providerId, request);
    }
    return catalogRequests.get(providerId);
  }

  const featureLabels = { vision: "Bildanalyse", tools: "Tools", json: "JSON", streaming: "Streaming" };
  const stateLabels = {
    reported: "vom Provider gemeldet",
    unsupported: "laut Provider nicht unterstützt",
    unknown: "unbekannt",
  };

  forms.forEach((form) => {
    const provider = form.querySelector("[data-ai-task-provider]");
    const input = form.querySelector("[data-ai-task-model]");
    const status = form.querySelector("[data-ai-model-status]");
    if (!provider || !input || !status) return;
    const startValue = input.value;
    let models = new Map();
    let requestNo = 0;
    let select = null;
    select = window.TomSelect ? new window.TomSelect(input, {
      maxItems: 1,
      create: (text) => {
        const value = String(text || "").trim();
        return value.length && value.length <= 200 ? { value, text: value + " (manuell)" } : false;
      },
      persist: false,
      searchField: ["text"],
      valueField: "value",
      labelField: "text",
      sortField: [{ field: "text", direction: "asc" }],
      placeholder: "Modell suchen oder Kennung eingeben",
      onChange: updateDescription,
    }) : null;

    function currentValue() {
      return select ? select.getValue() : input.value;
    }

    function updateDescription() {
      const selected = models.get(currentValue());
      if (!selected) return;
      const bits = [];
      if (selected.context_tokens != null) bits.push("Kontext: " + selected.context_tokens.toLocaleString("de-DE") + " Token (gemeldet)");
      for (const [feature, label] of Object.entries(featureLabels)) {
        const value = selected.features && selected.features[feature] || "unknown";
        bits.push(label + ": " + (stateLabels[value] || stateLabels.unknown));
      }
      status.textContent = bits.join(" · ");
    }

    async function loadCatalog(keepSelection) {
      const serial = ++requestNo;
      const id = provider.value;
      const previous = keepSelection ? currentValue() : "";
      models = new Map();
      if (select) {
        select.clear(true);
        select.clearOptions();
        select.addOption({ value: "", text: "Provider-Standardmodell" });
        if (previous) select.addOption({ value: previous, text: previous + " (gespeichert)" });
        select.setValue(previous || "", true);
        select.disable();
      } else {
        input.disabled = !id || id === "0";
        if (!keepSelection) input.value = "";
      }
      if (!id || id === "0") {
        status.textContent = "Die bestehende Standardroute wird verwendet.";
        return;
      }
      status.textContent = "Modelle werden vom ausgewählten Server geladen …";
      try {
        const options = await catalog(id);
        if (serial !== requestNo) return;
        for (const entry of options) {
          if (!entry || typeof entry.id !== "string") continue;
          models.set(entry.id, entry);
          if (select) select.addOption({ value: entry.id, text: entry.id });
          else if (![...input.options].some((x) => x.value === entry.id)) input.add(new Option(entry.id, entry.id));
        }
        if (select) {
          select.enable();
          select.refreshOptions(false);
          if (previous) select.setValue(previous, true);
        }
        status.textContent = options.length
          ? options.length + " Servermodelle geladen. Eigenschaften erscheinen nach der Auswahl."
          : "Der Server meldet keine Modelle; eine manuelle Modell-ID ist möglich.";
        updateDescription();
      } catch (error) {
        if (serial !== requestNo) return;
        if (select) select.enable();
        status.textContent = "Modellabfrage fehlgeschlagen: " + (error && error.message || "unbekannter Fehler")
          + ". Du kannst die Modell-ID manuell eingeben.";
      }
    }

    provider.addEventListener("change", () => loadCatalog(false));
    loadCatalog(Boolean(startValue));
  });
})();
