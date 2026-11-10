/* Lightweight Markdown authoring for TAKT Wissen.
 * Native form is always the authoritative fallback; the server is responsible
 * for rendering preview (Markdown HTML is disabled on the backend).
 * No third-party CDN, no editable HTML and no hidden model calls.
 */
(function () {
  'use strict';
  const templates = {
    article: "## Überblick\n\nWas ist wichtig?\n\n## Vorgehen\n\n1. Erster Schritt\n2. Nächster Schritt\n\n## Verweise\n\n",
    process: "## Zweck und Ergebnis\n\n## Auslöser\n\n## Zuständige Rollen\n\n## Ablauf\n\n1. Schritt\n2. Entscheidung oder Übergabe\n3. Abschluss\n\n## Sonderfälle und Vertretung\n\n## Dokumente und Rechtsgrundlagen\n\n",
    checklist: "## Ziel\n\n- [ ] Vorbereitung\n- [ ] Durchführung\n- [ ] Abschluss und Dokumentation\n\n## Hinweise\n\n",
    faq: "## Frage\n\n**Antwort:**\n\n## Hintergrund und Quellen\n\n",
    experience: "## Ausgangssituation\n\n## Praktische Erfahrung\n\n## Was hat funktioniert?\n\n## Grenzen / offene Fragen\n\n"
  };

  const commands = [
    {label: 'Überschrift', icon: 'fa-heading', open: '## ', close: '', placeholder: 'Überschrift', block: true},
    {label: 'Fett', icon: 'fa-bold', open: '**', close: '**', placeholder: 'wichtiger Begriff'},
    {label: 'Liste', icon: 'fa-list-ul', open: '- ', close: '', placeholder: 'Listenpunkt', block: true},
    {label: 'Aufgabe', icon: 'fa-list-check', open: '- [ ] ', close: '', placeholder: 'Arbeitsschritt', block: true},
    {label: 'Zitat', icon: 'fa-quote-left', open: '> ', close: '', placeholder: 'Quelle oder Hinweis', block: true},
    {label: 'Code', icon: 'fa-code', open: '\x60', close: '\x60', placeholder: 'Code oder Feldname'},
    {label: 'Link', icon: 'fa-link', open: '[', close: '](https://)', placeholder: 'Linktext'}
  ];

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  document.querySelectorAll('form[data-knowledge-editor]').forEach(function (form) {
    const textarea = form.querySelector('textarea[data-knowledge-markdown]');
    if (!textarea) return;
    const csrf = form.querySelector('[name="csrf"]');
    const article = form.querySelector('[name="article_id"]');
    const space = form.querySelector('[name="space_id"]');
    if (!csrf || (!article && !space)) return;

    const toolbar = element('div', 'knowledge-editor-toolbar');
    toolbar.setAttribute('role', 'toolbar');
    toolbar.setAttribute('aria-label', 'Markdown-Formatierung');
    toolbar.setAttribute('aria-controls', textarea.id);
    commands.forEach(function (cmd) {
      const button = element('button', 'knowledge-toolbar-button');
      button.type = 'button';
      button.title = cmd.label;
      button.setAttribute('aria-label', cmd.label);
      const icon = element('i', 'fa-solid ' + cmd.icon);
      icon.setAttribute('aria-hidden', 'true');
      button.appendChild(icon);
      button.addEventListener('click', function () {
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const selected = textarea.value.slice(start, end) || cmd.placeholder;
        const prefix = cmd.block && start > 0 && textarea.value[start - 1] !== '\n' ? '\n' : '';
        const insertion = prefix + cmd.open + selected + cmd.close;
        textarea.setRangeText(insertion, start, end, 'end');
        textarea.focus();
        textarea.dispatchEvent(new Event('input', {bubbles: true}));
      });
      toolbar.appendChild(button);
    });

    const templateButton = element('button', 'knowledge-toolbar-template', 'Vorlage einfügen');
    templateButton.type = 'button';
    templateButton.setAttribute('aria-label', 'Passende Gliederungsvorlage einfügen');
    templateButton.addEventListener('click', function () {
      const type = form.querySelector('[name="kind"]')?.value || 'article';
      const content = templates[type] || templates.article;
      if (textarea.value.length + content.length > textarea.maxLength) return;
      const prefix = textarea.value && !textarea.value.endsWith('\n') ? '\n\n' : '';
      textarea.setRangeText(prefix + content, textarea.selectionStart,
                            textarea.selectionEnd, 'end');
      textarea.focus();
      textarea.dispatchEvent(new Event('input', {bubbles: true}));
    });
    toolbar.appendChild(templateButton);

    const previewButton = element('button', 'knowledge-toolbar-template', 'Vorschau');
    previewButton.type = 'button';
    previewButton.setAttribute('aria-pressed', 'false');
    previewButton.setAttribute('aria-label', 'Markdown-Vorschau anzeigen');
    toolbar.appendChild(previewButton);
    textarea.parentNode.insertBefore(toolbar, textarea);

    const preview = element('div', 'knowledge-markdown knowledge-editor-preview');
    preview.id = textarea.id + '-preview';
    preview.hidden = true;
    preview.setAttribute('role', 'region');
    preview.setAttribute('aria-label', 'Vorschau des Wissensbeitrags');
    textarea.insertAdjacentElement('afterend', preview);

    const note = element('p', 'form-text knowledge-editor-note',
      'Markdown wird sicher gerendert. Die Vorschau ist unverbindlich; gespeichert wird erst über das Formular.');
    preview.insertAdjacentElement('afterend', note);

    previewButton.addEventListener('click', async function () {
      if (!preview.hidden) {
        preview.hidden = true;
        textarea.hidden = false;
        previewButton.textContent = 'Vorschau';
        previewButton.setAttribute('aria-pressed', 'false');
        textarea.focus();
        return;
      }
      const data = new FormData();
      data.set('csrf', csrf.value);
      data.set('body_md', textarea.value);
      data.set('article_id', article ? article.value : '0');
      data.set('space_id', space ? space.value : '0');
      previewButton.disabled = true;
      preview.textContent = 'Vorschau wird erstellt …';
      preview.hidden = false;
      try {
        const response = await fetch('/wissen/vorschau', {
          method: 'POST', body: data, credentials: 'same-origin',
          cache: 'no-store', headers: {'Accept': 'application/json'}
        });
        if (!response.ok) throw new Error('Die Vorschau konnte nicht erstellt werden.');
        const result = await response.json();
        // Backend markdown-it renders with raw HTML disabled.
        preview.innerHTML = typeof result.html === 'string' ? result.html : '';
        textarea.hidden = true;
        previewButton.textContent = 'Zurück zum Text';
        previewButton.setAttribute('aria-pressed', 'true');
      } catch (error) {
        preview.textContent = error.message || 'Vorschau nicht verfügbar.';
        previewButton.setAttribute('aria-pressed', 'false');
      } finally {
        previewButton.disabled = false;
      }
    });

    form.addEventListener('submit', function () {
      // Submission always carries the original editable textarea content.
      textarea.hidden = false;
    });
  });
}());
