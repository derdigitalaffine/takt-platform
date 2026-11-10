/* Progressive-enhancement visual editor for TAKT Wissen.
 * Markdown textareas and server-side authorization remain authoritative.
 * The block UI generates Markdown only; it never sends data automatically.
 */
(function () {
  'use strict';
  const api = window.TAKTKnowledgeBlocks;
  if (!api) return;
  const iconMap = {
    paragraph: 'fa-align-left', heading: 'fa-heading', bullet: 'fa-list-ul',
    ordered: 'fa-list-ol', checklist: 'fa-list-check', quote: 'fa-quote-left',
    callout: 'fa-circle-info', table: 'fa-table', link: 'fa-link',
    code: 'fa-code', raw: 'fa-file-code'
  };
  const templates = {
    article: '## Überblick\n\nWas ist wichtig?\n\n## Vorgehen\n\n1. Erster Schritt\n2. Nächster Schritt',
    process: '## Zweck\n\n## Verantwortliche\n\n## Ablauf\n\n1. Eingang\n2. Bearbeitung\n3. Abschluss\n\n## Sonderfälle',
    faq: '## Häufige Frage\n\nAntwort und Quellen.',
    checklist: '## Checkliste\n\n- [ ] Vorbereitung\n- [ ] Durchführung\n- [ ] Dokumentation',
    experience: '## Ausgangssituation\n\n## Erfahrung\n\n## Hinweise und Grenzen'
  };

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function button(label, icon, action, cls) {
    const b = el('button', cls || 'knowledge-visual-action');
    b.type = 'button';
    b.title = label;
    b.setAttribute('aria-label', label);
    if (icon) {
      const i = el('i', 'fa-solid ' + icon);
      i.setAttribute('aria-hidden', 'true');
      b.appendChild(i);
      if (cls && (cls.includes('btn ') || cls.includes('add-line'))) {
        b.appendChild(document.createTextNode(' ' + label));
      }
    } else {
      b.textContent = label;
    }
    b.addEventListener('click', action);
    return b;
  }
  function labelWrap(label, control) {
    const wrap = el('label', 'knowledge-block-field');
    wrap.appendChild(el('span', 'knowledge-block-field-label', label));
    wrap.appendChild(control);
    return wrap;
  }
  function textControl(value, description, multiline, onchange, cls) {
    const control = el(multiline ? 'textarea' : 'input', cls || 'knowledge-visual-input');
    if (!multiline) control.type = 'text';
    if (multiline) control.rows = Math.min(9, Math.max(2, String(value).split('\n').length + 1));
    control.value = String(value || '');
    control.setAttribute('aria-label', description);
    control.addEventListener('input', function () { onchange(control.value); });
    return control;
  }
  function ensureText(block) {
    if (['bullet', 'ordered', 'checklist'].includes(block.kind)) {
      return (block.items || []).map(i => i.text).join('\n');
    }
    if (block.kind === 'table') return api.format(block);
    return block.text || '';
  }

  document.querySelectorAll('form[data-knowledge-editor]').forEach(function (form) {
    const textarea = form.querySelector('textarea[data-knowledge-markdown]');
    if (!textarea || !form.querySelector('input[name="csrf"]')) return;
    const toolbar = form.querySelector('.knowledge-editor-toolbar');
    const originalPreview = document.getElementById(textarea.id + '-preview');
    const host = textarea.parentNode;
    const maxLength = Number(textarea.maxLength) || 60000;
    let doc = api.parse(textarea.value);
    let visual = false;
    let invalid = false;
    let dragging = -1;

    const shell = el('section', 'knowledge-visual-shell');
    shell.setAttribute('aria-label', 'Visueller Wissenseditor');
    shell.hidden = true;
    const header = el('div', 'knowledge-visual-head');
    const heading = el('div', 'knowledge-visual-title');
    heading.appendChild(el('strong', '', 'Inhaltsblöcke'));
    heading.appendChild(el('span', '', 'Schritte, Hinweise und Inhalte frei anordnen.'));
     const visualButton = button('Visuelle Ansicht', 'fa-layer-group', function () { switchMode(true); });
    const markdownButton = button('Markdown-Quelltext', 'fa-code', function () { switchMode(false); });
    visualButton.classList.add('knowledge-mode-button');
    markdownButton.classList.add('knowledge-mode-button');
    visualButton.appendChild(document.createTextNode(' Visuell'));
    markdownButton.appendChild(document.createTextNode(' Markdown'));
    header.appendChild(heading);
    shell.appendChild(header);

    const list = el('div', 'knowledge-visual-list');
    list.setAttribute('role', 'list');
    shell.appendChild(list);
    const actions = el('div', 'knowledge-visual-bottom');
    const addKind = el('select', 'form-select knowledge-visual-add-kind');
    addKind.setAttribute('aria-label', 'Art des neuen Blocks');
    api.KINDS.forEach(function (kind) {
      const o = el('option', '', api.LABELS[kind]); o.value = kind; addKind.appendChild(o);
    });
    const add = button('Block hinzufügen', 'fa-plus', function () {
      const block = api.newBlock(addKind.value);
      doc.blocks.push(block);
      doc.structureDirty = true;
      refresh(doc.blocks.length - 1);
    }, 'btn btn-primary');
    const template = button('Gliederung aus Vorlage ergänzen', 'fa-wand-magic-sparkles', function () {
      const kind = form.querySelector('[name="kind"]')?.value || 'article';
      const text = templates[kind] || templates.article;
      if (doc.blocks.length && !window.confirm('Gliederungsvorlage am Ende ergänzen?')) return;
      const appendix = api.parse(text).blocks;
      doc.blocks.push(...appendix);
      doc.structureDirty = true;
      refresh(doc.blocks.length - 1);
    }, 'btn btn-outline-secondary');
    actions.append(addKind, add, template);
    shell.appendChild(actions);
    const status = el('p', 'knowledge-visual-status');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    shell.appendChild(status);

    const switcher = el('div', 'knowledge-visual-switcher');
    switcher.appendChild(el('span', 'knowledge-visual-switcher-label', 'Bearbeitungsmodus'));
    const switchControls = el('div', 'knowledge-visual-switcher-controls');
    switchControls.append(visualButton, markdownButton);
    switcher.appendChild(switchControls);
    if (toolbar) host.insertBefore(switcher, toolbar);
    else host.insertBefore(switcher, textarea);
    host.insertBefore(shell, textarea);

    // Single source of truth is always the Markdown textarea, including form submit.
    function sync(message) {
      try {
        const text = api.serialize(doc);
        if (text.length > maxLength) {
          throw new Error('Der Inhalt überschreitet die zulässigen ' + maxLength + ' Zeichen.');
        }
        textarea.value = text;
        invalid = false;
        status.classList.remove('knowledge-visual-error');
        status.textContent = message || '';
        return true;
      } catch (err) {
        invalid = true;
        status.classList.add('knowledge-visual-error');
        status.textContent = err.message || 'Inhalt kann nicht gespeichert werden.';
        return false;
      }
    }

    function setDirty(block) {
      block.dirty = true;
      sync();
    }

    function refresh(focusIndex) {
      list.replaceChildren();
      if (!doc.blocks.length) {
        const empty = el('p', 'knowledge-visual-empty',
          'Hier ist noch Platz für Wissen. Wähle einen Blocktyp und füge deinen ersten Block ein.');
        list.appendChild(empty);
      }
      doc.blocks.forEach(function (block, index) {
        const card = el('section', 'knowledge-visual-card knowledge-visual-' + block.kind);
        card.setAttribute('role', 'listitem');
        card.dataset.blockIndex = String(index);
        card.tabIndex = -1;
        const top = el('div', 'knowledge-visual-card-head');
        const drag = el('span', 'knowledge-visual-drag');
        drag.draggable = true;
        drag.title = 'Mit der Maus ziehen, um den Block zu verschieben';
        drag.setAttribute('aria-label', 'Block verschieben');
        drag.appendChild(el('i', 'fa-solid fa-grip-vertical'));
        drag.addEventListener('dragstart', function (event) {
          dragging = index;
          event.dataTransfer.effectAllowed = 'move';
          event.dataTransfer.setData('text/plain', String(index));
          card.classList.add('knowledge-block-dragging');
        });
        drag.addEventListener('dragend', function () {
          dragging = -1;
          card.classList.remove('knowledge-block-dragging');
        });
        card.addEventListener('dragover', function (event) {
          if (dragging >= 0) event.preventDefault();
        });
        card.addEventListener('drop', function (event) {
          if (dragging < 0) return;
          event.preventDefault();
          if (dragging !== index) {
            const moved = doc.blocks.splice(dragging, 1)[0];
            doc.blocks.splice(index, 0, moved);
            doc.structureDirty = true;
            sync('Block verschoben.');
            refresh(index);
          }
          dragging = -1;
        });
        top.appendChild(drag);
        top.appendChild(el('i', 'fa-solid ' + iconMap[block.kind] + ' knowledge-visual-type-icon'));
        const kind = el('select', 'knowledge-visual-type form-select form-select-sm');
        kind.setAttribute('aria-label', 'Blocktyp ändern');
        api.KINDS.forEach(function (type) {
          const opt = el('option', '', api.LABELS[type]);
          opt.value = type;
          if (block.kind === type) opt.selected = true;
          kind.appendChild(opt);
        });
        kind.addEventListener('change', function () {
          const newKind = kind.value;
          const oldText = ensureText(block);
          // Type conversion is intentional and visible; preserve textual payload.
          if (block.kind === 'raw' && newKind !== 'raw' &&
              !window.confirm('Dieser Block enthält ursprüngliches Markdown. Wirklich den Typ wechseln?')) {
            kind.value = block.kind;
            return;
          }
          if (newKind === 'table') {
            const parsed = api.parse(oldText).blocks;
            if (!(parsed.length === 1 && parsed[0].kind === 'table')) {
              if (!window.confirm('Der bisherige Text passt nicht in eine Tabelle. Durch eine neue leere Tabelle ersetzen?')) {
                kind.value = block.kind;
                return;
              }
            } else {
              doc.blocks[index] = parsed[0];
              doc.blocks[index].dirty = true;
              doc.structureDirty = true;
              sync('Tabellenformat übernommen.'); refresh(index);
              return;
            }
          }
          if (newKind === 'heading' && oldText.includes('\n') &&
              !window.confirm('Eine Überschrift ist einzeilig. Absätze in eine Zeile umwandeln?')) {
            kind.value = block.kind;
            return;
          }
          const fresh = api.newBlock(newKind);
          fresh.text = oldText;
          if (fresh.items) {
            fresh.items = oldText.split('\n').map(v => ({text: v, done: false}));
          }
          doc.blocks[index] = fresh;
          doc.structureDirty = true;
          sync('Blocktyp geändert. Bitte die Formatierung prüfen.');
          refresh(index);
        });
        top.appendChild(kind);
        const operations = el('div', 'knowledge-visual-operations');
        const up = button('Block nach oben verschieben', 'fa-arrow-up', function () {
          if (api.move(doc, index, -1)) { sync('Block nach oben verschoben.'); refresh(index - 1); }
        });
        const down = button('Block nach unten verschieben', 'fa-arrow-down', function () {
          if (api.move(doc, index, 1)) { sync('Block nach unten verschoben.'); refresh(index + 1); }
        });
        up.disabled = index === 0;
        down.disabled = index === doc.blocks.length - 1;
        operations.append(up, down);
        operations.appendChild(button('Block duplizieren', 'fa-copy', function () {
          // Clone the entire block, including advanced Markdown and all table cells.
          const duplicate = JSON.parse(JSON.stringify(block));
          doc.blocks.splice(index + 1, 0, duplicate);
          doc.structureDirty = true;
          sync('Block dupliziert.'); refresh(index + 1);
        }));
        operations.appendChild(button('Block löschen', 'fa-trash', function () {
          if (!window.confirm('Diesen Inhaltsblock wirklich löschen?')) return;
          doc.blocks.splice(index, 1);
          doc.structureDirty = true;
          sync('Block entfernt.'); refresh(Math.min(index, doc.blocks.length - 1));
        }, 'knowledge-visual-action knowledge-visual-delete'));
        top.appendChild(operations);
        card.appendChild(top);

        const body = el('div', 'knowledge-visual-card-body');
        const update = function (value) { block.text = value; setDirty(block); };
        if (block.kind === 'heading') {
          const level = el('select', 'form-select form-select-sm knowledge-heading-level');
          level.setAttribute('aria-label', 'Überschriftenebene');
          [1, 2, 3, 4, 5, 6].forEach(function (n) {
            const opt = el('option', '', 'Überschrift ' + n);
            opt.value = String(n);
            if (block.level === n) opt.selected = true;
            level.appendChild(opt);
          });
          level.addEventListener('change', function () { block.level = Number(level.value); setDirty(block); });
          body.appendChild(level);
          body.appendChild(textControl(block.text, 'Überschrift', false, update, 'knowledge-visual-input knowledge-visual-heading-input'));
        } else if (['bullet', 'ordered', 'checklist'].includes(block.kind)) {
          const entries = el('div', 'knowledge-block-items');
          (block.items || []).forEach(function (entry, line) {
            const row = el('div', 'knowledge-block-item');
            if (block.kind === 'checklist') {
              const checked = el('input', 'form-check-input');
              checked.type = 'checkbox';
              checked.checked = Boolean(entry.done);
              checked.setAttribute('aria-label', 'Aufgabe ' + (line + 1) + ' erledigt');
              checked.addEventListener('change', function () { entry.done = checked.checked; setDirty(block); });
              row.appendChild(checked);
            } else {
              row.appendChild(el('span', 'knowledge-block-item-marker',
                block.kind === 'ordered' ? String(line + 1) + '.' : '•'));
            }
            row.appendChild(textControl(entry.text, 'Listeneintrag ' + (line + 1), false, function (value) {
              entry.text = value; setDirty(block);
            }));
            row.appendChild(button('Eintrag entfernen', 'fa-xmark', function () {
              block.items.splice(line, 1);
              if (!block.items.length) block.items.push({text: '', done: false});
              setDirty(block); refresh(index);
            }));
            entries.appendChild(row);
          });
          body.appendChild(entries);
          body.appendChild(button('Weiteren Eintrag hinzufügen', 'fa-plus', function () {
            block.items.push({text: '', done: false}); setDirty(block); refresh(index);
          }, 'knowledge-visual-add-line'));
        } else if (block.kind === 'table') {
          const scroller = el('div', 'knowledge-visual-table-scroll');
          const grid = el('table', 'knowledge-visual-table');
          grid.setAttribute('aria-label', 'Tabellenzellen bearbeiten');
          (block.table || []).forEach(function (cells, row) {
            const tr = el('tr');
            cells.forEach(function (value, col) {
              const td = el(row === 0 ? 'th' : 'td');
              td.scope = row === 0 ? 'col' : undefined;
              td.appendChild(textControl(value, 'Zeile ' + (row + 1) + ', Spalte ' + (col + 1),
                false, function (text) { block.table[row][col] = text; setDirty(block); }));
              tr.appendChild(td);
            });
            grid.appendChild(tr);
          });
          scroller.appendChild(grid);
          body.appendChild(scroller);
          const tools = el('div', 'knowledge-visual-table-tools');
          const addRow = button('Zeile hinzufügen', 'fa-plus', function () {
            if (block.table.length >= 40) return;
            block.table.push(block.table[0].map(() => ''));
            setDirty(block); refresh(index);
          }, 'knowledge-visual-add-line');
          const removeRow = button('Letzte Zeile entfernen', 'fa-minus', function () {
            if (block.table.length <= 1) return;
            if (!window.confirm('Letzte Tabellenzeile entfernen?')) return;
            block.table.pop(); setDirty(block); refresh(index);
          }, 'knowledge-visual-add-line');
          const addCol = button('Spalte hinzufügen', 'fa-plus', function () {
            if (block.table[0].length >= 12) return;
            block.table.forEach(row => row.push(''));
            setDirty(block); refresh(index);
          }, 'knowledge-visual-add-line');
          const removeCol = button('Letzte Spalte entfernen', 'fa-minus', function () {
            if (block.table[0].length <= 1) return;
            if (!window.confirm('Letzte Tabellenspalte entfernen?')) return;
            block.table.forEach(row => row.pop());
            setDirty(block); refresh(index);
          }, 'knowledge-visual-add-line');
          addRow.disabled = block.table.length >= 40;
          removeRow.disabled = block.table.length <= 1;
          addCol.disabled = block.table[0].length >= 12;
          removeCol.disabled = block.table[0].length <= 1;
          tools.append(addRow, removeRow, addCol, removeCol);
          body.appendChild(tools);
        } else if (block.kind === 'link') {
          body.appendChild(labelWrap('Linktext',
            textControl(block.text, 'Linktext', false, update)));
          body.appendChild(labelWrap('Zieladresse (https:// oder lokaler Pfad)',
            textControl(block.href, 'Linkadresse', false, function (v) { block.href = v; setDirty(block); })));
        } else {
          if (block.kind === 'code') {
            body.appendChild(labelWrap('Sprache (optional)',
              textControl(block.lang, 'Codesprache', false, function (v) { block.lang = v; setDirty(block); })));
          }
          const multiline = ['paragraph', 'quote', 'callout', 'code', 'raw'].includes(block.kind);
          body.appendChild(textControl(block.text, api.LABELS[block.kind] + ' bearbeiten',
            multiline, update, 'knowledge-visual-input knowledge-visual-text-' + block.kind));
          if (block.kind === 'raw') {
            body.appendChild(el('small', 'knowledge-visual-raw-hint',
              'Original-Markdown: komplexe Formatierung bleibt erhalten. Bei Änderungen den Quelltext selbst bearbeiten.'));
          }
        }
        card.appendChild(body);
        card.addEventListener('keydown', function (event) {
          if (!event.altKey || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
          event.preventDefault();
          const delta = event.key === 'ArrowUp' ? -1 : 1;
          if (api.move(doc, index, delta)) {
            sync('Block per Tastatur verschoben.'); refresh(index + delta);
          }
        });
        list.appendChild(card);
      });
      if (typeof focusIndex === 'number' && focusIndex >= 0) {
        const chosen = list.children[focusIndex];
        if (chosen) chosen.focus();
      }
    }

    function switchMode(toVisual) {
      if (toVisual === visual && toVisual) return;
      if (toVisual) {
        // The previous Markdown preview must be closed before visual editing.
        if (originalPreview && !originalPreview.hidden) {
          const previewToggle = toolbar?.querySelector('[aria-label="Markdown-Vorschau anzeigen"]');
          if (previewToggle) previewToggle.click();
        }
        doc = api.parse(textarea.value);
        visual = true;
        shell.hidden = false;
        textarea.hidden = true;
        if (toolbar) toolbar.hidden = true;
        if (originalPreview) originalPreview.hidden = true;
        refresh();
      } else {
        if (visual && !sync('Markdown-Quelltext aktualisiert.')) return;
        visual = false;
        shell.hidden = true;
        textarea.hidden = false;
        if (toolbar) toolbar.hidden = false;
      }
      visualButton.setAttribute('aria-pressed', String(visual));
      markdownButton.setAttribute('aria-pressed', String(!visual));
      visualButton.classList.toggle('is-active', visual);
      markdownButton.classList.toggle('is-active', !visual);
    }

    form.addEventListener('submit', function (event) {
      if (visual && !sync()) {
        event.preventDefault();
        event.stopImmediatePropagation();
        status.focus();
        return;
      }
      if (visual && invalid) event.preventDefault();
    }, true);
    status.tabIndex = -1;
    switchMode(true);
  });
}());
