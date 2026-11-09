# TAKT: Interne Anliegen ↔ Prozesse – verbindliche Produktspezifikation

Stand: 09.11.2026 · Entscheidungen des Interviews, Fragen 1–13: jeweils **D**
(Fragen 13 und folgende Detailentscheidungen auf ausdrücklichen Nutzerwunsch
nach den fachlich und sicherheitstechnisch empfohlenen Varianten).

## Leitplanken

- Bestehende Anliegen, Online-Anträge, Prozesseditoren, Aufgaben und Rechte
  bleiben abwärtskompatibel.
- Die Verbindung ist **optional, standardmäßig aus** und separat aktivierbar;
  keine automatische Nachmigration bestehender Anliegen.
- Das Anliegen bleibt führender Vorgang (ANL-...), kann **0..n** eigenständige
  Prozessinstanzen besitzen. Jede Instanz referenziert eine **veröffentlichte,
  unveränderliche ProcessVersion** und die zum Start gültige Regelrevision.
- Ein Prozessstart erfolgt nur ausdrücklich beim Einreichen, durch zuständige
  Bearbeitende oder per freigegebener Kategorieautomatik. Jede Startart hat eigene
  Berechtigungen, Freigaben und deduplizierte Startschlüssel.
- Ein Anliegen darf niemals die Zugriffsrechte auf einen Prozess oder dessen
  Unterlagen erweitern; umgekehrt gilt das Gleiche.

## Entscheidungen und Akzeptanzkriterien

1. **Start**: Bei Einreichung, manuell in der Bearbeitung, oder Kategorieautomatik;
   pro Kategorie/Organisation/Prozess granular konfigurierbar, initial aus.
2. **Vernetzung**: 0..n Prozessinstanzen pro Anliegen; zentraler Hub, keine
   Doppelaufgaben, regelbasierte/manuelle Abschlussentscheidung.
3. **Daten**: Festes Feldmapping, optional datenschutzgerecht begrenzte
   KI-Extraktion und manuelle Korrektur. Vorschau, Quellnachweis, Validierung;
   niemals fingierte Angaben. Keine implizite Übernahme verschlüsselter Felder.
4. **Rechte**: Getrennte Rechte für Auswahl, Start, Freigabe, Bearbeitung,
   Konfiguration; Organisation, Rolle, Mandat und aktive Vertretung prüfen;
   alle Aktionen serverseitig autorisieren, Freigaben auditieren.
5. **Aufgaben/Status**: Je Arbeitsschritt eine führende Aufgabe, keine doppelten
   Reminder; Statusaggregation und manuelle Ausnahmen mit Begründung;
   blockiert/fehlgeschlagen/ausstehend separat sichtbar.
6. **Hub**: Moderne responsive, barrierearme Prozess-Zeitleiste im Anliegen;
   einfache Freigaben direkt, komplexe Aktionen über echte Prozessansicht;
   keine blind verlinkten nicht mehr existierenden Seiten.
7. **Administration**: Globale Sicherheitsgrenzen; organisationsbezogene
   Zuordnung, delegierte Fachbearbeitung, Prüfung/Freigabe kritischer
   Änderungen; unveränderliche Regelrevisionen, Rollback für NEUE Vorgänge.
8. **Fehler**: Persistente Zustände, deduplizierte Trigger und Side Effects,
   sichere Retry-Policy; unbekannte Wirkung einer externen Aktion verlangt
   menschliche Prüfung, kein blindes Wiederholen. Pausieren/Fortsetzen/
   Abbrechen kontrolliert und auditierbar.
9. **KI**: Stufen aus/beraten/vorschlagen/autorisiert ausführen je Aktion;
   keine Umgehung von Geschäftsregeln, expliziter human-in-the-loop bei
   Genehmigungen und finanziellen Entscheidungen; offline/ohne KI nutzbar.
10. **Orchestrierung**: Sequenziell, parallel, Bedingungen, Abhängigkeiten,
    definierbare Abschlussregeln und Cycle-/DAG-Prüfung; bedingte Starts
    idempotent, keine unendlichen Trigger-Schleifen.
11. **Datenschutz**: Objekt-, Organisations-, Feld- und Dateirechte getrennt
    erzwingen. Vertrauliche Anliegen fail-closed; KI-Suche, Suchindex,
    Dokumentenvorschau, E-Mail, Export, API und Hintergrundjobs dürfen keine
    vertraulichen Daten über anderen Zugriffsweg offenlegen.
12. **Vorgangsakte**: Gemeinsame gefilterte Aktivitätenansicht, gezielte
    Referenzfreigaben für Dokumente/Kommentare, keine pauschale Kopie;
    Provenienz, Version, Zugriff und Löschung am Original respektieren.
13. **Änderungsmanagement**: Anliegen bleiben bearbeitbar; feldbasierte
    Differenzen prüfen, wesentliche Änderungen neu genehmigen, bereits
    ausgeführte Schritte/Bestellungen nie stillschweigend überschreiben;
    ggf. Ergänzungsprozess oder Änderungsanforderung.

## Weitere Festlegungen (empfohlene Varianten, ohne weitere Interviews)

- **Mandantengrenzen**: Organisation/Fachbereich serverseitig auf jeder
  Prozessinstanz und jedem Trigger prüfen. Keine cross-org Verlinkung ohne
  ausdrücklich zugewiesenes Mandat.
- **Veröffentlichung und Migration**: Neue Regeln zuerst als Entwurf, Review,
  Freigabe und dann aktiv. Bestehende Instanzen bleiben an ihrer Revision und
  ProcessVersion; Migration nur als separate autorisierte Aktion.
- **Audit**: Actor, Zeitpunkt, alte/neue Zustandswerte und Regelrevision;
  keine sensitiven Freitexte in generischen Protokollen.
- **Wiedervorlage/Fristen**: Fristen und Vertretungen aus dem zuständigen
  Prozess übernehmen; abgestimmte Erinnerungen und Eskalationen.
- **Sichtbarkeit**: Antragstellende erhalten nur erlaubten Fortschritt.
  Interne Bearbeitende sehen nur ihre organisatorisch und objektbezogen
  freigegebenen Daten, auch in /tasks.
- **Betrieb**: Transaktionssichere Tests für Parallelstarts, CSRF, fehlende
  Rechte, abgelaufene Freigaben, Datenschutz, Rollback und Migrationspfad.
  Feature-Switch auf Aus, bis die Gesamtkette und CI geprüft sind.
- **Produktgestaltung**: moderner Mantine-kompatibler Stil, klare
  Handlungsbuttons, keine überdimensionierten Seitentitel, mobil nutzbar.

## Architektur und Umsetzung – strikte Reihenfolge

### Phase 0 · Sichere Basis (dieser erste Commit)
Additive Tabellen für Regelrevision, pro Anliegen/Prozess-Version gespeicherte
Instanzen und Audit. Fail-closed Schalter und Policy-Normalisierung/Graphprüfung.
**Wichtig:** Noch kein ausführbarer Prozessstart und kein versprochener Hub.

### Phase 1 · Generische Engine
Die bestehende `workflow.py`-Engine setzt `FormResponse` und `resp.form`
voraus und verwendet in Auto-/Payment-/Mail-Schritten antragsspezifische
Seiteneffekte. **Keine künstlichen FormResponse-Datensätze** als Abkürzung.
Gemeinsame Engine-Schnittstelle/Task-Adapter mit explizitem Kontexttyp
(Formularantrag oder Anliegen) und zugelassenen Side Effects bauen;
Formularverhalten durch Regressionstests unverändert halten.

### Phase 2 · Administratorregeln und manuelle Starts
Pro Kategorie und Organisation zulässige veröffentlichte Prozesse
zuordnen. Entwurf/Review/Freigabe/Revision und serverseitige ACLs.
Erst nach dieser Phase im Hub einen überprüften manuellen Start aktivieren,
mit idempotentem Schlüssel und korrekter Vorabfreigabe.

### Phase 3 · Hub und Aufgaben
Schritte/Ergebnisse/Fristen/Fehler und gefilterte Aktivitäten anzeigen;
Prozessaufgaben als genau eine Quelle in „Meine Aufgaben“ integrieren,
nicht als zusätzliche künstliche native Tasks. Freigabeaktionen absichern.

### Phase 4 · Advanced Orchestration
Trigger beim Einreichen, automatische Kategoriezuordnung, DAG,
Parallelität, Statusaggregation, Retry/Recovery, Änderungsmanagement.
KI-Ergänzung ausschließlich optional/autorisiert.

### Phase 5 · Sicherheits- und Rollout-Gate
Migrationstest Bestand, role/org isolation, confidential isolation,
side effect dedup, Integration mit allen Moduleinstellungen, A11y,
Browser- und Python-CI. Standardmäßig AUS bis produktionsreif.
