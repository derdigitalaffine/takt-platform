(() => {
  "use strict";
  const el = document.getElementById("shared-calendar");
  if (!el) return;
  const form = document.getElementById("calendar-event-form"),
    fields = form.elements,
    sources = new Map();
  const localValue = (date) => {
    const d = new Date(date);
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
  };
  function values(start, end) {
    fields.start.value = start.slice(0, 10);
    fields.end.value = end.slice(0, 10);
    if (start.includes("T")) fields.start_time.value = start.slice(11, 16);
    if (end.includes("T")) fields.end_time.value = end.slice(11, 16);
  }
  function time(key) {
    return new Date(fields[key].value + "T" + fields[key + "_time"].value);
  }
  function duration() {
    if (fields.all_day.checked) return;
    const minutes = (time("end") - time("start")) / 60000;
    if (minutes > 0) fields.duration.value = String(minutes);
  }
  function endFromDuration() {
    if (fields.all_day.checked) return;
    const minutes = Number(fields.duration.value),
      start = time("start");
    if (minutes > 0 && Number.isFinite(start.getTime())) {
      const end = localValue(new Date(start.getTime() + minutes * 60000));
      fields.end.value = end.slice(0, 10);
      fields.end_time.value = end.slice(11, 16);
    }
  }
  function toggleTimes() {
    for (const row of form.querySelectorAll(".calendar-time"))
      row.hidden = fields.all_day.checked;
    for (const key of ["start_time", "end_time", "duration"])
      fields[key].disabled = fields.all_day.checked;
  }
  fields.all_day.addEventListener("change", toggleTimes);
  fields.duration.addEventListener("input", endFromDuration);
  for (const key of ["start", "start_time"])
    fields[key].addEventListener("change", endFromDuration);
  for (const key of ["end", "end_time"])
    fields[key].addEventListener("change", duration);
  const calendar = new FullCalendar.Calendar(el, {
    locale: "de",
    initialView: "dayGridMonth",
    height: "auto",
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "dayGridMonth,timeGridWeek,listMonth,multiMonthYear",
    },
    loading(isLoading) {
      const indicator = document.getElementById("calendar-loading");
      if (indicator) indicator.hidden = !isLoading;
    },
    eventClick(info) {
      const event = info.event;
      if (event.extendedProps.source && event.extendedProps.url) {
        window.location.assign(event.extendedProps.url);
        return;
      }
      if (event.extendedProps.kind === "closure") {
        window.location.assign(event.extendedProps.url);
        return;
      }
      if (!event.extendedProps.canWrite) {
        const dialog = document.createElement("dialog");
        dialog.className = "pt-dialog";
        const title = document.createElement("h2");
        title.textContent = event.title;
        title.className = "h5";
        const text = document.createElement("p");
        text.textContent =
          event.start.toLocaleString("de-DE") +
          " · " +
          (event.extendedProps.location || "") +
          " " +
          (event.extendedProps.description || "");
        const close = document.createElement("button");
        close.textContent = "Schließen";
        close.className = "btn btn-outline-secondary";
        close.onclick = () => dialog.close();
        dialog.append(title, text, close);
        document.body.append(dialog);
        dialog.addEventListener("close", () => dialog.remove());
        dialog.showModal();
        return;
      }
      document.getElementById("event-delete").hidden = false;
      fields.kind.value = "event";
      toggleKind();
      const series = !!event.extendedProps.series;
      document.getElementById("series-warning").hidden = !series;
      fields.replace_series.required = series;
      fields.replace_series.checked = false;
      fields.repeat.value = series
        ? event.extendedProps.repeat.toLowerCase()
        : "none";
      fields.repeat_count.value = series ? event.extendedProps.repeatCount : 10;
      fields.id.value = series ? event.extendedProps.seriesId : event.id;
      fields.kind.disabled = true;
      fields.version.value = event.extendedProps.version;
      fields.calendar_id.value = event.extendedProps.calendarId;
      fields.org_id_event.value = event.extendedProps.orgId || "";
      fields.include_children.checked =
        event.extendedProps.includeChildren !== false;
      fields.title.value = series
        ? event.extendedProps.masterTitle
        : event.title;
      fields.all_day.checked = event.allDay;
      toggleTimes();
      const a = series ? event.extendedProps.masterStart : event.startStr,
        b = series ? event.extendedProps.masterEnd : event.endStr;
      values(
        event.allDay ? a.slice(0, 10) : localValue(a),
        event.allDay
          ? new Date(new Date(b).getTime() - 86400000)
              .toISOString()
              .slice(0, 10)
          : localValue(b),
      );
      duration();
      fields.location.value = event.extendedProps.location;
      fields.description.value = event.extendedProps.description;
      document.getElementById("event-editor").open = true;
      fields.title.focus();
    },
  });
  calendar.render();
  const closureCheckbox = document.querySelector("[data-closures]");
  let closureSource;
  function loadClosures() {
    if (closureSource) {
      closureSource.remove();
      closureSource = null;
    }
    if (closureCheckbox.checked)
      closureSource = calendar.addEventSource({
        id: "closures",
        url: "/kalender/organisationstermine",
        success: (data) => data.events,
      });
  }
  closureCheckbox.addEventListener("change", loadClosures);
  loadClosures();
  function toggleKind() {
    const closed = fields.kind.value === "closure";
    document.getElementById("closure-fields").hidden = !closed;
    document.getElementById("event-audience").hidden = closed;
    for (const row of form.querySelectorAll(".calendar-series"))
      row.hidden = closed;
    for (const field of [
      fields.calendar_id,
      fields.location,
      fields.description,
    ]) {
      field.closest(".col-md-6").hidden = closed;
      field.disabled = closed;
    }
    if (closed) fields.all_day.checked = true;
    fields.all_day.disabled = closed;
    toggleTimes();
  }
  fields.kind.addEventListener("change", toggleKind);
  for (const check of document.querySelectorAll("[data-calendar]")) {
    function update() {
      const id = check.dataset.calendar;
      if (!check.checked) {
        sources.get(id)?.remove();
        sources.delete(id);
        return;
      }
      sources.set(
        id,
        calendar.addEventSource({
          id,
          events: async (info, success, failure) => {
            try {
              const response = await fetch(
                "/kalender/" +
                  id +
                  "/data?start=" +
                  encodeURIComponent(info.startStr) +
                  "&end=" +
                  encodeURIComponent(info.endStr),
              );
              if (!response.ok)
                throw Error("Kalender konnte nicht geladen werden.");
              const data = await response.json();
              success(
                data.events.map((e) => ({
                  ...e,
                  extendedProps: { ...e.extendedProps, calendarId: id },
                })),
              );
            } catch (e) {
              document.getElementById("calendar-error").textContent = e.message;
              failure(e);
            }
          },
        }),
      );
    }
    check.addEventListener("change", update);
    update();
  }
  form.addEventListener("reset", () => {
    setTimeout(() => {
      fields.id.value = "";
      fields.version.value = "";
      document.getElementById("event-delete").hidden = true;
      fields.replace_series.required = false;
      document.getElementById("series-warning").hidden = true;
      toggleKind();
    }, 0);
  });
  document
    .getElementById("event-delete")
    .addEventListener("click", async () => {
      if (
        !fields.id.value ||
        !confirm("Diesen Termin einschließlich aller Serientermine löschen?")
      )
        return;
      try {
        const response = await fetch(
          "/kalender/" + fields.calendar_id.value + "/termine",
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": document.querySelector("meta[name=csrf]").content,
            },
            body: JSON.stringify({
              id: fields.id.value,
              version: fields.version.value,
              action: "delete",
            }),
          },
        );
        if (!response.ok) {
          const result = await response.json();
          throw Error(result.detail || "Termin konnte nicht gelöscht werden.");
        }
        form.reset();
        calendar.refetchEvents();
      } catch (error) {
        document.getElementById("event-error").textContent = error.message;
      }
    });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const error = document.getElementById("event-error"),
      submit = form.querySelector("[type=submit],button:not([type])");
    submit.disabled = true;
    try {
      const all = fields.all_day.checked,
        data = Object.fromEntries(new FormData(form));
      data.all_day = all;
      data.time_zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (!all) {
        data.start = time("start").toISOString();
        data.end = time("end").toISOString();
      }
      const closed = fields.kind.value === "closure";
      if (!closed) data.org_id = fields.org_id_event.value;
      if (closed) {
        data.all_day = true;
        delete data.id;
      }
      const response = await fetch(
        closed
          ? "/kalender/schliesszeiten"
          : "/kalender/" + encodeURIComponent(data.calendar_id) + "/termine",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": document.querySelector("meta[name=csrf]").content,
          },
          body: JSON.stringify(data),
        },
      );
      if (!response.ok) {
        const result = await response.json();
        throw Error(result.detail || "Termin konnte nicht gespeichert werden.");
      }
      form.reset();
      error.textContent = "";
      calendar.refetchEvents();
    } catch (e) {
      error.textContent = e.message;
    } finally {
      submit.disabled = false;
    }
  });
})();
