# Benutzergruppen als vollwertige Organisationsknoten

## Ziel

Die bisherigen TAKT-Benutzergruppen und die bestehende Organisationshierarchie
bleiben fachlich ein System. Der feste Organisationsknotentyp `gruppe` wird
im Baum als **Gruppe** mit dem Symbol `fa-people-group` angezeigt.

### Kein Doppelmodell

* `groups.id` ist weiterhin die kanonische ID einer Benutzergruppe. Alle
  bestehenden Gruppen-Mitgliedschaften (`group_members`), Benutzerrechte,
  Organisationsrollen, Einladungen, Freigaben, Anwesenheits- und
  Seminarfunktionen behalten ihre bisherigen Group-IDs.
* `groups.org_id` ist eine eindeutige, optionale Verknüpfung zur vorhandenen
  `organizations`-Tabelle. Der verknüpfte Knoten hat stets `kind=gruppe`.
  Gruppen werden **nicht** als zweite, kopierte Benutzergruppe angelegt.
* `init_db()` migriert bei jedem Start fehlende Gruppenverknüpfungen
  idempotent. Alte Gruppen werden ohne Namensabgleich auf der Stammebene
  eingefügt. Eine später vom Administrator festgelegte Hierarchie wird
  danach niemals durch die Migration zurückgesetzt.
* Die Personenverwaltung sowie der Benutzer-CSV-Import erzeugen neue
  Gruppenknoten automatisch im selben Datenbankvorgang. Die bestehende
  Gruppenverwaltung bleibt als alternative Oberfläche nutzbar.
* Bearbeitung im Organisationsbaum (Name, Beschreibung, Elternknoten,
  Aktivierung, Reihenfolge, Stammdaten) wirkt auf dieselbe Gruppe. Eine
  Umwandlung zwischen „Gruppe“ und anderen Objekttypen ist untersagt;
  zum Umstrukturieren wird der Knoten verschoben, nicht der Typ geändert.
* Gruppen-IDs, persönliche Zuordnungen, Gruppenrolle und optionaler
  Gruppenleiter bleiben erhalten.

### Personal und Berechtigungen

**Wichtig:** Mitgliedschaft in einer Benutzergruppe ist keine automatische
Personal-Hauptzuordnung, keine Stellenkapazität und keine Personalbesetzung.
Der Gruppenstand wird weiterhin ausschließlich aus `group_members`
gelesen. Dieser Stand erscheint in der Organisationsansicht, beim
Personenpicker, in der Org-Zuordnungsübersicht und bei der Leseberechtigung
des Gruppenknotens.

Bestehende zusätzliche OrgMembership-/HR-Hauptzuordnungen bleiben
unverändert. Die Organisationsrollen verwenden weiter
`organization_role_grants.group_id` und werden nie durch implizite
globale Gruppenrechte ersetzt.

Gruppen mit aktiven Bereichsrollen sind vor unberechtigter Veränderung
geschützt. Bei Strukturänderungen mit gruppenbasierten Personen gelten
dieselben Anforderungen an `org_members` wie bei gewöhnlichen
Organisationseinheiten. `org_roles` schützt rollenrelevante
Baumverschiebungen, auch auf den übergeordneten Knoten.

Extern/OIDC-synchronisierte Gruppenmitgliedschaften
(`GroupMember.manual=False`) werden bei der manuellen Bearbeitung
nicht entfernt. Nur manuelle Mitglieder können so entfernt werden.

### Verwaltungsoberflächen

* `/admin/organization`: Gruppen sind regulär als Knoten sichtbar.
  Die Auswahl einer Gruppe zeigt echte Mitglieder und ermöglicht
  Mitgliederverwaltung mit dem vorhandenen gemeinsamen Personenpicker.
* `/admin/users#gruppen`: zeigt einen direkten Link zum verknüpften
  Organisationsknoten; Gruppenleitung und sonstige Gruppendaten bleiben
  erreichbar.
* Neue Knoten mit Typ „Gruppe“ erzeugen zugleich eine echte neue
  Gruppe. Von der Gruppenverwaltung aus neu angelegte Gruppen erscheinen
  auf der Baum-Stammebene.
* Organisationen und Benutzergruppen können beliebig innerhalb
  des Baumes platziert werden, inklusive untereinander verschachtelter
  Ebenen, unter Beachtung der bestehenden Zyklus- und Rechteprüfung.

### Migration und Rollback

Für bestehende Installationen wird beim Start einmalig die nullable
Spalte `groups.org_id` und ein eindeutiger Index ergänzt. Der
Datenbestand der Benutzer-, Gruppen- und Fachmodultabellen wird **nicht**
umgeschrieben. Neue Org-Knoten entstehen nur für Gruppen ohne gültige
Verknüpfung. Schema und Link bleiben bei einem App-Rollback bestehen;
ältere App-Versionen ignorieren die zusätzliche Spalte. Vor einem
Produktivrollout eine Datenbank-Sicherung vornehmen und neue Knoten
und Berechtigungen an einer Kopie testen.

Bei der Prüfung sind insbesondere folgende Altprozesse zu testen:
Gruppeneinladungen zu Formularen, Seminaren, Umläufen, Aufgabenboards,
Kalenderfreigaben, OIDC-Synchronisation, Krankmelder-Bereichsrollen,
Personenpicker, Gruppen-CSV-Import und die bestehende Rollenvererbung.
