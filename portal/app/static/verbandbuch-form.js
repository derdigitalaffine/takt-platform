/* Accessible enhancement; without JS all three sections and native submit remain available.
 * No localStorage/sessionStorage, telemetry or sensitive-data logging. */
(() => {
  "use strict";
  const form = document.querySelector("[data-vb-wizard]");
  if (!form) return;
  const steps = [...form.querySelectorAll("[data-vb-step]")];
  const indicators = [...document.querySelectorAll("[data-vb-nav]")];
  const next = form.querySelector("[data-vb-next]");
  const prev = form.querySelector("[data-vb-prev]");
  const submit = form.querySelector("[data-vb-submit]");
  const status = document.getElementById("vb-wizard-status");
  if (steps.length !== 3 || indicators.length !== 3 || !next || !prev || !submit) return;
  let index = 0;
  const titles = ["Ort und Zeit", "Ereignis", "Erste Hilfe"];
  function show(n, focus = false) {
    index = Math.max(0, Math.min(steps.length - 1, n));
    steps.forEach((step, i) => { step.hidden = i !== index; });
    indicators.forEach((item, i) => {
      if (i === index) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
      item.dataset.vbComplete = String(i < index);
    });
    prev.hidden = index === 0;
    next.hidden = index === steps.length - 1;
    submit.hidden = index !== steps.length - 1;
    if (status) status.textContent = `Schritt ${index + 1} von 3 · ${titles[index]}`;
    if (focus) {
      const heading = steps[index].querySelector("h2");
      if (heading) { heading.tabIndex = -1; heading.focus({preventScroll:true}); }
      if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) steps[index].scrollIntoView({block:"start",behavior:"smooth"});
    }
  }
  function validateStep(i) {
    const controls = [...steps[i].querySelectorAll("input,select,textarea")];
    for (const control of controls) {
      if (control.disabled) continue;
      if (!control.checkValidity()) {
        show(i);
        control.reportValidity();
        control.focus();
        return false;
      }
    }
    return true;
  }
  next.addEventListener("click", () => { if (validateStep(index)) show(index + 1, true); });
  prev.addEventListener("click", () => show(index - 1, true));
  form.addEventListener("submit", event => {
    for (let i = 0; i < steps.length; i++) {
      if (!validateStep(i)) { event.preventDefault(); return; }
    }
    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
    submit.textContent = "Wird geschützt gespeichert …";
  });
  // Server-side validation errors must remain visible after a failed submission.
  const serverErrors = document.querySelector(".alert-danger[role=alert]");
  if (serverErrors) {
    serverErrors.focus();
    form.dataset.vbEnhanced = "true";
    steps.forEach(step => { step.hidden = false; });
    next.hidden = true; prev.hidden = true; submit.hidden = false;
    if (status) status.textContent = "Bitte die markierten Angaben prüfen";
    return;
  }
  form.dataset.vbEnhanced = "true";
  show(0);
})();
