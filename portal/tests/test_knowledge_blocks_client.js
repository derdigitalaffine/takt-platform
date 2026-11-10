'use strict';
/* No-dependency Node contracts for the shipped visual Markdown block engine. */
const assert = require('node:assert/strict');
const test = require('node:test');
const model = require('../app/static/knowledge-blocks.js');
const BT = String.fromCharCode(96);

test('unmodified Markdown round-trips byte for byte, including unsupported constructs', () => {
  const sources = [
    '',
    'Ein Absatz',
    '## Titel\n\nEin zweiter Absatz\n',
    '\n\n# Kopf\r\n\r\nWeitere Zeile\r\n',
    '> **Hinweis:** Datenschutz\n\n- [ ] Aufgabe A\n- [x] Aufgabe B',
    '<div data-special="yes">Unbekannte Erweiterung</div>\n\n[Link](https://example.org)\n',
    '1. Eins\n2. Zwei\n\n* drei\n* vier',
    '| Titel | Wert |\n| --- | --- |\n| Text | 42 |',
    BT.repeat(3) + 'python\nprint("a")\n\nprint("b")\n' + BT.repeat(3) + '\n\nNach dem Code',
    '   - Verschachtelt\n\nFolgeseite\n\n',
    'Vorher\n\n> Zitat\n> mit neuer Zeile\n\nNachher',
    '\n\nNur Anfang\n\n\n'
  ];
  for (const source of sources) {
    const document = model.parse(source);
    assert.equal(model.serialize(document), source, 'round-trip failed for ' + JSON.stringify(source));
  }
});

test('classifies the eleven supported block types and retains advanced Markdown', () => {
  const sample = [
    '## Überschrift',
    'Absatz mit **fett** und _kursiv_',
    '- Eins\n- Zwei',
    '1. Erstens\n2. Zweitens',
    '- [ ] Offen\n- [x] Fertig',
    '> Aussage',
    '> **Hinweis:** Nicht vergessen',
    '| Name | Wert |\n| --- | --- |\n| Artikel | 2 |',
    '[Mehr erfahren](https://example.org/hilfe)',
    BT.repeat(3) + 'json\n{"a": 1}\n' + BT.repeat(3),
    '<details><summary>Erweiterung</summary></details>'
  ].join('\n\n');
  const doc = model.parse(sample);
  assert.deepEqual(doc.blocks.map(b => b.kind), [
    'heading', 'paragraph', 'bullet', 'ordered', 'checklist', 'quote',
    'callout', 'table', 'link', 'code', 'raw'
  ]);
  assert.equal(model.serialize(doc), sample);
});

test('editing a single block preserves untouched neighboring Markdown verbatim', () => {
  const text = '# Titel\n\nEin **wichtiger** Absatz.\n\n<!-- hidden user extension -->\n';
  const doc = model.parse(text);
  doc.blocks[1].text = 'Ein geänderter Absatz.';
  doc.blocks[1].dirty = true;
  assert.equal(model.serialize(doc), '# Titel\n\nEin geänderter Absatz.\n\n<!-- hidden user extension -->\n');
});

test('moving blocks changes order without dropping text or advanced blocks', () => {
  const original = '# Eins\n\n<!-- special -->\n\nEnde\n';
  const doc = model.parse(original);
  assert.equal(model.move(doc, 0, -1), false);
  assert.equal(model.move(doc, 0, 2), false);
  assert.equal(model.move(doc, 0, 1), true);
  assert.equal(model.serialize(doc), '<!-- special -->\n\n# Eins\n\nEnde\n');
});

test('checklist checkmarks and list rows serialize correctly after editing', () => {
  const doc = model.parse('- [ ] Erledigen\n- [x] Abgeschlossen');
  assert.equal(doc.blocks[0].kind, 'checklist');
  doc.blocks[0].items[0].done = true;
  doc.blocks[0].items.push({done: false, text: 'Prüfen'});
  doc.blocks[0].dirty = true;
  assert.equal(model.serialize(doc), '- [x] Erledigen\n- [x] Abgeschlossen\n- [ ] Prüfen');
});

test('code fences expand when edited code contains a fence', () => {
  const block = model.newBlock('code');
  block.lang = 'js';
  block.text = 'const x = "' + BT.repeat(3) + '";';
  const rendered = model.format(block);
  assert.ok(rendered.startsWith(BT.repeat(4) + 'js\n'));
  assert.ok(rendered.endsWith('\n' + BT.repeat(4)));
});

test('links fail closed for dangerous protocols, and permit trustworthy URLs', () => {
  const block = model.newBlock('link');
  block.text = 'Start';
  block.href = 'javascript:alert(1)';
  assert.throws(() => model.format(block), /sichere/);
  block.href = '//evil.example';
  assert.throws(() => model.format(block), /sichere/);
  block.href = 'data:text/html,bad';
  assert.throws(() => model.format(block), /sichere/);
  block.href = 'https://example.com';
  assert.equal(model.format(block), '[Start](https://example.com)');
  block.href = '/wissen/raum/4';
  assert.equal(model.format(block), '[Start](/wissen/raum/4)');
});

test('editable table serializes to CommonMark table, preserving literal pipe cells', () => {
  const doc = model.parse('| A | B |\n| --- | --- |\n| Eine | Zwei |');
  assert.equal(doc.blocks[0].kind, 'table');
  doc.blocks[0].table[1][0] = 'Eins | zwei';
  doc.blocks[0].dirty = true;
  assert.match(model.serialize(doc), /Eins \\[|] zwei/);
  assert.match(model.serialize(doc), /[|] --- [|] --- [|]/);
});

test('adding, deleting and reordering blocks works without external state', () => {
  const doc = model.parse('A');
  doc.blocks.push(model.newBlock('heading'));
  doc.blocks[1].text = 'Neu';
  doc.structureDirty = true;
  assert.equal(model.serialize(doc), 'A\n\n## Neu');
  model.move(doc, 1, -1);
  assert.equal(model.serialize(doc), '## Neu\n\nA');
  doc.blocks.pop();
  assert.equal(model.serialize(doc), '## Neu');
});

test('typed blocks do not manufacture HTML or unsafe external fetches', () => {
  const block = model.newBlock('paragraph');
  block.text = '<script>alert("x")</script>';
  assert.equal(model.format(block), '<script>alert("x")</script>');
  // Rendering sanitization stays on the server (MarkdownIt html:false).
  assert.equal(model.newBlock('heading').level, 2);
  assert.throws(() => model.newBlock('executable-html'), /Unbekannter/);
});
