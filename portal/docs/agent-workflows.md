# TAKT Agent: freigegebene Modulabläufe

Der globale Agent benötigt ein aktives KI-Modul, `ai_chat` und mindestens einen
freigeschalteten Bereich. Er nutzt ausschließlich fest registrierte Fachservices.
Es gibt keinen Browser-Fernzugriff, keine frei wählbaren URLs und keine Codeausführung.

| Bereich | Lesen | Nach ausdrücklicher Freigabe schreiben |
| --- | --- | --- |
| Aufgaben | Sichtbare Aufgaben, Personen | Erstellen, zuweisen, Priorität und zulässigen Status ändern |
| Interne Anliegen / Bestellungen | Sichtbare nicht vertrauliche Anliegen, erlaubte Folgestatus | Erstellen mit Routingvorschau, zuweisen, Status ändern; Lieferant, Bestellreferenz und Lieferdatum bei Bestellungen |
| Kalender | Zugängliche Kalender und gespeicherte Einzel-/Serientermin-Metadaten mit Ereignisrechten | Einzeltermin in beschreibbarem freien Kalender anlegen, mit Beginn/Ende und expliziter Zeitzone |
| Formulare | Metadaten eigener bzw. freigegebener Formulare, mit `forms`-Rolle | Geschlossene Kopie ohne Antworten, Einladungen oder öffentlichen Link; interne Grenze bleibt erhalten |
| Prozesse | Prozessnamen und Veröffentlichungsstatus mit `processes`-Rolle | Weiterarbeit über den verlinkten Facheditor |
| DMS | Nur explizit für KI freigegebene, weiterhin geeignete manuelle Wissensakten; beschreibbare Zielbereiche | Akte zwischen Bereichen mit Schreibrecht verschieben, Aufbewahrung über den bestehenden Fachservice |

DMS setzt zusätzlich `ai_knowledge`, aktivierte Wissensnutzung und Live-Bereichsrechte
voraus. Keine Formularantworten, Anhänge, Bürger-/Personenakten oder Buchungsakten
werden über diesen Adapter an den Provider übergeben. Prozessdefinitionen und
Formularschemas werden ebenfalls nicht an die Planung übertragen.

## Beispielabläufe

- „Suche meine Kalender. Plane eine Besprechung am 12.11.2026 von 9 bis 10 Uhr
  in Berlin im Projektkalender und erstelle eine Aufgabe zur Vorbereitung.“
- „Suche das Formular Raumanfrage und bereite eine geschlossene Kopie vor.“
- „Suche die freigegebene Wissensakte Projektwissen und verschiebe sie nach Projektablage.“
- „Setze meine Bestellung auf bestellt, Lieferant Büro GmbH, Referenz BEST-42,
  erwartete Lieferung 20.11.2026.“

Bis zu sechs lesende Suchen liefern belegte IDs. Höchstens vier Schreibschritte
werden als geordneter Plan mit vollständigen zu speichernden Texten und Zielen
vorgeschlagen. Unklare Angaben führen zu einer Rückfrage. Die letzten drei
Benutzereingaben bleiben kurzzeitig serverseitig als Kontext, keine Suchresultate
oder früheren Befehle als ausführbare Berechtigung. Vor jedem neuen Plan werden
Datensätze erneut gesucht. „Neu beginnen“ löscht Kontext und offene Bestätigung.

Schreibpläne bleiben ausschließlich serverseitig, sitzungs-/nutzergebunden,
kurzlebig und einmalig. Ein neuer Planversuch entwertet den alten auch bei Fehlern.
Alle Endpunkte verlangen CSRF. Bei Bestätigung werden Modul-/Rollenrechte,
Datensatzrechte, Versionen, DMS-Freigaben, Zielbereiche und Routing erneut geprüft.
Ein Fehler rollt den gesamten Plan einschließlich Fach-Audit zurück. Erfolgreiche
Schritte erscheinen zusätzlich in `agent_audit` (Person, Werkzeug, Ziel-ID/-URL,
Zeitpunkt; keine Prompt- oder Inhaltskopien).

Es gibt keine automatische Veröffentlichung, Löschung, Genehmigung,
Ressourcenbuchung, Einladungsmail oder Änderung einer Terminserie. Abhängigkeiten
auf noch nicht angelegte IDs benötigen einen weiteren bestätigten Plan. Kalender
mit Fachquellen behalten ihre eigenen Abläufe. Der bestehende kurzlebige
Server-Stash bleibt für einen einzelnen Serverprozess ausgelegt; für horizontalen
Betrieb ist ein gemeinsamer atomarer Bestätigungsspeicher erforderlich.

## Prüfung

`pytest -q tests/test_agent.py tests/test_agent_modules.py` prüft Bestätigung,
Wiederholungsschutz, CSRF, Sitzungsbindung, Daten-/Rechterevokation, DMS-Opt-in,
Bestellregeln und transaktionale Rücknahme. `python tests/browser/agent_ui_smoke.py`
prüft den realen Ablauf mit deterministischem Provider, Links, Freigabe, Verwerfen,
Neustart, Tastatur und mobiler Ansicht. Beide laufen in der Portal-CI.
