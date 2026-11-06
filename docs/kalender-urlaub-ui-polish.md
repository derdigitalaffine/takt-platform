# UI-Polish Kalender & Urlaub

**Stand:** 06.11.2026 · Änderungsumfang von [PR zur Gestaltung](https://github.com/derdigitalaffine/takt-platform/pulls). Dieser Abschnitt dokumentiert die neue Oberflächenschicht, keine neuen Fachrechte.

## Ziel und Gestaltungsregeln

Die bestehenden Takt-Komponenten – Bootstrap-Designsystem, FullCalendar Standard, eigene Personenzeitachse, geteilte Organisationsauswahl und gespeicherte Informationsdichte – bleiben erhalten. Der UI-Polish verbessert die Präsentation und Bedienbarkeit **ohne ein zweites Kalender- oder Abwesenheitssystem**.

- Ruhige, hochwertige Verwaltungssprache: definierte Abstände, klare Abschnittstitel, subtile Rahmen, lesbare Statuspillen und explizite Sekundärinformationen.
- Ein gemeinsamer, ausschließlich auf Kalender-/Urlaubsseiten beschränkter Stylesheet-Layer `portal/app/static/planning-polish.css`. Er nutzt die vorhandenen Bootstrap-Variablen für Hell/Dunkel und die vorhandene persönliche Komfort-/Kompaktdichte.
- Eine kleine progressive Ergänzung `planning-polish.js` fügt Kalender-Quellensuche, Alle-ein-/ausblenden und einen Direkteinstieg in den Termin-Editor hinzu. Ohne JavaScript bleiben Formulare, Freigaben und Kalenderauswahl grundsätzlich nutzbar.
- Keine erfundenen Krankheits-, Berufsschul- oder Gleitzeitdaten; die Serverantwort entscheidet weiterhin darüber, welche Abwesenheit überhaupt angezeigt werden darf.

## Kalender

| Bereich | Änderung |
| --- | --- |
| Startseite | Arbeitsbereichsleiste, direkter Einstieg „Neuer Termin“, getrennte Übersicht, ruhigeres Raster |
| Kalenderquellen | Aufklappbares Panel, lokale Suche, Trefferzähler, Alle anzeigen/ausblenden, Freigabe-Links bleiben bei der zugehörigen Quelle |
| Monats-/Wochen-/Jahres-/Listenansicht | Verfeinerte FullCalendar-Schaltflächen, Fokusmarkierungen, Platzverteilung und Datumsüberschriften, bestehende Kalenderengine und API unverändert |
| Datenabruf | Screenreaderfreundlicher Ladestatus; bestehende serverseitige Fehlertexte bleiben erhalten |
| Termin- und Schließzeiteditor | Bessere Kennzeichnung, verständliche Hilfetexte und sichtbar gruppierte Primär-/Sekundäraktionen. Serieneingriffe bleiben ausdrücklich zustimmungsbedürftig |
| Gerätezugänge, Abo-Links | Visuell ausgezeichnete aktive/widerrufene Zugänge, bessere Warnung zu sensiblen Zugangslinks, hilfreiche Leerzustände |
| Freigaben und Einrichtung | Lesbare Sichtbarkeitsstufe, Freigabezähler und direkte Hilfe-Navigation für iOS, Android, Desktop und Outlook |

## Urlaub

| Bereich | Änderung |
| --- | --- |
| Gemeinsamer Einstieg | Organisationskontext in eigener Leiste, direkt verständlicher gewählter Workflow, weiterhin gespeicherte Komfort-/Kompaktdichte |
| Planer | Personenanzahl, klarer Hinweis auf Zeitauswahl/Konfliktprüfung, Legende für Geplant/Beantragt/Verbindlich/Abwesend/Besetzungshinweis; Zeitachse mit sticky Namen und ruhigerem Layout |
| Eingabe- und Konfliktpanel | Beibehaltenes rechtsseitiges Panel und mobile Vollansicht; Kennzeichnung der Entwurfssituation und Screenreader-Fehlerstatus |
| Mobile Bedienung | Editor trägt `role=dialog`, `aria-modal`, beschrifteten Titel; Tab/Shift+Tab bleiben im offenen Dialog, Escape und Schließen stellen den bisherigen Fokus wieder her |
| Mein Urlaub / Genehmigungen | Status wird zusätzlich zu Farbsignalen als Textpille angezeigt. Einträge haben semantisch passendere Überschriften und klarere Leerzustände |
| Schließzeiten & Notbesetzung | Status „Besetzung abgedeckt/Notbesetzung offen“, Anzahl, separate Hinweise bei fehlender Abdeckung; keine neue Closure-Tabelle |
| Verwaltung | Einhaltung bestehender fünf Seiten; verständliche Arbeitsmodell-Zählung und fehlende-Konfiguration-Hinweise, weiterhin separate CSRF- und Rechteprüfungen |

## Accessibility, Datenschutz, technische Grenzen

Die gesamte UI benutzt vorhandene Kontrast- und Theme-Tokens, legt bei Tastaturfokus einen klaren Ring an und berücksichtigt `prefers-reduced-motion` sowie Systemfarben mit `forced-colors`. Der mobile Dialog wird mit Fokusfang und Fokuswiederherstellung verbessert. Kalenderquellensuche und Statusfilter sind **rein lokal auf bereits serverseitig freigegebene Inhalte begrenzt**. Es werden weder vertrauliche Krankgründe noch weitergehende Zugriffsrechte an den Client übertragen.

Die Bezeichnung **„externe ZE-Software“** bleibt verbindlich. Deren Status ist nicht automatisiert verifiziert; eine persönliche Bestätigung bleibt eine freiwillige, gekennzeichnete Selbstauskunft. Auf die vorhandenen Krankmeldungen, Vertretungen, Seminare und Abwesenheiten wird über die bestehenden Module zurückgegriffen, ohne Daten zu kopieren.

**Nicht verändert:** Kalender- und Urlaubs-Fachdatenmodelle, Genehmigungs- und Stornierungsentscheidungen, Zeitzonen-/Serienlogik, ICS-/CalDAV-Pfade, Rollen und serverseitige Berechtigungen. Keine neue Designbibliothek, keine FullCalendar-Premium-Abhängigkeit.

## Abnahme und Testmatrix

- `pytest -q tests` für bestehende Termin-, Abwesenheits-, Kalender-, Urlaubs-, Rollen- und Sicherheitsregressionen.
- `python tests/browser/leave_ui_smoke.py`: Urlaubseintrag, Verbindlichmachen, Konfliktvorschau, Zeitraum und Zoom über Speichervorgänge, mobiler Dialog inklusive Escape und Fokuswiederherstellung, Kalendererstellung, Quellensuche, Alle ein-/ausblenden, persönliche Informationsdichte, Termin- und Schließzeiterfassung sowie Notbesetzung.
- `python tests/browser/person_timeline_smoke.py`: eigene Zeitachse, Tastatur, responsive/mobile Darstellung, Jahresansicht mit vielen Personen.
- Vorhandene GitHub-Jobs `seminars-browser`, `tasks-browser`, `surveys-browser`, `kanban-browser` decken den Rest der Oberfläche auf Regressionen ab.

**Freigabe:** Nur den CI-Stand des finalen PR-Commits als Freigabenachweis verwenden. Automatisierte Chromium-Tests ersetzen keine vollständige Abnahme realer iPhone-/Android-/Outlook-Clients. Bei geänderten Browser-/Betriebssystemversionen im Zweifel die mobile Toolbar und Schriftvergrößerung erneut prüfen.

Siehe auch [Fachkonzept](kalender-urlaub-konzept.md), [bestehender Umsetzungsstand](kalender-urlaub-umsetzungsstand.md) und [Security-Review #185](SECURITY-REVIEW-PR185.md).
