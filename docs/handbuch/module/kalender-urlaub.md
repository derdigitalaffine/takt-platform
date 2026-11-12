# Kalender & Urlaub

**TAKT-Benutzeranleitung · aktualisiert: November 2026**

[← Alle Anleitungen](../../BENUTZERHANDBUCH.md) · [Grundlagen & Anmeldung](../grundlagen.md) · [Admin-Handbuch](../../ADMIN-HANDBUCH.md)

> **Wozu?** Termine teilen, Abwesenheiten planen und gegebenenfalls Urlaub genehmigen.
>
> **Für wen?** Nutzende freigeschalteter Kalender und Urlaub-Funktionen.

**Im Portal öffnen:** `/kalender` (sofern für dich freigeschaltet). Wenn du den Eintrag nicht siehst, nutze **Module entdecken** oder frage nach deinen Rechten.

## Schnellstart: So gehst du vor

1. Öffne **Kalender**, um persönliche, organisatorische oder freigegebene Kalender zu sehen.
2. Erstelle oder bearbeite Termine im Kalender, sofern du dazu berechtigt bist; prüfe die Sichtbarkeit.
3. Öffne **Urlaub** für eigene Anträge, Personenzeitachsen und die gegebenenfalls zugewiesene Genehmigung.
4. Nutze für externe Kalendergeräte den persönlichen CalDAV-/Kalenderzugang und gib Gerätezugänge nicht weiter.

**Wichtig:** Kalenderzugriffe, Urlaubsanträge und Genehmigungen sind nicht identisch berechtigt. Eine Einladung zu einem Termin veröffentlicht keine privaten Kalenderdetails.

## Ausführliche Bedienung

Die folgenden ausführlicheren Arbeitsschritte stammen aus dem bisherigen Handbuch und wurden passend zu diesem Modul zusammengestellt.

## Kalender und Urlaub – getrennte Arbeitsbereiche

**Kalender** und **Urlaub** sind zwei eigenständige Menüpunkte unter „Termine & Veranstaltungen“. Der Kalender verwaltet Termine und Gerätezugänge; Urlaub ist für die persönliche und gemeinsame Abwesenheitsplanung zuständig. Die neuen Änderungen werden in [PR #185](https://github.com/derdigitalaffine/takt-platform/pull/185) geprüft.

Unter **Urlaub** stehen – je nach Berechtigung – fünf Bereiche zur Verfügung: **Planer**, **Mein Urlaub**, **Genehmigungen**, **Schließzeiten & Notbesetzung** und **Verwaltung**. Die Verwaltung trennt Urlaubsverfahren, Besetzungsregeln, Arbeitsmodelle, Feiertage und Konten in eigene Unterseiten. Mitarbeitende starten mit dem eigenen Urlaub; Leitungen, Stellvertretungen und Planende können die Teamzeitachse öffnen. Auf dem Handy bleibt der Editor vollständig bedienbar.

**Planen:** Im Planer markieren Sie einen Zeitraum durch Ziehen oder Klicken und prüfen die vorausgefüllten Angaben im Detailbereich. Nach dem Speichern bleiben Monat/Quartal/Jahr und der zuletzt betrachtete Zeitraum je Einheit in der Browser-Sitzung erhalten. Die verbindliche Besetzung wird erneut auf dem Server geprüft; keine einzelne Drag-and-drop-Bewegung soll ohne Bestätigung automatisch Urlaub verbindlich ändern.

**Leitungskennzeichen:** Bei fachlich relevanten Personen sehen Sie „Leitung“ bzw. „Stellvertretung“. Beide Rollen können für einen Bereich mehrfach und gleichzeitig vergeben sein. Wer eine dieser Rollen innehat, kann selbstverständlich auch eigenen Urlaub eintragen. Bei internem Workflow ist Selbstgenehmigung ausgeschlossen; standardmäßig wird die höhere Einheit gefragt. Ist die **externe ZE-Software** für Genehmigungen zuständig, gibt es keine zusätzliche interne Genehmigung. Die persönliche Aussage „Extern genehmigt“ kann die Verwaltung je Einheit einschalten; sie bleibt eine Selbstauskunft.

**Weitere Abwesenheiten:** Bereits über **Abwesenheiten & Vertretungen** erfasste Zeiten, eindeutig zugeordnete Krankmeldungen und bestätigte Seminartermine fließen in die Anzeige und Besetzung ein, ohne als neue Urlaubsanträge gespeichert zu werden. Kolleginnen und Kollegen ohne Zuständigkeit sehen bei fremden Abwesenheiten nur „Abwesend“. Zuständige Vorgesetzte dürfen den erforderlichen Grund sehen, nicht aber Diagnosen, Atteste oder medizinische Anlagen. Vertretungsrechte bleiben weiterhin im bestehenden Abwesenheitsbereich.

**Darstellung und Organisation:** Neben komfortabler Anzeige ist eine kompakte Darstellung wählbar, die auch in Kalender, Benutzer- und Organisationsverwaltung gilt. Die Auswahl wird persönlich gespeichert. Der zuletzt genutzte berechtigte Organisationsbereich wird nach Möglichkeit übernommen.



Wenn die Verwaltung das Modul **Kalender & Urlaub** freigeschaltet hat, finden Sie unter **Termine & Veranstaltungen** die Einträge **Kalender & Urlaub** (`/kalender`) und **Urlaubsplanung** (`/urlaub`). Sichtbare Kalender und Urlaubsbereiche hängen von Ihren Organisationszuordnungen und den jeweiligen Freigaben ab.

### Kalender ansehen und teilen

Unter **Kalender & Urlaub** können Sie die Ihnen freigegebenen persönlichen, gemeinsamen und Organisationskalender auswählen. Fachtermine (beispielsweise Besprechungen, Seminare, Aufgaben oder Buchungen) werden nur mit den jeweils geltenden Fachrechten angezeigt; ihre Bearbeitung bleibt im zuständigen Modul. Berechtigte Personen können eigene Kalender anlegen, Freigaben vergeben und Termine erfassen. **Öffentliches Veröffentlichen** ist ein eigenes Recht und wird nicht durch eine normale Kalenderfreigabe erteilt.

### Urlaub eintragen und im Bereich planen

1. **Urlaubsplanung** öffnen und die gewünschte, für Sie sichtbare **Organisationseinheit** auswählen. Dort sehen Sie die Personenzeitachse mit geplanten, beantragten und verbindlichen Zeiträumen und – je nach Freigabe – Besetzung und Schließzeiten.
2. Mit **Monat**, **Quartal** oder **Jahr** den Überblick wählen. Zeitraum und Zoom merkt sich die Seite **für jede Einheit in der aktuellen Browser-Sitzung** – auch nach dem Speichern und Neuladen. Mehrere Urlaube im gerade sichtbaren Ausschnitt können Sie nacheinander eintragen, ohne ständig zurücknavigieren zu müssen. Liegt ein neuer Eintrag **außerhalb** des sichtbaren Zeitraums, zeigt der Kalender danach automatisch dessen Zeitraum an und **behält die Zoomstufe**.
3. Über die Zeitachse oder das Formular **Zeitraum eintragen** Person, Beginn/Ende und bei Bedarf **Vormittag/Nachmittag** festlegen. Die Konfliktvorschau prüft die Besetzung; eine Planung ist noch keine verbindliche Genehmigung. Die gleiche Eingabe ist über Formular und Tastatur möglich, auch wenn das Zeichnen mit der Maus nicht passt.
4. Abhängig von der Einstellung Ihres Bereichs wird Urlaub gemeinsam geplant, intern eingereicht/genehmigt oder nach externer Genehmigung von Ihnen **als Selbstauskunft** bestätigt. Ein eigener Eintrag in Takt ist **keine automatische Meldung an externe ZE-Software**. Im reinen Planungsmodus kann ein Zeitraum ausdrücklich verbindlich markiert werden.
5. Eine Änderung eines bereits verbindlichen Urlaubs wird zunächst als neue Planung gespeichert. Bis zur nötigen Bestätigung bleibt der bisherige Zeitraum wirksam. Schließzeiten und Notbesetzung beachten die gesonderten Bereichsregeln. Nur berechtigte Planende oder Genehmigende können fremde Einträge bzw. Regeln ändern.

**Wichtig – Unterschied zu Abwesenheiten:** Die zuvor beschriebene Seite **Abwesenheiten** verwaltet unter anderem Übergaben und Vertretungen. Eine optionale Übernahme eines verbindlichen Urlaubs in die Abwesenheitsübersicht verleiht **keine Vertretungsrechte**. Die in Takt angezeigten internen Urlaubskonten sind optional; für extern verwaltete Konten wird kein Resturlaub vorgetäuscht.

### Kalender auf Mobilgerät oder im Mailprogramm nutzen

Öffnen Sie im Kalenderbereich **Kalender verbinden** (`/kalender/hilfe`). Sie können für jedes Gerät einen eigenen Zugang mit gezielt ausgewählten Kalendern erstellen und später widerrufen. Auf dem iPhone/iPad wird über HTTPS ein **einmalig herunterladbares Profil** mit eigenem Gerätepasswort angeboten; für andere Geräte werden CalDAV-Angaben angezeigt. Freie Kalender erlauben je nach Freigabe Änderungen per CalDAV; Fachkalender bleiben über die Schnittstelle lesend. Für Outlook ohne passende CalDAV-Anbindung steht ein **widerrufbares ICS-Leseabo** bereit. Dessen Aktualisierung hängt vom Kalenderprogramm ab. Behandeln Sie Profile und geheime Abolinks wie Zugangsdaten; bei Verlust widerrufen.

Weiterführend: [Organisationsrollen](../../organisationsverwaltung.md) und [Implementierung, Prüfungen und Geräte-Grenzen](../../kalender-urlaub-umsetzungsstand.md).

## Hilfe, Rechte und weiterführende Informationen

- [Allgemeine Bedienung, Sicherheit und Problemlösung](../grundlagen.md)
- [Übersicht aller Module](../../BENUTZERHANDBUCH.md)
- Für administrative Einstellungen: [Admin-Handbuch](../../ADMIN-HANDBUCH.md)

> **Hinweis:** Alle Funktionen hängen von den aktivierten Modulen, deiner Rolle und den einzelnen Freigaben ab. Für externe Gäste gelten nur die ausdrücklich angebotenen Zugangswege.

## Für Blöde erklärt:

Du willst wissen, wann etwas stattfindet – oder Urlaub planen?

1. Für Termine den **Kalender** öffnen.
2. Termin auswählen oder anlegen und die Beteiligten prüfen.
3. Für Urlaub in den **Urlaubsbereich** wechseln.
4. Zeitraum eintragen und gegebenenfalls die Freigabe abwarten.
5. Bei Kalender-Abos persönliche Links vertraulich behandeln.

**Merksatz:** Ein Kalendereintrag ist nicht automatisch ein genehmigter Urlaubsantrag.
