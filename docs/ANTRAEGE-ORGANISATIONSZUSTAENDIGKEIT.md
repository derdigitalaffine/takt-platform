# Organisatorische Zuständigkeit bei Anträgen und Vorgängen

Online-Anträge können weiterhin einer einzelnen Person oder einer bestehenden
Benutzergruppe zugewiesen werden. Zusätzlich wird die **tatsächliche
Bearbeitungszuständigkeit** über jeden aktiven Knoten des zentralen
Organisationsbaums angeboten: Verwaltung, Fachbereich, Sachgebiet, Einrichtung,
Team, Arbeitgeber oder Gruppe. Eine Gruppe ist seit der Zusammenführung der
Benutzerverwaltung ein echter Org-Knoten.

## Zwei verschiedene Angaben
- `forms.org_id` ist **die öffentliche zuständige Stelle im Antragskatalog**
  (z. B. Gebietskörperschaft oder Einrichtung), mit Wappen und Adresse.
  Die Katalogangabe erzeugt **keine Bearbeitungsrechte**.
- `forms.app_org_id` ist die organisatorische **Standardbearbeitung**.
  `form_responses.responsible_org_id` ist der auf den eingegangenen Vorgang
  angewandte Stand. `application_tasks.responsible_org_id` ist die
  konkrete Zuständigkeit des Arbeitsschritts.
  Diese drei optionalen Foreign Keys werden additiv migriert.

## Routing, Prozesse und Benachrichtigungen
- Im Formularreiter „Antrag“ und in Antwort-Weiterleitungsregeln werden aktive
  Hierarchieknoten angeboten. Der erste Treffer bestimmt die Zuweisung,
  sonst greift die Standardzuständigkeit.
- Neue Antragseingänge übernehmen die Einstellung als eigenen Vorgangswert.
  Bestehende Vorgänge/Prozessversionen werden nicht umgeschrieben.
- Eine spätere Zuweisung des Vorgangs oder einzelner Arbeitsschritte kann
  ebenfalls an einen aktiven Org-Knoten erfolgen.
- Im Prozesseditor ist „Organisationseinheit / Gruppe“ ein zusätzlicher
  Zuständigkeitsmodus. Auch automatische Neuzuweisungen und
  Fristüberschreitungs-Eskalationen unterstützen einen Org-Knoten.
- Gruppen mit `kind=gruppe` nutzen dieselben vorhandenen `GroupMember`
  wie Gruppenrechte, Einladungen und Freigaben. Andere Organisationseinheiten
  nutzen explizite `OrgMembership`-Zuordnungen.
- Nur **direkte, aktive Mitglieder der ausgewählten Einheit** erhalten
  Bearbeitungszugriff, Aufgaben und Benachrichtigungen; Stellvertretungen
  bleiben gemäß bestehender TAKT-Logik wirksam. Die Zugehörigkeit zu einem
  übergeordneten Bereich öffnet nicht automatisch personenbezogene
  Antragsdaten aus untergeordneten Bereichen.
- Die Org-Verknüpfung ist auch für Org-Knoten mit null direkt zugeordneten
  Personen technisch zulässig. Für solche Fälle muss eine Bearbeitungsperson
  zugeordnet werden; die bisherigen Fallbacks/E-Mail-Konfigurationen
  gelten weiter.

## Bestandsdaten und Sicherheit
- `Form.app_group_id`, `FormResponse.group_id` und
  `ApplicationTask.group_id` bleiben unverändert verfügbar und auswertbar.
  Vorhandene Antworten, Gruppen-IDs, Rollen, Vorgänge und Aufgaben behalten
  ihre Zuweisungen. Änderungen an einer bestehenden Zuweisung sind bewusst
  neue, dokumentierte Vorgänge.
- Beim Bearbeiten vorhandener Formularvoreinstellungen werden alte Gruppen,
  soweit bereits im Org-Baum verknüpft, im neuen Picker vorselektiert.
- Frühere Prozessschritte mit dem Modus `group` funktionieren weiterhin;
  der neue Modus `org` ergänzt sie, statt Prozessdefinitionen still
  umzuschreiben. Laufende Vorgänge bleiben an ihrer Prozessversion.
- Org-Auswahlen werden serverseitig auf existierende aktive Knoten und
  eine vollständig aktive Ahnenkette validiert. Ein nicht vorhandener oder
  inaktiver Knoten wird mit HTTP 422 zurückgewiesen.
- Keine impliziten globalen Rechte, keine automatischen Unterbaum-Freigaben,
  keine Vermischung mit der öffentlichen „Zuständigen Stelle“.

## Tests und Rollout
Die Regression prüft Standard-/bedingtes Routing, Rechte fremder Benutzer,
direkte Org- und Gruppenmitgliedschaft, inaktive Knoten, Prozessschritte,
Aufgabenlisten, Erinnerungs-Empfänger und die Formular-/Vorgangsoberflächen.
Bestehende Umfrage-, Abstimmungs-, Kalender- und Seminarfunktionen bleiben
unverändert. Vor dem Produktivstart Datenbank sichern und die
vollständige CI einschließlich Browser-Prüfungen ausführen.
