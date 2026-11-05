/* Leave subsection navigation and progressive enhancement of the existing forms. */
(() => {
  "use strict";
  const calendarPresent = !!document.getElementById("leave-calendar");
  const policy = document.querySelector("[data-leave-policy-topic]");
  if (policy) {
    const topic = policy.dataset.leavePolicyTopic;
    const groups = {
      verfahren: ["workflow", "external_url", "approval_units", "sync_absence"],
      besetzung: ["minimum", "conflict_mode", "notify_only_warnings", "advanced", "minimum_capacity"],
      feiertage: ["holiday_state"],
      urlaubskonten: ["internal_account"],
    };
    const names = new Set(groups[topic] || groups.verfahren);
    const namesUsed = new Set(Object.values(groups).flat());
    const form = policy.querySelector("form");
    if (form) {
      for (const field of form.querySelectorAll("input[name],select[name]")) {
        if (!namesUsed.has(field.name)) continue;
        const owner = field.closest("label") || field;
        owner.hidden = !names.has(field.name);
        if (field.name === "holiday_state") {
          const title = form.querySelector('label[for="leave-holidays"]');
          if (title) title.hidden = !names.has(field.name);
        }
      }
      const hints = [
        ["Genehmigungsweg:", "verfahren"],
        ["Gesetzliche Feiertage", "feiertage"],
        ["Verbindliche Sperren", "besetzung"],
        ["Die Übernahme erteilt", "verfahren"],
      ];
      for (const paragraph of form.querySelectorAll("p")) {
        for (const [needle, owner] of hints)
          if (paragraph.textContent.includes(needle)) paragraph.hidden = topic !== owner;
      }
    }
    const descriptions = {
      verfahren: "Interne Genehmigungen sind optional. Bei externer ZE-Software gibt es keine automatische Schnittstelle und keine doppelte interne Entscheidung.",
      besetzung: "Mindestbesetzung und Konfliktregeln gelten für verbindliche Zeiten; Vorschauen reservieren keine Kapazität.",
      feiertage: "Arbeitsfreie Feiertage und Sonderdienste sind unabhängig von den Preisregeln der Ressourcenbuchung.",
      urlaubskonten: "Interne Urlaubskonten sind optional. Bei externer ZE-Software zeigt Takt keine erfundenen Resturlaubswerte.",
    };
    const intro = document.createElement("p");
    intro.className = "leave-setting-intro small";
    intro.textContent = descriptions[topic] || "";
    policy.prepend(intro);
  }
  document.addEventListener("click", async (event) => {
    if (!calendarPresent) {
      const edit = event.target.closest("[data-leave-edit-link]");
      if (edit) {
        location.assign(edit.dataset.leaveEditLink);
        return;
      }
      const closure = event.target.closest("[data-closure-plan]");
      if (closure) {
        const unit = document.getElementById("leave-unit")?.value;
        const params = new URLSearchParams({
          unit, person: closure.dataset.person, start: closure.dataset.start,
          end: closure.dataset.end, start_half: closure.dataset.startHalf || "am",
          end_half: closure.dataset.endHalf || "pm",
        });
        location.assign("/urlaub/planer?" + params.toString());
        return;
      }
      const copy = event.target.closest("[data-leave-copy]");
      if (copy) {
        const heading = copy.closest(".leave-request-card")?.querySelector("h2")?.textContent;
        if (!heading) return;
        try {
          await navigator.clipboard.writeText(heading.trim());
          copy.textContent = "Zeitraum kopiert";
        } catch (_) {
          copy.textContent = "Bitte Datum manuell übernehmen";
        }
      }
    }
  });
})();
