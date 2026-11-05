# Kalender, Organisation und Urlaubsplanung – Interviewstand 04.11.2026

Dieses Dokument bewahrt die fachlichen Anforderungen aus dem Workshop-Interview vom 04.11.2026. Die Umsetzung aus [PR #182](https://github.com/derdigitalaffine/takt-platform/pull/182) (Organisation) und [PR #184](https://github.com/derdigitalaffine/takt-platform/pull/184) (Kalender/Urlaub) ist seit 05.11.2026 in `main` enthalten. Dies bleibt das **Anforderungs- und Entscheidungsprotokoll**, nicht die Betriebsanleitung: tatsächliche Implementierung, Teststand und Grenzen stehen in der [Abnahmeübersicht](kalender-urlaub-umsetzungsstand.md) sowie im [Admin-Handbuch](ADMIN-HANDBUCH.md#kalender--urlaubsplanung-konfigurieren).

## Verbindlich vereinbarte Anforderungen

1. Dynamische Organisationshierarchie: VG und Ortsgemeinden mit eigenen Unterstrukturen; parallel Verwaltung, Abteilungen, Fachbereiche, Sachgebiete, Teams und Arbeitsbereiche. Ebenentypen und Tiefe sind konfigurierbar.
2. Personen haben eine Hauptzuordnung und zusätzliche Zuordnungen. Besetzungsrelevanz wird je Zuordnung ausdrücklich festgelegt; Hauptzuordnung zählt standardmäßig, zusätzliche standardmäßig nicht. Im erweiterten Modell sind Einsatzanteile zu berücksichtigen. Auf übergeordneten Ebenen keine Doppelzählung derselben Person.
3. Je Einheit Mindestbesetzung nach Personenzahl, Arbeitskapazität oder beidem. Einfacher Modus zählt Personen ohne Arbeitszeit-/Teilzeitgewichtung. Erweiterter Modus verwendet individuelle, zeitlich gültige Wochenpläne, Arbeitszeiten und Einsätze. Die Kapazitätsformel und ihr Bezugsintervall müssen an konkreten Vollzeit-/Teilzeitbeispielen eindeutig spezifiziert werden; Beschäftigungsanteil und Arbeitszeit dürfen nicht doppelt gewichtet werden.
4. Je Besetzungsregel Warnung oder verbindliche Sperre. Warnungen können berechtigte Genehmiger mit protokollierter Begründung übergehen. Regeln aller betroffenen Einheiten einschließlich übergeordneter Ebenen prüfen.
5. Genehmigungsweg je Einheit konfigurierbar: ohne Genehmigung, einstufig, mehrstufig. Leitungen dürfen Einstellungen nur bei ausdrücklich delegiertem Konfigurationsrecht ändern. Bei Mehrfachzugehörigkeit entscheidet der Weg der Hauptzuordnung; andere betroffene Leitungen erhalten Konflikthinweise.
6. Ohne Genehmigung sind zwei klar erklärte Varianten wählbar: Sperrverletzung verhindert verbindliche Eintragung oder nur bei Sperrverletzung ist eine geregelte Ausnahmegenehmigung nötig. Keine stillschweigende Umgehung.
7. Zusätzlich reiner Planungsmodus: Urlaub einfach eintragen, ohne Genehmigungsworkflow oder externen Bestätigungsschritt. Er unterstützt gemeinsam erstellte Bereichspläne. Die ausdrückliche Markierung „verbindlich“ bleibt für eine optionale Abwesenheitsübernahme möglich.
8. Unverbindliche Wünsche und offene Anträge sind Vorschaukonflikte, keine Kapazitätsreservierungen. Erst beim Verbindlichmachen gegen den aktuellen Stand prüfen und atomar buchen.
9. Eigene Einträge durch Mitarbeitende, fremde Einträge durch zuständige Leitungen und explizit benannte Bereichsplaner. Planungsrechte sind von Genehmigungen, Konfiguration und externen Selbstauskünften getrennt.
10. Mitarbeitende sehen im freigegebenen Bereich Namen, Zeiträume und Planungsstand. Kommentare, Begründungen und sensible Abwesenheitsgründe sind gesondert geschützt. Dies gilt in Weboberfläche, JSON, CalDAV und ICS gleichermaßen.
11. Urlaub in ganzen und halben Tagen; Vormittag/Nachmittag passend zum Arbeitsmodell. Keine beliebigen Urlaubsstunden für die erste Fassung.
12. Für die konkrete Instanz führt eine externe ZE-Software Arbeitszeit- und Urlaubskonten sowie die dortige Genehmigung. Keine Schnittstelle geplant. Takt darf keine Resturlaubsanzeige erfinden und keinen Status aus der externen ZE-Software als verifiziert behaupten.
13. Allgemeine Einstellung zur externen Kontenverwaltung. Optional internes Urlaubskonto mit Anspruch, Übertrag und Resturlaub für andere Installationen. Kontenverwaltung, Planungsgenauigkeit und Genehmigungsweg sind voneinander unabhängige Einstellungen mit verständlichen Voreinstellungen.
14. Parallelbetrieb: konfigurierbarer Link zur externen ZE-Software, kopierbare Angaben, Aufgaben/Erinnerungen für noch extern zu erledigende Schritte. Mitarbeitende bestätigen externe Genehmigung selbst; sichtbar als „Extern genehmigt – Selbstauskunft“, mit Person und Zeitpunkt protokolliert. Geänderter Zeitraum erfordert neue Auskunft.
15. Einzelne oder mehrtägige Schließzeiten mit Urlaubspflicht sind eigene Regelobjekte, keine Feiertage. Betroffene Organisationseinheiten/Unterbereiche und Ausnahmen auswählen. Automatische Vormerkung je Person als noch erforderliche Planung, ohne bereits genehmigten Urlaub doppelt zu erzeugen. Im reinen Planungsmodus keine künstliche Antragspflicht.
16. Notbesetzung ausnehmen. Je Bereich Einteilung durch Leitung oder direkte Selbsteintragung. Erforderliche Besetzung und Konflikte sichtbar; abweichende Regeln für Schließzeiten ausdrücklich festlegen.
17. Abwesenheiten: automatische Übernahme je Bereich zuschaltbar; nach interner Genehmigung, externer Selbstauskunft oder im reinen Planungsmodus nach „verbindlich“. Ein Urlaubseintrag allein gewährt keine Vertretungsrechte.
18. Bereits verbindlicher Urlaub bleibt wirksam, bis eine Änderung geprüft und passend zum Ablauf bestätigt wurde. Erst dann Urlaub und Abwesenheit gemeinsam umstellen, keine Lücke oder Doppelübernahme.
19. Verbindlicher Urlaub und alle wirksamen Abwesenheiten reduzieren Besetzung. Kalendertermine allein tun dies nicht.
20. Zentrales, wiederverwendbares Modul „Kalender“ mit gemeinsamen Darstellungs-, Rechte-, Serien-, Zeitzonen-, Export- und Schnittstellenfunktionen. Bestehende Fachkalender schrittweise auf gemeinsame Adapter umstellen; Fachmodule behalten ihre Geschäftsregeln.
21. Jahrestermine sind rein informativ, keine Anwesenheitspflicht oder Urlaubssperre. Wirkung auf Besetzung ausschließlich über eigene Regeln/Schließtage.
22. Zielgruppe eines Jahrestermins standardmäßig gewählte Einheit einschließlich Untereinheiten; ausdrücklich einschränkbar.
23. Persönliche sowie geteilte Team-/Projektkalender. Anlegen/Teilen berechtigungsabhängig; öffentliches Veröffentlichen eigenes Recht. Freigaben: intern, öffentlich, einzelne Benutzer und Gruppen sowie organisatorische Zielgruppen.
24. CalDAV lesend/schreibend, ICS lesend abonnierbar, mit denselben serverseitigen Rechten. Schreibfähigkeit je Kalenderart freischalten. Fachänderungen durchlaufen dieselben Prüfungen wie in Takt; nötige weitere Schritte in Takt fortsetzen. Keine stille Bestätigung einer abgelehnten oder nur teilweise möglichen Änderung.
25. Zielclients: alle Outlook-Varianten, Android, Apple auf iOS, Thunderbird. Zusatzkomponenten zulässig. Wo kein Schreibzugriff möglich ist: ICS lesen, in Takt bearbeiten. Keine pauschale native CalDAV-Zusage für sämtliche Outlook-Versionen.
26. Relevante Vorgänge verbindlich im Takt-Eingang; E-Mail ergänzend einstellbar, sofort oder gesammelt.
27. Größenordnung: etwa 150 Personen insgesamt, 20–30 je Fachbereich.

## Bedienkonzept

Das ausführliche [UI- und Umsetzungskonzept](kalender-urlaub-ui.md) konkretisiert die folgenden Leitlinien. Technologiewahl: FullCalendar Standard bleibt die Basis; eine eigene Takt-Custom-View bildet die Personenzeitachse ab. Keine Premium- oder zweite Kalenderbibliothek.

Ein Kalenderbereich mit auswählbaren überlagerten Kalendern, Suche, Tages-/Wochen-/Monats-/Jahresansichten und verständlichen Freigaben. Urlaubsplanung als Bereichsansicht mit fixierter Namensspalte, gruppierbaren Organisationseinheiten, Monats-/Quartals-/Jahreszoom, Arbeits-/Feiertagen und halben Tagen. Zeitraum zeichnen, Vorschau mit Konflikten, bewusste Übernahme. Gleichwertige Datums-/Tastatureingabe ohne Ziehen. Mobil fokussierte Zeiträume und Personen statt unbedienbarer verkleinerter Jahrestabelle. Status nie ausschließlich über Farben darstellen.

Konfiguration über einfache Voreinstellungen und bei Bedarf Detailregeln; geerbte Einstellungen und tatsächliche Auswirkungen ausdrücklich anzeigen. Kein unübersichtlicher Schalterwald. Rollen und Personenverwaltung verwenden die gemeinsamen Takt-Komponenten.

## Technische Leitplanken und Ausgangslage vor der Implementierung

- `Organization`/`orgs.py`: bestehender Baum mit festen Typen, bereits in Ressourcen, Krankmelder, Rechtstexten und Anträgen referenziert. Bestehende IDs und Fachzuordnungen erhalten. Gruppen und Organisationszugehörigkeit erfüllen unterschiedliche Zwecke und werden nicht ungefragt gegenseitig synchronisiert.
- `User.permissions`: globale Einzelrechte; bisher keine allgemein definierbare globale Rollentabelle. Neue Bereichsrollen benötigen einen eigenen, zentral geprüften Geltungsbereich und dürfen nicht zu globalen Rechten werden.
- `Absence`/`absence.py`: bisher tagesgenau, Vertretungszustimmung kann Abwesenheitsstatus beeinflussen. Für Halbtage und den neuen Ablauf müssen tatsächliche Abwesenheit, Urlaubsentscheidung und Vertretungszustimmung sauber getrennt werden. Halbtagsurlaub darf keine ganztägigen Vertretungsrechte auslösen.
- Vor PR #184 vorhandene ICS-Pfade: Meetings/RSVP, Seminarteilnahmen, Ressourcenbuchungen und Belegungsabos, Terminbuchungsabos, festgelegte Terminumfragen. Aufgaben haben zusätzlich Kalenderdarstellungen. `ics.py`, `resources.ics`, `bookings.to_ics` waren getrennte Erzeuger; ein gemeinsamer CalDAV-Server bestand **zu diesem Zeitpunkt** nicht. Der integrierte Stand ist in der [Abnahmeübersicht](kalender-urlaub-umsetzungsstand.md) beschrieben.
- Fachobjekte bleiben führend. Kalender stellt sie über Adapter dar, statt alle Fachmodelle durch kopierte Termine zu ersetzen. Freie Termine werden im Kalenderkern gespeichert.
- Neue Tabellen und versionierte Migrationen für Mitgliedschaften, Bereichsrollen, Kalender, Freigaben, Urlaubsplanung, Regeln und Protokollierung. Keine unstrukturierten JSON-Listen für sicherheitskritische Berechtigungen.
- Serverseitige Prüfungen vor jeder Abfrage/Mutation/Exportausgabe, einschließlich Suchtreffern, Zählern, Discovery, Batch-Reports und Synchronisation. Rollenrechte entziehen wirkt bei folgenden Anfragen; keine globale nutzerübergreifende Rechte-Caches.
- Verbindlichmachen, Besetzungsprüfung, Quotenbuchung und Abwesenheitsübernahme transaktional; gleichzeitige Anträge dürfen keine Kapazität doppelt vergeben. Versionen/ETags verhindern Überschreiben neuerer Daten. Wiederholte Requests dürfen keine doppelten Abwesenheiten, Kontobuchungen oder Nachrichten erzeugen.
- Bereichsrollen via Gruppen erfordern Schutz bestehender Benutzer-/Gruppenänderungen gegen indirekte Rechteausweitung, einschließlich CSV-Import. Kein Selbstgewähren zusätzlicher Rollen oder Ausweiten auf andere Hierarchieäste.
- ICS-Abos erhalten getrennte widerrufbare, zweckgebundene Lesetokens; öffentlich ist eine bewusste Freigabe, nicht ein Kalender mit erratbarer URL. CalDAV erhält begrenzte Client-Zugänge, sichere Parser, Größen-/Zeitlimits und nachvollziehbare Änderungsprotokolle. Widerruf verhindert zukünftige Abrufe; bereits beim Client gespeicherte Daten kann Takt nicht zurückholen.
- Ganztägige Einträge, Zeitzonen/Sommerzeit, Serien und Ausnahmen, UIDs, Löschungen und Wiederholungen standardkonform behandeln. Bei Fachkalendern festlegen, welche Clientfelder beschreibbar sind; unbekannte Felder dürfen keine Freigaben oder Statusentscheidungen überschreiben.

## Umsetzung und Abnahme

1. Organisationshierarchie, Zuordnungen und zentrale Bereichsrechte mit sicherer Benutzer-/Gruppenintegration.
2. Kalenderkern und Rechte, Jahrestermine und freie Kalender, gemeinsame UI-Komponenten.
3. Migration vorhandener Kalenderadapter und bestehender Links, sichere ICS-Abos.
4. Besetzungs-/Arbeitsmodelle, Schließtage und Notbesetzung; einfache Planung zuerst durchgängig nutzbar machen.
5. Genehmigungsvarianten, Parallelbetrieb mit externer ZE-Software, optionales Urlaubskonto und idempotente Abwesenheitsübernahme.
6. CalDAV und Clientmatrix, modulweise Schreibfreigaben; kein pauschales Freischalten unfertiger Fachadapter.

Diese Reihenfolge war der technische Umsetzungsplan des Interviews. Die in #182 und #184 abgeschlossenen Arbeiten sind inzwischen gemergt; das Kalender-/Urlaubsmodul wird trotzdem zunächst **deaktiviert** ausgeliefert und muss durch die Administration freigeschaltet werden. Client-Matrix und Betriebseinschränkungen bleiben in der [Abnahmeübersicht](kalender-urlaub-umsetzungsstand.md) ausgewiesen.

Pflichttests: Rechte über alle Hierarchieebenen und Gruppen, Haupt-/Zusatzzuordnungen, keine Doppelzählung, Tages-/Halbtags-/Teilzeitfälle, Schließtag mit Notbesetzung, mehrere gleichzeitig verbindlich werdende Anträge, veraltete Daten, Änderungen ohne Lücken/Duplikate, externe Selbstauskunft, datenschutzgerechte Kalenderprojektionen, CalDAV-/ICS-Clientmatrix, Rechteentzug, Serien/DST und vollständige bestehende CI. Browserprüfung mit 30 Personen je Fachbereich, Maus/Tastatur/Touch, Hell/Dunkel und konfiguriertem Branding. Vor Einsatz moderierter Test mit Mitarbeitenden und Leitung.

## Referenzen

- https://www.rfc-editor.org/rfc/rfc4791.html – CalDAV und ETags.
- https://www.rfc-editor.org/rfc/rfc5545.html – iCalendar, Ganztag, Serien und Zeitzonen.
- https://www.rfc-editor.org/rfc/rfc6578.html – WebDAV-Synchronisation.
- https://support.microsoft.com/en-us/outlook/sync-your-icloud-calendar-with-outlook-for-mac – Einschränkungen der nativen CalDAV-Unterstützung.
- https://manual.davx5.com/introduction.html – Android-Synchronisationskomponente.
