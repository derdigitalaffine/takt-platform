# TAKT – Prozess-Hub & einheitliche Aufgabenübersicht (#292)

## Zweck und sichere Standardwerte

Die Verbindung von internen Anliegen und Prozessen ist optional und über
`anliegen_process_integration_enabled` standardmäßig **deaktiviert**.
Bestehende Anliegen, Formularanträge, native Aufgaben, Prozessrevisionen
und Daten bleiben nach diesem Inkrement unverändert.

Das Anliegen bleibt zentraler Vorgang. Eigenständige
`AnliegenProcessTask`-Objekte bleiben **einzige verbindliche Quelle**
für offene Prozessschritte; die Oberfläche erstellt **keine** zusätzlichen
normalen TAKT-Aufgaben.

## Prozess-Hub

Die Detailseite `/anliegen/{id}#anliegen-processes` zeigt:

- Anzahl laufender, freizugebender, blockierter und beendeter Prozesse.
- Je Prozess die unveränderliche veröffentlichte Version, ungefähren
  Fortschritt (erledigte/übersprungene Schritt-IDs), offenen Aufgaben,
  nächste Schritte und die früheste Frist.
- Direkte Bearbeitung von Arbeitsschritten und Genehmigungen nur für
  Personen mit expliziter Prozessbearbeitungsberechtigung plus
  tatsächlicher Objekt- und Organisationszuständigkeit.
- Optionaler Link zur vollständigen Prozessdefinition **nur** für
  Personen mit dem bereits bestehenden Prozesseditorrecht.
- Kombinierte Chronik aus Anliegenereignissen, dokumentierten
  Prozesszustandswechseln, vorhandenen Kommentaren und intern
  verschlüsselten Begründungen. Die Timeline wird **vor** dem Rendern
  rollen- und objektbezogen gefiltert.
- Referenzen auf bereits vorhandene Dateien der **verknüpften nativen
  Anliegen-Aufgabe**, sofern deren eigenes Berechtigungsmodell die
  Datei zulässt. Existenzprüfung beim Anzeigen, erneute Autorisierung
  im originären Task-/DMS-Dateiendpunkt. Es werden keine Dateikopien
  oder zusätzlichen Download-Routen erzeugt.

## „Meine Aufgaben“

Für berechtigte Prozessbearbeitende werden offene Prozessschritte
über `task_overview.collect` als eigene Quelle
`anliegen_process` eingeblendet und direkt mit
`#prozess-schritt-{id}` verknüpft.

Wird für denselben Nutzer und dieselbe Anliegen-ID bereits ein offener
Prozessschritt angezeigt, wird die übergeordnete native Anliegen-Aufgabe
**nur in der zusammengeführten Aufgabenansicht** ausgeblendet.
Sie wird weder gelöscht noch auf „erledigt“ gesetzt. Für andere
Personen ohne zulässigen Prozessschritt ändert sich die bestehende
Aufgabenansicht nicht.

Eine Gruppe wird als Gruppenaufgabe angezeigt; Vertretungen werden
durch die vorhandenen `absence.acting_ids` und
`acting_group_ids` aufgelöst. Dieselben Rechte gelten auch für die
serverseitige Aktion. Das gemeinsame Dashboard erzeugt keine
duplizierten Reminder/Benachrichtigungen.

## Status und Abschluss

Je Prozessversion werden die bei Freigabe aktiven Regelrevisionen
beibehalten. `completion_state` kombiniert die
Abschlussregel der verknüpften Läufe:

- `manual`: Keine automatische Erledigung.
- `all_success`: Alle verknüpften Läufe müssen erfolgreich beendet sein.
- `any_success`: Mindestens einer muss erfolgreich beendet sein.
- Falls `all_success` und `any_success` gemischt vorliegen,
  gewinnt die strengere `all_success`-Regel.

Ein Abschluss erfolgt **nur** über `anliegen.update_status` und nur
dann, wenn dieser Statuswechsel fachlich zulässig ist. Bei erfüllter
Bedingung geschieht dies nach dem letzten autorisierten
Arbeitsschritt; alternativ kann eine berechtigte Person explizit
„Abschluss übernehmen“ wählen. Laufende Prozesse werden dadurch
nicht stillschweigend gelöscht.

Wer ein Anliegen trotz nicht erfolgreich abgeschlossener Prozesse
manuell auf `done` oder `closed` setzen möchte, benötigt eine
Begründung (10–1000 Zeichen). Diese wird in
`anliegen_process_overrides` **verschlüsselt und mit Actor/Zeitstempel**
gespeichert. Meldende sehen nur den bekannten Anliegenstatus,
nicht die interne Begründung. Ein Abschluss über die verknüpfte
**native TAKT-Aufgabe** darf diese Vorschrift nicht umgehen;
stattdessen bleibt das Anliegen offen und ein neutraler Hinweis
wird protokolliert.

## Grenzfälle und offene Folgepunkte

- Vertrauliche Anliegen sind für neue Prozessstarts gesperrt.
- Ein allgemeines `anliegen_manage`-Recht allein reicht **nicht**
  aus, um interne Prozessschritte anderer Organisationen zu sehen
  oder auszuführen.
- Bei deaktivierter Integration werden keine neuen Prozessaufgaben
  eingeblendet; vorhandene Läufe bleiben zur Einsicht sichtbar.
- Der Hub kopiert keine Kommentare oder Dokumente und sendet selbst
  keine zusätzlichen Benachrichtigungen.
- **#293** bleibt für organisationsübergreifende Prozessketten,
  DAG-Verzweigungen, aufwendige Daten-/Dokumentfreigaben,
  Fristen-Eskalationen und optionalen KI-Agenten zuständig.
- **#294** ist der gesonderte Rollout-/Datenschutz-Sicherheitscheck.
