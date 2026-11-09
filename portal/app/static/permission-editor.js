/* Local, dependency-free permission editor. Names/values intentionally unchanged. */
(function () {
  'use strict';
  function init(editor) {
    var search = editor.querySelector('[data-permission-search]');
    var groups = Array.from(editor.querySelectorAll('[data-permission-group]'));
    var total = editor.querySelector('[data-permission-count]');
    var empty = editor.querySelector('[data-permission-empty]');
    function normalized(value) {
      return (value || '').toLocaleLowerCase('de-DE').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    }
    function update() {
      var query = normalized(search.value.trim()), visibleCount = 0, selected = 0, all = 0;
      groups.forEach(function (group) {
        var options = Array.from(group.querySelectorAll('[data-permission-option]'));
        var groupSelected = 0, groupVisible = 0;
        options.forEach(function (option) {
          var input = option.querySelector('input[name="perm"]');
          var matched = !query || normalized(option.dataset.search || option.textContent).includes(query);
          option.hidden = !matched;
          if (matched) { groupVisible++; visibleCount++; }
          if (input.checked) { groupSelected++; selected++; }
          all++;
        });
        group.hidden = !groupVisible;
        if (query && groupVisible) group.open = true;
        var counter = group.querySelector('[data-permission-group-count]');
        if (counter) counter.textContent = groupSelected + ' / ' + options.length;
      });
      total.textContent = selected + ' von ' + all + ' vergeben';
      empty.hidden = !!visibleCount;
    }
    search.addEventListener('input', update);
    editor.addEventListener('change', function (event) {
      if (event.target.matches('input[name="perm"]')) update();
    });
    editor.addEventListener('click', function (event) {
      var button = event.target.closest('[data-permission-action]');
      if (!button || !editor.contains(button)) return;
      var action = button.dataset.permissionAction;
      if (action === 'expand' || action === 'collapse') {
        groups.filter(function (g) { return !g.hidden; }).forEach(function (g) {
          g.open = action === 'expand';
        });
      } else if (action === 'select-group' || action === 'clear-group') {
        var group = button.closest('[data-permission-group]');
        if (!group) return;
        group.querySelectorAll('[data-permission-option]').forEach(function (option) {
          if (option.hidden) return; // Search filters only visible choices.
          var checkbox = option.querySelector('input[name="perm"]');
          if (!checkbox.disabled) checkbox.checked = action === 'select-group';
        });
        update();
      }
    });
    update();
  }
  document.querySelectorAll('[data-permission-editor]').forEach(init);
}());
