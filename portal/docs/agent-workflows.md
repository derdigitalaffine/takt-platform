# Hotfix: rechte Agentenspalte und zuverlässige Formularvorschläge

Der globale Einstieg ist ein fester Button außerhalb des Headers. Er öffnet denselben
zentralen Agenten rechts; der Agent erscheint nicht mehr in der Menü-Navigation.
Auf schmalen Geräten füllt die Spalte den Bildschirm. Die Einbettung ist ausschließlich
innerhalb derselben Herkunft für `/agent` und den kompatiblen `/ki`-Einstieg erlaubt;
alle anderen bisherigen Framing-Grenzen bleiben bestehen. Fachvorschläge wechseln
in den Hauptbereich, nicht in eine verschachtelte Fachmaske.

Agenten-JSON-Endpunkte liefern auch bei `Accept: */*` strukturierte Fehler. Der Client
fordert JSON an und zeigt bei unerwartetem HTML eine verständliche Statusmeldung.
Kurze Nachrichten wie „ja“ sind gültige Gesprächsfortsetzungen und ersetzen keine
verbindliche Schreibbestätigung. `create_form` erzeugt nach Fachmaskenvorschau und
expliziter Bestätigung einen internen, geschlossenen Formularentwurf mit konkreten
Fragen. Kein öffentlicher Link, keine Einsendung und kein Antragsprozess entstehen.
Die freigegebenen einfachen Fragetypen werden mit dem vorhandenen Baukasten
normalisiert; komplexere Fragen können anschließend dort ergänzt werden.

## Weiterhin geltende Fachregeln

`/agent` ist der maßgebliche LLM-Chat. Navigation, Modulkarte und globaler Einstieg
führen dorthin. `/ki` und die bisherigen Chat-Endpunkte bleiben kompatible Aliase
für denselben Arbeitsplatz; es gibt keinen zweiten Seitenpanel-Chat mehr.
Modellwahl, persönliche Unterhaltungen, Export, sichere Markdown-Darstellung,
freigegebenes Wissen, optionale Websuche sowie Text-/Bildanalyse bleiben erhalten. Auch Modellwechsel, Gesprächsverzweigungen und temporäre Chats ohne gespeicherten Verlauf stehen im selben Arbeitsplatz bereit. Temporäre Chats bleiben reine Antworten ohne Fachaktionen oder Wissensabruf.

Die standardmäßig aktive Bedienunterstützung beantwortet Fragen und recherchiert
in berechtigten Fachbereichen. Für reine Text-/Bildanalyse steht im selben Chat
weiter der bisherige Antwortmodus mit Streaming zur Verfügung. Ein Bild wird nur
über die bestehende berechtigungsgeprüfte Bildanalyse verarbeitet. Interne Quellen
und Fachreferenzen im Verlauf werden vor Anzeige, Export **und erneuter Verwendung
als LLM-Kontext** mit den aktuellen Rechten geprüft.

| Bereich | Fachunterstützung |
| --- | --- |
| Aufgaben | Suchen; neue Aufgaben vorbereiten; Zuständigkeit, Priorität und zulässigen Status vorschlagen |
| Interne Anliegen | Eigene/zugewiesene/unzugewiesene Anliegen, Bestellungen, Kategorien und Folgestatus finden; Erfassung mit Routingvorschau; Zuweisung und Bearbeitung; Lieferant, Referenz und Lieferdatum |
| Anliegenverwaltung | Für Administratoren: nicht vertrauliche Kategorien, Aktivierung und Personen-/Leitungsrouting; bestehende aktive Zuständigkeiten nur bei ausdrücklichem Auftrag übernehmen |
| Geschützte Anliegen | Sensible Eingaben werden vor jedem LLM-/Verlaufsaufruf abgefangen und ausschließlich lokal im sitzungsgebundenen Server-Stash an das manuelle geschützte Formular übergeben. Kein Inhalt wird an das LLM oder den KI-Chatverlauf gesendet. |
| Urlaub | Eigene Anträge sowie explizit planbare/zu entscheidende Anträge suchen; eigenen Entwurf anlegen, berechtigt gefundenen Zeitraum ändern; Einreichung, Verbindlichmachen, Genehmigung/Ablehnung, Storno und Ausnahmen nach bestehenden Fachregeln |
| Krankmelder | Lokale Erkennung ohne LLM/Chatverlauf; eindeutige Angaben für ohne AU, AU, eAU oder Kind krank vorausfüllen; explizite Formularvorschau und Bestätigung; berechtigte Einzelbearbeitung per exaktem Aktenzeichen (Status, interne Notiz, Nachricht) |
| Kalender | Berechtigte Einzeltermine nach Titel, ID und Zeitraum suchen; zeitgebundene und ganztägige Einzeltermine erstellen, ändern oder ausdrücklich bestätigt löschen; Serien und Quellkalender bleiben im nativen Bereich |
| Formulare | Metadaten eigener/freigegebener Formulare finden; geschlossene Kopie ohne Antworten, Einladungen und öffentlichen Link; interne Grenze bleibt erhalten |
| Prozesse | Prozessnamen und Veröffentlichungsstatus mit passender Rolle finden; Weiterarbeit im verlinkten Facheditor |
| DMS | Nur explizit für KI freigegebene geeignete manuelle Wissensakten finden; in Bereiche mit aktuellem Schreibrecht verschieben; Aufbewahrung über bestehenden Fachservice |

DMS erfordert zusätzlich aktivierte Wissensnutzung, `ai_knowledge`, die aktuell konfigurierte Quellenfreigabe (Einzelauswahl oder administrative Sammlung mit Ausnahmen)
und Live-Bereichsrechte. Keine Bürger-, Personen-, Antrags- oder Buchungsakten,
Anhänge, Formularantworten oder Prozessdefinitionen gelangen über den Adapter an
die Planung. Geschützte Kategorien werden nicht über das LLM administriert.

## Übergabe an den Programmbereich

1. Bis zu sechs erlaubte Suchen liefern belegte IDs. Fehlende Angaben werden im
   Chat geklärt; bis zu vier Schreibschritte werden sparsam vorgeschlagen.
2. Der Agent bietet einen Link zum passenden Programmbereich mit vorausgefüllter
   echter Fachmaske an. Der bewusste Klick öffnet sie im Hauptfenster. Inhalte bleiben im Server-Stash; die URL enthält nur einen
   zufälligen, sitzungs-/nutzergebundenen Planbezug. Öffnen speichert nichts.
3. Die vom Werkzeug unterstützten Felder sind editierbar. Andere Felder sind für
   diesen Vorschlag gesperrt. Änderungen werden vor jeder Übernahme erneut anhand
   der aktuellen Fachservices, Rechte, Versionen und erlaubten Ziele normalisiert.
4. „Vorschlag prüfen“ zeigt die endgültigen Werte **nach** den manuellen Änderungen.
   Erst „Diesen Schritt verbindlich speichern“ schreibt, mit CSRF und einmaliger
   Bestätigung. Der Schritt verwendet bestehende Services und deren Fach-Audit;
   zusätzlich dokumentiert `agent_audit` Person, Werkzeug, Ziel-ID/-URL und Zeit.
5. Weitere Schritte öffnen anschließend nacheinander ihre eigene Fachmaske. Jeder
   Schritt ist eine eigene bestätigte Transaktion. Bereits gespeicherte Schritte
   bleiben bestehen, wenn später verworfen wird. Die Plan-ID rotiert nach jedem
   Speichern; alte Tabs oder alte Bestätigungen können keinen Schritt wiederholen.

Ein neuer Planversuch, eine neue Unterhaltung oder das ausdrückliche Verwerfen
entwertet offene Vorschläge. Bei geänderten Daten/Rechten ist ein neuer Plan nötig.
Die kompatible API `/agent/execute` bestätigt unveränderte vollständige Pläne weiter
atomar; nach einer manuellen Fachmaskenbearbeitung ist ausschließlich deren neue
Einzelbestätigung gültig. Der bestehende kurzlebige prozesslokale Server-Stash
bleibt eine PoC-Grenze; horizontale Ausführung benötigt einen gemeinsamen atomaren
Bestätigungsspeicher.

Es gibt keine Browser-Fernsteuerung, frei wählbaren Tool-URLs, Codeausführung,
autonome Veröffentlichung, Löschung, Genehmigung, Ressourcenbuchung oder Änderung
einer Terminserie. Eine administrative Kategorie-Routingänderung übernimmt dieselben
Fachgrenzen wie die native Verwaltung (maximal 300 Vorgänge je Fachlauf).

## Einzeltermine

Zeitgebundene Termine benötigen ISO-Zeitpunkte mit explizitem Offset; ganztägige
Termine verwenden im Vorschlag und Fachformular ein einschließliches Enddatum.
Der vorhandene Kalenderdienst speichert das exklusive Kalender-Ende. Änderungen
übernehmen nicht geänderte Titel, Beschreibungen, Orte und Zielgruppen exakt.
Vorschau und Bestätigung benennen vorherigen und neuen Zeitraum; beim Löschen
stehen der konkrete Termin und die endgültige Entfernung ausdrücklich im Vorschlag.
Der native Kalender und der Agent verwenden denselben Löschdienst mit Kalender-Audit.

Nur tatsächlich lesbare, beschreibbare Einzeltermine in freien Kalendern sind
bearbeitbar. Datensatz-/Kalenderstand und aktuelle Rechte werden beim Speichern
unter der Organisationssperre erneut geprüft. Serienänderungen und Serienlöschung
werden im Agenten abgelehnt; Quellkalender behalten ihre eigenen Fachabläufe.
Ein fehlender oder bei der Zeitumstellung mehrdeutiger Zeitpunkt wird nicht still
umgerechnet. Ein bereits explizit geplanter Offset bleibt bei unveränderten
Fachmaskenwerten erhalten. Einladungen, Besprechungsräume und Ressourcenbuchungen
sind eigene Fachabläufe und werden nicht als freie Kalendertermine ausgegeben.

## Geschützter Krankmelder

Krankmeldeanfragen werden vor Provider-, Wissens- und Gesprächsverarbeitung lokal
abgefangen. Originaltexte und medizinische Daten werden nicht in den KI-Verlauf
übernommen. Ältere Gesundheitsturns aus dem bisherigen Chat werden nicht erneut als
Modellkontext verwendet. Ein reiner Text-/Bildanalysemodus bleibt eine gesonderte,
bewusst gewählte Funktion; die automatische Bedienunterstützung nutzt diese
lokale Krankmeldergrenze.

Der Adapter übernimmt nur eindeutig benannte vollständige Datumsangaben bzw.
explizite relative Tage und erfindet keine Feststellungsdaten, Versicherungsart,
Bescheinigung oder Kinderdaten. Bei unklarem Meldeweg führt ein Link zur nativen
Auswahl. Die einfache Meldung gilt weiterhin nur für heute an Werktagen. Persönliche
Stammdaten kommen wie bisher aus dem angemeldeten Konto; Arbeitgeber wird nur bei
eindeutiger Auswahl vorgeschlagen. Fehlendes ergänzt die Person in der Fachmaske.

Die Fachmaske erstellt zunächst eine sichtbare Vorschau einschließlich ausgewählter
Datei; jede Änderung verwirft die Bestätigung. Erst das ausdrückliche Bestätigungsfeld
und Absenden erstellen die Meldung über den bestehenden Krankmelder samt Prüfung,
verschlüsselter Ablage, Nachweisverarbeitung und Benachrichtigungen. Einmalige,
sitzungsgebundene Vorschläge werden serverseitig aufbewahrt. Auch Fehlereingaben
bleiben im Server-Stash statt im signierten Sitzungscookie. Alte Tabs, neue Pläne,
Zurücksetzen oder neue Unterhaltungen entwerten offene Vorschläge. Die bestehende
begrenzte prozesslokale Stash-Lebensdauer gilt auch hier.

Zur Bearbeitung muss das genaue Aktenzeichen einer einzelnen Krankmeldung genannt
werden. Aktuelle Arbeitgeberzuständigkeit wird vor Suche, Vorschau und Speicherung
geprüft. Statusnamen müssen eindeutig sein; Notiz und Nachricht benötigen einen
expliziten Doppelpunkt mit dem gewünschten Text. Nachrichten werden als öffentliche
Statusseiten-Nachrichten mit möglichem E-Mail-Versand ausgewiesen; interne Notizen
bleiben intern. Die Vorschläge nutzen dieselben nativen Formulare mit erneuter
Bestätigung. Datensatzänderungen und Rechteentzug entwerten die Freigabe.
Krankmelder-Zugriffsprotokoll und Agenten-Schreibaudit halten die Operationen fest,
ohne Diagnosen, Dateien oder Statuslink-Geheimnisse ins Agenten-Audit zu schreiben.
Export, Massenbearbeitung und Löschung bleiben native manuelle Funktionen.

## Urlaubsabläufe

`create_leave` plant ausschließlich den eigenen Urlaub, `edit_leave` bindet einen
zuvor berechtigt gefundenen Antrag. Bei einer Änderung bleibt der bisher wirksame
Urlaub bis zur erneuten Entscheidung bestehen. `leave_command` akzeptiert nur die
konkret angebotenen Operationen; im Fachformular ist dafür nur die Begründung
änderbar. Die Person und die Operation sind durch den serverseitigen Plan gebunden.
Die zusätzliche Suche `search_leave_requests` unterscheidet eigene Anträge,
planbare Vorgänge und offene Entscheidungen. Ein gewöhnlicher Kollegenzugriff auf
die Zeitachse berechtigt nicht zum Abruf von Urlaubsdetails im Agenten.

Einreichung, Genehmigungsstufen, Vier-Augen-Prinzip, externe persönliche
Selbstauskunft, Storno, Konten und Besetzung werden vom bestehenden Urlaubsservice
geprüft. Vor der Vorschau wird ein Entscheidungsbefehl in einem zurückgerollten
Savepoint validiert: keine dauerhaften Status-, Audit-, Postfach-, Outbox- oder
Abwesenheitsänderungen. Beim Speichern prüft der Service alles erneut; eine
geänderte Version, Hauptzuordnung oder Verfahrenskonfiguration entwertet den
Vorschlag. Die endgültige Genehmigung erfordert stets die menschliche Bestätigung.
Neue Entwürfe werden nicht stillschweigend eingereicht oder genehmigt; ein weiterer
Schritt findet den gespeicherten Antrag erneut, statt eine noch nicht vorhandene
ID zu erfinden. Administrative Löschung bleibt im gesonderten manuellen Ablauf.

## Administrative Korrektur von Urlaubsabwesenheiten

Administratoren können im Urlaubsplaner einen eingetragenen Urlaub oder eine
unabhängige manuelle Abwesenheit über „… löschen“ öffnen. Die Vorschau nennt Person,
Zeitraum und Auswirkungen; Begründung und Bestätigungsfeld sind Pflicht. Beim
Speichern werden Administratorrecht, CSRF und der gelesene Datenstand erneut
geprüft. Aktiver Urlaub, seine eigene Abwesenheitskopie und die wirksame
Urlaubskontoanrechnung werden aufgehoben; fremde Zeiträume bleiben erhalten.

Der Urlaub bleibt ausschließlich als stornierter Nachweis mit `admin_delete`-Audit
und zusätzlichem `leave_admin_removals`-Korrekturprotokoll erhalten. Er erscheint
nicht mehr in aktiven Listen oder Kalenderdaten und kann nicht über normale
Urlaubsbefehle wieder aktiviert werden. Manuelle Abwesenheiten werden mit eigenem
Korrekturprotokoll entfernt. Das funktioniert auch nach einem Organisationswechsel;
die normale Genehmigung und ihre Vier-Augen-Regeln werden nicht verändert. Diese
administrative Löschung erfolgt bewusst manuell, nicht durch ein LLM-Werkzeug.

## Prüfung

Die Agenten-/KI-/Urlaubstests prüfen Rollen, Datensätze, CSRF, Sitzungsbindung,
Rechteentzug, geänderte Daten, Routing, bearbeitete Vorschauen, Wiederholungsschutz,
Verlaufsrechte und administrative Entfernung samt Abwesenheitskopie und Audit.
`python tests/browser/agent_ui_smoke.py` prüft mit deterministischem Provider alle
umgesetzten Fachübergaben, aufeinanderfolgende Bestätigungen, geschützte Erfassung,
Chatverlauf, mobile Ansichten und die administrative Urlaubskorrektur. Die Prüfung
läuft in der Portal-CI; kein echter LLM-Dienst und keine Produktionsdaten werden
in den Tests verwendet.
