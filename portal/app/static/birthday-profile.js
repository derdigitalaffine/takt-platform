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
    const now = new Date(), year = now.getFullYear();
    const age = year - Number(parsed[1]);
    preview.textContent = display + " · Am nächsten Geburtstag wird das Alter angezeigt (z. B. " + age + " im Jahr " + year + ").";
  };
  date.addEventListener("change", update);
  date.addEventListener("input", update);
  mode.addEventListener("change", update);
  update();
})();