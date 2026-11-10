/* Krankmelder: Formularlogik (Bemerkungsfeld je Arbeitgeber, Folgebescheinigung, privat versichert). */
(function () {
  'use strict';
  var form = document.getElementById('krank-form');
  if (!form) { return; }
  if (form.elements.agent_health) {
    const review = form.querySelector('[data-health-review]');
    const send = form.querySelector('[data-health-send]');
    const confirm = form.elements.agent_confirm;
    form.querySelector('[data-health-preview]').addEventListener('click', () => {
      // Confirmation is deliberately required only after reviewing valid fields.
      confirm.required = false;
      const valid = form.reportValidity();
      confirm.required = true;
      if (!valid) return;
      const list = form.querySelector('[data-health-values]'); list.replaceChildren();
      for (const field of form.querySelectorAll('input, select, textarea')) {
        if (field.disabled || ['hidden', 'checkbox', 'submit'].includes(field.type) || !field.name || (field.type === 'radio' && !field.checked)) continue;
        const label = form.querySelector('label[for="' + field.id + '"]') || form.querySelector('label[for="' + field.id + '-display"]');
        const term = document.createElement('dt'); term.textContent = field.type === 'radio' ? field.closest('fieldset')?.querySelector('legend')?.textContent || label?.textContent : label?.textContent || field.name;
        const value = document.createElement('dd');
        value.textContent = field.type === 'radio' ? label?.textContent || field.value : field.type === 'file' ? [...field.files].map(f => f.name).join(', ') || 'Kein Nachweis – gegebenenfalls nachreichen' :
          field.tagName === 'SELECT' ? field.selectedOptions[0]?.textContent || '–' : field.value || '–';
        list.append(term, value);
      }
      review.hidden = false; send.hidden = false; confirm.checked = false;
      review.scrollIntoView({block: 'nearest'});
    });
    form.addEventListener('input', event => {
      if (event.target === confirm) return;
      review.hidden = true; send.hidden = true; confirm.checked = false;
    });
    form.addEventListener('change', event => {
      if (event.target === confirm) return;
      review.hidden = true; send.hidden = true; confirm.checked = false;
    });
  }
  var employer = document.getElementById('kf-employer');
  var remarks = document.getElementById('kf-remarks-box');
  var syncRemarks = function () {
    var opt = employer && employer.options[employer.selectedIndex];
    if (remarks) { remarks.classList.toggle('d-none', !(opt && opt.dataset.remarks === '1')); }
  };
  if (employer) { employer.addEventListener('change', syncRemarks); syncRemarks(); }

  var first = document.getElementById('kf-first');
  var from = form.querySelector('input[name="from"][data-first-required]');
  var syncFirst = function () {
    if (!first || !from) { return; }
    var isFirst = first.value === '1';
    from.required = isFirst;
    var star = form.querySelector('label[for="kf-from"] .text-danger');
    if (star) { star.classList.toggle('d-none', !isFirst); }
  };
  if (first) { first.addEventListener('change', syncFirst); syncFirst(); }

  var hint = document.getElementById('kf-private-hint');
  var syncInsured = function () {
    var priv = form.querySelector('input[name="insured"][value="private"]');
    var on = !!(priv && priv.checked);
    if (hint) { hint.classList.toggle('d-none', !on); }
    var btn = form.querySelector('button[type="submit"]');
    if (btn && form.dataset.kind === 'eau') { btn.disabled = on; }
  };
  form.querySelectorAll('input[name="insured"]').forEach(function (el) { el.addEventListener('change', syncInsured); });
  syncInsured();

  var to = form.querySelector('input[name="to"]');
  if (from && to) {
    from.addEventListener('change', function () { if (from.value) { to.min = from.value; } });
  }
  form.addEventListener('submit', function () {
    var btn = form.querySelector('button[type="submit"]');
    if (btn) { setTimeout(function () { btn.disabled = true; }, 0); }
  });
})();
