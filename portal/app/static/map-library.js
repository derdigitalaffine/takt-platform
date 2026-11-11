/* Filtering never clears a selection; the server validates every selected layer again. */
(function () {
  var search = document.getElementById('library-layer-search');
  if (!search) return;
  var form = search.form, rows = Array.from(form.querySelectorAll('.map-library-choice'));
  var status = document.getElementById('library-selection-status');
  var submit = form.querySelector('button[type="submit"], button:not([type])');
  function update() {
    var query = search.value.trim().toLocaleLowerCase('de'), visible = 0;
    rows.forEach(function (row) {
      row.hidden = !row.textContent.toLocaleLowerCase('de').includes(query);
      if (!row.hidden) visible++;
    });
    var selected = form.querySelectorAll('input[name="layers"]:checked').length;
    status.textContent = visible + ' Ebenen angezeigt · ' + selected + ' von höchstens 100 ausgewählt' + (selected > 100 ? '. Bitte Auswahl verkleinern.' : '.');
    submit.disabled = selected === 0 || selected > 100;
  }
  search.addEventListener('input', update);
  form.addEventListener('change', update);
  update();
})();
