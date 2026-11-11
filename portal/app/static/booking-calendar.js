/* Terminbuchung: Zeitbereiche im Wochenkalender (FullCalendar) aufziehen und entfernen; Dialoge zu Buchungen. */
(function () {
  'use strict';
  var el = document.getElementById('bk-calendar');
  var csrf = (document.querySelector('meta[name="csrf"]') || {}).content || '';

  /* --- Dialoge Verschieben / Absagen -------------------------------------- */
  function openModal(id, btn, attr) {
    var modal = document.getElementById(id);
    var form = modal.querySelector('form');
    form.action = form.dataset.actionBase + btn.getAttribute(attr);
    modal.querySelectorAll('.js-bk-name').forEach(function (x) { x.textContent = btn.dataset.bkName; });
    modal.querySelectorAll('.js-bk-when').forEach(function (x) { x.textContent = btn.dataset.bkWhen; });
    bootstrap.Modal.getOrCreateInstance(modal).show();
  }
  document.addEventListener('click', function (ev) {
    var mv = ev.target.closest('[data-bk-move]');
    if (mv) { openModal('move-modal', mv, 'data-bk-move'); return; }
    var cn = ev.target.closest('[data-bk-cancel]');
    if (cn) { openModal('cancel-modal', cn, 'data-bk-cancel'); }
  });

  if (!el || !window.FullCalendar) { return; }
  var pageId = el.dataset.page;
  var readonly = el.dataset.readonly === '1';   // nur ansehen (Freigabe ohne Bearbeiten)
  var events = JSON.parse(document.getElementById('bk-events').textContent || '[]');

  function post(url, fields) {
    var body = fields instanceof FormData ? fields : new FormData();
    if (!(fields instanceof FormData)) {
      Object.keys(fields || {}).forEach(function (k) { body.append(k, fields[k]); });
    }
    if (!body.has('csrf')) { body.append('csrf', csrf); }
    return fetch(url, { method: 'POST', body: body, headers: { 'X-Requested-With': 'fetch' }, credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok && r.status !== 422) { throw new Error('HTTP ' + r.status); }
        return r.json();
      });
  }
  function toast(text, error) {
    if (window.Swal) {
      Swal.fire({ toast: true, position: 'top-end', timer: error ? 6000 : 2500, showConfirmButton: false,
        icon: error ? 'error' : 'success', title: text });
    }
  }
  function reload(list) {
    // Der angezeigte Tag / die Woche und die Scrollposition bleiben unverändert.
    calendar.batchRendering(function () {
      calendar.removeAllEvents();
      list.forEach(function (e) { calendar.addEvent(e); });
    });
  }
  function node(tag, className, content) {
    var el = document.createElement(tag);
    if (className) { el.className = className; }
    if (content !== undefined) { el.textContent = content; }
    return el;
  }
  function updateAvailability(info) {
    if (!info) { return; }
    [['free', 'free_count'], ['slots', 'slot_count']].forEach(function (entry) {
      var value = document.querySelector('[data-bk-stat="' + entry[0] + '"] .stat-value');
      if (value) { value.textContent = String(info[entry[1]]); }
    });
    var count = document.querySelector('[data-bk-window-count]');
    if (count) { count.textContent = String(info.window_count); }

    var root = document.getElementById('bk-availability-content');
    if (!root) { return; }
    var days = info.days || [];
    var children = [];
    if (days.length) {
      var grid = node('div', 'bk-availability-grid');
      days.forEach(function (day) {
        var card = node('div', 'bk-day-preview');
        var heading = node('div', 'd-flex justify-content-between flex-wrap gap-1 mb-2');
        heading.appendChild(node('strong', '', day.label));
        heading.appendChild(node('span', 'small text-secondary', day.count + ' Zeiten'));
        card.appendChild(heading);
        var times = node('div', 'd-flex flex-wrap gap-2');
        (day.slots || []).forEach(function (slot) {
          var chip = node('span', 'bk-time-chip', slot.time);
          if (slot.free > 1) { chip.appendChild(node('small', '', '· ' + slot.free + ' frei')); }
          times.appendChild(chip);
        });
        if (day.count > day.slots.length) {
          times.appendChild(node('span', 'small text-secondary align-self-center', '+ ' + (day.count - day.slots.length) + ' weitere'));
        }
        card.appendChild(times);
        grid.appendChild(card);
      });
      children.push(grid);
      children.push(node('p', 'small text-secondary mb-0 mt-3',
        'Vorschau der nächsten sieben verfügbaren Tage. Alle buchbaren Zeiten stehen auf der öffentlichen Buchungsseite.'));
    } else {
      var empty = node('div', 'bk-empty');
      empty.appendChild(node('i', 'fa-regular fa-calendar-xmark'));
      var description = node('div');
      description.appendChild(node('strong', 'd-block text-body', 'Zurzeit keine buchbaren Termine'));
      description.appendChild(document.createTextNode(info.window_count
        ? 'Zeitbereiche sind vorhanden. Prüfe, ob sie in der Zukunft liegen, lang genug für einen Termin sind und der eingestellte Vorlauf bereits erfüllt ist.'
        : 'Lege zuerst einen Zeitbereich im Kalender an. Daraus entstehen die freien Buchungsslots automatisch.'));
      empty.appendChild(description);
      children.push(empty);
    }
    root.replaceChildren.apply(root, children);
  }
  function applyChange(data) {
    if (!data || !data.ok || !Array.isArray(data.events)) { return false; }
    reload(data.events);
    updateAvailability(data.availability);
    var status = document.getElementById('bk-window-status');
    if (status) { status.textContent = data.message || 'Zeitbereiche aktualisiert.'; }
    toast(data.message || 'Zeitbereiche aktualisiert.', false);
    return true;
  }
  var busy = false;
  function saveWindow(url, fields, form) {
    if (busy) { return Promise.resolve(); }
    busy = true;
    el.classList.add('bk-updating');
    var submit = form && form.querySelector('[type="submit"]');
    if (submit) { submit.disabled = true; }
    var formStatus = form && form.querySelector('[data-bk-form-status]');
    if (formStatus) { formStatus.textContent = 'Wird gespeichert …'; }
    return post(url, fields).then(function (data) {
      if (!applyChange(data)) {
        var msg = (data && data.error) || 'Der Zeitbereich konnte nicht gespeichert werden.';
        if (formStatus) { formStatus.textContent = msg; }
        toast(msg, true);
      } else if (formStatus) { formStatus.textContent = data.message; }
    }).catch(function () {
      var msg = 'Verbindung fehlgeschlagen. Bitte erneut versuchen.';
      if (formStatus) { formStatus.textContent = msg; }
      toast(msg, true);
    }).finally(function () {
      busy = false;
      el.classList.remove('bk-updating');
      if (submit) { submit.disabled = false; }
    });
  }
  var windowForm = document.querySelector('[data-bk-window-form]');
  if (windowForm && !readonly) {
    windowForm.addEventListener('submit', function (ev) {
      ev.preventDefault();
      saveWindow(windowForm.action, new FormData(windowForm), windowForm);
    });
  }
  function windowAt(date) {
    var t = date.getTime();
    return calendar.getEvents().find(function (e) {
      return e.extendedProps.kind === 'window' && e.start.getTime() <= t && t < e.end.getTime();
    });
  }

  var calendar = new FullCalendar.Calendar(el, {
    locale: 'de',
    initialView: window.innerWidth < 768 ? 'timeGridDay' : 'timeGridWeek',
    initialDate: el.dataset.initial || undefined,
    firstDay: 1,
    allDaySlot: false,
    slotMinTime: '07:00:00',
    slotMaxTime: '20:00:00',
    slotDuration: '00:15:00',
    slotLabelInterval: '01:00',
    snapDuration: '00:15:00',
    nowIndicator: true,
    selectable: !readonly,
    selectMirror: true,
    selectMinDistance: 5,
    height: 'auto',
    expandRows: true,
    weekNumbers: true,
    headerToolbar: { left: 'prev,next today', center: 'title', right: 'timeGridWeek,timeGridDay,dayGridMonth' },
    businessHours: { daysOfWeek: [1, 2, 3, 4, 5], startTime: '08:00', endTime: '17:00' },
    events: events,
    selectAllow: function (info) {
      return info.start.toDateString() === new Date(info.end.getTime() - 1).toDateString() && info.start > new Date(Date.now() - 864e5);
    },
    select: function (info) {
      calendar.unselect();
      if (info.view.type === 'dayGridMonth') { calendar.changeView('timeGridDay', info.start); return; }
      saveWindow('/bookings/' + pageId + '/windows', { start: info.startStr, end: info.endStr });
    },
    dateClick: function (info) {
      if (readonly) { return; }
      var w = windowAt(info.date);
      if (!w) { return; }
      var fmt = function (d) { return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }); };
      Swal.fire({
        title: 'Zeitbereich entfernen?', icon: 'question',
        text: w.start.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit' }) + ', ' + fmt(w.start) + '–' + fmt(w.end) + ' Uhr. Buchungen darin bleiben bestehen.',
        showCancelButton: true, confirmButtonText: 'Entfernen', cancelButtonText: 'Abbrechen', reverseButtons: true,
        buttonsStyling: false, customClass: { confirmButton: 'btn btn-danger ms-2', cancelButton: 'btn btn-outline-secondary' }
      }).then(function (res) {
        if (!res.isConfirmed) { return; }
        saveWindow('/bookings/' + pageId + '/windows/' + w.extendedProps.wid + '/delete', {});
      });
    },
    eventClick: function (info) {
      if (info.event.extendedProps.kind !== 'booking') { return; }
      var row = document.querySelector('[data-bk-cancel="' + info.event.extendedProps.bid + '"]');
      if (row) { row.closest('tr').scrollIntoView({ behavior: 'smooth', block: 'center' }); row.closest('tr').classList.add('table-warning'); }
    }
  });
  calendar.render();
  window.bkCalendar = calendar;
})();
