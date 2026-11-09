(() => {
  const el = document.getElementById("birthday-calendar");
  if (!el || !window.FullCalendar) return;
  const year = Number(el.dataset.birthdayYear);
  const today = el.dataset.birthdayToday;
  const month = Number(today.slice(0, 4)) === year ? today.slice(5, 7) : "01";
  const calendar = new FullCalendar.Calendar(el, {
    locale: "de",
    initialView: "dayGridMonth",
    initialDate: year + "-" + month + "-01",
    height: "auto",
    firstDay: 1,
    displayEventTime: false,
    dayMaxEvents: true,
    headerToolbar: {left: "prev,next today", center: "title", right: "dayGridMonth,listMonth"},
    buttonText: {today: "Heute", month: "Monat", list: "Liste"},
    events: async (range, success, failure) => {
      try {
        const params = new URLSearchParams({start: range.startStr, end: range.endStr});
        const response = await fetch("/kalender/quellen/birthdays/data?" + params.toString(), {credentials: "same-origin", cache: "no-store"});
        if (!response.ok) throw new Error("Geburtstage konnten nicht geladen werden.");
        const payload = await response.json();
        success(payload.events || []);
      } catch (error) {
        failure(error);
        const message = document.getElementById("birthday-calendar-error");
        if (message) message.textContent = error.message;
      }
    },
    eventClick: (info) => info.jsEvent.preventDefault(),
    eventDidMount: (info) => {
      info.el.title = info.event.title + " · Geburtstag";
    },
  });
  calendar.render();
})();