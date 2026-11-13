# Organisationsverwaltung

Seit [PR #182](https://github.com/derdigitalaffine/takt-platform/pull/182) und [PR #184](https://github.com/derdigitalaffine/takt-platform/pull/184) ist die gemeinsame Organisationsverwaltung in `main` integriert. Unter **Administration → Organisation** wird die vorhandene Körperschaftsstruktur um frei kombinierbare Organisationsebenen ergänzt. Bestehende IDs und Verknüpfungen in Rechtstexten, Ressourcen, Krankmeldungen und Anträgen bleiben erhalten. Anschriften, Kontakt, Farben und Wappen werden direkt bei derselben Organisationseinheit gepflegt. Die früheren Körperschaftsadressen leiten hierher weiter.

## Personen und Gruppen

Eine Person hat eine Hauptzuordnung und beliebig viele zusätzliche Zuordnungen. Die erste Zuordnung wird automatisch zur Hauptzuordnung. Beim Wechsel bleibt die bisherige Hauptzuordnung zusätzlich bestehen. Dazu sind Zuordnungsrechte in beiden Einheiten erforderlich. Vor dem Entfernen einer Hauptzuordnung muss bei vorhandenen Zusatzzuordnungen eine andere Hauptzuordnung gewählt werden.

Für die Besetzungsplanung zählt die Hauptzuordnung standardmäßig mit, eine zusätzliche Zuordnung standardmäßig nicht. Dies ist je Zuordnung änderbar. Der Einsatzanteil beschreibt die organisatorische Zuordnung und ersetzt kein Arbeitszeitmodell. Die Urlaubsplanung prüft relevante Einheiten und Vorfahren gemeinsam.

Gruppen bleiben Freigabegruppen. Organisatorische Zuordnungen erzeugen keine Gruppenmitgliedschaften. Bereichsrollen können direkt Personen oder bestehenden Gruppen zugewiesen werden. Bei Gruppen gelten sie auch für künftige Mitglieder. Benutzer- und Gruppenverwaltung verlinken Zuordnungen sowie Herkunft und Geltungsbereich der Rollen.

## Komfortable Auswahl und Sammelaktionen

Personenzuordnungen und Bereichsrollen verwenden dieselbe Auswahl wie Kalenderfreigaben und die Mehrfachzuordnung von Arbeitsmodellen. Namen, E-Mail-Adressen und angezeigte Zusatzinformationen sind durchsuchbar. Gruppen lassen sich getrennt filtern. „Alle Treffer auswählen“ ergänzt nur sichtbare Treffer; eine neue Suche verändert zuvor ausgewählte Einträge nicht. Auswahlchips und eine Anzahl machen die Gesamtauswahl sichtbar. Entfernen einzelner Einträge und Leeren der Auswahl sind getrennte Aktionen.

Sammelaktionen umfassen maximal 500 eindeutige Einträge. Jede Person bzw. jedes Ziel wird mit den gleichen Bereichsprüfungen wie bei Einzelaktionen verarbeitet. Ein ungültiges oder unberechtigtes Ziel verwirft die gesamte Aktion. Ohne JavaScript stehen die nativen Kontrollkästchen und die serverseitigen Prüfungen zur Verfügung. Eine bestehende Hauptzuordnung in der aktuellen Einheit bleibt bei erneuter Zuordnung erhalten; ein Wechsel in eine andere Einheit benötigt weiterhin Rechte auf beiden Seiten.

## Gemeinsamer Organisations- und Benutzer-Editor (PR #185)

Der [Integrations-PR #185](https://github.com/derdigitalaffine/takt-platform/pull/185) (mit [Security- und Abnahmecheckliste](SECURITY-REVIEW-PR185.md)) verbindet **Administration → Organisation** und **Benutzer & Gruppen** über denselben mobilen Seitenpanel-Editor. Haupt-/Zusatzzuordnungen, Besetzungsrelevanz, Einsatzanteil und beliebig viele Bereichsrollen werden in einer zusammengefassten Bearbeitung verarbeitet. Alle betroffenen Daten werden mit dem vorhandenen globalen Organisationsversionsstand geprüft und in einer Transaktion gespeichert; bei fehlenden Rechten oder veraltetem Stand erfolgt keine Teilübernahme. Gruppenrollen bleiben eigenständige Zuweisungen.

Die Organisation zeigt eine **Exploreransicht** mit Baum und eine alternativ auswählbare **hierarchische Tabelle** mit Such- und Kontextfunktionen. In Rollenübersichten erscheint jede Person nur einmal pro Einheit; ihre Rollen einschließlich geerbter Geltungsbereiche erscheinen als Chips. Rollen können in der Sammelbearbeitung **mehrfach ausgewählt und ergänzt oder gezielt entzogen** werden, ohne nicht ausgewählte Rollen zu ersetzen. Jede Rolle bekommt individuell die Option „einschließlich Untereinheiten“. Personenbezogene Änderungen sind sowohl aus der Benutzerliste als auch dem Organisations-Explorer erreichbar.

**Leitung und stellvertretende Leitung** sind unterschiedliche sichtbare Bezeichnungen mit identischen fachlichen Rechten für Planung und Genehmigung. Es dürfen mehrere Leitungen und Stellvertretungen je Einheit tätig sein. Sie erhalten damit weder automatisch globale Administratorrechte noch das gesonderte Recht zur Urlaubsregel- oder Rollenverwaltung; eigene Urlaubsanträge können sie nicht selbst genehmigen. Beide Tags werden in den fachlich relevanten Personenansichten dargestellt.

Der zuletzt verwendete, weiterhin freigegebene Organisationsbereich wird für Kalender, Urlaub und Organisationsübersicht übernommen; direkte Links bleiben maßgeblich. Benutzerinnen und Benutzer können zwischen komfortabler und kompakter Darstellung wechseln. Diese Einstellung sowie Explorer-/Tabellenwahl werden im eigenen Benutzerkonto gespeichert.

## Rechte

Admins dürfen alles. Globale Rechte sind getrennt:

- **Organisation**: Struktur, Ebenentypen und Stammdaten pflegen.
- **Organisationszuordnungen verwalten**: Zuordnungen aller Personen pflegen.
- **Organisationsrollen vergeben**: Bereichsrollen vergeben und entziehen.

Bereichsrollen gelten wahlweise nur für die Einheit oder einschließlich Untereinheiten:

| Rolle | Umfang |
| --- | --- |
| Leitung | Bereich ansehen; Planung und Genehmigung |
| Stellvertretende Leitung | Dieselben fachlichen Planungs- und Genehmigungsrechte wie Leitung, als Stellvertretung gekennzeichnet |
| Bereichsplanung | Bereich ansehen; Planung |
| Genehmigung | Bereich ansehen; Genehmigung |
| Zuordnungen verwalten | Zuordnungen innerhalb des Bereichs pflegen |
| Bereichseinstellungen | Stammdaten, Anschrift, Kontakt und Wappen pflegen; kein Verschieben oder Aktivieren |
| Abwesenheiten verwalten | Bestehende Abwesenheiten der Personen mit Hauptzuordnung im Bereich verwalten |

Bereichsrollen vergeben keine globalen Rechte und erlauben weder Konten-/Gruppenverwaltung noch das Delegieren von Rollen. Das Kalender-/Urlaubsmodul verwendet Planungs- und Genehmigungsrollen für die konfigurierten Abläufe. Die gesonderte Rolle „Urlaubsregeln verwalten“ erlaubt das Einstellen von Ablauf, Besetzung, Arbeitsmodellen, Schließzeiten und internen Ansprüchen. Leitungen erhalten bewusst nicht automatisch die separate Rolle zur Verwaltung vorhandener Abwesenheiten und Vertretungen.

Ein inaktiver Vorfahr deaktiviert geerbte Bereichsrechte für dessen Zweig. Globale Verwalter können inaktive Strukturen weiterhin pflegen. Strukturänderungen mit Auswirkungen auf bestehende Zuordnungen oder Rollen benötigen zusätzlich die jeweiligen globalen Rechte. Rollenführende Gruppen und Konten sind vor Änderungen durch schwächer berechtigte Benutzerverwalter geschützt; dies umfasst CSV-Import und Passwortzurücksetzen.

## Betrieb und Nachvollziehbarkeit

Der Start legt additive Tabellen für Ebenentypen, Zuordnungen, Rollenzuweisungen, Änderungsprotokoll und Versionsstand an. Es werden keine bestehenden Organisationseinheiten ersetzt oder automatisch Personen zugeordnet. Ein Backup vor einem Softwareupdate bleibt Bestandteil des üblichen Betriebsablaufs.

Alle Organisationsaktionen einschließlich der bisherigen kompatiblen Schreibadressen prüfen einen gemeinsamen Versionsstand. Veraltete Änderungen werden mit HTTP 409 abgelehnt. Neue Organisationsaktionen werden mit handelnder Person, Zeitpunkt und sachlichen Änderungsdaten protokolliert. Die Oberfläche zeigt die letzten Änderungen der ausgewählten Einheit.

Die Organisationsstruktur und ihre Bereichsrollen bilden die Freigabegrundlage für **Kalender & Urlaub**. Das Modul bleibt nach dem Update zunächst ausgeschaltet; Admins aktivieren es unter **Module** und konfigurieren je Organisationseinheit Planung, Genehmigung, Feiertage und Besetzung in der Urlaubsansicht. Im Planungsbereich bleiben Zeitraum und Zoom bei mehreren Speichervorgängen erhalten; außerhalb liegende neue Urlaubszeiten werden direkt im passenden Zeitraum gezeigt. Das [fachliche Konzept](kalender-urlaub-konzept.md), die [Umsetzung und Abnahme](kalender-urlaub-umsetzungsstand.md) sowie das [Admin-Handbuch](ADMIN-HANDBUCH.md#kalender--urlaubsplanung-konfigurieren) erläutern Details und Grenzen.

## Personalratswahl – getrennte Fachmandate

Das Modul Personalratswahl verknüpft jede Wahl über `org_id` mit einer bestehenden Organisationseinheit. Bei der Einrichtung ist zusätzlich zum globalen Recht `prwahl_setup` eine eigene Organisationszuordnung oder die Berechtigung für Bereichseinstellungen der gewählten Einheit erforderlich; Administratoren können die technische Einrichtung vornehmen. Inaktive Einheiten und inaktive Vorfahren können nicht verwendet werden.

**Die Organisationshierarchie vererbt ausdrücklich keine Einsicht in Wahlakten.** Leitung, Stellvertretung, Bereichsplanung, Genehmigung und globale Administratoren erhalten durch ihre Organisationsrechte kein Wahlmandat. Für jeden Wahlbereich müssen eigenständige, nachweisbare Fachmandate vergeben werden: technische Einrichtung (`coordinator`), Wahlvorstandsvorsitz (`chair`), Wahlvorstandsmitglied (`member`), Schriftführung (`clerk`), Rechtsprüfung (`legal`) oder eingeschränkte Prüfung (`auditor`). Die Wahlvorstandsbestellung wird durch die Rollenvergabe im Portal nicht ersetzt. Fachmandate werden bei jeder Wahlroute separat geprüft, einschließlich Kalenderexport, Auszählung und Dokumentenzugriff. Inaktive Benutzerkonten und deaktivierte Organisationszweige sind gesperrt.

Die technische Einrichtungsrolle ist **keine Wahlvorstandsrolle**. Die verbindliche Ergebnisbestätigung und das Versenden von Wahlvorstandseinladungen bleiben dem explizit zugeordneten Vorsitz vorbehalten. Organisationsmitgliedschaft ist keine Voraussetzung für eine rechtmäßig bestellte externe Wahlvorstandsperson; deren Fachmandat wird explizit und nachweisbar vergeben. Die Zuordnung zu anderen TAKT-Modulen erzeugt weder zusätzliche Wahlrechte noch veröffentlicht sie Wahlakten.
