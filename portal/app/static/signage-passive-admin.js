(() => {
  'use strict';
  document.querySelectorAll('[data-sg-scope]').forEach(form => {
    const kind = form.querySelector('[data-sg-template]');
    const scope = form.querySelector('[data-sg-passive]');
    const building = form.querySelector('[data-sg-building]');
    const floor = form.querySelector('[data-sg-floor]');
    const origin = form.querySelector('[data-sg-origin]');

    function limitOptions(select, allowed) {
      Array.from(select.options).forEach(option => {
        option.disabled = option.hidden = Boolean(option.value) && !allowed(option);
      });
      if (select.selectedOptions[0]?.disabled) select.value = '';
    }

    function update() {
      if (scope) {
        const passive = kind.selectedOptions[0].hasAttribute('data-passive');
        scope.hidden = scope.disabled = !passive;
        building.required = passive;
        floor.required = ['sign_floor', 'sign_corridor'].includes(kind.value);
        origin.required = kind.value === 'sign_corridor';
      }
      limitOptions(floor, option => option.dataset.building === building.value);
      limitOptions(origin, option => option.dataset.building === building.value &&
        (kind?.value !== 'sign_corridor' || option.dataset.floor === floor.value));
    }

    [kind, building, floor].forEach(field => field?.addEventListener('change', update));
    update();
  });

  const form = document.querySelector('[data-sg-overrides]');
  form?.elements.room_id.addEventListener('change', () => {
    const rule = form.elements.room_id.selectedOptions[0].dataset;
    form.elements.label.value = rule.label || '';
    form.elements.arrow.value = rule.arrow || '';
    form.elements.rank.value = rule.rank || '0';
    form.elements.hidden.checked = Boolean(rule.hidden);
  });
})();
