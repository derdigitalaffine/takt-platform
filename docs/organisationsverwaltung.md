# Organisationsverwaltung

Unter **Administration → Organisation** wird die vorhandene Körperschaftsstruktur um frei kombinierbare Organisationsebenen ergänzt. Bestehende IDs und Verknüpfungen in Rechtstexten, Ressourcen, Krankmeldungen und Anträgen bleiben erhalten. Anschriften, Kontakt, Farben und Wappen werden direkt bei derselben Organisationseinheit gepflegt. Die früheren Körperschaftsadressen leiten hierher weiter.

## Personen und Gruppen

Eine Person hat eine Hauptzuordnung und beliebig viele zusätzliche Zuordnungen. Die erste Zuordnung wird automatisch zur Hauptzuordnung. Beim Wechsel bleibt die bisherige Hauptzuordnung zusätzlich bestehen. Dazu sind Zuordnungsrechte in beiden Einheiten erforderlich. Vor dem Entfernen einer Hauptzuordnung muss bei vorhandenen Zusatzzuordnungen eine andere Hauptzuordnung gewählt werden.

Für die Besetzungsplanung zählt die Hauptzuordnung standardmäßig mit, eine zusätzliche Zuordnung standardmäßig nicht. Dies ist je Zuordnung änderbar. Der Einsatzanteil beschreibt die organisatorische Zuordnung und ersetzt kein Arbeitszeitmodell. Die Urlaubsplanung prüft relevante Einheiten und Vorfahren gemeinsam.

Gruppen bleiben Freigabegruppen. Organisatorische Zuordnungen erzeugen keine Gruppenmitgliedschaften. Bereichsrollen können direkt Personen oder bestehenden Gruppen zugewiesen werden. Bei Gruppen gelten sie auch für künftige Mitglieder. Benutzer- und Gruppenverwaltung verlinken Zuordnungen sowie Herkunft und Geltungsbereich der Rollen.

## Komfortable Auswahl und Sammelaktionen

Personenzuordnungen und Bereichsrollen verwenden dieselbe Auswahl wie Kalenderfreigaben und die Mehrfachzuordnung von Arbeitsmodellen. Namen, E-Mail-Adressen und angezeigte Zusatzinformationen sind durchsuchbar. Gruppen lassen sich getrennt filtern. „Alle Treffer auswählen“ ergänzt nur sichtbare Treffer; eine neue Suche verändert zuvor ausgewählte Einträge nicht. Auswahlchips und eine Anzahl machen die Gesamtauswahl sichtbar. Entfernen einzelner Einträge und Leeren der Auswahl sind getrennte Aktionen.

Sammelaktionen umfassen maximal 500 eindeutige Einträge. Jede Person bzw. jedes Ziel wird mit den gleichen Bereichsprüfungen wie bei Einzelaktionen verarbeitet. Ein ungültiges oder unberechtigtes Ziel verwirft die gesamte Aktion. Ohne JavaScript stehen die nativen Kontrollkästchen und die serverseitigen Prüfungen zur Verfügung. Eine bestehende Hauptzuordnung in der aktuellen Einheit bleibt bei erneuter Zuordnung erhalten; ein Wechsel in eine andere Einheit benötigt weiterhin Rechte auf beiden Seiten.

## Rechte

Admins dürfen alles. Globale Rechte sind getrennt:

- **Organisation**: Struktur, Ebenentypen und Stammdaten pflegen.
- **Organisationszuordnungen verwalten**: Zuordnungen aller Personen pflegen.
- **Organisationsrollen vergeben**: Bereichsrollen vergeben und entziehen.

Bereichsrollen gelten wahlweise nur für die Einheit oder einschließlich Untereinheiten:

| Rolle | Umfang |
| --- | --- |
| Leitung | Bereich ansehen; Planung und Genehmigung |
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

Das fachliche Konzept für Kalender, Urlaubsplanung, Schließtage und Novatime-Parallelbetrieb steht in [kalender-urlaub-konzept.md](kalender-urlaub-konzept.md).
