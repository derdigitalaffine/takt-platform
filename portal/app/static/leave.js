/* The timeline proposes changes; the same server commands handle every input method. */
(async () => {
  "use strict";
  const el = document.getElementById("leave-calendar");
  if (!el) return;
  const form = document.getElementById("leave-form");
  const feedback = document.getElementById("leave-feedback");
  let requests = [],
    people = [];
  function report(error) {
    feedback.textContent = error.message;
    feedback.hidden = false;
    feedback.scrollIntoView({ block: "nearest" });
  }
  async function send(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok)
      throw Error(
        typeof data.detail === "string"
          ? data.detail
          : "Bitte Eingaben prüfen.",
      );
    return data;
  }
  function edit(row, proposal) {
    if (!form) return;
    form.setAttribute("action", row ? "/urlaub/" + row.id : "/urlaub");
    form.dataset.requestId = row ? row.id : "";
    for (const input of form.querySelectorAll("[data-edit-meta]"))
      input.remove();
    if (row)
      for (const [name, value] of Object.entries({
        version: row.version,
        action: "save",
      })) {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = value;
        input.dataset.editMeta = "1";
        form.append(input);
      }
    const values = proposal
      ? {
          person_id: proposal.personId,
          starts_on: proposal.start,
          ends_on: proposal.end,
          start_half: proposal.startHalf,
          end_half: proposal.endHalf,
        }
      : row;
    if (values)
      for (const key of [
        "person_id",
        "starts_on",
        "ends_on",
        "start_half",
        "end_half",
      ])
        if (form.elements[key].tomselect)
          form.elements[key].tomselect.setValue(String(values[key]), true);
        else form.elements[key].value = values[key];
    const person = form.elements.person_id;
    person.disabled = !!row;
    if (person.tomselect) person.tomselect[row ? "disable" : "enable"]();
    document.getElementById("leave-editor-title").textContent = row
      ? "Urlaubszeit ändern"
      : "Zeitraum eintragen";
    document.getElementById("leave-edit-note").hidden = !row || !row.effective;
    document.getElementById("leave-submit").textContent = row
      ? "Änderung als Entwurf speichern"
      : "Als geplant speichern";
    document.getElementById("leave-reset").hidden = !row;
    document
      .getElementById("leave-editor")
      .scrollIntoView({ block: "center", behavior: "smooth" });
    (
      document.getElementById("leave-starts_on-display") ||
      form.elements.starts_on
    ).focus();
  }
  function payload() {
    const data = Object.fromEntries(new FormData(form));
    data.person_id = form.elements.person_id.value;
    if (form.dataset.requestId) data.request_id = form.dataset.requestId;
    return data;
  }
  async function preview() {
    const data = await send("/urlaub/preview", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": form.elements.csrf.value,
      },
      body: JSON.stringify(payload()),
    });
    const area = document.getElementById("leave-preview-content");
    area.replaceChildren();
    if (!data.conflicts.length)
      area.textContent =
        "Keine Besetzungskonflikte. Beim Verbindlichmachen wird erneut geprüft.";
    for (const issue of data.conflicts) {
      const p = document.createElement("p");
      p.textContent = `${issue.forecast ? "Möglicher Konflikt mit Planungen" : issue.mode === "block" ? "Sperre" : "Warnung"}: ${issue.day}, ${issue.half === "am" ? "Vormittag" : "Nachmittag"} · verfügbar ${issue.available}, erforderlich ${issue.minimum} (Bereich ${issue.org_id})`;
      p.className = issue.forecast ? "text-secondary" : "fw-semibold";
      area.append(p);
    }
    document.getElementById("leave-preview").hidden = false;
  }
  for (const button of document.querySelectorAll("[data-closure-plan]"))
    button.addEventListener("click", () =>
      edit(null, {
        personId: button.dataset.person,
        start: button.dataset.start,
        end: button.dataset.end,
        startHalf: button.dataset.startHalf || "am",
        endHalf: button.dataset.endHalf || "pm",
      }),
    );
  if (form) {
    document
      .getElementById("leave-check")
      .addEventListener("click", () => preview().catch(report));
    document.getElementById("leave-reset").addEventListener("click", () => {
      form.reset();
      edit(null);
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = document.getElementById("leave-submit");
      button.disabled = true;
      feedback.hidden = true;
      try {
        await send(form.getAttribute("action"), {
          method: "POST",
          headers: { Accept: "application/json" },
          body: new URLSearchParams(payload()),
        });
        location.reload();
      } catch (error) {
        report(error);
        button.disabled = false;
      }
    });
  }
  for (const command of document.querySelectorAll("[data-leave-command]"))
    command.addEventListener("submit", async (event) => {
      event.preventDefault();
      feedback.hidden = true;
      const data = new FormData(command);
      if (event.submitter) data.set("action", event.submitter.value);
      const buttons = command.querySelectorAll("button");
      buttons.forEach((b) => (b.disabled = true));
      try {
        await send(command.getAttribute("action"), {
          method: "POST",
          headers: { Accept: "application/json" },
          body: data,
        });
        location.reload();
      } catch (error) {
        report(error);
        buttons.forEach((b) => (b.disabled = false));
      }
    });
  for (const settings of document.querySelectorAll('form[method="post"]')) {
    if (settings === form || settings.hasAttribute("data-leave-command"))
      continue;
    settings.addEventListener("submit", async (event) => {
      event.preventDefault();
      feedback.hidden = true;
      const body = new FormData(settings);
      if (event.submitter?.name)
        body.set(event.submitter.name, event.submitter.value);
      const buttons = settings.querySelectorAll("button");
      buttons.forEach((b) => (b.disabled = true));
      try {
        const response = await fetch(
          settings.getAttribute("action") || location.href,
          { method: "POST", body },
        );
        if (!response.ok) {
          const data = await response.json();
          throw Error(
            typeof data.detail === "string" ? data.detail : "Eingaben prüfen.",
          );
        }
        location.assign(response.url);
      } catch (error) {
        report(error);
        buttons.forEach((b) => (b.disabled = false));
      }
    });
  }
  try {
    const data = await send(
      "/urlaub/data?unit=" + encodeURIComponent(el.dataset.unit),
    );
    requests = data.requests;
    people = data.people;
    for (const button of document.querySelectorAll("[data-leave-edit]"))
      button.addEventListener("click", () =>
        edit(requests.find((r) => String(r.id) === button.dataset.leaveEdit)),
      );
    for (const button of document.querySelectorAll("[data-leave-copy]"))
      button.addEventListener("click", async () => {
        const row = requests.find(
          (r) => String(r.id) === button.dataset.leaveCopy,
        );
        try {
          await navigator.clipboard.writeText(
            `Urlaub: ${row.starts_on} (${row.start_half === "am" ? "Vormittag" : "Nachmittag"}) bis ${row.ends_on} (${row.end_half === "am" ? "Vormittag" : "Nachmittag"})`,
          );
          button.textContent = "Zeitraum kopiert";
        } catch (error) {
          report(
            Error(
              "Kopieren nicht verfügbar. Bitte den angezeigten Zeitraum übernehmen.",
            ),
          );
        }
      });
    const view = TaktPersonTimeline.create({
      people,
      onSelect(p) {
        edit(null, p);
      },
      onChangeRequest(p) {
        edit(
          requests.find((r) => r.id === p.event.extendedProps.requestId),
          p,
        );
      },
      onEventClick({ event }) {
        const row = requests.find(
          (r) => r.id === event.extendedProps.requestId,
        );
        if (!row) {
          const dialog = document.createElement("dialog");
          dialog.className = "p-4 rounded";
          const text = document.createElement("p");
          text.textContent =
            "Wirksame Abwesenheit · " +
            event.startStr +
            " bis " +
            event.endStr +
            " (Ende ausschließlich).";
          const close = document.createElement("button");
          close.type = "button";
          close.className = "btn btn-outline-secondary";
          close.textContent = "Schließen";
          close.onclick = () => dialog.close();
          dialog.append(text, close);
          document.body.append(dialog);
          dialog.addEventListener("close", () => dialog.remove());
          dialog.showModal();
          return;
        }
        if (event.extendedProps.canEdit) edit(row);
        else
          document
            .getElementById("leave-row-" + row.id)
            ?.scrollIntoView({ block: "center", behavior: "smooth" });
      },
    });
    const events = [];
    function addEvent(row, range, id, status, title) {
      const end = new Date(range.ends_on + "T00:00:00Z");
      end.setUTCDate(end.getUTCDate() + 1);
      events.push({
        id,
        title,
        start: range.starts_on,
        end: end.toISOString().slice(0, 10),
        allDay: true,
        extendedProps: {
          personId: row.person_id,
          requestId: status === "absence" ? null : row.id,
          canEdit:
            status !== "absence" &&
            people.some(
              (p) => String(p.id) === String(row.person_id) && p.canSelect,
            ),
          startHalf: range.start_half,
          endHalf: range.end_half,
          status,
        },
      });
    }
    for (const row of requests) {
      if (row.effective)
        addEvent(
          row,
          row.effective,
          row.id + ":effective",
          row.external_attested ? "external" : "binding",
          "Verbindlicher Urlaub",
        );
      if (["planned", "requested"].includes(row.status))
        addEvent(
          row,
          row,
          row.id + ":proposal",
          row.status,
          row.effective ? "Urlaubsänderung" : "Urlaubsplanung",
        );
    }
    for (const row of data.absences || [])
      addEvent(row, row, "absence:" + row.id, "absence", "Abwesend");
    let summaryKey = "";
    const calendar = new FullCalendar.Calendar(el, {
      plugins: [view.plugin],
      initialView: "taktPeople",
      locale: "de",
      height: "auto",
      headerToolbar: {
        left: "prev,next today",
        center: "title",
        right: "taktPeople,taktPeopleQuarter,taktPeopleYear",
      },
      events,
      datesSet(info) {
        const key = info.startStr + info.endStr;
        if (key === summaryKey) return;
        summaryKey = key;
        send(
          "/urlaub/besetzung?unit=" +
            encodeURIComponent(el.dataset.unit) +
            "&start=" +
            encodeURIComponent(info.startStr) +
            "&end=" +
            encodeURIComponent(info.endStr),
        )
          .then((value) => view.setSummaries(value.summaries, value.holidays))
          .catch(report);
      },
    });
    view.attach(calendar);
    calendar.render();
  } catch (error) {
    report(error);
  }
})();
