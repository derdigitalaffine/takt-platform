# Umfragen: Teilnahmeerkennung und sichere Weiterentwicklung

Stand: 12. November 2026 · Beschlussgrundlage: zehnstufiges TAKT-Interview, alle Entscheidungen **D**.

## Zielbild

TAKT erhält eine einheitliche **Teilnahmeoberfläche und Integrationsschicht** für Formularumfragen,
Terminumfragen, Abstimmungen und Live-Umfragen. **Nicht** vereinheitlicht werden die
fachlichen Antwort-Engines, wo ihre Semantik abweicht.

Verbindlich geplant:

1. Abgeschlossene Teilnahmen erkennen; Bearbeitung, weitere Einreichung und Einsicht konfigurierbar.
2. Berechtigte Zugangswege eines Benutzers zusammenführen, ohne anonyme Antwortinhalte zu verknüpfen.
3. Antwortkorrekturen als Änderung der vorhandenen Teilnahme, mit fristgebundener Freigabe und
   datenschutzgerechter Versionierung; keine zusätzliche Rücklaufzählung.
4. Teilnahmecockpit mit Rücklauf, Verantwortlichkeiten, Filtern, Ausnahmen und Berechtigungen.
5. Freiwillige, begrenzte mehrstufige Erinnerungen; abgeschlossene Einladungen beenden Erinnerungen.
6. Einmalige oder bewusst mehrfache Einreichungen, öffentliche und persönliche Links, anonyme
   Teilnahmerechte und transparente Grenzen der Wiedererkennung.
7. „Meine Umfragen“, Dashboard, „Meine Aufgaben“, persönliche Statusübersicht ohne Dateneinsicht,
   wo Vertraulichkeit entgegensteht.
8. Unterschiedlich freigegebene Ergebnisse mit Mindestgruppengrößen und Schutz vor
   Reidentifizierung durch kleine Filtergruppen.
9. Ereignisbasierte optionale Integrationen in Organisation, Kalender, Seminare, Besprechungen,
   Prozesse, Benachrichtigungen und KI; deaktivierte Module dürfen Kernfunktionen nicht sperren.
10. Inkrementelle Einführung mit Datenmigration, Tests, Rückfallkonzept und PR/CI-Gates.

## Unveränderliche Live-Umfrage-Invarianten

Die bestehende Live-Engine in `live.py` und `routes_live.py` bleibt **autoritativ** für
`/l/{token}`, `/l/{token}/answer`, `/l/{token}/upvote` und den Moderationszustand.

- **Ein Gerät, eine änderbare Antwort je Frage**: `X-Live-Device` und gerätebezogener
  Hash bleiben für Teilnahme und Anonymität erforderlich.
- **Quiz**: richtige Lösungen und Scoreboard bleiben bis zur Freigabe verborgen;
  Freigabe sperrt Antworten; Zeitlimits werden auf dem Server geprüft.
- **Wortwolke, Pinnwand, Q&A**: Spezialregeln zur Eingabemenge, Moderation und zum
  Hochstimmen dürfen nicht als normale Formularantwort behandelt werden.
- **Moderierter/freier Ablauf**: nur aktive Fragen beantworten; Sperrungen, manuelle
  Freigabe und bewusstes Zurücksetzen/Neustarten einer Runde bleiben unverändert.
- **Beamer und Export**: keine unberechtigte Einsicht in Lösungen oder Antworten;
  Gerätetoken, Gerätehashes und Anzeigenamen nicht in anonymen Rohdaten exportieren.
- **QR-Codes, öffentliche Teilnahmen und Seminarschnittstellen** bleiben verwendbar,
  ohne Anmeldung oder erzwungene Benutzeridentität.
- **Live-Zwischenergebnisse** sind eine eigene Freigabeart, die nicht durch
  allgemeine Ergebnisfreigaben überschrieben werden darf.

Die geplante gemeinsame Teilnahmeansicht darf Live-Umfragen nur über einen
**lesenden Adapter** integrieren; keine FK-Verknüpfung der Live-Antworten mit
User-IDs und keine Änderung bestehender Antwort-/Moderationsrouten.

Bestehende Regressionen: `portal/tests/test_live.py`,
`portal/tests/test_live_quiz.py`, `portal/tests/test_survey_workspace.py`.
Vor jeder Live-Integration zusätzlich Browserprüfung: Smartphone-QR, erneute Antwort,
Freigabe, Timer, Reset, Wortwolke, Q&A, Beamer, Export und Anonymität.

## Inkrement 1: sichere Teilnahmeerkennung (dieser PR)

Änderungen betreffen ausschließlich bestehende Formularumfragen (nicht Live-Umfragen).
Bekannte angemeldete Personen werden anhand bereits gespeicherter
nicht-anonymer Antworten erkannt – unabhängig davon, ob sie über einen öffentlichen
oder persönlichen Link eingereicht wurden. Der offene-Einladungen-Bereich zieht
ältere, eindeutig zuordenbare Antworten hinzu. Neue Antworten über öffentliche Links
markieren passende Einladungen als erledigt.

Anonyme oder nicht angemeldete öffentliche Besucher erhalten ausschließlich einen
signierten, nicht identifizierenden **Browser-Beleg** für denselben öffentlichen Link.
Er verhindert versehentliche Doppeleinreichungen **in diesem Browser**, aber **nicht**
eine zweite Teilnahme über ein anderes Gerät, gelöschte Cookies oder private Fenster.
Das ist keine Wahlberechtigungsprüfung. Mit `multiple=True` sind weitere Einreichungen
ausdrücklich weiterhin möglich und werden vor der erneuten Eingabe angekündigt.

Online-Anträge werden vom Abgleich nach `FormResponse` ausgenommen: mehrere
fachlich eigenständige Anträge derselben Person müssen weiterhin möglich sein.
Seminar-Evaluationsformulare nutzen ihre eigenständige Abschlusslogik; das Inkrement
ändert deren Routing nicht.

**Bestandsschutz:** Keine neuen Tabellen oder destruktiven Migrationen; bestehende
Antworten, persönlicher Einladungscode und öffentliche Links bleiben erhalten.

## Inkrement 2: persönlicher Umfrage-Arbeitsplatz

Separater, lesender Adapter `my_surveys.py`: `/meine-umfragen` zeigt
persönliche Formular-Einladungen, identifizierbare eigene Formularantworten,
Terminumfrage-Einladungen und Einträge im Wählerverzeichnis. Der Adapter
fragt ausschließlich den **Teilnahmestatus** ab – niemals Ballots,
Frageantworten oder Live-Gerätehashes. Das ist bewusst kein Ersatz für
das später geplante gemeinsame transaktionale Berechtigungsmodell.

- Nicht-anonyme Formularteilnahmen werden konto- bzw. persönlich
  einladungsbasiert zusammengeführt; mehrfach vorhandene Antworten bleiben
  eine Übersichtskachel je Umfrage. Anonyme Einladung: nur `submitted_at`.
- Terminumfragen: nur eindeutig zugeordnete `user_id` oder nachweislich
  durch den Organisator angelegte Einladungen (`invited_at`) mit zur
  Portalanmeldung passender E-Mail. **Öffentliche** Angaben einer beliebigen
  E-Mail-Adresse reichen nicht zum Kontozugriff auf einen persönlichen
  Änderungstoken. Die Startseitenanzeige verwendet dieselbe Einschränkung.
- Abstimmungen: nur eigene Wählerverzeichniseinträge bzw. echte persönliche
  Einladungen. Es wird nie auf `VoteBallot` zugegriffen. Bei geheimer Wahl
  nur der Status „abgegeben“, niemals die eigene Stimmabgabe als Antwort.
- Live-Umfragen: **nicht** im persönlichen Verlauf; gerätebezogene
  Teilnahmen sind absichtlich keine Benutzeridentität. Moderator-/Quiz-/
  QR-Antwortwege bleiben unverändert.
- Offene persönliche Einladungen werden über die bestehende
  `task_overview` als Quelle „Umfragen“ in „Meine Aufgaben“ eingebunden
  und nach Erledigung aus der offenen Liste entfernt.
- Der Weg ist modulunabhängig: Nur Formularserver, nur Umfrage-/Abstimmungsmodul,
  beide, oder keines davon aktiv; ohne aktiviertes Modul liefert die Route 404.
- Kein neues Datenbankschema, keine Änderungen an Live-Endpunkten,
  keine automatische Erinnerungsflut und keine Rückwirkung auf Anträge.

Regressionssuite: `test_my_surveys.py` sowie die vorhandenen
`test_live.py`, `test_live_quiz.py` und Browsertests.

## Inkrement 3: berechtigtes, lesendes Teilnahme-Cockpit

`/teilnahme-cockpit` verwendet die bereits vorhandenen ACL-Mechanismen
für Formular-, Termin- und Stimmabfragen; für Live-Umfragen ist nur die
Besitzerrolle (oder Portaladministration) freigeschaltet. Ergebnisansichten
der jeweiligen Fachmodule bleiben die alleinigen Quellen für fachliche
Einzeldaten und dynamische Veröffentlichungsregeln.

- Das Cockpit liefert Einladungszahlen, erledigte Einladungen, offene
  Einladungen und gegebenenfalls die Gesamtzahl der Antworten.
- In den Summen wird zwischen **Rücklauf aus Einladungen** und zusätzlichen
  öffentlichen Antworten unterschieden. Für öffentliche Teilnahme ohne
  Einladung ist eine verlässliche Quote nicht berechenbar.
- Ein anonymes Live-Gerät wird nur als **aggregierter Distinct-Count** gezählt;
  weder Gerätehash, Anzeigename noch Antworten werden zurückgegeben.
- Bei geheimer Wahl wird ausschließlich `VoteVoter.voted`/Berechtigung
  aggregiert. Es erfolgt kein Zugriff auf `VoteBallot`.
- Die Sichtbarkeit ist unabhängig von der Teilnahmesicht der
  eingeladenen Person: Persönliche Einladung ist keine Berechtigung,
  andere Teilnahmen auszuwerten. Das Cockpit erfordert Besitzer/Admin
  oder mindestens Einladungs-/Managementfreigabe.
- Alle Datensätze bleiben in den ursprünglichen Engine-Tabellen;
  es sind keine Migrationen oder Änderungen an Live-POST-Endpunkten nötig.

Regressionssuite: `portal/tests/test_survey_cockpit.py` plus
`test_live.py`, `test_live_quiz.py`, `test_my_surveys.py`
und die bestehenden Browserprüfungen.

## Weitere Ausbaustufen


- Einheitliches fachliches Teilnahme-API je Engine mit getrenntem Identitäts-,
  Berechtigungs- und Antwortmodell; Adapter statt globaler Duplikatsperre.
- Anonyme Einmalberechtigungen per persönlichem, von Antwortdaten getrenntem Token,
  mit offen dokumentierten Bedrohungsmodellen und Vorab-Datenschutzprüfung.
- Korrektur-Workflow mit Versionierung, Fristen, Änderungsfreigaben und gesperrten
  förmlichen Stimmen.
- Neue Oberfläche „Meine Umfragen“/Teilnahmecockpit, Aufgaben- und Benachrichtigungsadapter.
- Ergebnisfreigaben mit Aggregationsschwellen, Filter-Suppression und Auditierung.
- Optionaler Reminder-Worker mit Idempotenz, Zustellstatus und Versandlimits.
- Schema-Migration, schrittweise Aktivierung, Browserabnahme, Daten-Backup und
  Rollback vor breiter Produktivsetzung.

**Wichtige technische Einschränkung:** Die Abfrage einer vorhandenen Antwort und
das Anlegen einer neuen Antwort sind in diesem ersten Inkrement noch keine
datenbankseitig atomare Einmalteilnahme-Garantie bei parallelen Requests.
Die spätere Teilnahme-/Berechtigungs-Engine benötigt dafür serverseitig
transaktional durchgesetzte Eindeutigkeitsbedingungen für einmalige Zugänge.
Ebenfalls darf aus einer Browser-Wiedererkennung keine personenbezogene
Anonymitätszusage abgeleitet werden.

## Prüfung und Rollout

1. Gesamte Portal-Pytest-Suite, insbesondere `test_survey_participation.py`,
   `test_live.py`, `test_live_quiz.py`.
2. Vor Freigabe öffentliche Links (mit/ohne Anmeldung), individuelle Einladungen,
   Anonymität, ausdrücklich erlaubte Mehrfachabgaben und Antragsausnahme testen.
3. Live-Endpunkte und Datenschutz-Regressionen bei jeder Änderung erneut prüfen.
4. Nach bestandenem PR-Merge Deployment gesondert ausführen; Merge bedeutet
   noch keine produktive Aktivierung. Bei Rollback vorherigen Anwendungsstand
   deployen; dieses Inkrement hat keine Datenschemamigration.
