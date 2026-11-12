# Fachspezifikation TAKT-Modul Digitales Verbandbuch
Stand 12.11.2026. Ziel: geschützte Dokumentation jeder tatsächlich geleisteten Ersten Hilfe nach §24 Abs.6 DGUV Vorschrift 1, optionales Unfallanzeige-/Arbeitsschutzmodul. Interviews 1–64: D in relevanten Verbandsbuchfragen.

## Rechtsabgrenzung
- Erste-Hilfe-Dokumentation ist eine eigene Fachakte. DGUV: betroffene Person; Ort/Datum/Uhrzeit/Hergang; Art/Umfang Verletzung/Erkrankung; Zeugen; Datum/Uhrzeit und Art der Hilfeleistung; Ersthelfende. Vertraulich, Einzelaufzeichnungen fünf Jahre, danach datenschutzgerecht löschen (gesetzliche Prüf-/Sperrpflichten im Einzelfall gesondert).
- Beinaheunfall ohne Erste-Hilfe-Leistung, Unfallanzeige, Gefährdungs-/Ereignismeldung und eAU/Krankmeldung sind **andere Domänentypen**; konfigurierbare Querverweise, keine stillschweigende Gleichsetzung.
- §193 SGB VII Unfallanzeige: etwa Tod oder mehr als drei Tage Arbeitsunfähigkeit, besondere Personengruppen; gesetzliche Frist grundsätzlich drei Tage ab Kenntnis; Personalrat: Mitunterzeichnung oder bei Datenübertragung Kenntnisnahme eines bestimmten Mitglieds vor Absendung; Fachkraft für Arbeitssicherheit/Betriebsarzt informieren. Menschliche Prüfung, Trägerzuständigkeit, Sonderfälle beachten.

## Personenkreise und Scope
Tenant → Arbeitgeber → Organisationseinheit/Standort → Vorfall. Alle tatsächlichen betroffenen Personenkreise, soweit zulässig (Beschäftigte, Auszubildende, Gäste, Fremdpersonal, Ehrenamt, ggf. weitere), mit eigenem Beschäftigungs-/Versicherungsstatus; niemals aus TAKT-Account Existenz Versicherungsschutz folgern.
Ersthelfenden-Register mit Schulungs-/Qualifikationsstand, ohne automatisches Ersetzen der fachlichen Zuständigkeit.

## Objektmodell
FirstAidEvent(id, tenant_id, employer_id, location_id, occurred_at, recorded_at, status, privacy_class, reporter, data_revision, retention_due_at);
FirstAidSubject(event_id, local_ref_or_external_pseudonym, protected_identifiers);
FirstAidMeasure(event_id, aid_at, treatment, first_aider_ids);
Witness; InjuryDescription; EventAttachment (isolated encrypt-at-rest); FirstAidCorrection(immutable append-only diff, reason, actor);
FirstAidAccessGrant(tenant/employer/case, purpose, expiry), FirstAidAuditMetadata, DisclosureRequest, DataExportRecord, LegalHold(reason/approver/review_date), DeletionProof(no health description), DataKeyVersion.
Separate IncidentReportDraft/ReportSubmission/InsuranceCarrier/PRNoticeRecord for §193-SGB-VII and separate OccupationalSafetyEvent for Beinaheunfälle.
Vorgeschriebene Felder nicht unbemerkt aus Formularschema entfernb ar, fachliche Erweiterungsfelder nur freigegeben und datenminimiert.

## Bedrohungsmodell und Datensicherheit
Gesundheitsdaten nach Art.9 DSGVO: Datenfeld-, File-, Such-, Cache-, Backup-, Audit- und Exportzugriff schützen. Kein KI/RAG, generisches Suche/Chat, normales Task-Board, E-Mail-Inhalt, Telemetrie oder Analytics mit Detaildaten. Module komplett OFF bis bewusster Aktivierung.
- Globale technische Adminrechte ≠ fachliche Einsichtsrechte. Notfallzugriff nur nach dokumentiertem Berechtigungsprozess, zweckgebunden, zeitbegrenzt und nachvollziehbar, nach Möglichkeit 2-Personen-Freigabe.
- Storage verschlüsselt mit eigenem Key/Envelope-Konzept, Schlüssel nicht unbemerkt aus altem `security.encrypt` für API-Keys ableiten; Keyrotation/Verlust-/Restore-Prozedur testbar, Schlüssel in Backups strikt separieren.
- API schützt ACL pro Datensatz und Feld, reauthentifiziert kritische Aktionen (MFA), CSRF/rate-limit/server validation, nosniff/no-store, keine Referer-Leaks und keine unbefugten Exporte.
- Ausdruck/Download mit sichtbarem Aktenhinweis, minimaler Metadaten, Exportzweck und Zugangsnachweis; File Scans, MIME/Größenlimit, Metadatenhygiene.

## UX und Workflows
Einstieg `/verbandbuch` mit `Erste-Hilfe-Leistung dokumentieren` und `Meine Meldung` je Berechtigung; kompaktes mobiles Formular + ausführliche Fassung; Pflichtfelder/Zeugennamen in verständlichen Abschnitten; Personensuche nur bei Zugriffsrecht und erlaubtem Scope; ohne Anmeldung nur bewusst freigegebene sichere Gasttoken, Rate limit und abgetrennte Uploadfläche.
QR je Standort führt zu einem signierten Einstieg, NICHT zu einer Zugriffserweiterung oder einem Gesundheitsdaten-Token. Separate Personenrollen: erfassen, eigene Fälle, bestätigen, bearbeiten, auswerten, exportieren, Datenschutz-Anfrage, Admin-Konfiguration.
Bei verspäteter Eingabe Ereigniszeit und Eintragszeit transparent; Korrekturen append-only, nicht unbemerkt überschreiben. Betroffene erhalten geprüften Auskunfts-/Ergänzungskanal und keine Einsicht auf fremde Fälle.

## Offline (spätere sichere Freigabe)
Offline-Entwürfe nur nach nachgewiesenem Sicherheitstest: endgerätegebundener, bei Entsperrung sicher geschützter kurzlebiger Schlüssel; kein Health-Payload in LocalStorage, unverschlüsseltem IndexedDB, Browser-Cache, Push oder Logs; explizite Löschfrist, Remote-Wipe/Logout-Löschung soweit technisch realisierbar, Konfliktmanagement und Versandbestätigung. Falls Sicherheitskriterien nicht erfüllt, Funktion aus.

## Optionale TAKT-Integration (genau ein verbindlicher Service statt Doppelhaltung)
Kontrakt `secure_case_adapter`: `FirstAidCaseRef` mit case_id/tenant_id/employer_id/opaque_permission_scope und typisierte, explizite Operationen. `forms` darf nur freigegebenes Erfassungs-Frontend sein; der sensitive Payload wird DIREKT an die isolierte Fachservice-Grenze geliefert, keine `FormResponse`-/`ApplicationRequest`-Kopie. 
`processes`: nur speziell für Fachfälle validierte `ProcessExecutionContext(kind='first_aid')`; nicht einfach vorhandene `workflow.start` mit FormResponse verwenden. Fieldmapping allowlist, keine externen Side Effects ohne Freigabe. 
`tasks`: neutrale Info ('Ein geschützter Vorgang erfordert deine Bearbeitung'), fachliches ACL-Prüfen beim Öffnen. 
`dms`: lediglich sichere Referenzen; keine ungeschützte Suche/Vorschau oder Volltextindex. 
`notifications`: nur abgespeckte Ereigniskennzeichen, niemals Diagnosen, Namen in Mail-/Push-Payload ohne gesonderte Rechtsgrundlage. 
Fehlende Module: Fallback im Verbandsbuch eigenständig, externe Anbindung disabled/404; nie kaputte Seiten.

## Unfallanzeige §193 SGB VII
Getrennter Übergang 'Prüfung der Anzeigepflicht erforderlich' mit Menschenentscheidung, Träger anhand Arbeitgeber und Rechtsform, vorgangsbezogene Pflichtfelder, nachvollziehbare Kenntnis-/Fristzeitpunkte, gesetzliche Beteiligung Personalrat, FASI/Betriebsarzt-Benachrichtigung, gültige Ausgabe- und Übergabewege. Kein automatischer API-Versand ohne geklärte Rechts-/Schnittstellenfreigabe. Evidenz der Signatur/Kenntnisnahme ohne pauschale Online-Signaturbehauptung.

## Retention / Aufbewahrung
Digitaler Erste-Hilfe-Eintrag je Eintrag fünf Jahre; Fristbeginn, Rechtsgrundlagen, Ausnahmen und ggf. Legal Holds explizit freigeben, regelmäßig auf weitere Erforderlichkeit prüfen. Löschung im aktiven Store, Index, Files, Queue, Replikaten und soweit möglich Backups mit dokumentierter Recovery-Löschung / Cryptographic Erasure-Konzept; keine Komplettbuch-Ablauffrist für digitale Einzeleinträge. Zusammengefasste Statistik nur reidentifikationsgeschützt, kleine Zellen unterdrücken, kein Drilldown für Unberechtigte.

## Gate/Tests
Vor Prod: VVT, Art.9-Rechtsgrundlage und Zweckbindung geprüft, DSFA-Vorprüfung dokumentiert, Schutzbedarf/DSFA falls notwendig, Datenschutzbeauftragten-/Arbeitsschutz-Freigabe, Security-Pentest, Restore-Drill, Schlüsseltausch, autorisierte und verweigerte Abfragen, Direktlinks und Cache-/HTML-/PDF-Lecktests, Löschlauf/Legal Hold/Export-DSAR Tests, A11y, QR-Abuse, Massen-Zugriff, offline datensicher.
