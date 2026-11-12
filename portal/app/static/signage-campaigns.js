/* Progressive enhancement for the central signage console. No JS is required to
   view existing campaigns, but dependent selectors are safer with it. */
(() => {
  'use strict';
  const form = document.querySelector('[data-sg-central-form]');
  if (!form) return;
  const building = form.querySelector('[data-sg-campaign-building]');
  const room = form.querySelector('[data-sg-campaign-room]');
  const floor = form.querySelector('[data-sg-campaign-floor] select');
  const floorHolder = form.querySelector('[data-sg-campaign-floor]');
  const screenList = form.querySelector('[data-sg-campaign-displays]');
  const scopeInputs = [...form.querySelectorAll('[name=scope]')];
  const event = form.querySelector('[data-sg-campaign-event]') || form.querySelector('input[type=hidden][name=event_id]');
  const window = form.querySelector('[data-sg-manual-window]');
  const preset = form.querySelector('[data-sg-campaign-preset]');
  const priority = form.querySelector('[data-sg-campaign-priority]');
  let editedPriority = !!form.querySelector('[name=campaign_id]');
  priority?.addEventListener('input', () => { editedPriority = true; });

  function filterSelect(select, bid) {
    if (!select) return;
    const options = [...select.options];
    for (const option of options) {
      if (option.value) {
        option.disabled = option.dataset.building !== bid;
        option.hidden = option.disabled;
      }
    }
    if (select.selectedOptions.length && select.selectedOptions[0].disabled) select.value = '';
    if (!select.value) {
      const first = options.find(option => option.value && !option.disabled);
      if (first) select.value = first.value;
    }
  }
  function updateScope() {
    const scope = scopeInputs.find(input => input.checked)?.value || 'building';
    floorHolder.hidden = scope !== 'floor';
    if (floor) floor.disabled = scope !== 'floor';
    for (const row of screenList.querySelectorAll('.sg-campaign-screen')) {
      const selected = row.querySelector('[name=screen_ids]');
      const excluded = row.querySelector('[name=excluded_ids]');
      const match = row.dataset.building === building.value;
      row.hidden = !match;
      selected.disabled = scope !== 'selected' || !match;
      excluded.disabled = scope === 'selected' || !match;
      row.querySelector('[data-sg-select]').hidden = scope !== 'selected';
      row.querySelector('[data-sg-exclude]').hidden = scope === 'selected';
    }
  }
  function updateBuilding() {
    const bid = building.value;
    filterSelect(room, bid);
    filterSelect(floor, bid);
    updateScope();
  }
  function updateEvent() {
    const linked = !!(event && event.value);
    window.hidden = linked;
    for (const field of window.querySelectorAll('input')) {
      field.required = !linked;
      field.disabled = linked;
    }
  }
  scopeInputs.forEach(input => input.addEventListener('change', updateScope));
  building.addEventListener('change', updateBuilding);
  event?.addEventListener('change', updateEvent);
  preset?.addEventListener('change', () => {
    if (editedPriority || !priority) return;
    priority.value = preset.selectedOptions[0]?.dataset.priority || priority.value;
  });
  updateBuilding();
  updateEvent();
})();
