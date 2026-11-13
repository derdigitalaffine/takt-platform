# TAKT-Roadmap: Personalratswahl und digitales Verbandbuch
Stand: 12.11.2026 · Status: verbindliche Planungsgrundlage; keine Produktivfreigabe · Verantwortlich: Produkt / Datenschutz / Fachstellen

## Projektziel
Zwei unabhängig aktivierbare Fachmodule auf Basis des bestehenden TAKT-Portals. Beide nutzen zentrale Identität/Organisation, behalten aber eigene fachliche Datenspeicher, Policies, Workflows und Prüfungen. Das Verbandbuch kann optional über **sichere, typisierte Adapter** mit Formulare, Anträge und Prozesse integriert werden. Die Personalratswahl nutzt KEINE gewöhnliche `/votes`-Wahlurne als rechtsverbindlichen elektronischen Wahlkanal.

## Interview-Beschlüsse
- Block 1, Fragen 1–28: **D durchgehend** (vom Nutzer am 12.11.2026 bestätigt).
- Block 2, Fragen 29–64: **D durchgehend** (vom Nutzer am 12.11.2026 bestätigt).
- Weitere Detailentscheidungen: auf expliziten Nutzerwunsch die jeweils umfassendste **fachlich empfohlene und rechtlich zulässige** Variante, OHNE weitere Rückfragen.
- D bedeutet NICHT: unzulässige Online-Wahl, automatisierte juristische Entscheidungen, unkontrollierte sensible Datenübernahme oder unbeschränkter Administrationszugriff.

## Verbindliche Prinzipien
1. Fail closed: Module und jede einzelne Anbindung sind standardmäßig AUS; Abschalten verhindert alle APIs, Side Effects, Worker, Navigation, Exporte und Suchindizes.
2. Mandanten- und Arbeitgeberisolierung mit expliziten Fachrollen und minimalem Zugriff; keine indirekte Rechteeskalation durch Admin, Task, DMS oder Suche.
3. Rechtstexte werden als versionierte **Regelpakete mit Quellen, Geltungszeitraum, Diff, Testfällen, fachlicher Freigabe** geführt. Keine unverifizierten Fristen und Wahlrechtsannahmen hart codieren.
4. Wahlvorstand entscheidet über Vorschläge, Einsprüche, Berechtigung, Ergebnis und Rechtsbehelfe. Kein Rechtsentscheid durch Algorithmus oder KI.
5. Wahlgeheimnis: Identitäts-, Teilnahme- und Stimmenbereiche kryptographisch/logisch trennen. Auszählung papierbasierter Stimmen nur ohne Identitätsbezug. Online-Stimmabgabe separat, deaktiviert und ohne Rechtsfreigabe NICHT ausführbar.
6. Gesundheitsdaten: eigene Sicherheitszone, Schlüsselmanagement, minimalisierte Benachrichtigungen; KI, generische Prozesse, Suche, RAG, analytics und Logging dürfen die Falldaten NICHT abgreifen.
7. Ersthilfe-Dokumentation ≠ Unfallanzeige; rechtlich und organisatorisch getrennter Workflow.
8. Fristen, Aufbewahrung, Löschung, Datenauskunft, Backup-Retention, Export und Sonderfälle sind pro Fachdomäne nach freigegebener Regelversion zu testen.
9. Barrierefreie, moderne, responsiv einheitliche UI mit Tastatur-, Mobil-, Screenreader- und Hell/Dunkel-Abnahme.
10. Agenten dürfen Codevorschläge erzeugen, aber keine rechtlich wirksamen Wahlentscheidungen oder medizinische Bewertungen automatisieren.

## Abhängigkeiten des bestehenden Repos
- `portal/app/main.py`: MODULES, enabled_modules und Admin-Domains/Module.
- `portal/app/db.py`: SQLAlchemy/SQLite, USERS/PERMISSIONS, bestehende Organisationsmodelle, WAL.
- `portal/app/nav.py`: Navigation und Favoriten, Module-Discovery.
- `portal/app/workflow.py` sowie `portal/app/process_context.py`, `portal/app/anliegen_process_engine.py`: Workflow/ProcessVersion und bereits vorhandene typisierte Adapter.
- `portal/app/routes_votes.py`, `portal/app/surveys.py`: UI-Wiederverwendung möglich; Stimmenbehandlung NICHT übernehmen.
- `portal/app/security.py`: bestehende API-Key-Fernet-Verschlüsselung darf nicht ungeprüft als Fach-Schlüsselmanagement für Gesundheitsdaten dienen.
- DMS, Formulare, Aufgaben, Organisation und OIDC über geprüfte Adapterschnittstellen; Module funktionieren auch ohne diese Module.

## Meilensteine und Freigabegates
### M0 – Recht/Sicherheit/Produktarchitektur (BLOCKIEREND)
RLP-Geltungsraum, Wahlarten und Modellentscheidungen; vertiefter Rechtsabgleich LPersVG/WOLPersVG mit Fachjuristen und Wahlvorstand; DGUV/SGB VII, Datenschutzkonzept, VVT, DSFA-Vorprüfung, Sicherheitsarchitektur, Schlüsselverwaltung, Legal Hold, Audit. Exportierbare und freigegebene Regelpakete. **Keine Produktivfreigabe vor M0.**
### M1 – Gemeinsame Plattformbausteine
Modulregister/Domains, Konfigurations-/Fachrollen-/Organisationsadapter, Mandantengrenzen, Ereignis- und Verschlüsselungsgrundlagen, Feature-Flags, Dokumentenversionierung, API-Vertrag, Tests; keine Datensicht durch alleinige globale Administratorrolle.
### M2-W – Personalratswahl MVP (PAPIERBASIERTE WAHL)
Wahlaufsetzung, Wahlvorstand, Stichtagsverzeichnis, Regeln/Fristen, Einsprüche, Listen/Kandidaturen, Wahlvorschläge, Mustervordrucke, Bekanntmachung, Wahlmaterial, Briefwahlverwaltung, manuelle papierbasierte Zählung, Sitzverteilung/Prüfung, Bekanntgabe, Ergebnisakte.
### M2-V – Verbandbuch MVP (ERSTHILFE)
Sicheres Erfassungsformular und mobile Kurzaufnahme, Pflichtfelder, differenzierte Rollen, Arzt-/Gesundheitsdaten-Abschirmung, revisionssichere Korrekturen, anlassbezogene Nachweise, sichere Exporte, individuelle Fünfjahreslöschung, Backups.
### M3 – Fachliche Erweiterungen
Wahl: Sonderwahlen/Teilwahlen, Mehrfachwahlen, Rechtsschutz/Ausnahmen, verbesserte Dokumentenpakete, Audit und Archiv. Verbandbuch: externer/personengebundener Zugang, offline unter strengem Key-Konzept, Arbeitsschutz-Auswertung, Unfallanzeige-SGB-VII mit Personalratsbeteiligung.
### M4 – Optionale Integrationen
Verbandbuch ↔ Formulare/Anträge/Prozesse über **explizite Feld- und Rechtefreigabe**; Aufgaben nur als pseudonymisierte Metadaten; Dokumente als sichere Referenzen; keine generische Suche/KI. Wahlmodul ↔ Organisation, DMS, Kalender, Aufgaben und Benachrichtigungen durch separierte Fachadapter.
### M5 – Betriebsreife
Angriffs- und Belastungstests, migrations-/restore-/recovery-Tests, unabhängige fachliche Wahltestfälle (Handrechnung), End-to-End-Rollen-Tests, Datenschutz-/Barrierefreiheits-Freigabe, sichere Einführungs-/Schulungspakete, Default OFF bis zur schriftlichen Freigabe.

## Vorgeschlagene Release-Struktur
- `prwahl-0.1`: internes Wahlmanagement-Demo mit Testdaten; NICHT rechtsverbindlich
- `verbandbuch-0.1`: Erfassung-Demo, keine realen Gesundheitsdaten vor Datenschutzfreigabe
- `prwahl-1.0`: freigegebene RLP-Papierwahl-Unterstützung
- `verbandbuch-1.0`: freigegebene elektronische Erste-Hilfe-Dokumentation
- `integrations-1.1`: freigegebene optionale Verbundprozesse
- `onlinewahl-research`: separater Feature-Branch/Projekt, KEIN Aktivierungspfad ohne nachgewiesene Zulässigkeit

## Definition of Done pro Issue
- Fachlicher Scope + explizite Nichtziele; Dataflow, PII-Klassifikation, Organisational Scope, Policy, API, UI; Versionierung/Migration und Rückwärtskompatibilität.
- Serverseitige AuthN/AuthZ auch für Direktlinks, Hintergrundjobs, Exporte, Mails, Suchindizes; Negativtests für fehlende/reduzierte Rechte.
- Kein Zugriff/Verhalten bei deaktiviertem Modul und fehlenden Integrationen.
- Unit-, Integrations-, E2E-, Accessibility-, Failure-/Retry-/Concurrency-Tests; Tests für manipulative Eingaben und Datenabfluss.
- Dokumentation, Changelog, Feature-Flag, sichere Rollbackstrategie, Security Review, rechtsfachliche Freigabe wo notwendig.

## Quellen / Rechtscheck vor Produktivsetzung
- RLP Innenministerium: https://mdi.rlp.de/themen/buerger-und-staat/oeffentliches-dienstrecht
- Landesrecht RLP (redaktionelle Konsolidierung; amtliches GVBl. ist maßgeblich): https://landesrecht.rlp.de/bsrp/gueUU
- dbb RLP Personalvertretungsrecht und Novellierung 2024/2025: https://www.dbb-rlp.de/service/personalraete-info/drucken/
- DGUV FAQ Ersthilfe: https://www.dguv.de/fb-erstehilfe/faq/index.jsp
- DGUV Dokumentation: https://www.dguv.de/fb-erstehilfe/themenfelder/dokumentation-von-erste-hilfe-leistungen/index.jsp
- DGUV Vorschrift 1 §24(6): https://www.bghm.de/arbeitsschuetzer/schriften-und-regelwerk/dguv-vorschriften/dguv-vorschrift-1/organisation-des-arbeitsschutzes/24-allgemeine-pflichten-des-unternehmers
- SGB VII §193: https://www.gesetze-im-internet.de/sgb_7/__193.html
- DSGVO Art. 5, 9, 25, 30, 32, 35; Landesdatenschutzrecht; Sozialdatenschutz je nach Träger/Rechtsgrundlage.

**Rechtsprüfung:** Quellen und Normtexte sind Input, nicht automatischer Nachweis von Rechtskonformität. Das Inkrafttreten, Übergangsrecht, konkrete Wahlart und Arbeitgeber-/Versichertenstatus sind je produktivem Einsatz zu verifizieren.
