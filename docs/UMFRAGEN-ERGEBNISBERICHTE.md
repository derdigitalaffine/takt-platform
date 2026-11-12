# TAKT Umfragen – Ergebnisberichte und Teilnahmebestätigungen

Stand: 12. November 2026. Verbindliches Interview: Fragen **1–6 jeweils D**.

## Fachliches Zielbild (verbindlich)

Alle vier Umfragearten – Formularumfragen, Terminumfragen, formelle
Abstimmungen sowie Live-Umfragen – erhalten ein konsistentes,
datenschutzgerechtes Berichtssystem. Eine Teilnehmeransicht zeigt
dagegen ausschließlich Informationen, die nach Zugang, Identität,
Anonymität und der vom Ersteller gewählten Freigabe tatsächlich sichtbar
sein dürfen.

Die vollständige Spezifikation umfasst:

1. **DIN A4:** Berichte für alle vier Arten mit auf die Fachlogik
   abgestimmtem Inhalt; bestehende CSV-/JSON-Ausgaben bleiben erhalten.
2. **Persistente Teilnehmerbestätigung:** nach dem Absenden und bei
   jedem späteren Wiederaufruf; persönliche Änderungen erzeugen keine
   weitere gezählte Teilnahme.
3. **Getrennte Freigaben:** eigener Status, eigene Antwort, aggregierte
   Zwischen-/Endergebnisse und Berichtsexport je nach Zeitpunkt und
   Berechtigung. Die Export-API muss dieselbe Policy wie die Webansicht
   erzwingen; ein direkter Dateilink darf keinen Zugriff erweitern.
4. **Report-Design:** Organisationsfarben/-logo, wiederholte Kopf- und
   Fußzeilen, Metadaten, Datum und Seitennummer; flexible Diagramme,
   Terminrankings und barrierearmes Layout. Einzelantworten bleiben im
   Standardbericht ausgeschlossen.
5. **Nachbereitung:** persönliche sichere Links, zulässige
   Erinnerungen, Ergebnisveröffentlichung, Terminfestlegung und
   ICS-Download. Nachrichten nur über erlaubte Versandwege, ohne
   Offenlegung geheimer Stimmen.
6. **Betriebssicherheit:** schrittweise Migration bzw. rückwärtskompatible
   Einführung, Funktionstests, Schutz der vorhandenen Live-Engine,
   Dokumentation, CI/PR-Gates und kontrollierter Rollout.

## Erste Umsetzung in PR #363

### Zugriffsgrenzen

* `GET /forms/{id}/export.pdf`: nur verwaltende Portalnutzer mit
  bestehender Form-`VIEW`-Berechtigung; ausschließlich
  `form.kind == "survey"`, niemals Online-Anträge über diesen Endpunkt.
* `GET /polls/{id}/export.pdf`: nur Nutzer mit bestehender
  Terminumfrage-`VIEW`-Berechtigung (analog CSV).
* Beide Antworten: `application/pdf`, `private, no-store`,
  `X-Content-Type-Options: nosniff`.
* **Kein ungesicherter Teilnehmer-PDF-Endpunkt.** Für eine spätere
  Ergebnisfreigabe wird zuerst eine gemeinsame Policy aus
  Identität/Einladungsnachweis, Veröffentlichung und erlaubten
  Berichtsinhalten benötigt.
* Die Berichte enthalten **keine Rohantworten, Namen, E-Mail-Adressen,
  Kommentare, Dateien oder personenbezogene Geodaten**. Nur
  anonymisierte bzw. fachlich aggregierte Werte.

### Gestaltung

`portal/app/survey_pdf.py` erzeugt ReportLab-Vektordokumente in
DIN A4 (Hochformat). Der Bericht nutzt das in den
Organisationseinstellungen definierte Primärfarbthema und – bei
unterstütztem Rasterformat – das bestehende Logo. Auch ohne Logo bleibt
das Layout vollständig. Wiederholte Kopf-/Fußzeilen und automatisch
aufteilbare Ergebniszeilen unterstützen längere Umfragen.

* Formularumfrage: Frage-für-Frage-Auswertung mit Balken/Skalen,
  Rücklauf und Durchschnitt; keine Roh-Freitext-/Geodaten.
* Terminumfrage: Abgabezahl, Einladungsrücklauf, festgelegter Termin,
  sortiertes Ranking in den Webfarben Grün/Gelb/Rot und Terminhinweise.

### Teilnahme nach dem Absenden

Terminumfragen behalten persönliche Links `/t/p/{token}`. Die Ansicht
zeigt jederzeit den gespeicherten Status, Datum, persönliche
Terminpräferenzen und bei festgelegtem Termin den privaten
`/t/p/{token}/termin.ics`-Download. Angemeldete Portalkonten werden
bei Zugriff über den öffentlichen Link anhand ihrer vorhandenen
`PollParticipant.user_id` wiedererkannt; eine erneute POST-Anfrage
ändert die vorhandene Antwort statt eine zweite Teilnahme anzulegen.
Ein Browser-Cookie bleibt bei Gästen nur ein praktischer Beleg und
keine verifizierte Identitätsfeststellung.

Formularumfragen behalten die bereits geschützte, dauerhafte
`done`-Ansicht. Die neue Dankeseite bietet einen Statuslink und
für angemeldete Teilnehmende `Meine Umfragen`.

### Nicht verändert

* Live-Umfrage-Routen, Freigabeschalter, Geräte-Hashes, Zeitlimits,
  Quizfragen, Wortwolken und Präsentationsansichten.
* Abstimmungs-/Wahl-Stimmzettel und ihre Anonymitätsgrenzen.
* Bestehende CSV-/JSON-Exporte und die Einladungskommunikation.

## Nachfolgende getrennt abzusichernde PRs

* Vollständige Ergebnisfreigaben je Umfrageart mit eigenen,
  persistenten, konfigurierbaren Einstellungen und identischer
  Web-/Export-Policy. Kleine Auswertungsgruppen ggf. unterdrücken.
* Eigenantworten für nicht-anonyme Formularumfragen mit
  accountgebundenen Leserechten; anonyme Teilnahmen nicht
  nachträglich zuordnen.
* Weitere Berichtstypen für Live-Umfragen und Modernisierung der
  bestehenden förmlichen Ergebnisprotokolle.
* Wiederverwendbare Vorlagen, optionales Querformat,
  umfangreiche Barrierefreiheitstests und visuelle Rendering-Snapshots.
* Ereignisgesteuerte Benachrichtigung über Ergebnisfreigabe,
  Genehmigung, Änderung, Frist und Termine nur mit Zustimmung,
  Versandbegrenzung, idempotenter Ausführung und Audit.
* Optionale Kalender- und Organisationsintegration ohne
  harte Abhängigkeit zu deaktivierten Modulen.

## Testplan

`test_survey_pdf.py` prüft A4-Seitenmaße, Textauslesbarkeit,
Mehrseitigkeit, Nichtoffenlegung der Rohantworten und die
Gleichheit der bestehenden Exportberechtigungen.

`test_poll_receipt.py` prüft dauerhafte Bestätigung, eigene
Terminanzeige nach Ende, kalenderfähigen persönlichen Link und
kontoübergreifende Wiedererkennung ohne Browser-Cookie.

Vor jeder Zusammenführung vollständige Testsuite mit
`test_live.py`, `test_live_quiz.py`, `test_survey_workspace.py`,
`test_my_surveys.py`, den bestehenden Browserprüfungen sowie
Berechtigungs- und Anonymitätsregressionen ausführen. Produktiver
Rollout wird gesondert durchgeführt; ein GitHub-Merge ist kein
automatisches Deployment.
