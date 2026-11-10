/* Fill a real TAKT form from an authenticated, session-bound server proposal.
   No automatic submit; edits receive another explicit server-rendered review. */
(async () => {
  'use strict';
  const params = new URLSearchParams(location.search);
  const nonce = params.get('agent_plan');
  if (!nonce) return;
  const main = document.querySelector('#inhalt');
  if (!main) return;
  const banner = document.createElement('section');
  banner.className = 'alert alert-info mb-4';
  banner.setAttribute('data-agent-draft', '');
  banner.setAttribute('role', 'status');
  banner.textContent = 'TAKT Agent lädt den ausgefüllten Vorschlag …';
  main.prepend(banner);
  try {
    const query = new URLSearchParams({plan_id: nonce, step: params.get('agent_step') || '0'});
    const response = await fetch('/agent/draft?' + query, {credentials: 'same-origin', cache: 'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Vorschlag nicht mehr verfügbar.');
    if (data.path !== location.pathname) throw new Error('Dieser Vorschlag gehört in einen anderen Programmbereich.');
    const tool = data.tool, id = data.id;
    const calendarTool = ['create_event', 'update_event', 'delete_event'].includes(tool);
    const selectors = {
      configure_anliegen_category: `form[action="/anliegen/kategorien/${id}"]`,
      create_form: 'form[action="/forms"]',
      set_krank_status: `form[action="/krankmelder/${id}/status"]`,
      add_krank_note: `form[action="/krankmelder/${id}/notiz"]`, send_krank_message: `form[action="/krankmelder/${id}/nachricht"]`,
      create_leave: '#leave-form', edit_leave: '#leave-form', leave_command: `#leave-row-${id} form[data-leave-command]`,
      create_task: 'form[data-task-create]', create_anliegen: '#anliegen-create',
      assign_task: `form[action="/aufgaben/${id}/bearbeiten"]`,
      set_task_priority: `form[action="/aufgaben/${id}/bearbeiten"]`,
      assign_anliegen: `form[action="/anliegen/${id}/assign"]`,
      set_anliegen_status: `form[action="/anliegen/${id}/status"]`,
      update_event: '#calendar-event-form', delete_event: '#calendar-event-form', create_event: '#calendar-event-form', copy_form: `form[action="/forms/${id}/copy"]`,
      move_dms: `form[action="/dms/move"]`
    };
    let form;
    if (tool === 'set_task_status') {
      form = Array.from(document.querySelectorAll(`form[action="/aufgaben/${id}/aktion"]`))
        .find(f => f.elements.action?.value === 'status' && f.elements.status?.value === data.fields.status);
    } else if (tool === 'set_anliegen_status') {
      form = Array.from(document.querySelectorAll(selectors[tool])).find(f => f.querySelector('select[name="status"]'));
      if (data.fields.supplier !== undefined) {
        form = Array.from(document.querySelectorAll(selectors[tool])).find(f => f.elements.supplier) || form;
      }
    } else {
      form = document.querySelector(selectors[tool] || 'form[data-no-agent-form]');
    }
    if (!form) throw new Error('Die Fachmaske ist nicht verfügbar. Bitte den Vorschlag neu planen.');
    const fields = {...data.fields};
    if (tool === 'set_krank_status') {
      const chosen = form.querySelector(`button[name="status"][value="${data.fields.status}"]`);
      if (!chosen || chosen.disabled) throw new Error('Dieser Statuswechsel ist nicht mehr verfügbar.');
      for (const button of form.querySelectorAll('button')) {
        if (button !== chosen) { button.disabled = true; button.hidden = true; }
      }
    }
    if (tool === 'leave_command') {
      const chosen = form.querySelector(`button[name="action"][value="${data.fields.command}"]`);
      if (!chosen) throw new Error('Diese Urlaubsaktion ist nicht mehr verfügbar. Bitte neu planen.');
      for (const button of form.querySelectorAll('button')) {
        if (button !== chosen) { button.disabled = true; button.hidden = true; }
      }
      chosen.type = 'submit';
    }

    const allowed = {
      configure_anliegen_category: ['title', 'routing', 'assignee_id', 'enabled', 'apply_open'],
      create_form: ['title'],
      set_krank_status: ['note'], add_krank_note: ['text'], send_krank_message: ['text'],
      create_leave: ['starts_on', 'ends_on', 'start_half', 'end_half'],
      edit_leave: ['starts_on', 'ends_on', 'start_half', 'end_half'], leave_command: ['reason'],
      create_task: ['title', 'description', 'priority', 'assignee_id', 'due_date', 'due_time', 'starts_at', 'tags', 'checklist'],
      create_anliegen: ['title', 'description_final', 'category_id'],
      assign_task: ['assignee_id'], set_task_priority: ['priority'], set_task_status: [],
      assign_anliegen: ['assignee_id'],
      set_anliegen_status: ['status', 'supplier', 'order_reference', 'expected_delivery'],
      create_event: ['title', 'description', 'location', 'calendar_id', 'start', 'end', 'start_time', 'end_time', 'all_day'],
      update_event: ['title', 'description', 'location', 'start', 'end', 'start_time', 'end_time', 'all_day'], delete_event: [],
      copy_form: [], move_dms: ['area_id']
    }[tool];
    function hidden(name, value) {
      let input = form.querySelector(`input[type="hidden"][name="${name}"]`);
      if (!input) { input = document.createElement('input'); input.type = 'hidden'; input.name = name; form.appendChild(input); }
      input.disabled = false;
      input.value = value;
    }
    if (calendarTool) {
      if (!fields.all_day) for (const key of ['start', 'end']) {
        const date = new Date(data.event_times[key]);
        const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString();
        fields[key] = local.slice(0, 10); fields[key + '_time'] = local.slice(11, 16);
      }
      fields.repeat = 'none';
      hidden('agent_timezone', Intl.DateTimeFormat().resolvedOptions().timeZone);
      const editor = document.querySelector('#event-editor');
      if (editor) { editor.hidden = false; editor.open = true; }
    }
    for (const [name, value] of Object.entries(fields)) {
      const control = form.elements.namedItem(name);
      if (!control || !('value' in control) || typeof control.dispatchEvent !== 'function') continue;
      if (control.type === 'checkbox') control.checked = value === true;
      else if (control.tomselect) control.tomselect.setValue(value == null ? '' : String(value), true);
      else control.value = value == null ? '' : String(value);
      if (!calendarTool) control.dispatchEvent(new Event('change', {bubbles: true}));
    }
    if (calendarTool) {
      form.elements.kind.dispatchEvent(new Event('change', {bubbles: true}));
      form.elements.all_day.dispatchEvent(new Event('change', {bubbles: true}));
      if (!fields.all_day) form.elements.duration.value = String((new Date(data.event_times.end) - new Date(data.event_times.start)) / 60000);
    }
    const hero = form.querySelector('.anliegen-hero');
    if (hero) hero.hidden = true;
    const draftDetails = form.querySelector('#anliegen-review');
    if (draftDetails) draftDetails.open = true;
    if (['create_leave', 'edit_leave'].includes(tool)) {
      document.getElementById('leave-edit-note').hidden = tool !== 'edit_leave';
    }
    // Only fields implemented by the tool can be changed in this proposal.
    for (const control of form.querySelectorAll('input, select, textarea, button')) {
      if (control.type === 'submit' || control.name === 'csrf' || control.name === 'agent_timezone') continue;
      if (!allowed.includes(control.name)) {
        control.disabled = true; control.tomselect?.disable();
      }
    }
    for (const details of form.querySelectorAll('details')) {
      if (Array.from(details.querySelectorAll('input,select,textarea')).some(c => allowed.includes(c.name))) details.open = true;
    }
    for (let parent = form.parentElement; parent && parent !== main; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    // Copy/status actions otherwise live in menus; expose their native form here.
    if (['copy_form', 'set_task_status', 'create_leave', 'edit_leave'].includes(tool)) banner.after(form);
    else form.before(banner);
    const submit = form.querySelector('button[type="submit"]:not(:disabled), button:not([type]):not(:disabled)');
    if (submit) { submit.className = 'btn btn-primary'; submit.textContent = 'Vorschlag prüfen'; }
    hidden('csrf', document.querySelector('meta[name="csrf"]')?.content || '');
    hidden('agent_plan', nonce); hidden('agent_step', String(data.step));
    form.action = '/agent/draft/review'; form.method = 'post';
    // Capture before calendar/task progressive-enhancement handlers.
    form.addEventListener('submit', event => {
      event.preventDefault(); event.stopImmediatePropagation();
      if (form.reportValidity()) HTMLFormElement.prototype.submit.call(form);
    }, true);
    banner.replaceChildren();
    const heading = document.createElement('h2'); heading.className = 'h5';
    heading.textContent = `TAKT-Agent-Vorschlag · ${data.total} Schritt${data.total === 1 ? '' : 'e'} offen`;
    const text = document.createElement('p'); text.textContent = 'Die Fachmaske ist ausgefüllt. Prüfen und bearbeiten Sie die freigeschalteten Angaben. Es wurde noch nichts gespeichert.';
    const preview = document.createElement('p'); preview.style.whiteSpace = 'pre-wrap'; preview.className = 'small text-break'; preview.textContent = data.preview;
    const back = document.createElement('a'); back.href = '/agent'; back.textContent = 'Zurück zum TAKT-Agenten';
    const discard = document.createElement('form'); discard.method = 'post'; discard.action = '/agent/draft/cancel';
    for (const [name, value] of Object.entries({csrf: document.querySelector('meta[name="csrf"]')?.content || '', plan_id: nonce})) {
      const input = document.createElement('input'); input.type = 'hidden'; input.name = name; input.value = value; discard.appendChild(input);
    }
    const discardButton = document.createElement('button'); discardButton.type = 'submit'; discardButton.className = 'btn btn-sm btn-outline-secondary'; discardButton.textContent = 'Vorschlag verwerfen'; discard.appendChild(discardButton);
    banner.append(heading, text, preview, back, discard);
    banner.scrollIntoView({block: 'start'});
    const first = form.querySelector('input:not([type="hidden"]):not(:disabled), textarea:not(:disabled), select:not(:disabled)');
    first?.focus({preventScroll: true});
  } catch (error) {
    banner.className = 'alert alert-warning'; banner.textContent = error.message;
  }
})();
