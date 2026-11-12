# TAKT – Issue-Landkarte, Arbeitsaufteilung und Entwicklungsreihenfolge
**Stand:** 12.11.2026 · **Repo:** derdigitalaffine/takt-platform · **Planungsbranch:** `planning/personalratswahl-verbandbuch-2026-11`

## Eindeutige Zuordnung
- **[Gesamt-Epic #384](https://github.com/derdigitalaffine/takt-platform/issues/384)** – Gemeinsame Architektur und Roadmap.
- **[Personalratswahl-Epic #385](https://github.com/derdigitalaffine/takt-platform/issues/385)** – Modul `prwahl`, RLP-first, gesetzesbasiertes Papierwahlmanagement; E-Voting explizit ausgeschlossen.
- **[Digitales Verbandbuch-Epic #386](https://github.com/derdigitalaffine/takt-platform/issues/386)** – Modul `verbandbuch`, DGUV-Erste-Hilfe-Dokumentation mit sensiblen Gesundheitsdaten und nur sicherer optionaler Integration.

*JEDES Issue* ist in seinem Titel und Body einem dieser Fachbereiche zugeordnet. Nummern S/W/V sind dauerhaft stabil und werden in Commits/PRs referenziert. Arbeitspakete sind aufeinander abgestimmt und erst nach den dokumentierten Freigabegates produktiv einsetzbar.

## Architekturgrundlagen – gemeinsame Plattformarbeiten S01–S06
| Ticket | GitHub-Issue | Phase | Direkt vorausgesetzt |
|:--|:--|:--|:--|
| S01 | [#387 – Rechts-, Wahl- und Gesundheitsdatenschutz-Matrix](https://github.com/derdigitalaffine/takt-platform/issues/387) | M0 | keine |
| S02 | [#388 – Registry, Domains, Navigation, Modul- und API-Sperren](https://github.com/derdigitalaffine/takt-platform/issues/388) | M1 | S01 |
| S03 | [#389 – Fachrollen, Dienststellen, Arbeitgeber und Mandanten](https://github.com/derdigitalaffine/takt-platform/issues/389) | M1 | S01 |
| S04 | [#390 – Datensicherheitszonen, Schlüssellifecycle und Audits](https://github.com/derdigitalaffine/takt-platform/issues/390) | M1 | S01 |
| S05 | [#391 – Typisierte Formulare-/Anträge-/Prozesse-/DMS-/Tasks-Adapter](https://github.com/derdigitalaffine/takt-platform/issues/391) | M1 | S02, S03, S04 |
| S06 | [#392 – Tests, Sicherheitsabnahme und Release-Gates](https://github.com/derdigitalaffine/takt-platform/issues/392) | M1/M5 | S01–S05 |

## Personalratswahl – Fachpakete W01–W14
| Ticket | GitHub-Issue | Phase | Direkt vorausgesetzt |
|:--|:--|:--|:--|
| W01 | [#393 – RLP-Rechtsregelpakete](https://github.com/derdigitalaffine/takt-platform/issues/393) | M0/M2 | S01, S03 |
| W02 | [#394 – Wahl-Setup und Wahlvorstand](https://github.com/derdigitalaffine/takt-platform/issues/394) | M2-W | W01, S02, S03 |
| W03 | [#395 – Wählerverzeichnis & Stichtag](https://github.com/derdigitalaffine/takt-platform/issues/395) | M2-W | W01, W02 |
| W04 | [#396 – Einsprüche](https://github.com/derdigitalaffine/takt-platform/issues/396) | M2-W | W03, S04 |
| W05 | [#397 – Rechtsfristen und Wahlkalender](https://github.com/derdigitalaffine/takt-platform/issues/397) | M2-W | W01, W02 |
| W06 | [#398 – Vorschläge & Kandidaturen](https://github.com/derdigitalaffine/takt-platform/issues/398) | M2-W | W03, W05 |
| W07 | [#399 – Wahlbekanntmachungen & Vordrucke](https://github.com/derdigitalaffine/takt-platform/issues/399) | M2-W | W02, W05 |
| W08 | [#400 – Briefwahl und Wahlmaterial](https://github.com/derdigitalaffine/takt-platform/issues/400) | M2-W | W03, W06, W07 |
| W09 | [#401 – Anonyme Papierauszählung](https://github.com/derdigitalaffine/takt-platform/issues/401) | M2-W | W08 |
| W10 | [#402 – Ergebnisrechner und Sitzverteilung](https://github.com/derdigitalaffine/takt-platform/issues/402) | M2-W | W01, W09 |
| W11 | [#403 – Ergebnis, Veröffentlichung & Nachrücker](https://github.com/derdigitalaffine/takt-platform/issues/403) | M2-W | W07, W10 |
| W12 | [#404 – Anfechtung und Wahlakte](https://github.com/derdigitalaffine/takt-platform/issues/404) | M3 | W11 |
| W13 | [#405 – Wahlcockpit und TAKT-Integration](https://github.com/derdigitalaffine/takt-platform/issues/405) | M4 | S05, W02, W11 |
| W14 | [#406 – E-Wahl-Rechtsmachbarkeit, KEIN Feature](https://github.com/derdigitalaffine/takt-platform/issues/406) | Research | S01, W01 |

## Digitales Verbandbuch – Fachpakete V01–V15
| Ticket | GitHub-Issue | Phase | Direkt vorausgesetzt |
|:--|:--|:--|:--|
| V01 | [#407 – DGUV-Datenmodell und Ereignistypen](https://github.com/derdigitalaffine/takt-platform/issues/407) | M0/M2 | S01, S03, S04 |
| V02 | [#408 – Mobiler QR-/Formular-Einstieg](https://github.com/derdigitalaffine/takt-platform/issues/408) | M2-V | V01, S02 |
| V03 | [#409 – Betroffene, Ersthelfer und Fremdpersonen](https://github.com/derdigitalaffine/takt-platform/issues/409) | M2-V | V01, S03 |
| V04 | [#410 – Fachrechte und Vertraulichkeit](https://github.com/derdigitalaffine/takt-platform/issues/410) | M2-V | V01, S04 |
| V05 | [#411 – Revision/Korrektur/Nachtrag](https://github.com/derdigitalaffine/takt-platform/issues/411) | M2-V | V01, V04 |
| V06 | [#412 – Anhänge & geschützte Exporte](https://github.com/derdigitalaffine/takt-platform/issues/412) | M2-V | V04, S04 |
| V07 | [#413 – Fünfjährige Aufbewahrung und sichere Löschung](https://github.com/derdigitalaffine/takt-platform/issues/413) | M2-V | V01, V04, S04 |
| V08 | [#414 – Auskunft, Kopie und Berichtigung](https://github.com/derdigitalaffine/takt-platform/issues/414) | M2/M3 | V04, V06 |
| V09 | [#415 – Unfallanzeige §193 SGB VII](https://github.com/derdigitalaffine/takt-platform/issues/415) | M3 | V01, V04, S01 |
| V10 | [#416 – Personalratsbeteiligung & FASI-Benachrichtigung](https://github.com/derdigitalaffine/takt-platform/issues/416) | M3 | V09, S05 |
| V11 | [#417 – Sicherer Offline-Modus](https://github.com/derdigitalaffine/takt-platform/issues/417) | M3 | V02, V05, S04 |
| V12 | [#418 – Aggregatstatistik und isolierte Suche](https://github.com/derdigitalaffine/takt-platform/issues/418) | M3 | V04, V07 |
| V13 | [#419 – Formulare-Anbindung ohne FormResponse-Health-Kopie](https://github.com/derdigitalaffine/takt-platform/issues/419) | M4 | S05, V01, V02, V04 |
| V14 | [#420 – Anträge-/Prozesse-/Tasks-Integration für Unfallanzeige](https://github.com/derdigitalaffine/takt-platform/issues/420) | M4 | S05, V09, V10, V13 |
| V15 | [#421 – VVT/DSFA/Datenschutz-/Security-/Betriebsfreigabe](https://github.com/derdigitalaffine/takt-platform/issues/421) | M5 | S06, V07, V14 |

## Agenten-Parallelisierung
**Lane A: Gemeinsame Sicherheit/Recht:** S01 zuerst, dann S02/S03/S04 parallel, S05 abhängig, S06 in allen Phasen als CI-Gate.
**Lane B: Wahl:** W01 rechtlich validieren, W02 bauen, W03+W05 in parallelen Branches, W04/W06/W07 nach Freigabe, W08 danach W09/W10, W11 als Abschluss; W12/W13 danach. W14 nur Research.
**Lane C: Verbandbuch:** V01 nach S01/S03/S04, V02/V03/V04 parallel, V05/V06/V07 nach V04; V08, V09 und V11 unabhängig nach ihren Gates; V10/V12, dann V13/V14; V15 final.
**Integrationskonflikte:** Änderungen an `portal/app/main.py`, `portal/app/nav.py`, `portal/app/db.py`, `portal/app/security.py`, `portal/app/workflow.py` und Organisation zuerst via S02–S05 koordinieren. Fachagenten bauen Fachservice-Grenzen und nutzen zentrale Registry; keine konkurrierenden Direktänderungen an Module-Registry oder Berechtigungsprüfern.

## Definition of Ready / Done
- Ready: D-Interviewentscheidungen 1–64 berücksichtigt, Scope/Nichtziele, Rechtsquelle, ACL- und Datenklassifizierung, betroffene Pfade, Migration, Testfälle, Modul-/Integrationsflags.
- Done: migrationssicherer Code, idempotente Aktionen, fachliche und Sicherheitsregressionen, E2E/Screenreader, Dokumentation; **nicht** gleichbedeutend mit juristischer oder datenschutzrechtlicher Betriebsfreigabe.
- Jede PR verlinkt mindestens ein S/W/V-Issue und das Epic sowie die Freigabeprüfungen.
- **Rollout:** Module standardmäßig aus; Demo nur mit synthetischen Daten; personenbezogene Live-Nutzung erst nach fachlicher Freigabe, Datenschutzprüfung und Betriebsfreigabe.
- **Wahl:** W14 bleibt aus jedem MVP ausgeschlossen; kein elektronischer Stimmkanal, keine Übernahme von `VoteBallot`.
- **Verbandbuch:** V13/V14 dürfen keine Gesundheitsdaten in normale Formular-/Antrags-/Task-Tabellen oder KI/RAG/DMS-Suche übertragen.

## Verbindliche Quellen im Repository
- `portal/docs/personalratswahl-verbandbuch-decisions.md`
- `portal/docs/personalratswahl-spec.md`
- `portal/docs/verbandbuch-spec.md`
- `portal/docs/personalratswahl-verbandbuch-adr.md`
- `docs/roadmaps/2026-11-personalratswahl-verbandbuch.md`
