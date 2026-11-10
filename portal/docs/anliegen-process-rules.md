# TAKT · Optionale Prozesszuordnungen für interne Anliegen (#291)

## Bedienung

Verwaltung: **Interne Anliegen → Kategorien & Zuständigkeiten → Prozessanbindung
konfigurieren**, URL `/anliegen/prozesse`. Hier können berechtigte Personen
publizierte, für interne Anliegen kompatible TAKT-Prozesse einer Kategorie und
optional einer Organisation zuordnen.

1. **Entwurf** mit Startarten `Einreichen`, `Bearbeitung`, `Kategorieautomatik`
   und der Startfreigabepflicht erzeugen.
2. Entwurf bearbeiten und **zur Prüfung vorlegen**.
3. Eine **andere berechtigte Person** genehmigt. Dabei werden Kompatibilität
   erneut geprüft und die aktuell veröffentlichte Version gepinnt.
4. Die Zuordnung ist **aktiv**, sobald der globale Schalter aktiviert ist.
5. Laufende Vorgänge nutzen die gespeicherte Prozessversion und ihre
   ursprüngliche Regelrevision. Änderungen erfolgen als **neue Revision**
   (Änderungsvorschlag, Review, Freigabe); die alte aktive Revision wird erst
   dann inaktiv. Ein vollständiger Rollback ist über eine neue Revision möglich.

Der globale Schalter `anliegen_process_integration_enabled` ist ohne
explizite Aktivierung AUS. Die Administrationsseite kann auch im
abgeschalteten Zustand für vorbereitende Regeln genutzt werden.

## Rechte

Zusätzliche, einzeln zuweisbare globale Berechtigungen:
- `anliegen_process_start`: optionalen Prozess auswählen oder als
  Fallbearbeitende starten, zusätzlich zum eigentlichen Objektzugriff.
- `anliegen_process_configure`: Entwürfe für eigene Organisationsbereiche,
  nur mit passenden Organisationsrechten `plan`/`settings`; der Prozess
  muss außerdem im bestehenden Prozesseditor zugänglich oder selbst erstellt
  sein.
- `anliegen_process_approve`: Regelreview und Startfreigabe für berechtigte
  Organisationsbereiche (Organisationsrecht `approve`); für die
  Startfreigabe ist zusätzlich eine Fall- oder explizite
  Organisationszuständigkeit erforderlich.

**Übergreifende Regeln** und die globale Ein-/Ausschaltung erfordern
einen Portaladministrator. Konfigurationsfreigaben erzwingen ein
Vier-Augen-Prinzip. Auch Prozessstarts mit verlangter Freigabe bleiben
in `requested` ohne Bearbeitungsschritte, bis eine andere berechtigte
Person sie bestätigt.

Vertrauliche Anliegen sind weiterhin kategorisch ausgeschlossen.
Organisationale Regeln dürfen keine fremde Organisation abdecken;
organisationsbezogene Regeln haben bei gleichem Prozess Vorrang vor
globalen Regeln.

## Start und Verarbeitung

- **Beim Einreichen** (optional): Ein Auswahlelement erscheint nur bei
  passender Kategorie, aktiver Regel, aktivierter Integration und
  expliziter Startberechtigung. Der ausgewählte Prozess startet in
  derselben Datenbanktransaktion wie die Erstellung des Anliegens.
  Verbotene Auswahl ⇒ kompletter Rollback.
- **Bei der Bearbeitung**: Berechtigte können in der Anliegen-Detailseite
  den Prozess auswählen und starten. Ein vom Server generierter Token
  verhindert Doppelverarbeitung bei erneutem Absenden.
- **Kategorieautomatik**: Nur ausdrücklich genehmigte automatische
  Starts werden ausgeführt. Die genehmigende Person ist die kontrollierte,
  organisatorisch gültige Ausführungsidentität. Ein bereits explizit
  gestarteter Prozess desselben Typs wird nicht noch einmal automatisch
  gestartet. Misslingt ein Auto-Start, bleibt das eingereichte Anliegen
  erhalten; die Fehlersituation wird allgemein protokolliert.
- Alle Starts nutzen die in #290 eingeführte, transaktionsgebundene
  Ausführung ohne künstliche FormResponse-Datensätze.

In diesem Inkrement bietet die Detailseite bereits eine kompakte
Prozessansicht, Startaktionen, Startfreigaben, manuelle Prüf- und
Freigabeschritte sowie Pausieren/Fortsetzen/Abbrechen. Die umfassende
Timeline, einheitliche Aufgabenintegration, Dateien und
Statusaggregation werden in **#292** ausgebaut.

## Sicherheit und Verfügbarkeit

- Jede zustandsändernde Route benötigt Benutzeranmeldung, CSRF,
  explizite Rechte und serverseitige Objektprüfung.
- Ratenbegrenzungen für Einreichen, Konfiguration, Start und Freigabe.
- Validierung vor Aktivierung **und** vor Start; nicht unterstützte
  Antragsschritte/Seiteneffekte werden nicht ausgeführt.
- Aktive Revisionen sind unveränderlich. Optimistische Sperre
  `state_version` auf Konfigurationsänderungen; partielle eindeutige
  Indizes verhindern mehrere gleichzeitige aktive Regeln je
  Kategorie/Prozess/Geltungsbereich.
- Sensible Inhalte werden nicht in der Freigabeübersicht gezeigt.
  Interne Prozesswerte/Kommentare bleiben verschlüsselt in der
  bestehenden Engine.
- Das Feature arbeitet auch ohne KI. Weder der globale Switch noch
  der Konfigurationseditor erfordert das KI-Modul.

## Noch ausstehend

#292: Integration aller Prozessaufgaben in „Meine Aufgaben“, vollständiger Hub,
Organisationseinsichten, intelligente Abschluss- und Dokumentansicht.

#293: Verkettete Prozesse, bedingte Starts und KI-Mapping; vollautomatische
externe Workflow-Aktionen müssen einzeln abgesichert und fachlich freigegeben
werden. Die aktuelle Engine lässt solche Aktionen bewusst nicht zu.
