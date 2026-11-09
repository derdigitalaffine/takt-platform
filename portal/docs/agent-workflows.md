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
| Kalender | Zugängliche Kalender und gespeicherte Terminmetadaten finden; Einzeltermin in beschreibbarem freien Kalender mit expliziter Zeitzone vorbereiten |
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
2. Der Agent öffnet unmittelbar den passenden Programmbereich mit vorausgefüllter
   echter Fachmaske. Inhalte bleiben im Server-Stash; die URL enthält nur einen
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
