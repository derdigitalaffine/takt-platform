# ADR: Zwei Fachdomänen statt direkter Wiederverwendung generischer FormResponse / VoteBallot
Stand: 12.11.2026 · Entscheidung: angenommen (Planung), operative Freigaben ausstehend.

## Kontext
TAKT-Portal: `portal/app/main.py` verwaltet Module; `portal/app/nav.py` die Navigation; `portal/app/db.py` SQLAlchemy/SQLite und Rechte; `portal/app/workflow.py` die antragsspezifische Prozessengine; `portal/app/routes_votes.py` allgemeine Abstimmungen. `portal/docs/anliegen-process-engine.md` dokumentiert bereits eine typisierte Kontexttrennung.

## Entscheidung
1. `prwahl` und `verbandbuch` als **eigenständige, opt-in aktivierbare** Module mit unabhängigen Fachobjekten und ACL.
2. Für `prwahl` niemals `VoteBallot`, allgemeine Vote-Tokens oder die Online-Abstimmungslogik für rechtsverbindliche Stimmabgabe übernehmen. Papierwahl wird digital vorbereitet und geprüft; Stimmen sind nur anonymes Auszählungsmaterial.
3. Für `verbandbuch` niemals Gesundheitsdaten in allgemeinen `FormResponse`-, `ApplicationRequest`-, Tasks-, DMS-, Chat-, RAG- oder Search-Payloads speichern. Formular-UI und Workflowdefinitionen dürfen über typisierte Adapter genutzt werden. Alle sensiblen Daten verbleiben im isolierten Fachservice.
4. API-/Event-Verträge müssen `tenant_id`, `employer_id`, `purpose`, `object_scope`, `version` und `correlation_id` prüfen. Fachereignisse nach außen nur anonym/metadatenminimal, ohne Body, Namen, Diagnosen, Fotos, Wahlidentitäten.
5. Technische Adminrechte dürfen keine stillen Ausnahmen zum Wahlgeheimnis oder zu Gesundheitsdaten schaffen; separate fachlich legitimierte Rollen.
6. Schlüssel-/Retention-/Audit-Lebenszyklen sind domain-spezifisch und getestet. SQLite/WAL ist derzeitige Ausgangsbasis, produktive Last-/Schutzbedarfsanalyse bestimmt nötige Isolation und DB-Weiterentwicklung.
7. Regeln immutable und signiert/freigegeben; fehlende Rechtsfreigabe führt zu sicheren Blockern statt automatischem Handeln.
8. Modul-Schalter einschließlich Domains-Registry, Agent, Tasks, Exporte, Background Jobs, Navigationslinks und Integrationen zentral testen und automatisch konsistent halten.

## Verworfen
- `VoteBallot` als allgemeiner elektronischer Wahlzettel der Personalratswahl.
- Zweite Kopie sensibler Formulardaten in Anträgen für bequemere Prozessstarts.
- Der Annahme, global admin könne ohne Anlass Gesundheitsdaten sehen.
- 'Alles D' als Rechtsfreigabe/DSFA oder als Genehmigung einer ungetesteten E-Wahl.

## Konsequenzen und Freigabegates
Höherer initialer Entwicklungsaufwand, dafür belastbare Datenschutz-/Mandantengrenzen und besseres Regelwerk-Migrationsmodell. Implementierung benötigt neue Fachservice-Adapter, Rollen, Tests, Admin-Catalog, Dokumentations- und Betriebsprozesse. Jede Freigabe stufenweise und getrennt nach Wahlart/Geltungsbereich bzw. Arbeitgeber/Versichertenkreis.
