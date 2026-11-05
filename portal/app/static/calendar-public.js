(() => {
  const el = document.getElementById("public-calendar");
  if (!el) return;
  new FullCalendar.Calendar(el, {
    locale: "de",
    initialView: "dayGridMonth",
    height: "auto",
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "dayGridMonth,listMonth,multiMonthYear",
    },
    events: {
      url: el.dataset.url,
      failure() {
        document.getElementById("public-calendar-error").textContent =
          "Kalender konnte nicht geladen werden.";
      },
    },
    eventClick({ event }) {
      const dialog = document.createElement("dialog");
      const title = document.createElement("h2");
      title.className = "h5";
      title.textContent = event.title;
      const text = document.createElement("p");
      text.textContent = [
        event.extendedProps.location,
        event.extendedProps.description,
      ]
        .filter(Boolean)
        .join(" · ");
      const close = document.createElement("button");
      close.className = "btn btn-outline-secondary";
      close.textContent = "Schließen";
      close.onclick = () => dialog.close();
      dialog.append(title, text, close);
      document.body.append(dialog);
      dialog.addEventListener("close", () => dialog.remove());
      dialog.showModal();
    },
  }).render();
})();
