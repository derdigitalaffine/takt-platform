# Interne Anliegen: typisierte Prozessengine (Issue #290)

## Grenzen dieses Inkrements

Der reale Prozessstart für interne Anliegen ist ein **Service**, noch keine
Benutzeraktion im Portal. Die optionalen Start-UI, Kategorienzuordnung,
Review-Freigabemaske, Prozess-Hub und task_overview-Verknüpfung werden in
#291 und #292 umgesetzt. `anliegen_process_integration_enabled` ist **ohne
expliziten Eintrag deaktiviert**; in der Standardinstallation entstehen weder
Prozessläufe noch neue Aufgaben durch das Vorhandensein dieser Engine.

## Kein künstlicher Formularantrag

`app.process_context.ProcessExecutionContext` unterscheidet ausdrücklich
`form_response` und `anliegen`. `app.process_engine.start` leitet echte
`FormResponse`-Objekte **unverändert** an die bisherige
`app.workflow.start` weiter. Interne Anliegen laufen ausschließlich durch
`app.anliegen_process_engine` mit den eigenen Tabellen
`anliegen_process_runs` und `anliegen_process_tasks`.

Die gemeinsame Prozessdefinition und der reine Bedingungsvergleich stammen
aus der bisherigen `workflow.py`. Ein interner Lauf hält die veröffentlichte
`ProcessVersion` fest. Änderungen am Entwurf oder neue Versionen ändern
laufende Instanzen nicht.

## Freigegebene Schritttypen in diesem Inkrement

| Schritt | Internes Verhalten |
| --- | --- |
| `task` | Eigenständige, persistierte manuelle Aufgabe mit Zuständigkeit, Prüfpunkten und validierten internen Feldern |
| `approval` | Genehmigen oder begründet ablehnen, optional Vier-Augen-Prinzip und definierter Ablehnungszweig |
| `auto` | Nur dann zulässig, wenn **keine** externen Aktionen definiert sind; persistierter, seiteneffektfreier Markierungsschritt |
| `request` | Abgelehnt vor Start, da öffentliches Nachforderungsportal und Formularfelder nicht auf Anliegen übertragbar sind |
| `confirm` | Abgelehnt vor Start, da antragsspezifische Bestätigungslinks fehlen |
| `payment` | Abgelehnt vor Start, da Zahler, Gebühr und Zahlungslinks eine eigene autorisierte Fachintegration benötigen |

Automatikaktionen wie `mail`, `pdf`, `assign` und `status` sowie
formulargebundene Fragebedingungen (source `q`) werden bei der
Kompatibilitätsprüfung *vor* Instanziierung einer internen Prozessaufgabe
abgelehnt. Antragsspezifische Schrittstatus werden ebenso abgewiesen.
Prozess-Endmetadaten wie `end_inform` lösen **keine** E-Mail und keine
unmittelbare Änderung des Anliegens aus; die spätere Aggregation gehört in
#292. Die Prüfung ist künftig beim Aktivieren einer Regel in #291
verpflichtend erneut auszuführen.

## Berechtigungen und sichere Zustände

- Der Feature-Schalter muss ausdrücklich aktiviert sein; eine
  `AnliegenProcessRule` muss `active`, genehmigt und für Kategorie,
  Organisation und Startart gültig sein.
- Vertrauliche Anliegen sind in diesem Inkrement **ausgeschlossen**;
  nicht einmal bei administrativen Rechten ist ihr Start möglich.
- Start durch meldende Person nur mit Einreichberechtigung, sonst durch
  tatsächlich berechtigte Bearbeitende. Automatisches Starten wird bis
  zu #291 nicht über HTTP freigegeben.
- Angeforderte Starts mit Freigabepflicht erzeugen **noch keine Schritte**.
  Eine zweite berechtigte Person muss ausdrücklich freigeben.
- Jede Aufgabenaktion prüft den aktuellen Vorgang, die Zuständigkeit und
  die aktive Benutzeridentität auf dem Server; bei Freigaben zusätzlich
  das Vier-Augen-Prinzip.
- Explizit übergebene Daten dürfen nur auf im Rule-Mapping freigegebene
  Zielfelder verweisen. Prozessdaten, Kommentare und Feldwerte werden
  verschlüsselt gespeichert; Audits enthalten keine freien Texte.
- Der durch den Aufrufer gelieferte stabile Startschlüssel ist eindeutig.
  Wiederholungen erzeugen keinen weiteren Lauf. Ein compare-and-swap auf
  `state_version` schützt Fortschrittsänderungen bei konkurrierenden
  Abschlüssen; einzelne Änderungen werden erst mit der umgebenden
  Datenbanktransaktion verbindlich.
- Externe Aktionen werden **nicht automatisch wiederholt** (sie werden
  gar nicht ausgeführt). Pausieren, Fortsetzen, Abbrechen und blockierte
  Zuständigkeiten sind persistierte, auditierte Zustände.
- Die Engine ruft **niemals eigenständig `db.commit()`** auf.

## Warum nicht alles auf einmal?

Die bisherige Workflow-Engine enthält antragsspezifische Empfänger,
Formularfelder, DMS- und Zahlungsreferenzen sowie E-Mail-Seiteneffekte.
Deren Umleitung in interne Anliegen ohne dedizierte Rechte- und Fachadapter
würde Datenlecks und unbeabsichtigte Vorgänge riskieren. Das
Integrationsinkrement liefert deshalb zuerst den sicheren Ausführungskern.
#291 muss konkrete Rechtetabellen und den aktiven Veröffentlichungs-/Startweg
einführen; #292 muss Aufgabenübersicht und Hub ergänzen.
