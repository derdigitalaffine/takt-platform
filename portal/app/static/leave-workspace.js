/* Leave subsection navigation and progressive enhancement of the existing forms. */
(() => {
  "use strict";
  const calendarPresent = !!document.getElementById("leave-calendar");
  const policy = document.querySelector("[data-leave-policy-topic]");
  if (policy) {
    // The server already renders only this tab's editable fields. JS merely
    // adds context and must never decide which sensitive setting is saved.
    const descriptions = {
      verfahren: "Interne Genehmigungen sind optional. Bei externer ZE-Software gibt es keine automatische Schnittstelle und keine doppelte interne Entscheidung.",
      besetzung: "Mindestbesetzung und Konfliktregeln werden vor jedem verbindlichen Eintrag serverseitig geprüft.",
      feiertage: "Arbeitsfreie Feiertage sind unabhängig von den Preisregeln der Ressourcenbuchung.",
      urlaubskonten: "Interne Urlaubskonten sind optional. Bei externer ZE-Software zeigt Takt keine erfundenen Resturlaubswerte.",
    };
    const intro = document.createElement("p");
    intro.className = "leave-setting-intro small";
    intro.textContent = descriptions[policy.dataset.leavePolicyTopic] || "";
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
