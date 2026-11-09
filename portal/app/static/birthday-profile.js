(() => {
  const date = document.getElementById("profile-birthdate");
  const mode = document.getElementById("profile-birthday-visibility");
  const preview = document.getElementById("birthday-preview-text");
  if (!date || !mode || !preview) return;
  const update = () => {
    const value = date.value, visibility = mode.value;
    const parsed = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/.exec(value);
    if (visibility === "hidden") {preview.textContent = "Nicht im Geburtstagskalender sichtbar."; return;}
    if (!parsed) {preview.textContent = "Bitte zuerst ein Geburtsdatum auswählen."; return;}
    const day = Number(parsed[3]), month = Number(parsed[2]);
    const display = day + "." + month + ".";
    if (visibility === "date") {preview.textContent = display + " · Geburtstag ohne Altersangabe."; return;}
    const now = new Date();
    let year = now.getFullYear();
    const today = (now.getMonth() + 1) * 100 + now.getDate();
    if (month * 100 + day < today) year++;
    const age = year - Number(parsed[1]);
    const leapNote = month === 2 && day === 29 ? " (in Nicht-Schaltjahren gemäß Organisationsregel)" : "";
    preview.textContent = display + leapNote + " · Im Jahr " + year + " wird im Kalender „wird " + age + "“ angezeigt.";
  };
  date.addEventListener("change", update);
  date.addEventListener("input", update);
  mode.addEventListener("change", update);
  update();
})();