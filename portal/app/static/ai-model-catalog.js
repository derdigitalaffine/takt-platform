/* Model catalog picker for Provider default and Embedding models.
 * Uses existing read-only, admin-only /models proxy; secrets never reach JS.
 * With JavaScript disabled the original freeform input remains usable.
 */
(() => {
  "use strict";

  const requests = new Map();
  function catalog(providerId, force) {
    if (force) requests.delete(providerId);
    if (!requests.has(providerId)) {
      const url = "/admin/ai/provider/" + encodeURIComponent(providerId) + "/models";
      const task = fetch(url, {
        credentials: "same-origin", cache: "no-store",
        headers: { Accept: "application/json" },
      }).then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(
          typeof payload.detail === "string" ? payload.detail : "Server nicht erreichbar"
        );
        if (!Array.isArray(payload.models)) throw new Error("Ungültige Modellliste des Servers");
        return payload.models;
      }).catch((error) => {
        requests.delete(providerId);
        throw error;
      });
      requests.set(providerId, task);
    }
    return requests.get(providerId);
  }

  const descriptions = {
    reported: "gemeldet",
    unsupported: "nicht unterstützt (gemeldet)",
    unknown: "unbekannt",
  };
  const featureNames = {
    vision: "Vision", tools: "Tool-Calling",
    json: "JSON", streaming: "Streaming",
  };

  function init(input, getProviderId, refreshButton, status) {
    if (!input || !status) return;
    let serial = 0;
    let models = new Map();
    let picker = null;

    function currentValue() {
      return picker ? picker.getValue() : input.value;
    }
    function describe() {
      const item = models.get(currentValue());
      if (!item) return;
      const flags = [];
      if (item.context_tokens) {
        flags.push("Kontext: " + item.context_tokens.toLocaleString("de-DE") + " Token (gemeldet)");
      }
      for (const [key, title] of Object.entries(featureNames)) {
        flags.push(title + ": " + (descriptions[(item.features || {})[key]] || descriptions.unknown));
      }
      status.textContent = flags.join(" · ");
    }

    if (window.TomSelect) {
      picker = new window.TomSelect(input, {
        maxItems: 1,
        maxOptions: 5000,
        create: (text) => {
          const value = String(text || "").trim();
          return value.length > 0 && value.length <= 200 && !/[\x00-\x1f]/.test(value)
            ? { value, text: value + " (manuell)" } : false;
        },
        persist: false,
        valueField: "value",
        labelField: "text",
        searchField: ["text", "hint"],
        sortField: [{ field: "text", direction: "asc" }],
        placeholder: "Servermodell suchen oder Modell-ID eingeben",
        onChange: describe,
      });
    }

    async function load({ clear = false, force = false } = {}) {
      const generation = ++serial;
      const providerId = String(getProviderId() || "");
      const existing = clear ? "" : currentValue().trim();
      models = new Map();
      if (picker) {
        picker.clear(true);
        picker.clearOptions();
        if (existing) picker.addOption({ value: existing, text: existing + " (gespeichert)" });
        picker.setValue(existing, true);
      } else if (clear) {
        input.value = "";
      }

      if (!providerId || providerId === "0") {
        status.textContent = "Zuerst Provider speichern oder einen Provider auswählen. Modell-ID kann weiterhin manuell eingetragen werden.";
        return;
      }

      status.textContent = "Lade vollständige Modellliste vom Server …";
      if (refreshButton) refreshButton.disabled = true;
      try {
        const list = await catalog(providerId, force);
        if (generation !== serial) return;
        for (const entry of list) {
          if (!entry || typeof entry.id !== "string" || !entry.id.length || entry.id.length > 200) continue;
          models.set(entry.id, entry);
          if (picker) {
            const hint = Object.entries(entry.features || {})
              .filter(([, state]) => state === "reported")
              .map(([cap]) => featureNames[cap] || cap).join(" ");
            picker.addOption({ value: entry.id, text: entry.id, hint });
          }
        }
        if (picker) {
          picker.refreshOptions(false);
          if (existing) picker.setValue(existing, true);
        }
        status.textContent = models.size
          ? models.size + " verfügbare Modelle vom Server geladen. Modell auswählen oder suchen."
          : "Keine Modelle vom Server gemeldet. Eine Modell-ID kann manuell eingetragen werden.";
        describe();
      } catch (error) {
        if (generation !== serial) return;
        status.textContent = "Modellliste nicht erreichbar: " +
          (error && error.message || "Unbekannter Fehler") +
          ". Eine Modell-ID kann weiterhin manuell eingetragen werden.";
      } finally {
        if (generation === serial && refreshButton) refreshButton.disabled = false;
      }
    }

    if (refreshButton) refreshButton.addEventListener("click", () => load({ force: true }));
    return { load };
  }

  const defaultBox = document.querySelector("[data-ai-default-model-picker]");
  if (defaultBox) {
    const picker = init(
      defaultBox.querySelector("[data-ai-catalog-model]"),
      () => defaultBox.getAttribute("data-provider-id"),
      defaultBox.querySelector("[data-ai-refresh-models]"),
      defaultBox.querySelector("[data-ai-catalog-status]"),
    );
    picker?.load();
  }

  const embeddingFields = [
    ["vector-provider", "vector-model"],
    ["ai-embedding-test-provider", "ai-embedding-test-model"],
  ];
  embeddingFields.forEach(([providerId, modelId]) => {
    const provider = document.getElementById(providerId);
    const input = document.getElementById(modelId);
    const status = input?.parentElement?.querySelector("[data-ai-catalog-status]");
    if (!input || !provider || !status) return;
    const picker = init(input, () => provider.value, null, status);
    provider.addEventListener("change", () => picker.load({ clear: true }));
    picker.load();
  });
})();
