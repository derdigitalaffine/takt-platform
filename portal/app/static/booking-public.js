/* Kleine progressive Verbesserungen; die Buchung funktioniert vollständig ohne JavaScript. */
(function () {
  'use strict';
  var search = document.getElementById('bk-type-search');
  if (search) {
    var tiles = Array.prototype.slice.call(document.querySelectorAll('[data-booking-type]'));
    var empty = document.getElementById('bk-search-empty');
    search.addEventListener('input', function () {
      var term = search.value.trim().toLocaleLowerCase('de');
      var count = 0;
      tiles.forEach(function (tile) {
        var show = tile.dataset.bookingType.indexOf(term) !== -1;
        tile.hidden = !show;
        if (show) { count++; }
      });
      if (empty) { empty.hidden = count !== 0; }
    });
  }

  // Der gesamte Ablauf benutzt echte GET-Schritte. Lediglich die Schaltfläche
  // erhält einen klaren Status, sobald eine Uhrzeit ausgewählt ist.
  var form = document.querySelector('.bk-slots-form');
  if (form) {
    var next = form.querySelector('[type="submit"]');
    var radios = Array.prototype.slice.call(form.querySelectorAll('input[name="slot"]'));
    function refresh() {
      var selected = radios.some(function (radio) { return radio.checked; });
      if (next) { next.disabled = !selected; }
    }
    form.addEventListener('change', refresh);
    refresh();
  }
})();
