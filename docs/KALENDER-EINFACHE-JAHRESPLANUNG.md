# Kalender vereinfacht: gemeinsame Jahresplanung und Fachkalender mit einem Klick

**Ziel:** Die bestehende Jahresplanung soll ohne langes Konfigurieren benutzbar sein. Eine gemeinsame Jahresansicht wird zum Kalender-Einstieg; vorhandene Fachkalender sind direkt sichtbar und sofort zuschaltbar.

## Bedienung

1. **Kalender öffnen:** `/kalender` zeigt sofort das ganze Jahr (die bisherige Monatsansicht bleibt über **Termine & Monat** bzw. `/kalender?ansicht=termine` erreichbar). Die bestehende `/kalender/jahr`-Verknüpfung ist ein direkter Jahreslink. Tag, Woche, Monat, Liste und Jahr funktionieren weiterhin mit FullCalendar Standard.
2. **Benötigte Fachtermine einblenden:** Im dauerhaft sichtbaren Abschnitt **Was möchten Sie sehen?** einen Fachkalender einmal anklicken. Ein zweiter Klick blendet ihn wieder aus. Die Auswahl betrifft die aktuelle Kalenderanzeige; der Fachdatensatz bleibt beim Ursprung.
3. **Eigene und gemeinsame Kalender:** Berechtigte bestehende Kalender stehen direkt darüber, unabhängig von der Quelle. „Alle zeigen / Alle ausblenden“ berücksichtigt **auch** die Fachkalender. Die Suche filtert sichtbare Auswahlmöglichkeiten, nicht die Fach- oder Personenrechte.
4. **Jahresplanung für alle einrichten:** Wenn noch kein passender gemeinsamer Jahreskalender vorhanden ist, gibt es eine **einzige, explizite Einrichtungsaktion**. Personen mit `calendar_publish` und `calendars` können einen internen Kalender **Jahresplanung** einrichten, der für alle angemeldeten Portalnutzer **lesbar** ist. Personen mit Kalender- und bereichsbezogenen Planungsrechten können stattdessen einen Bereichskalender erstellen. Wiederholtes Klicken erzeugt keinen zweiten Kalender desselben Geltungsbereichs.
5. **Termin erfassen:** Im bestehenden gemeinsamen Jahresplan führt **Jahrestermin eintragen** direkt in den bewährten Editor und wählt den richtigen Kalender vor. Schreibrechte bleiben strikt an die Kalenderrolle/Freigabe gebunden; ein gemeinsamer Lesekalender erlaubt nicht automatisch das Schreiben.
6. **Teamplanung:** Der direkte Einstieg **Teamabwesenheiten** öffnet weiterhin den berechtigten Personen-/Besetzungsplan. Ein persönlicher Urlaub ist im Hauptkalender ausschließlich für die jeweilige Person sichtbar; Teamabwesenheiten gehören nicht unkontrolliert in einen Kalender für alle.

## Datenmodell und Dublettenfreiheit

- Die ephemeren Fachkalender rufen `GET /kalender/quellen/{kind}/data` auf. Dieser Endpunkt benutzt denselben `calendar_sources.project()`-Projektor wie ein bereits angebundener Quellkalender und die vorhandenen berechtigungsgeprüften Exportfunktionen. Es werden **keine Kalender-, Seminar-, Urlaubs-, Krankmeldungs- oder Vertretungsdatensätze** angelegt, kopiert oder synchronisiert.
- Existiert für eine Fachquelle bereits ein berechtigt sichtbarer, angebundener Kalender, wird die Quelle als **dieser vorhandene Kalender** angezeigt und kein zweiter ephemerer Layer angeboten.
- Die bestehende Option „Fachkalender dauerhaft hinzufügen“ bleibt unter **Fachkalender auch auf Geräten nutzen** für CalDAV und ICS bestehen. Sie verwendet den bisherigen CSRF-geschützten und idempotenten `POST /kalender/quellen`-Weg.
- Der **gemeinsame Jahresplan** ist ein normaler `Calendar` mit `source="free"`, kein neues Modell. Sein Geltungsbereich ist entweder `internal` (angemeldete Benutzer) oder `organization`. Eine bestehende passende Jahresplanung beziehungsweise „Gemeinsame Jahrestermine“ wird wiederverwendet. Der neue Erstellungsweg prüft Berechtigung, Geltungsbereich und das Vorhandensein eines passenden Kalenders unter dem vorhandenen Transaktions-/Organisationslock.
- Fachtermine bleiben bearbeitbar **ausschließlich im ursprünglichen Fachmodul**. Ein Kalender-Overlay verschafft keine Schreibrechte für das zugrunde liegende Fachobjekt.

## Datenschutz und Sicherheit

- Der neue GET-Endpunkt prüft den globalen Quellentyp, einen auf maximal 400 Tage beschränkten Zeitraum und die aktuelle Anmeldung; `project()` filtert **jeden Fachdatensatz** mit bestehenden Berechtigungen.
- Urlaub im Fachkalender bedeutet **„Mein Urlaub“**, nicht „Urlaub der gesamten Organisation“. Eigene Abwesenheiten aus bestehenden Modulen bleiben personenbezogen. Krankmeldungsgründe, Diagnosen, Atteste, personenbezogene Notizen und fremde Urlaubsanträge gelangen nicht über den Fachkalender in die gemeinsame Jahresansicht.
- Die optionale persönliche Selbstauskunft zur Genehmigung in der **externen ZE-Software** bleibt davon unabhängig und ist nicht technisch verifiziert.
- Die Einrichtung des gemeinsamen Plans erfordert `calendars` plus `calendar_publish` für interne, für alle angemeldeten Personen sichtbare Kalender; ein Bereichskalender erfordert `calendars` und `org.plan` für die angegebene Einheit. **Öffentliches Teilen ohne Anmeldung wird von dieser Ein-Klick-Aktion nicht angeboten.**
- Angezeigte Quellen werden bei jedem Abruf erneut geprüft. Ein Benutzer, dem Rechte entzogen werden, kann nicht durch einen früheren Klick einen privaten Fachdatensatz weiter lesen.

## UI und Barrierefreiheit

Die Oberfläche bleibt beim vorhandenen Takt-/Bootstrap-Design, unterstützt Hell/Dunkel und Komfort/Kompakt, hat große Schaltflächen und ausdrücklich ausgeschriebene Zustände. Drei klar getrennte Wege führen zu **Jahresplanung**, **Termine & Monat** und **Teamabwesenheiten**. Die Jahresansicht ist auch ohne individuelle Einrichtung nutzbar. Der Layoutmodus passt die Navigation und Fachkalender-Auswahl an kleine Bildschirme an, ohne neue Frameworks.

Ohne JavaScript zeigt die Jahres-/Monatsauswahl weiterhin die korrekte serverseitig gerenderte Seite. Ein Fachkalender-Button fällt dann auf den bisherigen, CSRF-geschützten `POST /kalender/quellen`-Mechanismus zurück, damit ein Fachkalender dauerhaft angebunden werden kann.

## Tests und Abnahme

- Python: Jahres-Standardansicht und Monats-Umschaltung, ephemerer Fachkalender ohne Datensatzkopie, Endpunkt für unbekannte Quellen (404), ungültige Zeiträume (422), doppelte Einrichtungsversuche ohne doppelten Kalender, Autorisierung von Personen ohne Veröffentlichungsrecht sowie Schutz fremder Urlaubsdatensätze.
- Chromium: Jahresansicht sofort sichtbar, Fachkalender mit einem Klick an/aus, gemeinsamer Jahresplan in einer Aktion angelegt, direkter Einstieg „Jahrestermin eintragen“, Monatsansicht, vorhandene Termin-/Serien-/Schließzeitenabläufe und mobile Darstellung.
- GitHub: vollständige Portal-Python- und Browser-CI einschließlich übriger Module. Erst der **endgültige PR-Head-Commit** gilt als Nachweis.
- Noch nicht Bestandteil: neue Berufsschul- oder minutengenaue Gleitzeitquellen ohne vorhandenes Fachmodell; Änderungen an Berechtigungen von ICS/CalDAV/externen Anwendungen; vollständige reale Geräteabnahme.

## Administrator-Hinweis

Ein interner Jahresplan bedeutet **Lesesichtbarkeit für alle angemeldeten Konten**, nicht globale Schreibberechtigung. Berechtigte Mitarbeiter können über die bestehende **Freigaben verwalten**-Seite Schreibrechte erhalten. Bereichskalender behalten die fachlichen `org.plan`-Regeln. Für die Betriebsaufnahme zunächst einen gemeinsamen Kalender einrichten, Verantwortliche festlegen und nur die tatsächlich benötigten Fachkalender sichtbar schalten.

Siehe auch [Kalender-/Urlaubskonzept](kalender-urlaub-konzept.md), [vorheriger UI-Polish](kalender-urlaub-ui-polish.md) und [Security-Review](SECURITY-REVIEW-PR185.md).
