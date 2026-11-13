/* Unverbindliche Verfügbarkeitsvorschau; der Server prüft beim Buchen erneut. */
(() => {
  for (const form of document.querySelectorAll("[data-pool-availability]")) {
    const start = form.elements.namedItem("start");
    const end = form.elements.namedItem("end");
    const quantity = form.elements.namedItem("quantity");
    const asset = form.elements.namedItem("asset_id");
    const result = form.querySelector(".res-pool-availability");
    const submit = form.querySelector('button[type="submit"]');
    let revision = 0;
    async function check() {
      const run = ++revision;
      result.dataset.state = "";
      submit.disabled = false;
      if (!start.value || !end.value) {
        result.textContent = "Zeitraum auswählen, um die Verfügbarkeit zu prüfen.";
        return;
      }
      if (new Date(start.value) >= new Date(end.value)) {
        result.dataset.state = "busy";
        result.textContent = "Das Ende muss nach dem Beginn liegen.";
        submit.disabled = true;
        return;
      }
      const args = new URLSearchParams({asset_id: asset.value, start: start.value, end: end.value});
      try {
        const response = await fetch("/resources/intern/verfuegbarkeit?" + args, {credentials:"same-origin"});
        if (revision !== run) return;
        if (!response.ok) throw new Error("Prüfung nicht möglich");
        const info = await response.json();
        const enough = info.active && info.available >= Number(quantity.value);
        result.dataset.state = enough ? "ok" : "busy";
        result.textContent = enough
          ? info.available + " Stück für diesen Zeitraum frei."
          : "Nur " + info.available + " Stück im Zeitraum verfügbar.";
        submit.disabled = !enough;
      } catch (_) {
        if (revision !== run) return;
        result.textContent = "Verfügbarkeit wird beim Absenden geprüft.";
      }
    }
    [start, end, quantity].forEach(input => input.addEventListener("change", check));
  }
})();
