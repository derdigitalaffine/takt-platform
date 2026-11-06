(() => {
  "use strict";
  const el = document.getElementById("shared-calendar");
  if (!el) return;
  const form = document.getElementById("calendar-event-form"),
    fields = form.elements,
    sources = new Map();
  const preferenceKey = "takt-calendar-visible-v1:" + el.dataset.calendarUser;
  let sourcePreference = null;
  try {
    const stored = JSON.parse(sessionStorage.getItem(preferenceKey) || "null");
    if (stored && Array.isArray(stored.knownIds) && Array.isArray(stored.knownKinds))
      sourcePreference = stored;
  } catch (_) {
    // Browsing must still work when session storage is unavailable or corrupt.
  }
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
    initialView: el.dataset.calendarMode === "year" ? "multiMonthYear" : "dayGridMonth",
    initialDate: el.dataset.calendarDate || undefined,
    height: "auto",
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "dayGridMonth,timeGridWeek,timeGridDay,listMonth,multiMonthYear",
    },
    loading(isLoading) {
      const indicator = document.getElementById("calendar-loading");
      if (indicator) indicator.hidden = !isLoading;
    },
    datesSet(info) {
      // The built-in FullCalendar toolbar also changes views. Keep the
      // workspace mode indicator consistent with those view buttons.
      queueMicrotask(() => {
        if (el.isConnected) markMode(info.view.type === "multiMonthYear" ? "year" : "month");
      });
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
  // Both planning modes are FullCalendar views. Preserve the calendar instance,
  // loaded sources, editor state and document instead of navigating to a new page.
  const modeLinks = [...document.querySelectorAll("[data-calendar-mode-link]")];
  const modeFor = (url) => url.pathname === "/kalender/jahr" ? "year" : "month";
  function markMode(mode) {
    for (const link of modeLinks) {
      const selected = modeFor(new URL(link.href)) === mode;
      link.classList.toggle("active", selected);
      if (selected) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    el.dataset.calendarMode = mode;
    const heading = document.querySelector(".planning-context-title");
    const lead = document.querySelector(".planning-context-lead");
    if (heading) heading.textContent = mode === "year" ? "Jahresüberblick" : "Kalenderübersicht";
    if (lead) lead.textContent = mode === "year"
      ? "Das ganze Jahr auf einen Blick" : "Einzeltermine und Ihre Kalender";
    const yearInfo = document.querySelector(".calendar-year-information");
    if (yearInfo) yearInfo.hidden = mode !== "year";
  }
  function selectMode(mode, date) {
    const view = mode === "year" ? "multiMonthYear" : "dayGridMonth";
    if (date) calendar.gotoDate(date);
    calendar.changeView(view);
    markMode(mode);
  }
  for (const link of modeLinks) {
    link.addEventListener("click", (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey ||
          event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      const target = new URL(link.href);
      target.searchParams.set("date", localValue(calendar.getDate()).slice(0, 10));
      const mode = modeFor(target);
      selectMode(mode);
      if (target.href !== location.href) history.pushState({ planningMode: mode }, "", target);
    });
  }
  window.addEventListener("popstate", () => {
    if (!location.pathname.startsWith("/kalender")) return;
    const mode = modeFor(new URL(location.href));
    selectMode(mode, new URL(location.href).searchParams.get("date"));
  });
  markMode(el.dataset.calendarMode);
  // Ephemeral read-only Fachkalender: same server-side projector as attached
  // calendar sources, no additional Calendar rows and no duplicated terms.
  // Forms remain a safe POST fallback for browsers without JavaScript.
  const overlays = new Map();
  function rememberSelection() {
    const controls = [...document.querySelectorAll("input[data-calendar]")];
    const forms = [...document.querySelectorAll("form[data-inline-source]")];
    const snapshot = {
      knownIds: controls.map((item) => item.dataset.calendar),
      ids: controls.filter((item) => item.checked).map((item) => item.dataset.calendar),
      knownKinds: forms.map((item) => item.dataset.inlineSource),
      kinds: forms.filter((item) => item.querySelector("button")?.getAttribute("aria-pressed") === "true")
        .map((item) => item.dataset.inlineSource),
    };
    try {
      sessionStorage.setItem(preferenceKey, JSON.stringify(snapshot));
    } catch (_) {
      // Preferences are optional; no change to live calendar visibility.
    }
  }
  function showOverlay(form, on) {
    const kind = form.dataset.inlineSource;
    const button = form.querySelector("button");
    if (!button) return;
    if (!on) {
      overlays.get(kind)?.remove();
      overlays.delete(kind);
    } else if (!overlays.has(kind)) {
      const source = calendar.addEventSource({
        id: "fach:" + kind,
        events: async (info, success, failure) => {
          try {
            const params = new URLSearchParams({
              start: info.startStr,
              end: info.endStr,
            });
            const response = await fetch(
              "/kalender/quellen/" + encodeURIComponent(kind) + "/data?" + params,
              { credentials: "same-origin" },
            );
            if (!response.ok) throw Error("Fachkalender konnte nicht geladen werden.");
            const data = await response.json();
            success(data.events);
          } catch (error) {
            document.getElementById("calendar-error").textContent = error.message;
            failure(error);
          }
        },
      });
      overlays.set(kind, source);
    }
    button.setAttribute("aria-pressed", String(on));
    button.classList.toggle("is-active", on);
    const icon = button.querySelector(".calendar-source-toggle-icon");
    if (icon) {
      icon.classList.toggle("fa-regular", !on);
      icon.classList.toggle("fa-solid", on);
      icon.classList.toggle("fa-circle", !on);
      icon.classList.toggle("fa-circle-check", on);
    }
  }
  for (const overlay of document.querySelectorAll("[data-inline-source]")) {
    overlay.addEventListener("submit", (event) => {
      event.preventDefault();
      const button = overlay.querySelector("button");
      showOverlay(overlay, button?.getAttribute("aria-pressed") !== "true");
      rememberSelection();
    });
    const kind = overlay.dataset.inlineSource;
    const alreadyChosen = sourcePreference?.knownKinds?.includes(kind);
    const enabled = alreadyChosen
      ? sourcePreference.kinds?.includes(kind)
      : overlay.dataset.sourceDefault === "true";
    if (enabled) showOverlay(overlay, true);
  }
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
  document.querySelector("[data-year-new-event]")?.addEventListener("click", (event) => {
    const button = event.currentTarget;
    form.reset();
    fields.id.value = "";
    fields.version.value = "";
    fields.kind.disabled = false;
    fields.kind.value = "event";
    fields.calendar_id.disabled = false;
    fields.calendar_id.value = button.dataset.calendarId;
    document.getElementById("event-delete").hidden = true;
    const now = new Date();
    const day = localValue(now).slice(0, 10);
    fields.start.value = day;
    fields.end.value = day;
    fields.all_day.checked = true;
    toggleKind();
    const editor = document.getElementById("event-editor");
    editor.open = true;
    editor.scrollIntoView({ block: "start", behavior: "smooth" });
    fields.title.focus({ preventScroll: true });
  });
  for (const check of document.querySelectorAll("[data-calendar]")) {
    const id = check.dataset.calendar;
    if (sourcePreference?.knownIds?.includes(id))
      check.checked = sourcePreference.ids?.includes(id);
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
    check.addEventListener("change", () => {
      update();
      rememberSelection();
    });
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
