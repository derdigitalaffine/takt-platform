# TAKT: Bestandsaufnahme und Optimierungslauf – Personalratswahl / Digitales Verbandbuch

**Stand:** 13. November 2026 · **Status:** Code-Review des Main-Branches, keine produktive Abnahme.

## Umfang und Nachweislage

Geprüft wurden die Fachlogik, Routen, SQLAlchemy-Modelle, Jinja-Templates, statische Styles, Modulverwaltung, Handbuch-/Roadmap-Dokumentation und bestehende Regressionstests beider Module. Rechtsgrundlagen wurden mit offiziellen DGUV-Fachinformationen und den RLP-Landesrechts-/Wahlordnungsquellen abgeglichen. Eine installierte Serverumgebung, echte Personaldaten, produktive Konfiguration, verschlüsselte Sicherungen, Penetrationstests und Browser-End-to-End-Tests standen im GitHub-Review nicht zur Verfügung. Die neuen Tests wurden als Quellcode ergänzt, **nicht tatsächlich ausgeführt**; zu den Merge-Commits wurden keine CI-Läufe verifiziert.

## A. Digitales Verbandbuch – Ist-Zustand

| Bereich | Vorhanden | Bewertung / Grenze |
|---|---|---|
| Modulverwaltung | Modulschalter standardmäßig aus; separate Produktivfreigabe via `VERBANDBUCH_PRODUCTION_APPROVED` | **Freigabegate**: Eine Codeänderung aktiviert keine echte Gesundheitsdatenverarbeitung. |
| Fachzugriff | Globale Rechte plus ausdrückliches Standortmandat; Admin ohne automatisches Einsichtsrecht | Gute Grundisolation, organisatorisches Vier-Augen-Freigabeverfahren für Rechte noch nachzuweisen. |
| Organisationen | Standortverknüpfung; vollständiger `active_path` für QR, Capture, Review und Admin-Aktionen seit PR #477 | Sicherheitslücke bei deaktivierten Vorfahren geschlossen, Regressionstest vorhanden. |
| Datenerfassung | Mobile mehrteilige Maske, DGUV-Kernfelder, sachliche Fehlermeldungen, signierter QR-Einstieg | UX in unterschiedlichen Smartphone-/Screenreader-Konfigurationen nicht browsergetestet. |
| Gesundheitsschutz | Fachschlüssel (Fernet), verschlüsselte Fallinhalte und Gründe, keine allgemeine KI-/Suche-/DMS-Spiegelung | Vertraulichkeit hängt auch von Server/DB-Backups, Schlüsselverwaltung und betrieblichen Rollen ab. |
| Fallbearbeitung | Neutrale Quittung, Fachaktenansicht, Ausdruck, Audit, unveränderliches Original, verschlüsselte Korrekturhistorie | PR #478 erkennt *veraltete* Berichtigungsformulare; atomare Schreibkonflikte bei gleichzeitigem POST gesondert prüfen. |
| Aufbewahrung | Pro Akte mindestens fünf Jahre; täglicher Löschlauf; Löschsperre mit verschlüsselter Begründung; Löschbeleg | Backup-Löschung, Wiederherstellung, Legal-Hold-Aufhebung, Fristkontrolle und tatsächliche Job-Überwachung nachweisen. |
| Übersicht | 40 eigene Quittungen, 80 Review-Fälle in letzter Übersicht; clientseitiger Such-/Standortfilter | **Offen:** Serverweite, berechtigungsgebundene Suche/Paginierung. Aktuell erfasst der Filter keine älteren Fälle außerhalb der ersten 80. |
| Administration | Standorte, Rechtevergabe, Aktivierung, QR/A4-Aushang, Schlüsselerzeugung | Betriebsanweisung, DSB-Freigabe, DSFA-Prüfung und Schlüssel-Rotation fehlen als nachgewiesener Betriebsvorgang. |

### Verbandbuch – vor Produktivsetzung zwingend

1. **P0 Datenschutz/Betrieb:** Rechtsgrundlage Art. 9 DSGVO, VVT, DSFA-Vorprüfung und ggf. DSFA; verantwortliche Stelle, Personalvertretung und DSB beteiligen; dokumentierte Zweck- und Berechtigungsmatrix.
2. **P0 Kryptografie/Backup:** gesichertes, separat wiederherstellbares Fachschlüssel-Backup, getesteter Restore mit Fachakten, Rotation/Recovery-Prozess, Schlüsselverlustszenario und Regelung zur datenschutzgerechten Backuplöschung.
3. **P0 Qualität:** `pytest tests/test_verbandbuch.py` einschließlich negativer Zugriffstests und produktionsnaher DB-Transaktionen ausführen; CSRF, Statusumschaltung, QR, mobile Bedienung und Ausdrucken E2E prüfen. Simultane Berichtigungen in getrennten Sessions testen.
4. **P1 Fachablage:** Datenschutzkonforme paginierte Aktenliste, serverseitige Suche nach Aktenzeichen/Standort ohne Entschlüsselung, klare Gesamtzahl und leerer Filterzustand.
5. **P1 Betrieb:** tägliche Fristenjob-Überwachung, Löschbelegkontrolle, Löschsperren-Review und klar geregelte Aufhebung, Zugriffsentzugstest mit deaktivierten Elternorganisationen.

**Go/No-Go:** Kein automatisches Setzen des Produktivflags, bevor 1–3 nachweislich abgeschlossen und unterzeichnet sind.

## B. Personalratswahl – Ist-Zustand

| Bereich | Vorhanden | Bewertung / Grenze |
|---|---|---|
| Wahlbereiche | Geschützte Fachmandate, Organisationstypen, objektgebundene Aufgaben und Audit | Technische Org-Zugehörigkeit ist **nicht** automatisch die rechtliche Dienststellen-/Wahlkörperabgrenzung. |
| Wahlvorstand | Personenwahl aus aktiven Unterorganisationen inkl. Organisationsgruppen seit PR #470; serverseitig identische Scope-Prüfung | Rechtliche Bestellung, Wahlberechtigung und Gruppenvertretung bleiben separat zu prüfen. |
| Ablauf | Neun dokumentierbare Phasen, Terminplanung, Prüf- und Freigabepunkte | Dokumentation ist keine Durchführung einer rechtswirksamen Wahlhandlung. |
| Unterlagen | Versionierte vertrauliche Prüfentwürfe; 19 Formulararten; PDF und DOCX | Keine vollständige feld- und wortlautgetreue amtliche Vorlagenfreigabe. |
| Fiktive Demo | Über einklappbaren Einstieg abrufbar; 19 Vordrucke mit fiktiven Daten und PDF-/DOCX-Export seit PR #480 | Keine echte Wahl, keine Datenbankmutation, keine automatische Sitzverteilung oder Bekanntgabe. |
| Papierauszählung | Plausibilitätsprüfungen, aggregierte Zählerfassung, begrenzte d’Hondt-Rechenhilfe | Keine vollständige WOLPersVG-Regel-Engine; Gleichstände und Sonderfälle bleiben menschlich zu entscheiden. |
| Bekanntmachungen & Umläufe | Geführter Workflow mit Links zu Dokumenten, Umläufen und Nachweisen | **Nur Navigation:** keine belastbare Umlauf-API, keine Freigabekette und keine automatische Bekanntgabe. |
| Datenschutz | Keine digitalen Einzelstimmen/Online-Wahl, fachbezogene ACL und chiffrierte Formfassungen | Datenmodell für Wählerverzeichnis, Bewerbungen, Einsprüche und gesicherte Aufbewahrung nicht fertig. |

### Personalratswahl – priorisierte offene Blöcke

- **P0 Rechtsmodell:** Aktuelle LPersVG-/WOLPersVG-Fassung, rechtlich geprüftes Regelpaket, Geltungsbereich und nachweisbare Freigabe je Wahl. Keine automatischen verbindlichen Fristen oder Mandatsergebnisse vor Gate A.
- **P0 Daten & Verfahren:** Eigenständiges Wahlberechtigtenverzeichnis und Einsprüche (#395/#396), Wahlvorschläge und Zustimmungen (#398), Gruppen-/Sitzverfahren (#402), Ergebnisse und Akten (#403/#404); amtliche Vorlagen (#399) fachlich exakt vergleichen.
- **P1 Bekanntgabe/Umläufe:** Entwurf, echte interne Beschluss-/Umlaufreferenz, erlaubte öffentliche Inhalte, zuständiger Freigabeakteur, veröffentlichungsfähige Kanäle, Rückmeldestatus und Nachweis getrennt voneinander modellieren. **Keine** automatische Übertragung vertraulicher Wahlakten oder Unterzeichnerlisten. Eine elektronische Bekanntgabe darf nur erfolgen, wenn sie nach aktueller WOLPersVG rechtlich zulässig ist.
- **P1 UI:** Konsolidierte Seitenführung, durchgehende Filter/Suche, barrierearme Formfehler, Kontextaktionen und responsive Ansichten; echte Browser- und Drucktests.
- **P0 Qualität:** Vollständige Testmatrix gegen WOLPersVG, Negativtests zu Objekt-/Mandatsrechten, Migrations- und Restore-Tests; Demo-PDFs/Word-Dateien auf Layout und eindeutige Musterkennzeichnung prüfen.

## Gemeinsame Integrationsregeln

- **Keine Gesundheitsdaten** aus dem Verbandbuch in allgemeine Umläufe, E-Mails, KI-Agenten, Kalender, Aufgaben, Volltextsuche oder DMS überführen.
- **Keine Einzelstimmen** oder Wähler-/Unterstützerlisten aus der Personalratswahl in allgemeine TAKT-Funktionen übertragen.
- Falls für eine zulässige Bekanntmachung Daten veröffentlicht werden sollen: eigener redigierter Publikationsentwurf, eindeutig verantwortlicher Wahlvorstand, manueller Prüfschritt, Rechtsgrundlage und Veröffentlichungsaudit.
- Beide Module brauchen separate tenantbezogene Rollenprüfungen auch im Backend; Frontend-Ausblendungen reichen nicht.

## Konkrete Änderungen dieses Optimierungslaufs

- **PR #477:** vollständige aktive Organisationskette als Zugangsvoraussetzung im Verbandbuch.
- **PR #478:** Stale-Revision-Schutz bei Berichtigungen mit HTTP 409 und Regressionstest.
- **PR #480:** Vollständiger fiktiver 19-Vordruck-Katalog mit Muster-Vorschau sowie PDF-/DOCX-Generatoren ohne echte Wahlakten.

## Prüfplan (vor Betriebsfreigabe)

```sh
cd portal
python -m pytest -q tests/test_verbandbuch.py tests/test_prwahl.py tests/test_prwahl_workflow.py
python -m pytest -q tests/test_domains.py tests/test_user_handbook.py
python -m pytest -q tests
```

Zusätzlich: Browser-Smoke in Dark/Light, 320px/768px/Desktop, Tastatur/Screenreader; QR/CSRF/Grant-Entzug; PDF-/DOCX-Druckansichten; verschlüsselter Restore; tatsächliche 5-Jahres-Aufbewahrung; Entscheidung über Go/No-Go dokumentieren.

## Rechts- und Fachquellen

- [DGUV – Dokumentation von Erste-Hilfe-Leistungen](https://www.dguv.de/fb-erstehilfe/themenfelder/dokumentation-von-erste-hilfe-leistungen/index.jsp)
- [DGUV – FAQ, elektronische Dokumentation und Aufbewahrungsdauer](https://www.dguv.de/fb-erstehilfe/faq/index.jsp)
- [BGW – Meldeblock/Verbandbuch, Stand 03/2026](https://www.bgw-online.de/resource/blob/18958/dfc8822026b8885643adf357bc4c4e42/bgw09-17-000-verbandbuch-data.pdf)
- [dbb Rheinland-Pfalz – Landespersonalvertretungsrecht und Wahlordnung](https://www.dbb-rlp.de/service/personalraete-info/)
- [Personalratswahl – bestehende Entwicklungsroadmap](personalratswahl-roadmap.md)

**Wichtige Abgrenzung:** Diese Bestandsaufnahme ersetzt weder eine Datenschutz-Folgenabschätzung noch ein Rechtsgutachten oder eine fachliche Produktionsfreigabe.
