# Organisationsverwaltung

Unter **Administration → Organisation & Rollen** wird die vorhandene Körperschaftsstruktur um frei kombinierbare Organisationsebenen ergänzt. Bestehende IDs und Verknüpfungen in Rechtstexten, Ressourcen, Krankmeldungen und Anträgen bleiben erhalten. Anschriften und Wappen werden weiterhin im verlinkten Stammdateneditor gepflegt.

## Personen und Gruppen

Eine Person hat eine Hauptzuordnung und beliebig viele zusätzliche Zuordnungen. Die erste Zuordnung wird automatisch zur Hauptzuordnung. Beim Wechsel bleibt die bisherige Hauptzuordnung zusätzlich bestehen. Dazu sind Zuordnungsrechte in beiden Einheiten erforderlich. Vor dem Entfernen einer Hauptzuordnung muss bei vorhandenen Zusatzzuordnungen eine andere Hauptzuordnung gewählt werden.

Für die künftige Besetzungsplanung zählt die Hauptzuordnung standardmäßig mit, eine zusätzliche Zuordnung standardmäßig nicht. Dies ist je Zuordnung änderbar. Der Einsatzanteil beschreibt die organisatorische Zuordnung und ersetzt kein Arbeitszeitmodell. Eine Besetzungsberechnung ist noch nicht Bestandteil dieses Bausteins.

Gruppen bleiben Freigabegruppen. Organisatorische Zuordnungen erzeugen keine Gruppenmitgliedschaften. Bereichsrollen können direkt Personen oder bestehenden Gruppen zugewiesen werden. Bei Gruppen gelten sie auch für künftige Mitglieder. Benutzer- und Gruppenverwaltung verlinken Zuordnungen sowie Herkunft und Geltungsbereich der Rollen.

## Rechte

Admins dürfen alles. Globale Rechte sind getrennt:

- **Körperschaften (Stammdaten)**: Struktur, Ebenentypen und Stammdaten pflegen.
- **Organisationszuordnungen verwalten**: Zuordnungen aller Personen pflegen.
- **Organisationsrollen vergeben**: Bereichsrollen vergeben und entziehen.

Bereichsrollen gelten wahlweise nur für die Einheit oder einschließlich Untereinheiten:

| Rolle | Umfang |
| --- | --- |
| Leitung | Bereich ansehen; Zuständigkeit für kommende Planung und Genehmigung |
| Bereichsplanung | Bereich ansehen; Zuständigkeit für kommende Planung |
| Genehmigung | Bereich ansehen; Zuständigkeit für kommende Genehmigung |
| Zuordnungen verwalten | Zuordnungen innerhalb des Bereichs pflegen |
| Bereichseinstellungen | Name und Kontaktdaten pflegen; kein Verschieben oder Aktivieren |
| Abwesenheiten verwalten | Bestehende Abwesenheiten der Personen mit Hauptzuordnung im Bereich verwalten |

Bereichsrollen vergeben keine globalen Rechte und erlauben weder Konten-/Gruppenverwaltung noch das Delegieren von Rollen. Planungs- und Genehmigungsrollen stellen die Berechtigungsgrundlage für das spätere Kalender-/Urlaubsmodul bereit; sie erzeugen noch keinen Urlaubsworkflow. Leitungen erhalten bewusst nicht automatisch die separate Rolle zur Verwaltung vorhandener Abwesenheiten und Vertretungen.

Ein inaktiver Vorfahr deaktiviert geerbte Bereichsrechte für dessen Zweig. Globale Verwalter können inaktive Strukturen weiterhin pflegen. Strukturänderungen mit Auswirkungen auf bestehende Zuordnungen oder Rollen benötigen zusätzlich die jeweiligen globalen Rechte. Rollenführende Gruppen und Konten sind vor Änderungen durch schwächer berechtigte Benutzerverwalter geschützt; dies umfasst CSV-Import und Passwortzurücksetzen.

## Betrieb und Nachvollziehbarkeit

Der Start legt additive Tabellen für Ebenentypen, Zuordnungen, Rollenzuweisungen, Änderungsprotokoll und Versionsstand an. Es werden keine bestehenden Organisationseinheiten ersetzt oder automatisch Personen zugeordnet. Ein Backup vor einem Softwareupdate bleibt Bestandteil des üblichen Betriebsablaufs.

Beide Organisationseditoren prüfen einen gemeinsamen Versionsstand. Veraltete Änderungen werden mit HTTP 409 abgelehnt. Neue Organisationsaktionen werden mit handelnder Person, Zeitpunkt und sachlichen Änderungsdaten protokolliert. Die Oberfläche zeigt die letzten Änderungen der ausgewählten Einheit.

Das weitere Konzept für Kalender, Urlaubsplanung, Schließtage und Novatime-Parallelbetrieb steht in [kalender-urlaub-konzept.md](kalender-urlaub-konzept.md).
