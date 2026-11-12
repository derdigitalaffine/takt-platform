# Fachspezifikation TAKT-Modul Personalratswahl (RLP-first)
Status 12.11.2026: Planung / KEINE Rechtsfreigabe, Interviews 1–64 D (für Wahlfragen 1–14 und 29–46).

## Ziel/Nichtziele
Mandantenfähige, geführte und rechtlich versionierte Organisation von Personalrats-, JAV-, Gesamt-/Stufen- und Sonderwahlen nach je einschlägiger Norm. Unterstützt klassische geheime Papierwahl, Schriftliche Stimmabgabe, Zählung, Prüfung und Dokumenten-/Aktenverwaltung. **Kein** Ersatz der geheimen Urne durch `/votes`, kein Online-Stimmzettel, keine digital fingierte Unterschrift, keine automatisierte Feststellung durch KI. Sonderregelwerke werden erst nach eigener Normprüfung freigeschaltet.

## Nutzerrollen / Identity
- Zentral: tenant_admin/module_configurer dürfen Modulkatalog, technische Konfiguration, Zuordnungslinks bearbeiten, NICHT automatisch Wahlunterlagen oder Identitäten einsehen.
- Fachlich: election_initiator (Wahl anlegen), electoral_board_chair, electoral_board_member, election_clerk, independent_counter, observer (nur rechtlich erlaubte Daten), auditor_restricted, legal_reviewer, voter_selfservice_read.
- Rollen pro Wahlkörper + Dienststelle, zeitlich/objektbezogen, getrennt von organisationsweiten Leitungsrollen. Die Rechtsfähigkeit eines Wahlvorstands ist nicht durch TAKT-Adminrolle begründet.
- Einladungen/Zugriffswechsel mit MFA und Quorum für sensible Entscheidungen; Vertretungen nur soweit gesetzlich zulässig und dokumentiert.
- Anwesenheits-/Zugriffsprotokolle strikt vom Wahlgeheimnis getrennt, keine bloße Personen-/Gruppenmitgliedschaft als Freigabe.

## Domänenobjekte (Bezeichner als Implementierungsvorschlag)
Election(id, tenant, employer, legal_pack_version, body_type, state, election_dates, version);
ElectoralBodyScope(election_id, service_units, district, election_group);
BoardAppointment, BoardMandate, BoardDecision, BoardMember;
ElectorSnapshot(election, source_version, eligible_status, contestability, freeze_at);
ElectorChangeProposal, ElectorObjection, EligibilityDecision;
Nomination, NominationCandidate, NominationSupportAudit, CandidateConsent, DeficiencyNotice;
ElectionScheduleDeadline, ElectionNotice, PublicationProof, DocumentVersion;
PollingSite, MaterialBatch, MailBallotRequest, MailBallotDispatch, MailBallotReceipt;
CountSession, CountSheet, IndependentTally, Reconciliation, AllocationResult, ResultRelease;
Acceptance, SubstituteMember, ChallengeCase, ArchiveRecord, RetentionPolicy, ElectoralAuditEvent.
Jedes Objekt enthält `tenant_id`, Scope, timestamps, Provenienz, ACL und optimistische Version; referentielle Integrität + idempotente Actions.

## Zustandsmaschine
draft → legal_pack_review → board_constituted → voters_review → notice_approved → nominations_open → nominations_review → ballot_preparation → voting_open → voting_closed → counting → reconciliation → result_approval → published → legal_remedy_window → archived.
Separate blocked/error/withdrawn/re_election States; keine Änderung veröffentlichter Versionen. Umkehr nur über dokumentierte Korrektur und gegebenenfalls neue Wahl, niemals Löschen der Historie. Papierwahl ist führend; elektronische Statusaktion kein Beweis, dass physischer Schritt erfolgt ist.

## Recht / Regelpakete
Quelle RLP LPersVG/WOLPersVG, je amtliche Rechtsversion; Wahlart, Personalgruppen, Dienststellendefinition, Wahlvorstandsbestellung, Sitzberechnung, Aufteilung, Personen-/Verhältniswahl, gemeinsame/getrennte Wahl, JAV, Sonderwahlen, Einspruch, Briefwahl und Dokumentationsfristen als regelversionierte Daten mit kommentierten Entscheidungsbäumen.
- `RulePack`: jurisdiction, source_url, publication_ref, effective_from/to, hash, approved_by_two_roles, immutability, test_vectors.
- Fristenengine hat Gesetz-/Verordnungsgrundlage je Termin, Kalender-, Arbeits-/Feiertagstyp, Fristbeginn/-ende, Ausnahme, manuelle Override-Entscheidung und Prüfpfad. Keine kalendarischen Defaults ohne rechtlich geprüfte Regeln.
- Sensible Datenänderungen und Wahlberechtigungsvorschläge durch zuständigen Wahlvorstand bestätigen.
- Rechtsänderung erzeugt neue Regelversion, ändert **keine** laufende Wahl stillschweigend. Kompatibilitäts-/Übergangsrecht prüfen.

## Fachabläufe
1. Wahl anlegen mit Dienststellen-/Wahlkörper-Wizard und Vorschau, konfigurierbare Basis aus TAKT-Org.
2. Wählerverzeichnis importieren (CSV/Excel, HR nur erlaubte Quellen) → prüfen/deduplizieren → stichtagsbinden → Einsprüche und Wahlvorstandsbeschluss → freigegebenes Verzeichnis. Keine automatische Offenlegung außerhalb berechtigter Bekanntgabe.
3. Wahlkalender/Fristen/ Aufgaben aus freigegebener Regelversion; Freigabestatus für Bekanntmachungen/Dokumente.
4. Wahlvorschläge und Kandidaturen erfassen, notwendige Originale prüfen, Einwände, Zustimmung und Nachfristen, Ergebnis: zugelassene Vorschläge.
5. Stimmzettel/Vordrucke DOCX/PDF, Seriendruck, Druckprüfung, Vorabstimmung soweit nötig, Wahlmaterial und Briefwahlausgabe/Nachweis.
6. Papierwahl / Wahllokalsteuerung: keine Online-Erfassung von Einzelstimmen mit Wählerlink. Briefwahl-Rücklauf dokumentiert nur administrative Rückläufe; sobald Stimmzettel anonymisiert sind, darf kein Verknüpfungsschlüssel zu Wählern bestehen.
7. Auszählung: getrennte Zählsätze durch berechtigte Zählteams, Gleichheits-/Ungültigkeitsregeln nach freigegebenem RulePack, reconciled count, Sitzverteilung mit erklärbaren Rechenschritten, Double Check und protokollierter Wahlvorstandsfreigabe.
8. Veröffentlichung nur redaktionell/gesetzlich erlaubter Ergebnisse, kontrollierte Bekanntgabe, Annahme/Nachrücken, Wahlanfechtung, geschützte Wahlakte.
9. Wahlakte exportierbar, Originaldokumenten-/Aufbewahrungsregeln ausdrücklich von Datenschutzfreigaben getrennt.

## Schnittstellen
- `elections/` dedizierte Services, `/elections` UI mit Rollen-/Modulschalter, kein Vertrauen auf Link- oder Menüverstecken.
- Adapter: organization/user_import (read-only snapshot, minimal), calendar (Fristen ohne vertrauliche Namen), tasks (neutrale Aufgabentitel), DMS (geschützte Referenz), documents (Templates), notification (minimale Metadaten).
- `/votes` nur in Designanalyse/Wiederverwendung barrierefreier UI-Elemente; kein gemeinsamer Stimmendatensatz.
- API mit Object/tenant ACL bei jeder Operation; sichere PDF/DOCX Renderjobs.
- Rollen, Module, Domains, Navigation, Agent-Tool-Liste und Handbuch automatisch per Registry-/CI-Prüfung synchronisieren.

## Sicherheits-/Qualitäts-/Freigabeanforderungen
Testdatensätze für Personen-/Verhältniswahl, Wahlgruppen, knappe Sitze, Ein-/Austritt um Stichtag, Fristenwechsel/Feiertage, fehlerhafte Vorschläge, Wahlanfechtung; Unabhängiger Sollrechner mit dokumentiertem Referenzmaterial.
Negativtests: Wahlvorstand sieht keine fremde Wahl, global admin keine Wahlgeheimnisse, Rücklauf nicht mit Stimmzettel korrelierbar, manipulierter URL/CSRF, unerlaubte Veröffentlichung, defekte Importdaten, Doppelzählung, blockierter Feature-Schalter.
UI-Tastatur, Screenreader, kontrastreich, responsive; Warnungen bei fehlender Rechtsfreigabe. Nicht live schalten ohne unabhängigen Fachabnahmetest des konkreten RulePacks und rechtliche Verantwortungsübernahme.
