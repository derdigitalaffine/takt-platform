/* Takt's own MIT-licensed person timeline. FullCalendar Standard 6 custom-view API.
   No premium resource API, vendor patches, network requests or business decisions. */
(function (global) {
  "use strict";
  const DAY = 86400000;
  const statuses = {
    planned: ["Geplant", "○"],
    requested: ["Beantragt", "◷"],
    binding: ["Verbindlich", "✓"],
    external: ["Extern genehmigt · Selbstauskunft", "✓"],
    absence: ["Abwesend", "–"],
  };
  function dayNumber(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || ""))
      throw new Error("Gültiges Datum wählen.");
    const time = Date.parse(value + "T00:00:00Z");
    if (
      !Number.isFinite(time) ||
      new Date(time).toISOString().slice(0, 10) !== value
    )
      throw new Error("Gültiges Datum wählen.");
    return time / DAY;
  }
  const dayString = (n) => new Date(n * DAY).toISOString().slice(0, 10);
  function toSlots(start, end, startHalf = "am", endHalf = "pm") {
    if (!["am", "pm"].includes(startHalf) || !["am", "pm"].includes(endHalf))
      throw new Error("Tagesabschnitt prüfen.");
    const a = dayNumber(start) * 2 + (startHalf === "pm" ? 1 : 0);
    const b = dayNumber(end) * 2 + (endHalf === "pm" ? 2 : 1);
    if (b <= a) throw new Error("Das Ende muss nach dem Beginn liegen.");
    return [a, b];
  }
  function fromSlots(a, b) {
    if (!Number.isInteger(a) || !Number.isInteger(b) || b <= a)
      throw new Error("Ungültiger Zeitraum.");
    return {
      start: dayString(Math.floor(a / 2)),
      startHalf: a % 2 ? "pm" : "am",
      end: dayString(Math.floor((b - 1) / 2)),
      endHalf: (b - 1) % 2 ? "pm" : "am",
      endExclusive: dayString(Math.ceil(b / 2)),
    };
  }
  function pack(items) {
    const ends = [];
    return [...items]
      .sort((a, b) => a.a - b.a || b.b - a.b || a.id.localeCompare(b.id))
      .map((item) => {
        let track = ends.findIndex((end) => end <= item.a);
        if (track < 0) track = ends.length;
        ends[track] = item.b;
        return { ...item, track };
      });
  }
  function create(config = {}) {
    const FC = global.FullCalendar;
    if (!FC || !FC.createPlugin)
      throw new Error("FullCalendar Standard 6 zuerst laden.");
    let calendar,
      currentRoot,
      people = config.people || [],
      summaries = config.summaries || [];
    const collapsed = new Set();
    let query = "",
      sequence = 0,
      disposed = false;
    function node(tag, className, text) {
      const el = document.createElement(tag);
      if (className) el.className = className;
      if (text !== undefined) el.textContent = text;
      return el;
    }
    function button(text, cls, click) {
      const el = node("button", cls, text);
      el.type = "button";
      if (click) el.addEventListener("click", click);
      return el;
    }
    function refresh() {
      if (calendar && !disposed) calendar.render();
    }
    function render(props) {
      if (!calendar)
        throw new Error(
          "Personenzeitachse vor render() mit attach(calendar) verbinden.",
        );
      const previous = currentRoot;
      const oldScroll = previous && previous.querySelector(".pt-scroll");
      const scroll = oldScroll
        ? [oldScroll.scrollLeft, oldScroll.scrollTop]
        : [0, 0];
      const focused =
        previous && previous.contains(document.activeElement)
          ? document.activeElement.dataset.focus
          : null;
      const first = dayNumber(
        props.dateProfile.currentRange.start.toISOString().slice(0, 10),
      );
      const last = dayNumber(
        props.dateProfile.currentRange.end.toISOString().slice(0, 10),
      );
      const days = last - first,
        slots = days * 2;
      // The UI deliberately bounds the range; the server must also bound its queries.
      if (days < 1 || days > 366)
        return {
          domNodes: [
            node(
              "p",
              "alert alert-warning",
              "Bitte einen Zeitraum von höchstens einem Jahr wählen.",
            ),
          ],
        };
      const locale = config.locale || calendar.getOption("locale") || "de";
      const fmt = new Intl.DateTimeFormat(locale, {
        day: "2-digit",
        month: "2-digit",
        timeZone: "UTC",
      });
      const weekday = new Intl.DateTimeFormat(locale, {
        weekday: "short",
        timeZone: "UTC",
      });
      const describe = (slot) =>
        fmt.format(new Date(Math.floor(slot / 2) * DAY)) +
        (slot % 2 ? " nachmittags" : " vormittags");
      const root = node("section", "takt-person-timeline");
      currentRoot = root;
      root.dir = calendar.getOption("direction") === "rtl" ? "rtl" : "ltr";
      root.style.setProperty("--pt-slots", slots);
      root.setAttribute("aria-label", "Personenzeitachse");
      const toolbar = node("div", "pt-tools");
      const label = node("label", "pt-filter", "Person suchen");
      const search = node("input", "form-control");
      search.type = "search";
      search.value = query;
      search.dataset.focus = "search";
      label.append(search);
      toolbar.append(label);
      search.addEventListener("input", () => {
        query = search.value;
        refresh();
      });
      const hint = node(
        "p",
        "small text-secondary mb-0",
        "Zeitraum aufziehen oder „Eintragen“ wählen. Pfeile: Tageshälfte · Umschalt: Bereich · Enter: öffnen · Escape: verwerfen.",
      );
      toolbar.append(hint);
      root.append(toolbar);
      const live = node("p", "visually-hidden");
      live.setAttribute("aria-live", "polite");
      live.setAttribute("aria-atomic", "true");
      root.append(live);
      const scroller = node("div", "pt-scroll");
      root.append(scroller);
      scroller.tabIndex = 0;
      scroller.setAttribute(
        "aria-label",
        "Zeitachse horizontal und vertikal scrollen",
      );
      const table = node("table", "pt-table");
      scroller.append(table);
      const caption = node(
        "caption",
        "visually-hidden",
        "Personen und Zeiträume. Die Namensspalte bleibt beim Scrollen sichtbar.",
      );
      table.append(caption);
      const colgroup = node("colgroup");
      colgroup.append(node("col", "pt-name-col"));
      for (let d = 0; d < days; d++) colgroup.append(node("col", "pt-day-col"));
      table.append(colgroup);
      const head = node("thead"),
        header = node("tr");
      head.append(header);
      table.append(head);
      const corner = node("th", "pt-name", "Person / Bereich");
      corner.scope = "col";
      header.append(corner);
      const holidays = new Map(
        (config.holidays || []).map((d) => [d.date, d.label]),
      );
      const today = new Date().toLocaleDateString("en-CA", {
        timeZone: config.timeZone || "Europe/Berlin",
      });
      for (let d = first; d < last; d++) {
        const date = dayString(d),
          time = new Date(d * DAY),
          weekend = [0, 6].includes(time.getUTCDay());
        const cell = node(
          "th",
          (weekend ? "pt-weekend " : "") + (date === today ? "pt-today" : ""),
        );
        cell.scope = "col";
        cell.append(
          node("span", "", weekday.format(time)),
          node("strong", "", fmt.format(time)),
        );
        if (holidays.has(date)) {
          cell.append(node("span", "pt-holiday", holidays.get(date)));
          cell.classList.add("pt-weekend");
        }
        cell.setAttribute(
          "aria-label",
          date + (holidays.has(date) ? " · " + holidays.get(date) : ""),
        );
        header.append(cell);
      }
      const body = node("tbody");
      table.append(body);
      const source = calendar
        .getEvents()
        .filter((e) => e.allDay && e.startStr && e.endStr);
      let drag = null,
        suppressClick = 0;
      const entries = new Map();
      const visible = people.filter((p) =>
        (p.name + " " + (p.group || ""))
          .toLocaleLowerCase()
          .includes(query.toLocaleLowerCase().trim()),
      );
      const groups = new Map();
      visible.forEach((p) => {
        const key = String(p.groupId || p.group || "");
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(p);
      });
      function openRange(person, range, event) {
        const editable = event
          ? event.extendedProps.canEdit === true &&
            typeof config.onChangeRequest === "function"
          : person.canSelect === true && typeof config.onSelect === "function";
        const dialog = node("dialog", "pt-dialog");
        root.append(dialog);
        const form = node("form");
        form.method = "dialog";
        dialog.append(form);
        const titleId = "pt-dialog-" + ++sequence;
        const title = node(
          "h2",
          "h5",
          event ? event.title : "Zeitraum eintragen",
        );
        title.id = titleId;
        form.append(title);
        dialog.setAttribute("aria-labelledby", titleId);
        form.append(node("p", "", person.name));
        if (event)
          form.append(
            node(
              "p",
              "small",
              (statuses[event.extendedProps.status] || ["Eintrag"])[0],
            ),
          );
        const fields = {};
        [
          ["start", "Beginn"],
          ["end", "Ende einschließlich"],
        ].forEach(([key, text]) => {
          const row = node("div", "pt-date-row");
          const dateLabel = node("label", "", text),
            input = node("input", "form-control");
          input.type = "date";
          input.required = true;
          input.value = range[key];
          input.disabled = !editable;
          dateLabel.append(input);
          fields[key] = input;
          const halfLabel = node("label", "", "Tagesabschnitt"),
            select = node("select", "form-select");
          [
            ["am", "Vormittag"],
            ["pm", "Nachmittag"],
          ].forEach(([value, text]) => {
            const option = node("option", "", text);
            option.value = value;
            select.append(option);
          });
          select.value = range[key + "Half"];
          select.disabled = !editable;
          halfLabel.append(select);
          fields[key + "Half"] = select;
          row.append(dateLabel, halfLabel);
          form.append(row);
        });
        const error = node("p", "text-danger small");
        error.setAttribute("role", "alert");
        form.append(error);
        const actions = node("div", "pt-dialog-actions");
        form.append(actions);
        actions.append(
          button("Schließen", "btn btn-outline-secondary", () =>
            dialog.close(),
          ),
        );
        const submit = button(
          event ? "Änderung prüfen" : "Zeitraum prüfen",
          "btn btn-primary",
        );
        submit.type = "submit";
        if (editable) actions.append(submit);
        form.addEventListener("submit", async (ev) => {
          ev.preventDefault();
          if (!editable || submit.disabled) return;
          try {
            const [a, b] = toSlots(
              fields.start.value,
              fields.end.value,
              fields.startHalf.value,
              fields.endHalf.value,
            );
            const proposal = {
              ...fromSlots(a, b),
              personId: String(person.id),
            };
            submit.disabled = true;
            error.textContent = "Wird geprüft …";
            const result = await (event
              ? config.onChangeRequest({
                  ...proposal,
                  eventId: event.id,
                  event,
                })
              : config.onSelect(proposal));
            if (result !== false) dialog.close();
            else error.textContent = "Bitte den Zeitraum prüfen.";
          } catch (err) {
            error.textContent =
              err.message || "Der Zeitraum konnte nicht geprüft werden.";
          } finally {
            submit.disabled = false;
          }
        });
        const restore = document.activeElement;
        dialog.addEventListener(
          "close",
          () => {
            dialog.remove();
            if (restore && restore.isConnected)
              restore.focus({ preventScroll: true });
          },
          { once: true },
        );
        dialog.showModal();
      }
      function requested(person, a, b, event) {
        const range = fromSlots(a, b);
        openRange(person, range, event);
      }
      for (const [key, members] of groups) {
        const name = members[0].group;
        if (name) {
          const row = node("tr", "pt-group"),
            cell = node("th");
          cell.colSpan = days + 1;
          const toggle = button(
            (collapsed.has(key) ? "▸ " : "▾ ") + name + " · " + members.length,
            "btn btn-sm btn-link",
            () => {
              collapsed.has(key) ? collapsed.delete(key) : collapsed.add(key);
              refresh();
            },
          );
          toggle.setAttribute("aria-expanded", String(!collapsed.has(key)));
          toggle.dataset.focus = "group:" + key;
          cell.append(toggle);
          row.append(cell);
          body.append(row);
        }
        if (collapsed.has(key)) continue;
        for (const person of members) {
          const row = node("tr", "pt-person"),
            nameCell = node("th", "pt-name");
          nameCell.scope = "row";
          nameCell.append(node("strong", "", person.name));
          if (person.subtitle)
            nameCell.append(node("small", "", person.subtitle));
          row.append(nameCell);
          const cell = node("td", "pt-range-cell");
          cell.colSpan = days;
          row.append(cell);
          body.append(row);
          const lane = node("div", "pt-lane");
          cell.append(lane);
          lane.dataset.person = String(person.id);
          const canSelect =
            person.canSelect === true && typeof config.onSelect === "function";
          let cursor = first * 2,
            anchor = null;
          if (canSelect) {
            const add = button(
              "Eintragen",
              "btn btn-sm btn-outline-primary",
              () => requested(person, cursor, cursor + 1),
            );
            add.setAttribute(
              "aria-label",
              "Zeitraum für " + person.name + " eintragen",
            );
            add.dataset.focus = "add:" + person.id;
            nameCell.append(add);
            lane.tabIndex = 0;
            lane.setAttribute("role", "group");
            lane.dataset.focus = "lane:" + person.id;
            lane.setAttribute(
              "aria-label",
              person.name +
                ": " +
                describe(cursor) +
                ". Zeitraum mit Pfeilen und Enter auswählen.",
            );
          }
          const shade = node("div", "pt-shading");
          shade.setAttribute("aria-hidden", "true");
          lane.append(shade);
          for (let d = first; d < last; d++)
            if (
              [0, 6].includes(new Date(d * DAY).getUTCDay()) ||
              holidays.has(dayString(d))
            ) {
              const bg = node("span", "pt-nonwork");
              bg.style.insetInlineStart = (d - first) * 2 + "em";
              shade.append(bg);
            }
          const preview = node("div", "pt-selection");
          preview.hidden = true;
          lane.append(preview);
          function showSelection(a, b) {
            preview.hidden = false;
            preview.style.insetInlineStart = a - first * 2 + "em";
            preview.style.width = b - a + "em";
          }
          const items = source
            .filter(
              (e) => String(e.extendedProps.personId) === String(person.id),
            )
            .flatMap((e) => {
              try {
                const ep = e.extendedProps;
                const [a, b] = toSlots(
                  e.startStr.slice(0, 10),
                  dayString(dayNumber(e.endStr.slice(0, 10)) - 1),
                  ep.startHalf || "am",
                  ep.endHalf || "pm",
                );
                return b > first * 2 && a < last * 2
                  ? [{ id: e.id, a, b, event: e }]
                  : [];
              } catch (_) {
                return [];
              }
            });
          const packed = pack(items);
          lane.style.height =
            Math.max(
              64,
              (1 + Math.max(-1, ...packed.map((i) => i.track))) * 34 + 14,
            ) + "px";
          for (const item of packed) {
            const event = item.event,
              status = statuses[event.extendedProps.status]
                ? event.extendedProps.status
                : "absence";
            const a = Math.max(item.a, first * 2),
              b = Math.min(item.b, last * 2);
            const bar = button(
              statuses[status][1] +
                " " +
                event.title +
                " · " +
                statuses[status][0],
              "pt-event pt-status-" + status,
              () => {
                if (performance.now() < suppressClick) return;
                if (config.onEventClick) config.onEventClick({ event, person });
                else requested(person, item.a, item.b, event);
              },
            );
            bar.style.insetInlineStart = a - first * 2 + "em";
            bar.style.width = b - a + "em";
            bar.style.top = 7 + item.track * 34 + "px";
            bar.setAttribute(
              "aria-label",
              person.name +
                ": " +
                event.title +
                ", " +
                describe(item.a) +
                " bis " +
                describe(item.b - 1) +
                ", " +
                statuses[status][0],
            );
            const token = "event:" + person.id + ":" + event.id;
            bar.dataset.focus = token;
            bar.dataset.token = token;
            const text = node("span", "pt-event-text", bar.textContent);
            bar.replaceChildren(text);
            if (event.extendedProps.conflict) {
              bar.append(node("span", "pt-conflict", " ⚠ Konflikt"));
              bar.setAttribute(
                "aria-label",
                bar.getAttribute("aria-label") + ", Konflikt",
              );
            }
            if (
              event.extendedProps.canEdit === true &&
              config.onChangeRequest &&
              item.a >= first * 2 &&
              item.b <= last * 2
            ) {
              bar.dataset.edit = "move";
              ["start", "end"].forEach((edge) => {
                const handle = node("span", "pt-handle pt-handle-" + edge);
                handle.dataset.edit = edge;
                handle.setAttribute("aria-hidden", "true");
                bar.append(handle);
              });
            }
            lane.append(bar);
            entries.set(token, { ...item, bar, person, lane });
          }
          function slotAt(x) {
            const rect = lane.getBoundingClientRect();
            const offset = root.dir === "rtl" ? rect.right - x : x - rect.left;
            return (
              first * 2 +
              Math.max(
                0,
                Math.min(slots - 1, Math.floor((offset / rect.width) * slots)),
              )
            );
          }
          lane.addEventListener("keydown", (e) => {
            if (e.target !== lane) return;
            if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
              e.preventDefault();
              if (e.shiftKey && anchor === null) anchor = cursor;
              if (!e.shiftKey) anchor = null;
              const step =
                (e.key === "ArrowRight" ? 1 : -1) *
                (root.dir === "rtl" ? -1 : 1);
              cursor =
                e.key === "Home"
                  ? first * 2
                  : e.key === "End"
                    ? last * 2 - 1
                    : Math.max(
                        first * 2,
                        Math.min(last * 2 - 1, cursor + step),
                      );
              showSelection(
                Math.min(anchor === null ? cursor : anchor, cursor),
                Math.max(anchor === null ? cursor : anchor, cursor) + 1,
              );
              live.textContent = person.name + ": " + describe(cursor);
              lane.setAttribute("aria-label", live.textContent);
            } else if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              requested(
                person,
                Math.min(anchor === null ? cursor : anchor, cursor),
                Math.max(anchor === null ? cursor : anchor, cursor) + 1,
              );
            } else if (e.key === "Escape") {
              anchor = null;
              preview.hidden = true;
            }
          });
          lane.addEventListener("pointerdown", (e) => {
            if (e.button !== 0 || e.pointerType === "touch") return; // Touch keeps normal scrolling; use the visible form action.
            const bar = e.target.closest(".pt-event");
            if (bar && !e.target.closest("[data-edit]")) return;
            if (!bar && !canSelect) return;
            const item = bar ? entries.get(bar.dataset.token) : null;
            if (bar && !item) return;
            e.preventDefault();
            lane.focus({ preventScroll: true });
            lane.setPointerCapture(e.pointerId);
            drag = {
              lane,
              start: slotAt(e.clientX),
              person,
              item,
              edge: bar
                ? e.target.closest("[data-edit]").dataset.edit
                : "select",
              preview,
              slotAt,
            };
          });
          lane.addEventListener("pointermove", (e) => {
            if (!drag || drag.lane !== lane) return;
            const slot = slotAt(e.clientX),
              delta = slot - drag.start;
            let a, b;
            if (!drag.item) {
              a = Math.min(drag.start, slot);
              b = Math.max(drag.start, slot) + 1;
            } else {
              a = drag.item.a;
              b = drag.item.b;
              if (drag.edge === "move") {
                const shift = Math.max(
                  first * 2 - a,
                  Math.min(last * 2 - b, delta),
                );
                a += shift;
                b += shift;
              } else if (drag.edge === "start")
                a = Math.max(first * 2, Math.min(b - 1, a + delta));
              else b = Math.max(a + 1, Math.min(last * 2, b + delta));
            }
            drag.range = [a, b];
            showSelection(a, b);
          });
          lane.addEventListener("pointerup", (e) => {
            if (!drag || drag.lane !== lane) return;
            const finished = drag;
            drag = null;
            preview.hidden = true;
            if (lane.hasPointerCapture(e.pointerId))
              lane.releasePointerCapture(e.pointerId);
            if (
              finished.item &&
              (!finished.range ||
                (finished.range[0] === finished.item.a &&
                  finished.range[1] === finished.item.b))
            ) {
              suppressClick = performance.now() + 250;
              if (config.onEventClick)
                config.onEventClick({ event: finished.item.event, person });
              else
                requested(
                  person,
                  finished.item.a,
                  finished.item.b,
                  finished.item.event,
                );
              return;
            }
            suppressClick = performance.now() + 250;
            const [a, b] = finished.range || [
              finished.start,
              finished.start + 1,
            ];
            requested(person, a, b, finished.item && finished.item.event);
          });
          lane.addEventListener("pointercancel", () => {
            drag = null;
            preview.hidden = true;
          });
        }
      }
      if (!visible.length) {
        const row = node("tr"),
          cell = node(
            "td",
            "pt-empty",
            people.length
              ? "Keine passende Person."
              : "Keine Personen freigegeben.",
          );
        cell.colSpan = days + 1;
        row.append(cell);
        body.append(row);
      }
      if (summaries.length) {
        const foot = node("tfoot");
        table.append(foot);
        summaries.forEach((summary) => {
          const row = node("tr"),
            title = node("th", "pt-name", summary.label);
          title.scope = "row";
          row.append(title);
          const values = new Map((summary.days || []).map((d) => [d.date, d]));
          for (let day = first; day < last; day++) {
            const value = values.get(dayString(day)),
              cell = node("td", "pt-summary");
            if (!value || value.available == null || value.minimum == null) {
              cell.textContent = "–";
              cell.setAttribute(
                "aria-label",
                dayString(day) + ": Besetzung unbekannt",
              );
            } else {
              cell.textContent = value.available + "/" + value.minimum;
              cell.classList.toggle(
                "pt-shortage",
                value.available < value.minimum,
              );
              cell.setAttribute(
                "aria-label",
                dayString(day) +
                  ": " +
                  value.available +
                  " verfügbar, mindestens " +
                  value.minimum,
              );
            }
            row.append(cell);
          }
          foot.append(row);
        });
      }
      requestAnimationFrame(() => {
        if (!root.isConnected) return;
        scroller.scrollLeft = scroll[0];
        scroller.scrollTop = scroll[1];
        if (focused) {
          const target = [...root.querySelectorAll("[data-focus]")].find(
            (el) => el.dataset.focus === focused,
          );
          if (target) {
            target.focus({ preventScroll: true });
            if (target === search)
              search.setSelectionRange(query.length, query.length);
          }
        }
      });
      return { domNodes: [root] };
    }
    const plugin = FC.createPlugin({
      name: "takt-person-timeline",
      views: {
        taktPeople: {
          content: render,
          duration: { months: 1 },
          dateAlignment: "month",
          buttonText: "Personen",
        },
        taktPeopleQuarter: {
          type: "taktPeople",
          duration: { months: 3 },
          buttonText: "Quartal",
        },
        taktPeopleYear: {
          type: "taktPeople",
          duration: { years: 1 },
          buttonText: "Jahr",
        },
      },
    });
    return {
      plugin,
      attach(value) {
        if (calendar && calendar !== value)
          throw new Error(
            "Pro Kalender eine eigene Zeitachseninstanz verwenden.",
          );
        calendar = value;
      },
      setPeople(value) {
        people = value;
        refresh();
      },
      setSummaries(value) {
        summaries = value;
        refresh();
      },
      destroy() {
        disposed = true;
        currentRoot = null;
        people = [];
        summaries = [];
        calendar = null;
      },
    };
  }
  const api = { create, dayNumber, dayString, toSlots, fromSlots, pack };
  global.TaktPersonTimeline = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window === "undefined" ? globalThis : window);
