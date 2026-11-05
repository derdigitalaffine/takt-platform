# PR #185 – Security-, Datenschutz- und Qualitätsreview

**Stand: 05.11.2026 · Reviewdokument für [PR #185](https://github.com/derdigitalaffine/takt-platform/pull/185), nicht für den bereits ausgelieferten Stand in `main`.** Eine Dokumentation von Prüfpunkten ersetzt keine Produktionsabnahme oder Freigabe der neuesten CI-Ausführung.

## Grundsatz: Ein Fachobjekt, eine führende Quelle

| Vorgang | Führendes Modul | Verwendung im Urlaubsplaner |
| --- | --- | --- |
| Urlaubsentwurf, Antrag, Entscheidung | `LeaveRequest` und verknüpftes `LeavePolicy` | Eigene Zeitachse, Rechte, Historie, Konfliktprüfung |
| Bereits vorhandene Abwesenheit und Vertretung | `Absence` im bestehenden Abwesenheits-/Vertretungsmodul | Read-only-Verfügbarkeit. Manuelle Vertretungszuordnung wird nicht überschrieben |
| Bei aktiviertem Sync aus Urlaub abgeleitete Abwesenheit | Dieselbe `Absence`-Tabelle, mit eindeutigem `LeaveRequest.absence_id` / `LeaveAbsencePeriod` | Verknüpfte Zeiten werden nicht als zweiter Eintrag erneut ausgegeben |
| Benutzerzugeordnete Krankmeldung | `KrankReport`, verschlüsselte Daten bleiben im Krankmelder | Nur Zeitraum und datensparsam klassifizierte Verfügbarkeit, **keine** Kopie der Krankmeldung |
| Bestätigte Seminarteilnahme | `SeminarEnrollment` und veröffentlichte `SeminarSession` | Read-only-Zeitfenster und Besetzungswirkung, keine zweite Seminar-/Abwesenheitstabelle |
| Schließzeit/Notbesetzung | `Closure`, `EmergencyAssignment` | Gemeinsam mit dem Kalender genutztes Fachobjekt, kein zweiter Kalenderbestand |
| Externe ZE-Software | Externes Fachverfahren | Nur optionaler Link und ausdrücklich ungeprüfte persönliche Selbstauskunft; keine technische Synchronisierung |

**Abwesenheitsüberschneidungen:** Für die Verfügbarkeitsberechnung zählen Personen je Zeitsegment nur einmal. Vorhandene bestätigte manuelle Abwesenheiten dürfen durch neue verbindliche Urlaubseinträge nicht still überschrieben werden. Rückwirkende und historische Fachdatensätze verbleiben in ihren Originalmodulen.

## Autorisierung und Schutz vor Privilegienausweitung

- Jede mutierende Organisationsoperation prüft die aktuell berechtigte Organisationseinheit und die konkrete Fähigkeit (`members`, `roles`, `leave_settings`, `approve`). Ein fehlendes Menüelement allein schützt keine Operation.
- **Leitung** und **Stellvertretung** besitzen gleichwertige Fachrechte für Planung/Genehmigung; Verwaltungs- und Rollenrechte bleiben separat. Jede Rollenvergabe kann unabhängig entscheiden, ob Untereinheiten eingeschlossen sind. Mehrere Stelleninhaber sind zulässig.
- Eigener Urlaub benötigt bei aktiviertem internen Verfahren eine Entscheidung durch eine andere zuständige Person, einschließlich einer Stornierung bereits verbindlicher Zeiten. Der Standardweg führt für Leitungen/Stellvertretungen nach oben; explizite Genehmigungswege haben Vorrang. **Auch bei nachträglichen Änderungsentwürfen** verbleibt eine Stornierungsentscheidung ohne gesonderte Freigabekonfiguration bei der übergeordneten Stelle und darf nicht an andere Leitungen derselben Einheit zurückfallen.
- Eine ausdrücklich einem Elternbereich zugewiesene Genehmigung ist dort sichtbar, auch wenn die jeweilige Rolle **nicht** pauschal für Untereinheiten gilt. Dadurch entsteht **kein** allgemeines Recht, beliebige Krank- oder Urlaubsgründe aller Untereinheiten einzusehen.
- Der gemeinsame Personen-Editor dient beiden Verwaltungsseiten. Die API prüft Bearbeitungsfähigkeit je Einheit, den aktuellen Organisationsversionsstand und alle Änderungen innerhalb einer Transaktion. Bei fehlerhaften oder unberechtigten Zielobjekten gibt es keine Teilübernahme.
- Sammeländerungen an Bereichsrollen ergänzen ausgewählte Rollen oder entziehen ausdrücklich ausgewählte Rollen; nicht genannte Rollen bleiben bestehen. Die Vorschau listet sämtliche betroffenen Ziele (bis zum bestehenden Maximum von 500).

## Vertraulichkeit von Krank- und Abwesenheitsdaten

- Die Kalender-Zeitachse gibt nicht zuständigen Kolleginnen und Kollegen für fremde Abwesenheitsgründe ausschließlich **„Abwesend“** zurück – nicht nur ein im Browser verstecktes Feld.
- Der Krankstatus **„Krank“** ist auf betroffene Personen, Administrationsberechtigte, ausdrücklich zuständige Leitungen/Stellvertretungen und fachlich autorisierte Stellen beschränkt. Die besondere Unterart einer Krankmeldung (zum Beispiel Kindkrank) wird im Planer **nicht** weitergegeben.
- Inhalte von Krankmeldungen, Diagnosen, Nachweise, Klartextnotizen und Anhänge werden nicht in `/urlaub/data`, in die Urlaubsantragsdaten oder in den Kalender exportiert. Der bestehende Krankmelder bleibt für die Zugriffe auf Gesundheitsdaten verantwortlich.
- Benutzerzuordnung erfolgt nur über `KrankReport.user_id` beziehungsweise `SeminarEnrollment.user_id`, **nicht** durch erratene Namen oder E-Mail-Ähnlichkeit.
- Eine neue Projektion in externe ICS-/CalDAV-Abonnements ist **nicht** Teil dieses PR. Für eine spätere Ausweitung müssen die serverseitigen Sichtbarkeitsprüfungen und die Token-/Freigabeprüfung der jeweiligen Exportwege gesondert getestet werden.

## Transaktionen, CSRF und Eingabevalidierung

- Mutierende Formulare nutzen den vorhandenen CSRF-Schutz, Berechtigungskontrollen und – bei konkurrierenden Änderungen – den Versionsstand des Fachobjekts bzw. der Organisation.
- Die vier Policy-Reiter **Verfahren**, **Besetzung**, **Feiertage** und **Urlaubskonten** übermitteln ihren Reiternamen. Der Server speichert jeweils **nur die dazugehörigen Felder**; manipulierte Felder anderer Reiter bleiben wirkungslos. Arbeitsmodelle nutzen weiterhin ihre bereits bestehende eigene Fachroute.
- Vor dem ersten lokalen Reiter-Edit werden bislang wirksame übergeordnete Policy-Werte in die *eine* lokale `LeavePolicy` übernommen. **Wichtig:** Die bestehende Tabellenstruktur vererbt vollständige Policys, keine einzelnen Felder. Nach dem ersten lokalen Edit sind andere übernommene Werte daher ein **Snapshot** und reagieren nicht mehr automatisch auf spätere Änderungen am Elternbereich. Keine separate Schatten-Policy wird erzeugt. Eine echte feldweise Vererbung erfordert eine eigene, explizit migrations- und regressionstestbare Erweiterung.
- „Alle lokalen Bereichsregeln zurücksetzen“ ist ausschließlich im Verfahren-Reiter sichtbar, benennt die **vollständige** Wirkung und verlangt Bestätigung. Die Aktion löscht den lokalen Policy-Datensatz und aktiviert damit die vorhandene Vererbung erneut.
- Externe Zieladressen werden auf HTTP(S), gültigen Host, begrenzte Länge und fehlende eingebettete Zugangsdaten geprüft. Rücksprung-Adressen bei Formularaktionen werden auf dieselbe Herkunft und fest zugelassene Urlaubsrouten beschränkt.
- Die freiwillige Bestätigung „Extern genehmigt“ ist **standardmäßig ausgeschaltet**. Sie ist nur durch die betroffene Person zulässig und bleibt eine als solche gekennzeichnete Selbstauskunft, niemals ein verifizierter Status der externen ZE-Software.

## UI, Stabilität und Testmatrix

| Prüffeld | Absicherung |
| --- | --- |
| Genehmigung ohne pauschale Untereinheitenrechte | `tests/test_leave.py::test_parent_only_approver_sees_assigned_request_not_unrelated_leave` |
| Rollen- und Storno-Selbstentscheidung | `test_leader_cannot_approve_own_leave_and_defaults_to_parent` und `test_leadership_cannot_decide_own_internal_cancellation` |
| Keine Dopplung und Datenschutz beim Krankmelder | `test_existing_krankmeldung_is_private_read_only_projection` und `test_illness_source_reduces_staffing_without_duplicate_absence_records` |
| Isoliertes Speichern pro Konfigurationsreiter | `test_settings_tab_ignores_hidden_fields_and_preserves_other_settings` |
| Inherited Policy beim ersten lokalen Reiter-Edit | `test_first_scoped_settings_save_preserves_inherited_workflow` |
| Eigener Urlaub trotz anderer Leitungseinheit | `test_own_leave_remains_visible_when_leadership_selects_another_unit` |
| Gemeinsamer Rollen-Editor und Berechtigungsmatrix | `tests/test_organization.py` sowie `tests/browser/organization_ui_smoke.py` |
| Mobile Urlaubsbearbeitung und Kalenderkompatibilität | `tests/browser/leave_ui_smoke.py` |
| Gesamtrepo ohne unbeabsichtigte Seiteneffekte | GitHub-Workflow „Portal tests“ mit `pytest` und bestehenden Browser-Jobs |

**Freigaberegel:** Erst wenn der endgültige Head-Commit erfolgreich getestet und der PR reviewt ist, den Draft-Status aufheben. Ältere grüne Läufe belegen die neuesten Änderungen nicht automatisch.

## Betriebs- und Produktgrenzen

1. Vor dem Deployment Datenbankbackup und migrationssicheren Test mit Kopie des Produktionsschemas durchführen; das neue Feld für externe Selbstauskunft wird additiv mit dem sicheren Standard `False` ergänzt.
2. Ein vollständiges minutengenaues Gleitzeitkonto, zusätzliche fachliche Abwesenheitsarten mit unabhängigen Stundenregeln und automatischer Datenaustausch mit der externen ZE-Software gehören **nicht** zum vorliegenden PR; keine neuen Parallel-Quelltabellen erstellen.
3. Schul-/Seminarzeiten nutzen nur fachlich verifizierte, einem Benutzer zugeordnete und im vorhandenen Modul erfasste Termine. Eine noch nicht vorhandene Berufsschulquelle darf nicht durch Vermutungen nachgebildet werden.
4. Es liegen automatisierte Chromium-Prüfungen vor, aber keine belastbare vollständige Abnahme auf physischen iOS-/Androidgeräten und in allen Outlook-/CalDAV-Clients.
5. Die „Krank“-Anzeige ist ein sensibles personenbezogenes Datum. Das konkrete Rollen- und Berechtigungskonzept ist vor produktivem Einsatz mit den zuständigen Datenschutz-/Personalstellen abzustimmen.

## Manuelle Review-Checkliste vor Merge

- [ ] Mit Arbeitnehmerkonto und Leitungskonto dieselbe Organisationseinheit öffnen und den gesonderten Zugriff auf Krankgründe inklusive **Netzwerkantworten** prüfen.
- [ ] Als reiner Viewer eine fremde Krankmeldung, einen Urlaub und ein Seminar öffnen; ausschließlich „Abwesend“ erhalten.
- [ ] Leitung in A mit eigener Hauptzuordnung B: „Mein Urlaub“, eigene Planung und externe Selbstauskunft überprüfen; keinesfalls eigene Genehmigung oder Stornoentscheidung zulassen.
- [ ] Als nur für übergeordnete Einheit berechtigter Genehmiger einen ausdrücklich zugewiesenen Antrag bearbeiten; andere Anträge bleiben verborgen.
- [ ] In allen vier Policy-Reitern einzeln speichern, die jeweils anderen Werte danach prüfen, und den vollständigen Reset bewusst bestätigen.
- [ ] Mehrfachrollen aus Organisation und Benutzerliste vergeben/entziehen; Personen dürfen nicht doppelt erscheinen und Rollen dürfen nicht ungefragt überschrieben werden.
- [ ] Im mobilen Planer Zeitraum markieren, Vorschau/Bestätigung anzeigen, Seitenpanel schließen; bei älteren Kalenderabos und URLs keine Regression.
- [ ] Finale Python- und Chromium-CI einschließlich der letzten Migration, Formatierung und Sicherheitsregressionen auf dem **aktuellen** PR-Commit grün.

Siehe auch [Implementierungs- und Freigabestand](kalender-urlaub-umsetzungsstand.md), [Organisationsverwaltung](organisationsverwaltung.md), [Admin-Handbuch](ADMIN-HANDBUCH.md) und [PR #185](https://github.com/derdigitalaffine/takt-platform/pull/185).
