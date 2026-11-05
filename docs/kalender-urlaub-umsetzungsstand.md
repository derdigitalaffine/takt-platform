# Kalender und Urlaubsplanung: Abnahme

Tracking: [Issue #183](https://github.com/derdigitalaffine/takt-platform/issues/183). Die Organisationsgrundlage liegt in [PR #182](https://github.com/derdigitalaffine/takt-platform/pull/182). Die Kalenderänderung baut darauf auf; beide werden nicht automatisch zusammengeführt.

## Implementiert

- Kalenderkern mit persönlichen/geteilten, internen, öffentlichen und Organisationskalendern; zusätzliche Zielgruppe je Termin. Freigaben für Personen/Gruppen, getrenntes Publikationsrecht, identische Live-Prüfungen in Web, Export und CalDAV.
- FullCalendar Standard 6.1.21 und eigene Personenzeitachse für Monat/Quartal/Jahr, halbe Tage, Überlappungen, Filter, Tastatur-/Formulareingabe, Mausauswahl und Änderungsentwürfe. Gemeinsame responsive Kalendersteuerung und Designvariablen auch in bestehenden Kalenderoberflächen.
- Urlaub: einfache Personenzahl oder erweiterte Kapazität, datierte Wochenmodelle, zusätzliche Zuordnungen, deduplizierte Vorfahrenprüfung, getrennte Konfliktvorschau für Entwürfe, Warnungen/Sperren, optionale begründete Ausnahmeentscheidung oder bloße Benachrichtigung.
- Interne mehrstufige Genehmigung, reine Planung und externe eigene Selbstauskunft. Bereichsplanung, Genehmigung, Urlaubsregeln und Rollenverwaltung sind getrennte Rechte. Stornoanfragen und geschützter Entscheidungsverlauf.
- Änderungen lassen bisherige verbindliche Zeiträume bestehen. Atomare Besetzungs-/Kontenprüfung und Abwesenheitsübernahme unter gemeinsamem Organisationsschutz; Versionsprüfung und konkurrierende Genehmigungen getestet.
- Halbtagsgrenzen an eindeutig verknüpften Abwesenheiten; keine automatischen Vertretungsrechte. Die alten Vertretungsprüfungen schließen urlaubsverwaltete Einträge ausdrücklich aus. Manuelle Abwesenheiten bleiben eigenständige Datensätze und reduzieren die Besetzung.
- Optionales internes Urlaubskonto mit Anspruch, Übertrag, Verbrauch und Rest. Verbrauch wird je bestätigtem Zeitraum festgehalten. Arbeitsfreie Hälften werden nicht belastet; wenn der gesamte Arbeitstag nur eine geplante Hälfte enthält, entspricht deren kompletter Ausfall einem Urlaubstag. Externe Verwaltung blendet Kontowidgets aus; Link, Datumskopie und gekennzeichnete Selbstauskunft unterstützen den Parallelbetrieb.
- Schließzeiten werden im Jahreskalender oder der Urlaubsplanung am selben Fachobjekt angelegt. Urlaubspflichtmarker, Notbesetzung per Leitung/Selbsteintragung, wirksame Abwesenheitskonflikte, Änderungs-/Aufhebungsfunktion und besondere Besetzungsregeln.
- Verbindlicher Eingang in Takt, Hinweise in Übersicht/Aufgaben, persönliche zusätzliche E-Mails sofort oder täglich über die vorhandene Warteschlange.
- Fachprojektionen für Besprechungen/Einladungen, zugeordnete Seminartermine, festgelegte Terminumfragen, Ressourcen, Terminbuchungen, Aufgabentermine, eigenen Urlaub, Abwesenheiten und Schließzeiten. Daten bleiben im Fachmodul. Gemeinsame ICS-Hilfen; bestehende URLs bleiben gültig.
- Serien mit täglicher/wöchentlicher/monatlicher/jährlicher Wiederholung, Ausnahmen, Zeitzonen, Sommerzeit und erhaltener CalDAV-Rohressource. Webänderungen einer Serie verlangen eine ausdrückliche Bestätigung; einzelne Serienausnahmen können über CalDAV bearbeitet werden.
- CalDAV: Discovery, PROPFIND mit unbekannten Eigenschaften, Query mit Zeitfilter, Multiget einschließlich fehlender Objekte, Sync mit Löschungen und gerätegebundenen begrenzten Snapshots. Bedingte Änderungen mit ETags; sichere Größen-/Parsergrenzen. Keine Scheduling-/Einladungsfunktion über DAV.
- Eigene Gerätezugänge mit fest ausgewählten, später änderbaren Kalendern, sofortiger serverseitiger Rechteprüfung, Widerruf und optionaler administrativer Laufzeit. Apple-Profil mit dediziertem eingebettetem Passwort, einmaliger HTTPS-Ausgabe und ausschließlich gespeichertem Prüfwert. Kein Jamf/MDM.
- Widerrufbare ICS-Lesetokens und Einrichtungshilfe für iOS, Android, Thunderbird, klassisches/neues Outlook. Fachkalender werden über DAV/ICS lesend projiziert; fachliche Änderungen erfolgen in Takt. Freie Kalender unterstützen DAV-Schreibzugriff.

## Testnachweise

Die vollständige Python-Suite hat im Zwischenstand 642 Tests bestanden. Anschließende Ergänzungen werden gezielt und in der PR-CI geprüft. Eigene Browserprüfungen umfassen reale Formulare, verbindlichen Urlaub samt Änderung, Kalenderanlage, mobile Breite sowie die FullCalendar-Zeitachse. Der gemessene Aufbau der Jahresansicht mit 150 Personen lag lokal bei etwa 70 ms; die CI prüft ein großzügigeres Laufzeitlimit gegen erhebliche Regressionen.

Die GitHub-Actions-Pipeline ergänzt eine eigene Kalender-/Urlaubs-Browserprüfung zu den bestehenden Aufgaben-, Umfragen-, Seminar- und Boardprüfungen. Erst nach erfolgreicher vollständiger CI ist die Änderung technisch mergebereit.

## Bekannte Produktgrenzen und Betrieb

- Es wurde kein reales iPhone, Androidgerät oder Outlook installiert. Protokoll-/Profiltests und die dokumentierte Einrichtung sind keine Behauptung einer bestandenen physischen Gerätematrix. Outlook-Varianten ohne geeignete Schreibanbindung verwenden die ausdrücklich vereinbarte ICS-Lesealternative; Aktualisierungstakte bestimmt der Client.
- Ein exportiertes Apple-Profil ist ein Zugangsmittel. Widerruf schützt weitere Abrufe; lokale Kopien bereits gelesener Kalenderdaten verwaltet das Endgerät.
- Das Kalender-/Urlaubsmodul wird zunächst ausgeschaltet ausgeliefert. Administration aktiviert es über den vorhandenen Modulschalter und vergibt Bereichsrechte in der gemeinsamen Organisationsverwaltung. Neue Tabellen werden additiv über die bestehende Datenbankinitialisierung angelegt; bestehende Fachobjekt-IDs und ICS-Pfade bleiben erhalten.
- Die globale Organisationsversion serialisiert Schreibvorgänge in der bestehenden SQLite-Architektur. Bei einem späteren Datenbankwechsel sind dieselben Parallelitätsprüfungen erneut auszuführen.
- Reverse-Proxies müssen HTTPS korrekt weitergeben und persönliche ICS-Tokenpfade in ihren Zugriffsprotokollen ausblenden. Takt blendet sie in seinem eigenen Uvicorn-Zugriffsprotokoll aus.

## XMPP

Keine Chatimplementierung in dieser Änderung. Vor dem späteren XMPP-Modul wird das ausdrücklich gewünschte Interview geführt.
