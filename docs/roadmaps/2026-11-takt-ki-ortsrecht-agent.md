# TAKT KI 2.0 und Ortsrecht-Agent – Implementierungsroadmap (13.11.2026)

> **Stand:** Entwicklungsbeginn, nicht produktiv freigegeben. Verbindliche Entscheidungen: Interview 1–3, Fragen 1–100 jeweils D. Die Abschlussfragen 101–130 sind nicht beantwortet; als technische Arbeitsannahmen gelten die jeweils empfohlenen D-Varianten. Sicherheits- und Rechtsgrenzen haben Vorrang.

## Repository-Feststellungen

- FastAPI + SQLAlchemy + SQLite/WAL; additive Tabellen über `Base.metadata.create_all()` und idempotente Spaltenmigrationen in `db.py`.
- `AIProvider` enthält bisher genau eine `model_id`; Admin-/Chatfunktionen in `routes_ai.py`, Planner in `routes_agent.py`, Formular- und Anliegen-KI in `routes_forms.py`/`routes_anliegen.py`.
- `ai_provider.py` verwendet OpenAI-kompatible `/models` und `/chat/completions`, Server-Only-Key-Verwaltung und HTTPS.
- Rechtstextquellen: `LawText`, `LawVersion`, `LawAttachment` in `db.py`, Konvertierung `law_io.py`, Gliederung `laws.py`, Metadaten `laws_meta.py`.
- Kritischer Altstand: `laws.apply_planned()` aktiviert vorbereitete Fassungen anhand des Datums; `laws`-Recht deckt Bearbeiten und Veröffentlichen ab. Neue KI-Vorschläge dürfen in diese beiden Pfade nicht direkt hineingelangen.
- Bestehendes Designsystem verwendet Bootstrap 5, Tom Select und projektspezifische Styles. Kein neues UI-Framework.
- Berechtigungen und Datenklassifizierung sind serverseitige fachliche Grenzen, nicht bloß aus Prompts ableitbar.

## Phase 0 – Bestandskompatibilität und Datenfluss-Sicherheit

- [x] Implementierungsissues zu bestehenden Epics #193, #120 erstellt und abgegrenzt.
- [x] Explizite Aufgabenprofile (#424): `ai_task_profiles` als additive Tabelle; fehlende Zuordnung = altes Verhalten; falsch konfigurierte Zuordnung = kein stilles Fallback.
- [x] Live-Modellmetadaten aus vorhandenem `/models` mit `reported/unsupported/unknown` und begrenztem Output (#424).
- [ ] Sicherheitsprüfung DNS-Rebinding/Redirect-/Host-Allowlisting und TLS für lokale/nicht öffentliche Anbieter (#205).
- [ ] Migrationstests alte/neue DB, Backups, Wiederherstellung und Providerwechsel (#431).
- [ ] Nutzungsrichtlinien pro Datenklasse/Org, explizite Genehmigung bei Providerwechsel (#204, #206).

## Phase 1 – KI-Aufgabenrouting und Admin-UX

- [x] Chat-Neuanlage: Standardprofile; vorhandener Gesprächsprovider weiterhin maßgeblich.
- [x] Portalplaner, Formularassistent und Anliegenvorschlag: aufgabenbasierte Route; `/takt` bleibt ausdrückliche Aktionsgrenze (#425).
- [x] Keine automatische Übertragung bisheriger Chats an andere Task-Provider beim Planer (#425).
- [x] Admin-Endpunkt für Modellkatalog mit Admin-ACL und unveränderten Credentials; Tom-Select-gestützte Profilzuordnung (#426).
- [ ] Vollständige Multi-Adapter-Schnittstellen für native Ollama-Endpunkte, Responses, Vision, JSON Schema, Tool Calling (#200).
- [ ] Persönliche erlaubte Modellwahl, Kontext-/Kosten-/Tokenlimits und Qualitätstests (#203, #205, #206).
- [ ] Fähigkeiten aus nativen Providerinformationen und begrenzten Probeaufrufen verifizieren; niemals Namensheuristik.
- [ ] Fallunabhängige UX-E2E-Tastatur-/Mobil-/Dark-/Light-Tests (#431).

## Phase 2 – Ortsrecht-Original und Rechtsaktschema (vor KI-Übernahme)

- [ ] `laws_edit`, `laws_review`, `laws_publish` und optional `laws_manage`; Rechtemigration und Vier-Augen-Verfahren (#428, #120).
- [ ] Normwerk, Einzelrechtsakt, amtliches Original, Bekanntmachungsnachweis, konsolidierte Lesefassung und KI-Arbeitsstand trennen (#428).
- [ ] Unveränderliche Originaldateien und vollständige historische Metadatensnapshots, SHA-256 und Referenzierung (#428).
- [ ] Separate KI-Kandidaten; kein Schreiben in `LawText.body_md`, `planned_md`, `published` durch OCR/LLM.
- [ ] `apply_planned()` nur für gesondert bestätigte und freigegebene Fassungen zulassen; Tests für Frist-/Geltungslücken.

## Phase 3 – Sichere OCR und mehrstufige KI-Analyse

- [ ] Isolierter Compose-/OCR-Worker mit Tesseract, deutschen Sprachpaketen, optional Fraktur, MarkItDown; keine externen Fetches und keine Makros (#427).
- [ ] Seiten- und Bereichsanalyse, native Textextraktion, OCR-Fallback, positionsbezogene Quellreferenzen, bounded queue (#427).
- [ ] Struktur-, Metadaten-, Normverweis- und Texttreueagent als gesonderte aufgabenbasierte Modellprofile (#429).
- [ ] Versionierte strukturierte Ausgaben; Fallzahlen, Negationen, Geldwerte, Daten, Fristen und Paragraphenverweise besonders streng prüfen.
- [ ] Ungeklärte Belege blockieren ungeprüfte Übernahme; keine eigenständige Aussage zur Rechtswirksamkeit.

## Phase 4 – Human-in-the-Loop und Go-Live

- [ ] Einfach-/Expertenmodus im `/laws`-Editor, Original/PDF neben Markdown, Diff, Fundstellen, Feld- und Abschnittsfreigaben (#430).
- [ ] Keine KI-Speicherung oder Veröffentlichung ohne ausdrückliche nutzergebundene bestätigte Aktion und erneute ACL-/Versionskontrolle.
- [ ] Rechteprüfung, Barrierefreiheit, Offline-/Fehlerzustände, Regressionen des bestehenden Rechtstexteditors.
- [ ] Vollständige CI: Mock-Provider, OCR-Testkorpus, Sicherheits- und Migrationsprüfungen, E2E-Smokes, Wiederherstellungsprüfung (#431).
- [ ] Feature-Flags, Betriebsanleitung, Datenschutz- und juristische Fachfreigabe *vor* produktiver Aktivierung.

## Issue-Matrix

| Phase | Issue | Abhängigkeiten |
|---|---|---|
| A01 | #424 Modellregister/Discovery | #193 #194 #200 #203 |
| A02 | #425 Agentenrouting | #424 #206 |
| A03 | #426 Admin-UX/Modellpicker | #424 #201 #205 |
| R01 | #427 OCR/MarkItDown | #216 #120 |
| R02 | #428 Rechtsakte/Originale/Entwürfe | #120 #107 |
| R03 | #429 Extraktion/Texttreue | #424 #427 #428 |
| R04 | #430 Review-UI | #426 #427 #428 #429 |
| Q01 | #431 Test-/Security-/Releasegates | alle |

**Pull-Request-Regel:** Kleine, einzeln testbare Slices. Merge erst nach grünem CI und Freigabeprüfungen; Merge ist niemals eine automatische produktive Veröffentlichung von Rechtstexten.
