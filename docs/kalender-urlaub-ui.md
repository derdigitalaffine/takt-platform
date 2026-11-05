# Kalender und Urlaubsverwaltung: UI-Konzept und FullCalendar-Entscheidung

Konzeptstand: 04.11.2026; Integrationsstand: 05.11.2026. Ergänzt das [fachliche Konzept](kalender-urlaub-konzept.md) und dokumentiert die vereinbarte UI-Richtung. Kalenderkern, Personenzeitachse, Urlaubsworkflow und CalDAV wurden mit [PR #184](https://github.com/derdigitalaffine/takt-platform/pull/184) in `main` integriert. **Dieses Konzept ist keine Behauptung, dass jede hier skizzierte Komfortfunktion bereits ausgeliefert oder auf jedem Endgerät abgenommen wurde.** Verbindlich für den tatsächlichen Stand sind [Implementierung, Prüfungen und Betriebsgrenzen](kalender-urlaub-umsetzungsstand.md).

## 1. Verbindliche Technologieentscheidung

Auf ausdrücklichen Wunsch bleibt **FullCalendar Standard** die gemeinsame Kalenderbasis. Die Personenzeitachse entsteht als **eigene Takt-Custom-View**, vollständig aus eigenem Code. FullCalendar-Dateien im Vendor-Verzeichnis werden nicht verändert. Es wird weder Premium-Code kopiert noch eine zweite Kalenderbibliothek eingesetzt. Die eigene Erweiterung bleibt unter der MIT-Lizenz des Repos.

Der aktuelle Bestand nutzt FullCalendar Standard 6.1.21. Die Erweiterung bindet über dessen Custom-View-Schnittstelle an Datumsnavigation, Ansichtswechsel und Ereignisdaten an. Ein Upgrade auf FullCalendar 7 ist ein eigener Schritt mit Kompatibilitätstest; dabei haben sich Plugin- und Theme-APIs geändert. Keine gleichzeitige ungeprüfte Umstellung bestehender Kalender.

| Bestandteil | Auswahl | Begründung |
| --- | --- | --- |
| Tag, Woche, Monat, Jahresübersicht und Agenda | FullCalendar Standard | Gemeinsame Basis mit den vorhandenen Kalendern |
| Personen × Tage/Halbtage | Eigene Takt-Custom-View in FullCalendar | Fachlich passende Bedienung ohne Premium-Abhängigkeit |
| Formulare, Seitenpanel, Filter und Navigation | Gemeinsames Takt-Designsystem auf Bootstrap | Einheitliche Schaltflächen, Fokusführung, Branding, Hell/Dunkel |
| Zeitraum-/Konflikt-/Freigabedialoge | Wiederverwendbare Takt-Komponenten | Identische Bedeutung in allen Kalenderansichten |
| Prüfung, Statusänderungen, Freigaben | Python/FastAPI auf dem Server | Browserdarstellung ist keine Berechtigung oder Genehmigung |

**Mantine** ist eine gute freie React-Alternative für eine spätere umfassendere Frontendmodernisierung. Aktuell bietet auch `@mantine/schedule` Kalender- und Ressourcenansichten; `@mantine/dates/Calendar` allein ist hingegen ein Baustein für Datumauswahl. Für diesen Auftrag würde eine zusätzliche React-/Mantine-Oberfläche neben Bootstrap mehr Abstimmungsaufwand verursachen. Sie wird deshalb nicht eingeführt. EventCalendar und vis-timeline wurden als freie Alternativen geprüft, sind nach der FullCalendar-Entscheidung nicht Bestandteil des Zielstacks.

FullCalendar Standard steht unter MIT. Die fertige Resource Timeline des Herstellers gehört zu Premium mit gesonderter Lizenz. Eine kommunale Verwaltung darf nicht pauschal als kostenlos berechtigte Non-Profit-Organisation eingeordnet werden. Deshalb basiert die Personenansicht auf eigener Implementierung, nicht auf einer vermeintlich kostenlosen Premium-Freigabe.

## 2. Eine erkennbare Navigation

Im bestehenden Bereich „Termine & Veranstaltungen“ gibt es den sichtbaren Einstieg **Kalender & Urlaub**. Darunter werden drei klar benannte Arbeitsbereiche angeboten:

- **Kalender:** persönliche, freigegebene und organisatorisch relevante Termine.
- **Urlaubsplanung:** gemeinsame Planung des freigegebenen Bereichs; eigene Einträge sofort erreichbar.
- **Mein Urlaub:** eigene Planung, verbindliche Zeiten und offene Schritte; optional Urlaubskonto.

Leitungen und Genehmigende erhalten zusätzlich eine Ansicht **Offene Vorgänge**, die denselben verbindlichen Takt-Eingang nutzt. Es entsteht kein zweites unabhängiges Benachrichtigungssystem. Regeln und Freigaben liegen unter „Einstellungen“, nicht zwischen den täglichen Planungsaktionen. Sichtbarkeit richtet sich serverseitig nach Rollen, nicht nur nach versteckten Menüeinträgen.

Ein Wechsel zwischen Ansichten behält Datum, Organisationseinheit und freigegebene Filter. Rücknavigation, Reload und geteilte interne Links funktionieren. Links enthalten keine Abotokens oder sensiblen Gründe. Eine gespeicherte persönliche Ansicht erweitert niemals die Rechte.

## 3. Kalender: wenig Bedienoberfläche, klare Orientierung

Oben stehen Titel, sichtbarer Zeitraum, Heute sowie Vor/Zurück. Eine konsistente Ansichtsleiste wechselt zwischen Monat, Woche, Tag, Jahr und Liste. „Termin anlegen“ ist die primäre Aktion. Kalenderauswahl, Suche und weitere Filter stehen in einem aufklappbaren Seitenbereich; aktive Filter bleiben als kurze, entfernbare Angaben sichtbar.

Standardmäßig sind nur „Meine Termine“ und die relevanten Organisationskalender aktiviert. Beim ersten Einstieg erklärt eine kurze Übersicht die verfügbaren Kalender und ihre Zielgruppen. Einblendung, Farbe und Bearbeitungsrecht sind unterschiedliche Dinge. Ein ausgeblendeter Kalender bleibt auffindbar, ein nicht freigegebener Kalender wird nicht abgefragt.

Die **Jahresübersicht** zeigt zwölf ruhige Monatsfelder. Große organisationsweite Termine erhalten kurze Beschriftungen, weitere Einträge einen Zähler mit Tagesliste. Ein Klick öffnet Tag/Detailpanel. Eine reine Farbpunktwand reicht nicht. Kalenderfarben kennzeichnen die Quelle; Text und Symbol kennzeichnen Art und Zustand. Ein Wechsel der Kalenderfarbe verändert keine Statusbedeutung.

Terminbearbeitung erfolgt im rechten Detailpanel, mobil auf einer eigenen Vollansicht. Titel, Datum, Start, Ende und Dauer sind sofort sichtbar. Ende und Dauer aktualisieren sich gegenseitig; kein Umschalter zwischen zwei Eingabemodi. Ganztägige Termine haben verständliche Datumsgrenzen. Serien, Zielgruppe und Freigaben sind nachgeordnet, aber nachvollziehbar erreichbar. Ein Jahresereignis erhält keine stillen Auswirkungen auf die Besetzung.

## 4. Urlaubsplanung: Personenzeitachse mit Arbeitskontext

### Grundaufbau

Die Hauptansicht zeigt standardmäßig den Fachbereich der Hauptzuordnung mit etwa 20–30 Personen und einen Monat. Organisationseinheit, Zeitraum und Ansichtszoom bleiben oben sichtbar. Ein Wechsel zu zusätzlichen Zuordnungen ist erreichbar. Die gesamte Organisation wird nicht ungefragt aufgeklappt.

Links bleibt die Namensspalte fixiert, oben die Datumsachse. Organisationseinheiten lassen sich gruppieren und einklappen. Personen mit mehreren Zuordnungen werden innerhalb desselben betrachteten Bereichs nicht doppelt gezählt; zusätzliche Einsätze werden kenntlich gemacht. Eine fachliche Bereichsansicht kann mehrere Einsatzzeilen zeigen, ohne diese als verschiedene Personen zu behandeln.

Monat ist die Bearbeitungsansicht. Quartal und Jahr dienen vor allem der Übersicht; eine Auswahl kann zur präzisen Bearbeitung in den Monat wechseln. Die Jahresansicht quetscht 365 Tage nicht auf Bildschirmbreite. Fixierte Namen, Zoom und horizontales Scrollen bleiben erhalten. Kopf, Balken, Auswahl und Besetzungszeilen verwenden dieselbe Datumsprojektion.

**Umgesetzt seit #184:** Die sichtbare Zeitspanne und die Zoomstufe werden für jede Organisationseinheit in der laufenden Browser-Sitzung gespeichert. Nach dem Speichern und Neuladen wird der gewählte Ausschnitt beibehalten, solange der neue Urlaub in diesem Ausschnitt liegt. Ein außerhalb liegender neuer Eintrag öffnet den passenden Zeitraum in **derselben Zoomstufe**. Dies betrifft die Browser-Sitzung, nicht eine dauerhaft serverseitig synchronisierte persönliche Ansicht. Mehrfachspeichern und erneutes Laden sind im Chromium-Test abgedeckt.

### Visuelle Sprache

- Geplant: ruhiger umrandeter Balken, Beschriftung „Geplant“.
- Beantragt: gestrichelter Balken, Beschriftung „Beantragt“.
- Verbindlich: gefüllter Balken mit Symbol und Text. Die tatsächliche Herkunft bleibt im Detail sichtbar.
- Extern genehmigt: zusätzlich ausdrücklich „Selbstauskunft“, nicht als verifizierte Antwort der externen ZE-Software darstellen.
- Änderung offen: bisherige wirksame Zeit bleibt sichtbar; neuer Vorschlag erscheint als zugehöriger Entwurf.
- Andere wirksame Abwesenheit: neutral beschriftet, sensible Gründe werden nicht ausgeliefert.
- Schließtage: eigener Hintergrund mit Bezeichnung. Notbesetzung wird getrennt kenntlich gemacht.

Status, Abwesenheitsart und Konflikt sind verschiedene Eigenschaften. Ein Warnhinweis überschreibt nicht die Statusfarbe; Symbole und Text bleiben auch in Graustufen verständlich. Überlappende Einträge werden gestapelt, nicht verdeckt. Lange Namen und Texte dürfen die Datumsachse nicht verschieben.

### Zeitraum einzeichnen und bearbeiten

1. Mit der Maus in der eigenen oder berechtigt bearbeitbaren Personenzeile einen Bereich aufziehen. Ein Klick oder der sichtbare Knopf „Zeitraum eintragen“ öffnet denselben Ablauf ohne Ziehen.
2. Ein Panel zeigt Person, Beginn, Ende, Vormittag/Nachmittag und den gewählten Ablauf. Die sichtbare Tagesauswahl wird vor dem Speichern eindeutig bestätigt.
3. Die serverseitige Vorschau nennt betroffene Bereiche, konkrete Tage/Halbtage und Auswirkungen auf die Besetzung. Ein neutraler Ladezustand ersetzt alte Ergebnisse, solange erneut geprüft wird.
4. Eine zum Ablauf passende Aktion speichert als geplant, reicht einen Antrag ein oder markiert ausdrücklich verbindlich. „Speichern“ bedeutet nicht automatisch genehmigen.
5. Erst die Serverantwort aktualisiert den tatsächlichen Status. Veraltete Vorschauen, Rechteentzug und gleichzeitig veränderte Besetzung werden verständlich aufgelöst.

Verschieben und Randziehen dürfen später dieselbe Änderungsvorschau öffnen. Sie dürfen weder ohne Bestätigung verbindlichen Urlaub ändern noch Einträge zwischen Personen verschieben. Gleichwertig sind Datumsfelder und Tastaturbedienung. Escape verwirft eine laufende Auswahl; unsichere Änderungen gehen nicht still verloren.

Halbtage sind fachliche Tagesabschnitte. Sie dürfen nicht pauschal als zwölf Stunden oder als „00–12 Uhr“ in Arbeitszeitkonten berechnet werden. Die Darstellung kann zwei gleich große Hälften verwenden; der Server ordnet diese dem Arbeitsmodell zu. DST und UTC-Konvertierungen dürfen keine Tage verschieben.

## 5. Besetzung und Konflikte als Teil der Arbeit

Unter den Personen liegen datumsgenau ausgerichtete Besetzungszeilen für die relevante Einheit und gegebenenfalls betroffene Vorfahren. Beispiel: „Team Haushalt: 3 verfügbar / mindestens 4“ statt einer unerklärten roten Fläche. Im erweiterten Modus werden Personenzahl und Kapazität getrennt angezeigt. Angaben kommen aus dem berechtigten Serverbericht, nicht aus einer Zählung sichtbarer Urlaubsbalken.

Verbindliche Besetzung und Wunschprognose sind getrennte Ebenen. Eine Schaltfläche „Geplante Zeiten berücksichtigen“ ändert die Vorschau, nicht die Sperrprüfung. Fehlende Daten werden als unbekannt markiert und niemals grün dargestellt.

Bei Konflikten öffnet sich eine kompakte Liste mit Zeitpunkt, betroffenem Bereich, Ist/Soll, Regeltyp und nächstem möglichen Schritt. Berechtigte Genehmigende können Warnungen mit Begründung übergehen. Eine Sperre hat keinen generischen „Trotzdem speichern“-Knopf. Sensible Abwesenheitsgründe erscheinen weder in Tooltip noch in Netzwerkantworten.

Ein Konfliktbanner fasst den gewählten Zeitraum zusammen. Es werden nicht gleichzeitig Toast, Dialog und Warnbox für denselben Sachverhalt angezeigt. Hinweise bleiben am betroffenen Zeitraum verlinkt.

## 6. Parallelbetrieb mit externer ZE-Software

In der Instanz mit externer Kontenverwaltung erscheinen weder erfundener Resturlaub noch ein leeres Kontowidget. „Mein Urlaub“ zeigt pro Zeitraum die tatsächlich nötigen Schritte, zum Beispiel „In Takt geplant“, „Extern beantragen“ und „Externe Genehmigung selbst bestätigen“. Reiner Planungsmodus zeigt diese Schritte nicht.

Das Detail bietet kopierbare Datumsangaben und den konfigurierten Link zur externen ZE-Software. Es behauptet keine technische Übertragung. Die eigene Bestätigung enthält den Hinweis „Selbstauskunft“ und gilt nur für die angezeigte Fassung des Zeitraums. Ein Planer darf diese Auskunft nicht stellvertretend erfinden.

Offene externe Schritte werden im vorhandenen Takt-Eingang gesammelt, optional per E-Mail erinnert. Eine Änderung erhält nachvollziehbar einen neuen Prüfstand; der bisherige verbindliche Zeitraum bleibt bis zum Abschluss wirksam.

## 7. Schließtage und Notbesetzung

Schließzeiten können direkt im Jahreskalender angelegt werden. Kalender und Urlaubsplanung zeigen dasselbe Fachobjekt; es werden keine unabhängigen Kopien erzeugt. Die Sichtbarkeit berücksichtigt Haupt- und zusätzliche Zuordnungen sowie Bereichsrollen. Ein Klick führt in den berechtigt sichtbaren Planungsbereich zur Notbesetzung.

Ein Assistent erfasst Zeitraum, betroffene Organisationseinheiten einschließlich Untereinheiten, notwendige Notbesetzung und Ausnahmen. Vor Abschluss zeigt er die Auswirkungen: betroffene Personen, schon abgedeckte Zeiten, noch erforderliche Planung und widersprüchliche Einteilungen.

Die Planungsansicht stellt Schließzeit und Notbesetzung deutlich getrennt dar. Je Bereich ist Leitungseinteilung oder Selbsteintragung möglich. Eine Person in der Notbesetzung wird für dieselbe Zeit nicht gleichzeitig zu Pflichturlaub gedrängt. Bestehender verbindlicher Urlaub wird nicht automatisch überschrieben. Änderungen laufen über dieselben Vorschau- und Bestätigungsschritte.

## 8. Konfiguration ohne Schalterwald

Die Einstellungen zeigen zuerst ein verständliches Profil: „Gemeinsam planen“, „Interne Genehmigung“ oder „Externes System“. Kontenverwaltung und Besetzungsgenauigkeit sind davon unabhängige Einstellungen. Der einfache Modus fragt Personenzahlen ab; der erweiterte ergänzt Arbeitsmodelle und Kapazitäten.

Jede Einstellung zeigt ihre Herkunft, zum Beispiel „Geerbt aus Verwaltung“, und eine verständliche effektive Zusammenfassung. Eine berechtigte Leitung kann eine lokale Abweichung setzen oder zur Vererbung zurückkehren. Vor dem Speichern werden Auswirkungen auf vorhandene Einträge erklärt. Standardmäßig werden laufende verbindliche Vorgänge nicht rückwirkend umgedeutet.

## 9. Mobil, Tastatur und Barrierearmut

Mobil startet die Urlaubsplanung mit eigener Planung und einer Bereichsliste mit Zeiträumen, Status und Konflikten. Die breite Personenzeitachse ist optional scrollbar; sie wird nicht zur einzigen Bearbeitungsmöglichkeit. Ein Detailpanel wird zur gut bedienbaren Vollansicht. Aktionen bleiben mindestens 44 px hoch, und native Seitennavigation funktioniert.

Die Zeitachse braucht eine gleichwertige listen-/formularbasierte Bearbeitung. Tastaturauswahl bietet Fokus auf Person/Tag, Pfeile zum Wechsel des Tagesabschnitts, Shift für Bereichsauswahl, Enter zur Bestätigung und Escape zum Abbruch. Screenreader erhalten Person, Datum, Abschnitt und Status als Text. Fokus wird nach Dialogschluss sinnvoll zurückgegeben. Weder Farbe, Hover noch Drag-and-drop ist alleiniger Informationsträger.

Für die Abnahme gilt WCAG 2.2 AA als technisches Ziel, ohne pauschale Konformitätsbehauptung durch die Wahl einer Bibliothek. Geprüft werden Tastatur, Screenreader, 200/400-%-Zoom, hoher Kontrast, reduzierte Bewegung und reale Mobilgeräte.

## 10. Technische Grenzen der eigenen FullCalendar-Ansicht

Die Custom View verwendet FullCalendar für sichtbaren Datumsbereich, Navigation und Event Store. Eigener Code übernimmt Namensspalte, Tages-/Halbtagsprojektion, Gruppierung, Balkenlayout, Auswahl und fachliche Rückmeldungen. Er benötigt keine Premium-Resource-API. Daten und Berechtigungsangaben kommen durch einen Takt-Adapter.

Nur freigegebene Personen, Ereignisse und Besetzungsberichte werden übertragen. Ausgeblendete persönliche Spalten ersetzen keine serverseitige Filterung. Ändern ist standardmäßig ausgeschaltet und wird pro Person/Eintrag ausdrücklich angeboten. Auswahl- und Änderungsereignisse sind Vorschläge an den Server, keine direkten Statusänderungen. Zugriffe über CalDAV verwenden dieselben fachlichen Dienste.

Die Zeitachse behandelt reine Daten und Tageshälften ohne lokale Zeitstempel-Arithmetik. FullCalendar-Ganztagsenden bleiben exklusiv. Beim Übergang zur fachlichen API werden inklusive sichtbare Endtage und Tagesabschnitte ausdrücklich konvertiert. All-day-Ereignisse können mit gesonderten Halbtagsangaben angezeigt werden; beliebige Uhrzeitereignisse werden nicht still als Urlaub interpretiert.

Ansichtszustände bleiben instanzbezogen: Filter, Gruppen, Scrollposition und Auswahl dürfen nicht zwischen Benutzerkonten oder Kalenderinstanzen wandern. Ein erneuter Abruf darf keine alten Rechte wiederherstellen. Leere Daten, Ladefehler, abgebrochene Anfragen und Versionskonflikte erhalten eigene Zustände.

150 Personen und ein Jahr sind der Belastungstest. Monat und Fachbereich bleiben die Voreinstellung. DOM-Elemente werden nicht für jede Kombination aus Person und Halbtag angelegt; das Raster ist eine Hintergrunddarstellung. Bei späterer Virtualisierung darf ein Screenreader nicht auf unsichtbar abgeschnittene Einträge angewiesen sein. Vollständige Listen und Export bleiben gesondert erreichbar.

## 11. Umsetzungs- und Abnahmeplan

| Stufe | Lieferumfang | Nachweis |
| --- | --- | --- |
| A | Custom View mit Monats-/Quartals-/Jahresbereich, fixierten Namen, Gruppierung, Statusbalken, Halbtagsauswahl und Formularalternative | Isolierter Browservertrag gegen die tatsächlich gebündelte FullCalendar-Version; zwei Instanzen, Navigation, DST, Überlappungen, XSS, mobile Breite und Darkmode |
| B | Kalenderkern mit berechtigten Datenadaptern, Jahresterminen und freien Kalendern | Bestehende Kalenderlinks funktionieren; einheitliche Detail- und Freigabeabläufe |
| C | Durchgängige einfache Urlaubsplanung samt serverseitiger Konfliktvorschau | Mitarbeitende planen selbst; Bereichsplaner bearbeiten berechtigt; kein Fake-Genehmigungsstatus |
| D | Schließtage, Notbesetzung, interne/externe Abläufe und optionale Abwesenheitsübernahme | Parallelfälle und Änderungen ohne Lücke oder Doppelbuchung |
| E | CalDAV/ICS und schrittweise Migration der Fachkalender | Rechteentzug, Serien, Zeitzonen und vereinbarte Clientmatrix |

Stufe A ersetzt nicht B–E. Eine isolierte UI-Demonstration wird nicht als fertiges Urlaubsmodul veröffentlicht. Zuerst wird ein vollständiger einfacher Planungsablauf freigeschaltet, anschließend die zusätzlichen Betriebsarten.

Moderierter Test vor Einführung: Eine Mitarbeiterin zeichnet Urlaub ein, korrigiert einen Halbtag und erkennt den externen nächsten Schritt. Eine Leitung findet eine Unterbesetzung im Team und beim übergeordneten Bereich. Ein Planer ändert einen fremden Entwurf, kann aber keine externe Selbstauskunft bestätigen. Eine Person ohne Planungsrecht kann ihre Ansicht sicher lesen. Zusätzlich wird derselbe Ablauf per Tastatur und auf dem Smartphone geprüft.

Messbare Ziele: Datum/Status/Handlungsbedarf ohne Tooltip erkennbar; eigener Eintrag ohne Wechsel in Administration; Filter bleiben beim Ansichtswechsel erhalten; Serverkonflikte erhalten die Eingaben. Auf einem dokumentierten Referenzgerät sollen Fachbereichswechsel und Monatsnavigation nach vorhandenen Daten innerhalb einer Sekunde reagieren. Netzwerkzeit wird getrennt gemessen; bei Verzögerung bleibt die aktuelle Ansicht lesbar. Diese Ziele müssen im Prototyp gemessen werden und sind keine zugesagte Bibliotheksleistung.

## Quellen und Prüfstand

Herstellerangaben und Lizenzinformationen am 04.11.2026 geprüft. Versionsabhängige Details vor Einführung erneut gegen die konkret eingebundene Ausgabe prüfen.

- [FullCalendar Standard/Premium und Lizenzmodelle](https://fullcalendar.io/license).
- [FullCalendar 6: eigene JavaScript-Ansichten](https://legacy.fullcalendar.io/v6/custom-view-with-js).
- [FullCalendar 7: Änderungen der JavaScript-Schnittstelle](https://fullcalendar.io/docs/upgrading-from-v6-js).
- [FullCalendar: Tastatur und Screenreader](https://fullcalendar.io/docs/accessibility).
- [Mantine Schedule: MIT und Ansichten](https://mantine.dev/schedule/getting-started/); [Ressourcenansichten](https://mantine.dev/schedule/resources-schedule/).
- [EventCalendar: Ressourcenzeitachse und MIT-Lizenz](https://github.com/vkurko/calendar).
- [vis-timeline: Dokumentation](https://visjs.github.io/vis-timeline/docs/timeline/) und [MIT/Apache-2.0](https://github.com/visjs/vis-timeline/blob/master/LICENSE.md).

## 12. Integration bestehender Abwesenheiten und Vertretungen

Vor Umsetzung des Urlaubsworkflows wird die bestehende Abwesenheitsfunktion mit ihren tatsächlichen Zuständen, Vertretungszustimmungen, Zugriffsprüfungen, Benachrichtigungen und bereits gespeicherten Daten vollständig inventarisiert. Anhand realer Beispiele wird festgelegt, welche Felder eine fachlich wirksame Abwesenheit darstellen und welche ausschließlich die Berechtigung einer Vertretung betreffen. Bestehende Volltagsfälle dürfen durch die Erweiterung nicht verändert werden.

Ein verbindlicher Urlaubszeitraum erzeugt bei aktivierter Übernahme eine eindeutig dem Urlaub zugeordnete Abwesenheit. Die Übernahme ist wiederholbar und transaktional; erneute Anfragen erzeugen keine Duplikate. Ohne ausgewählte und berechtigte Vertretung entstehen keinerlei Vertretungsrechte. Ein halber Tag darf niemals eine ganztägige Stellvertretung freischalten. Sofern das bestehende Rechtemodell keine sicheren Teilzeitgrenzen unterstützt, wird die Vertretungsvergabe für diesen Fall gesperrt und der Grund verständlich angezeigt, bis die Zeitprüfung fachlich erweitert und getestet wurde.

Bei Änderungen bleibt die ursprüngliche wirksame Abwesenheit bis zum erfolgreichen Abschluss der neuen Prüfung erhalten. Bestätigung, Besetzungsprüfung, Beendigung/Anpassung der alten Abwesenheit, Neuanlage und Protokoll laufen atomar. Eine Stornierung benötigt einen zum jeweiligen Ablauf passenden Vorgang; das frühere externe System wird ohne Schnittstelle nicht als automatisch informiert dargestellt. Manuell erfasste Abwesenheiten werden nicht überschrieben oder gelöscht; Überschneidungen erscheinen als Konflikt zur bewussten Klärung. Dienstreise und Schulung können als wirksame Abwesenheit in der Besetzungsprüfung berücksichtigt werden, ohne dass sie in Urlaub oder Urlaubskonto umgedeutet werden.

Abnahmetests umfassen unter anderem: alten Volltagsvertretungsfall unverändert; Halbtagsurlaub ohne ganztägige Vertretung; keine Rechte bei fehlender Zustimmung; idempotente Doppelanfrage; Urlaubsänderung mit konkurrierender Besetzungsänderung; Abbruch/Rollback ohne Lücke; externe Selbstauskunft nur durch die betroffene Person; Storno mit manuell angelegter paralleler Abwesenheit; Datenschutz in Web, ICS und CalDAV; Rechteentzug bei bestehendem Client-Abo.

## 13. CalDAV-Einrichtung: bestätigte Entscheidungen

Nutzer richten persönliche, unverwaltete Geräte selbst ein. Jamf/MDM-Export, Verwaltungshilfen und automatische MDM-Verteilung entfallen auf ausdrücklichen Wunsch.

Pro Gerät wird ein eigener, einzeln widerrufbarer Zugang erzeugt. Er erweitert keine Personenrechte. Nutzer wählen die Kalender ausdrücklich aus; die Auswahl ist später in Takt änderbar. Lese-/Schreibfähigkeit wird zusätzlich durch Kalenderrechte und den Fachadapter begrenzt. Entzogene Personenrechte wirken auch für bereits eingerichtete Geräte.

Gerätezugänge gelten standardmäßig bis zum Widerruf. Die Administration kann eine Laufzeit vorgeben. Bei vorgegebenem Ablauf sind rechtzeitige Hinweise zur erneuten Einrichtung vorgesehen.

Auf ausdrücklichen Wunsch enthält das Apple-Konfigurationsprofil das neu erzeugte Gerätepasswort, damit Nutzer es nicht nochmals eingeben müssen. Es enthält niemals das Portalpasswort. Der Download erfolgt nur im authentifizierten, CSRF-geschützten Einrichtungsablauf über HTTPS, mit `Cache-Control: no-store`. Profil und Kennwort gehören nicht in URLs, Protokolle, E-Mails oder dauerhafte Profildateien auf dem Server. Der Server speichert nur den Prüfwert des Gerätepassworts. Bei erneuter Einrichtung wird ein neuer Zugang erzeugt, statt ein altes Passwort auszulesen.

Die XML-Profildatei ist durch das eingebettete Gerätepasswort selbst ein Zugangsmittel. Der Assistent kennzeichnet dies kurz und verständlich. Signierung und Verschlüsselung sind unterschiedliche Dinge: Eine Signatur würde das Passwort in der Datei nicht geheim halten. Apple empfiehlt Kennwörter nur in verschlüsselten Profilen; die ausdrücklich gewünschte einfache Selbstinstallation verwendet hier einen individuellen, eingeschränkt berechtigten und widerrufbaren Gerätezugang. [Apple CalDAV-Payload](https://developer.apple.com/de/documentation/devicemanagement/caldav), geprüft am 04.11.2026.
