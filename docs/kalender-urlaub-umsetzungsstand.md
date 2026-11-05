# Kalender und Urlaubsplanung: Implementierung und Abnahme

**Stand: 05.11.2026.** Die Organisationsgrundlage aus [PR #182](https://github.com/derdigitalaffine/takt-platform/pull/182) und Kalender/Urlaub aus [PR #184](https://github.com/derdigitalaffine/takt-platform/pull/184) sind in `main` integriert. Fachliches Tracking: [Issue #183](https://github.com/derdigitalaffine/takt-platform/issues/183). Der Funktionsstand wird hier von noch offenen Geräte-/Betriebsprüfungen abgegrenzt.

## Implementiert

- Kalenderkern mit persönlichen/geteilten, internen, öffentlichen und Organisationskalendern; zusätzliche Zielgruppe je Termin. Freigaben für Personen/Gruppen, getrenntes Publikationsrecht, identische Live-Prüfungen in Web, Export und CalDAV.
- FullCalendar Standard 6.1.21 und eigene Personenzeitachse für Monat/Quartal/Jahr, halbe Tage, Überlappungen, Filter, Tastatur-/Formulareingabe, Mausauswahl und Änderungsentwürfe. Zeitraum und Zoom werden je Bereich innerhalb der Browser-Sitzung auch über Neuladen und Speichern hinweg erhalten. Mehrere neue Einträge innerhalb des sichtbaren Bereichs verschieben den Ausschnitt nicht; nur außerhalb liegende neue Einträge führen zum passenden Zeitraum, ohne die Zoomstufe zu verändern. Gemeinsame responsive Kalendersteuerung und Designvariablen auch in bestehenden Kalenderoberflächen.
- Urlaub: einfache Personenzahl oder erweiterte Kapazität, datierte Wochenmodelle, zusätzliche Zuordnungen, deduplizierte Vorfahrenprüfung, getrennte Konfliktvorschau für Entwürfe, Warnungen/Sperren, optionale begründete Ausnahmeentscheidung oder bloße Benachrichtigung.
- Interne mehrstufige Genehmigung, reine Planung und externe eigene Selbstauskunft. Bereichsplanung, Genehmigung, Urlaubsregeln und Rollenverwaltung sind getrennte Rechte. Stornoanfragen und geschützter Entscheidungsverlauf.
- Änderungen lassen bisherige verbindliche Zeiträume bestehen. Atomare Besetzungs-/Kontenprüfung und Abwesenheitsübernahme unter gemeinsamem Organisationsschutz; Versionsprüfung und konkurrierende Genehmigungen getestet.
- Halbtagsgrenzen an eindeutig verknüpften Abwesenheiten; keine automatischen Vertretungsrechte. Die alten Vertretungsprüfungen schließen urlaubsverwaltete Einträge ausdrücklich aus. Manuelle Abwesenheiten bleiben eigenständige Datensätze und reduzieren die Besetzung.
- Optionales internes Urlaubskonto mit Anspruch, Übertrag, Verbrauch und Rest. Verbrauch wird je bestätigtem Zeitraum festgehalten. Arbeitsfreie Hälften werden nicht belastet; wenn der gesamte Arbeitstag nur eine geplante Hälfte enthält, entspricht deren kompletter Ausfall einem Urlaubstag. Externe Verwaltung blendet Kontowidgets aus; Link, Datumskopie und gekennzeichnete Selbstauskunft unterstützen den Parallelbetrieb.
- Schließzeiten werden im Jahreskalender oder der Urlaubsplanung am selben Fachobjekt angelegt. Urlaubspflichtmarker, Notbesetzung per Leitung/Selbsteintragung, wirksame Abwesenheitskonflikte, Änderungs-/Aufhebungsfunktion und besondere Besetzungsregeln.
- Verbindlicher Eingang in Takt, Hinweise in Übersicht/Aufgaben, persönliche zusätzliche E-Mails sofort oder täglich über die vorhandene Warteschlange.
- Fachprojektionen für Besprechungen/Einladungen, zugeordnete Seminartermine, festgelegte Terminumfragen, Ressourcen, Terminbuchungen, Aufgabentermine, eigenen Urlaub, Abwesenheiten und Schließzeiten. Daten bleiben im Fachmodul. Gemeinsame ICS-Hilfen; bestehende URLs bleiben gültig.
- Serien mit täglicher/wöchentlicher/monatlicher/jährlicher Wiederholung, Ausnahmen, Zeitzonen, Sommerzeit und erhaltener CalDAV-Rohressource. Webänderungen einer Serie verlangen eine ausdrückliche Bestätigung; einzelne Serienausnahmen können über CalDAV bearbeitet werden.
- CalDAV: Discovery, PROPFIND mit unbekannten Eigenschaften, Query mit Zeitfilter, Multiget einschließlich fehlender Objekte, Sync mit Löschungen und gerätegebundenen begrenzten Snapshots. Bedingte Änderungen mit ETags; sichere Größen-/Parsergrenzen. Änderungsprotokoll für Termin-/Freigabeänderungen mit Person, Gerätebezug und Zeitpunkt; keine Zugangsdaten oder kopierten Beschreibungen im Protokoll. Keine Scheduling-/Einladungsfunktion über DAV.
- Eigene Gerätezugänge mit fest ausgewählten, später änderbaren Kalendern, sofortiger serverseitiger Rechteprüfung, Widerruf und optionaler administrativer Laufzeit. Apple-Profil mit dediziertem eingebettetem Passwort, einmaliger HTTPS-Ausgabe und ausschließlich gespeichertem Prüfwert. Kein Jamf/MDM.
- Widerrufbare ICS-Lesetokens und Einrichtungshilfe für iOS, Android, Thunderbird, klassisches/neues Outlook. Fachkalender werden über DAV/ICS lesend projiziert; fachliche Änderungen erfolgen in Takt. Freie Kalender unterstützen DAV-Schreibzugriff.

- Einheitliche Organisationsverwaltung für Hierarchie, Körperschaften, Wappen, Anschrift, Kontakt, Benutzerzuordnungen und Bereichsrollen. Bestehende Organisationen und Fachverknüpfungen werden weiterverwendet, bisherige Verwaltungsadressen führen zur gemeinsamen Oberfläche. Bildwechsel löschen bisherige Dateien erst nach erfolgreichem Datenbankschreiben.
- Gemeinsame Personenauswahl mit Namen-/E-Mail-Suche, Personen-/Gruppenfilter, sichtbarer Auswahl und entfernbaren Auswahlchips. „Alle Treffer“ ergänzt die Auswahl; Suchen verwirft sie nicht. Sammelzuordnungen, Sammelentzug, Bereichsrollen, Kalenderfreigaben, Arbeitsmodelle und einzelne abweichende Arbeitstage prüfen jedes Ziel in derselben Transaktion. Native Kontrollkästchen bleiben ohne JavaScript nutzbar.
- Gesetzliche Feiertage werden unabhängig von Ressourcenpreisen für die Besetzung, Schließzeitpflicht und interne Konten berücksichtigt. Portalvorgabe, vererbte Bereichsvorgabe und deaktivierbarer Feiertagskalender; ein datierter Sonderdienst kann ausdrücklich davon abweichen. Bereits bestätigte Urlaubskontobelastungen bleiben festgehalten.

## Testnachweise und Freigabestand

Die vollständige Python-Suite hat für PR #184 **660 Tests bestanden** (vier Warnungen). Die [vollständige Portal-CI](https://github.com/derdigitalaffine/takt-platform/actions/runs/42055155667) auf dem geprüften PR-Stand war vor dem Merge **grün**: `pytest`, `tasks-browser`, `surveys-browser`, `seminars-browser`, `calendars-browser` und `kanban-browser`. Die CodeQL-Analysen für Python, JavaScript/TypeScript und GitHub Actions waren ebenfalls erfolgreich.

Die Chromium-Prüfung der Urlaubsansicht umfasst reale Formulare, verbindlichen Urlaub mit Änderung, Kalenderanlage, mobile Darstellung und Personenauswahl. Ergänzt wurden **mehrere unmittelbar aufeinanderfolgende Speichervorgänge im Quartalszoom**, die beibehaltene Navigation im sichtbaren Bereich, der gezielte Wechsel zu einem außerhalb liegenden neuen Zeitraum sowie das erneute Laden bei unverändertem Zoom. Die Zeitachse wurde außerdem mit Tastatur, überlappenden Einträgen und einer Jahresansicht mit 150 Personen geprüft. Der lokal gemessene Aufbau der Jahresansicht lag bei etwa 70 ms; die CI verwendet ein großzügigeres Regressionstest-Limit.

Der PR wurde als [Squash-Merge #184](https://github.com/derdigitalaffine/takt-platform/pull/184) in `main` übernommen (Merge-Commit `a2273e5b86cd0f72b4957bb0b304b57b765e3428`). Die nachfolgenden **reinen Dokumentationsänderungen** beschreiben diesen geprüften Funktionsstand; sie ersetzen keine separate Geräte- oder Produktionsabnahme.

## Bekannte Produktgrenzen und Betrieb

- Es wurde kein reales iPhone, Androidgerät oder Outlook installiert. Protokoll-/Profiltests und die dokumentierte Einrichtung sind keine Behauptung einer bestandenen physischen Gerätematrix. Outlook-Varianten ohne geeignete Schreibanbindung verwenden die ausdrücklich vereinbarte ICS-Lesealternative; Aktualisierungstakte bestimmt der Client.
- Ein exportiertes Apple-Profil ist ein Zugangsmittel. Widerruf schützt weitere Abrufe; lokale Kopien bereits gelesener Kalenderdaten verwaltet das Endgerät.
- Das Kalender-/Urlaubsmodul wird zunächst ausgeschaltet ausgeliefert. Administration aktiviert es über den vorhandenen Modulschalter und vergibt Bereichsrechte in der gemeinsamen Organisationsverwaltung. Neue Tabellen werden additiv über die bestehende Datenbankinitialisierung angelegt; bestehende Fachobjekt-IDs und ICS-Pfade bleiben erhalten.
- Die globale Organisationsversion serialisiert Schreibvorgänge in der bestehenden SQLite-Architektur. Bei einem späteren Datenbankwechsel sind dieselben Parallelitätsprüfungen erneut auszuführen.
- Reverse-Proxies müssen HTTPS korrekt weitergeben und persönliche ICS-Tokenpfade in ihren Zugriffsprotokollen ausblenden. Takt blendet sie in seinem eigenen Uvicorn-Zugriffsprotokoll aus.

## XMPP

Keine Chatimplementierung in dieser Änderung. Vor dem späteren XMPP-Modul wird das ausdrücklich gewünschte Interview geführt.
