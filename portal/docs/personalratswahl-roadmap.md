# Personalratswahl RLP – priorisierte Implementierungsroadmap

Stand: 13.11.2026 · Grundlage PR #447 · Epic #385

## Grundsatz

Eine dokumentierte Wahlhandlung ist keine implementierte Wahlfunktion. Die neun bestehenden Phasen, Wahlmandate, PDF-/DOCX-Prüfentwürfe und aggregierten Papierauszählungen sind ein Grundgerüst, keine juristische Freigabe. Die Papierwahl und die gesetzlich erforderlichen Originale bleiben führend. Online-Stimmabgabe ist ausdrücklich nicht Bestandteil der Umsetzung.

## P0 / Phase A: Rechts- und Datenfundament

- [ ] #393 Rechtlich versioniertes, von zuständiger Fachstelle abgenommenes LPersVG-/WOLPersVG-Regelpaket einschließlich Übergangsrecht und reproduzierbarer Testvektoren
- [ ] #394 Rechtliche Dienststellen-/Wahlkörperabgrenzung, Wahlvorstand, Vertreter und Fachmandate, getrennt von TAKT-Org-Baum
- [ ] #395 Wählerverzeichnis mit Import, Dubletten, Stichtag, Gruppen, Berichtigungen, datensparsamen ACL
- [ ] #396 Einsprüche, Beschlüsse, Verfahrensnachweise, revisionssichere Statuswechsel
- [ ] #397 Gesetzlich geprüfte Fristenengine mit Feiertagen, Arbeits-/Werktagen, Rechtsgrundlage und manuellem Prüfgate

**Gate A:** Ohne geprüfte Rechtsversion keine automatisch verbindliche Frist oder Sitzverteilung.

## P0 / Phase B: Wahlvorbereitung

- [ ] #398 Vorschlagslisten, Kandidaturen, Zustimmungen, Unterschriftennachweise, Mängel, Nachfrist, Zulassungsentscheidung
- [ ] #399 Feld- und wortlautgetreu abgeglichene amtliche Muster, Versionierung, Stimmzettel, Druckprüfung, Zustell-/Aushangnachweis

**Gate B:** Nur nach manueller Freigabe des Wahlvorstands zur Papierverwendung.

## P0 / Phase C: Wahl und Ergebnis

- [ ] #400 Wahllokale, Material, Helfende, Briefwahl-Rücklauf ohne Verknüpfung mit Einzelstimmen
- [ ] #401 Unabhängige Zählteams, Reconciliation, Korrektur und Vier-Augen-Freigabe
- [ ] #402 Gruppen-/Sitzverteilung und alle tatsächlich freigegebenen Wahlarten mit unabhängigen Testfällen
- [ ] #403 Wahlergebnis, Bekanntgabe, Annahme/Ablehnung, Ersatzmitglieder und Zustellnachweise

**Gate C:** Kein automatisch rechtlich festgestelltes Ergebnis und keine stillschweigende Losentscheidung.

## P1 / Phase D: Nachbereitung, Integration, Qualität

- [ ] #404 Wahlanfechtung, Sonderfälle, rechtssichere Wahlakten, Aufbewahrung, Export
- [ ] #405 Mantine-UI, geführte Workflows, TAKT-Integration, Barrierefreiheit, responsives Design
- [ ] Sicherheits- und Datenschutzfreigabe mit Testmatrix, Migration, Backup/Restore und produktivem Go/No-Go (gemeinsames S06-Issue)

## Pflichtkriterien für jedes Issue

1. Backendmodell, Migration und klarer API-Vertrag.
2. Tenant-, Wahl- und Objektberechtigung bei jedem Schreib-/Lesezugriff; negative ACL-Tests.
3. Revisionsfähiges Audit und dokumentierte Fehler-/Korrekturwege.
4. Intuitive, barrierearme TAKT-Oberfläche; keine ungeprüfte Freigabe durch einen einzelnen Klick.
5. Positive und negative Tests, Migrations-/Rollback-Nachweis und Dokumentation.
6. Rechtswirksame Funktionen nur nach unabhängiger Prüfung der aktuellen amtlichen Rechtsquellen und Formulare.

## Abhängigkeiten

A → B → C → D. UX, Sicherheit und automatisierte Tests laufen in jeder Phase mit. Bereits implementierte Teilfunktionen werden erweitert statt doppelt gebaut. W14 (#406) bleibt ein reines Rechts-/Machbarkeitsgutachten, kein Entwicklungsauftrag für elektronische Stimmabgabe.
