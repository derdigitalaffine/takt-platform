/* TAKT Wissen: lossless Markdown-backed visual block model.
 * No network, no HTML parsing, no executable content, no external dependencies.
 * Unchanged source (including EOLs, unknown extensions and fenced code) survives
 * visual/Markdown switching byte-for-byte. Edited blocks use CommonMark.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.TAKTKnowledgeBlocks = api;
}(typeof window !== 'undefined' ? window : null, function () {
  'use strict';
  const BT = String.fromCharCode(96);
  const KINDS = ['paragraph', 'heading', 'bullet', 'ordered', 'checklist',
                 'quote', 'callout', 'table', 'link', 'code', 'raw'];
  const LABELS = {
    paragraph: 'Absatz', heading: 'Überschrift', bullet: 'Aufzählung',
    ordered: 'Nummerierte Liste', checklist: 'Checkliste',
    quote: 'Zitat', callout: 'Hinweis', table: 'Tabelle',
    link: 'Link', code: 'Code', raw: 'Markdown-Original'
  };

  function normalizeLines(value) {
    return String(value || '').replace(/\r\n/g, '\n');
  }

  function rawBody(raw) {
    return raw.replace(/\r?\n$/, '');
  }

  function split(source) {
    const lines = String(source).match(/[^\n]*\n|[^\n]+$/g) || [];
    const chunks = [];
    let raw = '', separator = '', leading = '', fence = null;
    for (const line of lines) {
      const body = line.replace(/\r?\n$/, '');
      const blank = /^[ \t]*$/.test(body);
      if (blank && !raw && !fence && chunks.length === 0) {
        leading += line;
        continue;
      }
      if (blank && raw && !fence) {
        if (!separator) {
          const eol = raw.match(/\r?\n$/);
          if (eol) {
            raw = raw.slice(0, -eol[0].length);
            separator = eol[0];
          }
        }
        separator += line;
        continue;
      }
      if (separator && raw) {
        chunks.push({raw: raw, sep: separator});
        raw = '';
        separator = '';
      }
      raw += line;
      const fenceStart = body.match(new RegExp('^ {0,3}([' + BT + '~]{3,})'));
      if (!fence && fenceStart) {
        fence = {char: fenceStart[1][0], size: fenceStart[1].length};
      } else if (fence) {
        const close = body.trim();
        if (close.length >= fence.size && close.split('').every(ch => ch === fence.char)) fence = null;
      }
    }
    if (raw || separator) chunks.push({raw: raw, sep: separator});
    return {leading, chunks};
  }

  function parseChunk(chunk) {
    const raw = chunk.raw;
    const value = rawBody(raw);
    const lines = normalizeLines(value).split('\n');
    const node = {kind: 'raw', raw: raw, sep: chunk.sep, dirty: false, text: value};
    const set = (kind, fields) => Object.assign(node, {kind}, fields);

    const codeMatch = value.match(new RegExp('^ {0,3}([' + BT + '~]{3,})([^\\n]*)\\r?\\n([\\s\\S]*)\\r?\\n\\1[ \\t]*$'));
    if (codeMatch) return set('code', {lang: codeMatch[2].trim(), text: normalizeLines(codeMatch[3])});
    const heading = value.match(/^(#{1,6})[ \t]+([^\n]*)$/);
    if (heading) return set('heading', {level: heading[1].length, text: heading[2]});
    if (lines.length && lines.every(l => /^[-*+][ \t]+\[[ xX]\][ \t]*/.test(l))) {
      return set('checklist', {items: lines.map(l => ({
        done: /^[-*+][ \t]+\[[xX]\]/.test(l),
        text: l.replace(/^[-*+][ \t]+\[[ xX]\][ \t]*/, '')
      }))});
    }
    if (lines.length && lines.every(l => /^[-*+][ \t]+/.test(l))) {
      return set('bullet', {items: lines.map(l => ({text: l.replace(/^[-*+][ \t]+/, '')}))});
    }
    if (lines.length && lines.every(l => /^\d+[.)][ \t]+/.test(l))) {
      return set('ordered', {items: lines.map(l => ({text: l.replace(/^\d+[.)][ \t]+/, '')}))});
    }
    if (lines.length && lines.every(l => /^>[ \t]?/.test(l))) {
      const quoted = lines.map(l => l.replace(/^>[ \t]?/, '')).join('\n');
      if (/^\*\*Hinweis:\*\*[ \t]?/.test(quoted)) {
        return set('callout', {text: quoted.replace(/^\*\*Hinweis:\*\*[ \t]?/, '')});
      }
      return set('quote', {text: quoted});
    }
    const link = value.match(/^\[([^\]\n]+)\]\(([^()\n]+)\)$/);
    if (link) return set('link', {text: link[1], href: link[2]});
    if (lines.length >= 2 && lines.every(l => /^\|.*\|[ \t]*$/.test(l)) &&
        /^\|[\s:|\-]+\|[ \t]*$/.test(lines[1]) && lines[1].includes('-')) {
      const cells = line => line.trim().slice(1, -1).split(/(?<!\\)\|/).map(
        cell => cell.trim().replace(/\\\|/g, '|'));
      const header = cells(lines[0]);
      const rows = lines.slice(2).map(cells);
      if (header.length > 0 && header.length <= 12 && rows.every(row => row.length === header.length)) {
        return set('table', {table: [header].concat(rows), tableDelimiter: lines[1]});
      }
    }
    // Never silently reinterpret nested lists, HTML, extensions or fenced fragments.
    if (/^\s*(?:<[^>]+>|<!--|---+$|___+$)/m.test(value) ||
        (lines.some(l => /^ {2,}[-*+]\s/.test(l)))) {
      return node;
    }
    return set('paragraph', {text: normalizeLines(value)});
  }

  function parse(source) {
    const src = String(source || '');
    const data = split(src);
    return {
      leading: data.leading,
      trailing: (src.match(/\r?\n$/) || [''])[0],
      structureDirty: false,
      blocks: data.chunks.map(parseChunk)
    };
  }

  function newBlock(kind) {
    if (!KINDS.includes(kind)) throw new Error('Unbekannter Blocktyp.');
    const block = {kind: kind, raw: '', sep: '', dirty: true, text: ''};
    if (kind === 'heading') block.level = 2;
    if (kind === 'link') block.href = 'https://';
    if (kind === 'code') block.lang = '';
    if (['bullet', 'ordered', 'checklist'].includes(kind)) {
      block.items = [{text: '', done: false}];
    }
    if (kind === 'table') block.table = [['Spalte 1', 'Spalte 2'], ['', '']];
    return block;
  }

  function safeURL(href) {
    const value = String(href || '').trim();
    // Never manufacture JavaScript/data/file links. Relative URLs are local.
    if (!(/^(https?:\/\/[^\s]+|mailto:[^\s]+|\/(?!\/)[^\s]*)$/i.test(value))) {
      throw new Error('Links benötigen eine sichere https-, http-, mailto- oder lokale Adresse.');
    }
    return value.replace(/\)/g, '%29');
  }

  function format(block) {
    const txt = normalizeLines(block.text);
    switch (block.kind) {
      case 'heading':
        return '#'.repeat(Math.max(1, Math.min(6, Number(block.level) || 2))) +
          ' ' + txt.replace(/\n/g, ' ');
      case 'paragraph':
      case 'raw':
        return txt;
      case 'bullet':
        return (block.items || []).map(it => '- ' + String(it.text || '')).join('\n');
      case 'ordered':
        return (block.items || []).map((it, i) => (i + 1) + '. ' + String(it.text || '')).join('\n');
      case 'checklist':
        return (block.items || []).map(it => '- [' + (it.done ? 'x' : ' ') + '] ' + String(it.text || '')).join('\n');
      case 'quote':
        return txt.split('\n').map(line => '> ' + line).join('\n');
      case 'callout':
        return '> **Hinweis:** ' + txt.replace(/\n/g, '\n> ');
      case 'link':
        return '[' + String(block.text || '').replace(/\]/g, '\\]') + '](' + safeURL(block.href) + ')';
      case 'code': {
        const fences = (txt.match(new RegExp(BT + '+', 'g')) || []).reduce(
          (max, m) => Math.max(max, m.length), 0);
        const marker = BT.repeat(Math.max(3, fences + 1));
        const lang = String(block.lang || '').replace(/[\r\n<>]/g, '').split(BT).join('').trim();
        return marker + lang + '\n' + txt + '\n' + marker;
      }
      case 'table': {
        const rows = block.table || [];
        if (!rows.length || !rows[0].length || rows[0].length > 12 ||
            rows.some(row => row.length !== rows[0].length)) {
          throw new Error('Die Tabelle benötigt gleich viele Zellen je Zeile.');
        }
        const cellLine = row => '| ' + row.map(
          cell => String(cell || '').replace(/\|/g, '\\|').replace(/\r?\n/g, ' ')
        ).join(' | ') + ' |';
        const delimiter = typeof block.tableDelimiter === 'string' &&
          block.tableDelimiter.split('|').length === rows[0].length + 2
          ? block.tableDelimiter : '| ' + rows[0].map(() => '---').join(' | ') + ' |';
        return [cellLine(rows[0]), delimiter]
          .concat(rows.slice(1).map(cellLine)).join('\n');
      }
      default:
        throw new Error('Unbekannter Blocktyp.');
    }
  }

  function serialize(doc) {
    if (!doc || !Array.isArray(doc.blocks)) throw new Error('Ungültiges Wissensdokument.');
    if (!doc.structureDirty) {
      return doc.leading + doc.blocks.map(block => {
        if (!block.dirty) return block.raw + block.sep;
        const originalTrailing = !block.sep ? (block.raw.match(/\r?\n$/) || [''])[0] : '';
        return format(block) + block.sep + originalTrailing;
      }).join('');
    }
    const chunks = doc.blocks.map(block => {
      const text = block.dirty ? format(block) : block.raw;
      return text.replace(/\r?\n+$/, '');
    });
    return doc.leading + chunks.join('\n\n') + (doc.trailing || '');
  }

  function move(doc, index, delta) {
    const target = index + delta;
    if (index < 0 || target < 0 || target >= doc.blocks.length) return false;
    const block = doc.blocks.splice(index, 1)[0];
    doc.blocks.splice(target, 0, block);
    doc.structureDirty = true;
    return true;
  }

  return {KINDS, LABELS, parse, newBlock, format, serialize, move, safeURL};
}));
