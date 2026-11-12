# TAKT Umfragen – Ergebnisberichte und Teilnahmebestätigungen

Stand: 12. November 2026. Verbindliches Interview: Fragen **1–6 jeweils D**.

## Fachliches Zielbild (verbindlich)

Alle vier Umfragearten – Formularumfragen, Terminumfragen, formelle
Abstimmungen sowie Live-Umfragen – erhalten ein konsistentes,
datenschutzgerechtes Berichtssystem. Eine Teilnehmeransicht zeigt
dagegen ausschließlich Informationen, die nach Zugang, Identität,
Anonymität und der vom Ersteller gewählten Freigabe tatsächlich sichtbar
sein dürfen.

Die vollständige Spezifikation umfasst:

1. **DIN A4:** Berichte für alle vier Arten mit auf die Fachlogik
   abgestimmtem Inhalt; bestehende CSV-/JSON-Ausgaben bleiben erhalten.
2. **Persistente Teilnehmerbestätigung:** nach dem Absenden und bei
   jedem späteren Wiederaufruf; persönliche Änderungen erzeugen keine
   weitere gezählte Teilnahme.
3. **Getrennte Freigaben:** eigener Status, eigene Antwort, aggregierte
   Zwischen-/Endergebnisse und Berichtsexport je nach Zeitpunkt und
   Berechtigung. Die Export-API muss dieselbe Policy wie die Webansicht
   erzwingen; ein direkter Dateilink darf keinen Zugriff erweitern.
4. **Report-Design:** Organisationsfarben/-logo, wiederholte Kopf- und
   Fußzeilen, Metadaten, Datum und Seitennummer; flexible Diagramme,
   Terminrankings und barrierearmes Layout. Managementberichte enthalten
   zusätzlich eine vollständige, klar als vertraulich gekennzeichnete
   CSV-äquivalente Detailauswertung aller Teilnehmer und Antworten.
5. **Nachbereitung:** persönliche sichere Links, zulässige
   Erinnerungen, Ergebnisveröffentlichung, Terminfestlegung und
   ICS-Download. Nachrichten nur über erlaubte Versandwege, ohne
   Offenlegung geheimer Stimmen.
6. **Betriebssicherheit:** schrittweise Migration bzw. rückwärtskompatible
   Einführung, Funktionstests, Schutz der vorhandenen Live-Engine,
   Dokumentation, CI/PR-Gates und kontrollierter Rollout.

## Erste Umsetzung in PR #363

### Zugriffsgrenzen

* `GET /forms/{id}/export.pdf`: nur verwaltende Portalnutzer mit
  bestehender Form-`VIEW`-Berechtigung; ausschließlich
  `form.kind == "survey"`, niemals Online-Anträge über diesen Endpunkt.
* `GET /polls/{id}/export.pdf`: nur Nutzer mit bestehender
  Terminumfrage-`VIEW`-Berechtigung (analog CSV).
* Beide Antworten: `application/pdf`, `private, no-store`,
  `X-Content-Type-Options: nosniff`.
* **Kein ungesicherter Teilnehmer-PDF-Endpunkt.** Für eine spätere
  Ergebnisfreigabe wird zuerst eine gemeinsame Policy aus
  Identität/Einladungsnachweis, Veröffentlichung und erlaubten
  Berichtsinhalten benötigt.
* **Vertrauliche Managementberichte** enthalten nach ausdrücklicher
  Anforderung nun alle bereits im CSV-Export enthaltenen Felder: Namen,
  E-Mail-Adressen, Abgabezeiten, Freitexte, Kommentare, Terminwünsche,
  Antwortspalten und ggf. CSV-Geodaten. Die in CSV enthaltenen Werte
  werden nicht gekürzt oder stillschweigend weggelassen.
* Es werden **keine** persönlichen Identitäten nachträglich aus
  anonymen Antwortdatensätzen erschlossen. Die PDF-Detailauswertung
  übernimmt ausschließlich die bereits durch dieselbe Berechtigung
  zugänglichen Daten des jeweiligen CSV-Exports.
* Teilnehmer dürfen den vertraulichen Managementbericht nicht über
  einen persönlichen oder öffentlichen Umfragelink abrufen. Für
  freigegebene Teilnehmer-Ergebnisse ist eine getrennte, anonyme
  Darstellung mit eigener Berechtigungsprüfung vorgesehen.
* Geheime oder förmliche Stimmabgaben werden durch diese Änderung nicht
  offengelegt. Live-Quiz-/Abstimmungs-Engines bleiben unverändert.

### Gestaltung

`portal/app/survey_pdf.py` erzeugt ReportLab-Vektordokumente in
DIN A4 (Hochformat). Der Bericht nutzt das in den
Organisationseinstellungen definierte Primärfarbthema und – bei
unterstütztem Rasterformat – das bestehende Logo. Auch ohne Logo bleibt
das Layout vollständig. Wiederholte Kopf-/Fußzeilen und automatisch
aufteilbare Ergebniszeilen unterstützen längere Umfragen.

* Formularumfrage: Frage-für-Frage-Auswertung mit Balken/Skalen,
  Rücklauf und Durchschnitt; darunter vollständiger, paginierter
  Detailanhang mit allen CSV-Spalten pro Antwort inklusive Freitext
  und dort enthaltenen Geodaten.
* Terminumfrage: Abgabezahl, Einladungsrücklauf, festgelegter Termin,
  sortiertes Ranking in den Webfarben Grün/Gelb/Rot und Terminhinweise.

### Teilnahme nach dem Absenden

Terminumfragen behalten persönliche Links `/t/p/{token}`. Die Ansicht
zeigt jederzeit den gespeicherten Status, Datum, persönliche
Terminpräferenzen und bei festgelegtem Termin den privaten
`/t/p/{token}/termin.ics`-Download. Angemeldete Portalkonten werden
bei Zugriff über den öffentlichen Link anhand ihrer vorhandenen
`PollParticipant.user_id` wiedererkannt; eine erneute POST-Anfrage
ändert die vorhandene Antwort statt eine zweite Teilnahme anzulegen.
Ein Browser-Cookie bleibt bei Gästen nur ein praktischer Beleg und
keine verifizierte Identitätsfeststellung.

Formularumfragen behalten die bereits geschützte, dauerhafte
`done`-Ansicht. Die neue Dankeseite bietet einen Statuslink und
für angemeldete Teilnehmende `Meine Umfragen`.

### Nicht verändert

* Live-Umfrage-Routen, Freigabeschalter, Geräte-Hashes, Zeitlimits,
  Quizfragen, Wortwolken und Präsentationsansichten.
* Abstimmungs-/Wahl-Stimmzettel und ihre Anonymitätsgrenzen.
* Bestehende CSV-/JSON-Exporte und die Einladungskommunikation.

## Nachfolgende getrennt abzusichernde PRs

* Vollständige Ergebnisfreigaben je Umfrageart mit eigenen,
  persistenten, konfigurierbaren Einstellungen und identischer
  Web-/Export-Policy. Kleine Auswertungsgruppen ggf. unterdrücken.
* Eigenantworten für nicht-anonyme Formularumfragen mit
  accountgebundenen Leserechten; anonyme Teilnahmen nicht
  nachträglich zuordnen.
* Weitere Berichtstypen für Live-Umfragen und Modernisierung der
  bestehenden förmlichen Ergebnisprotokolle.
* Wiederverwendbare Vorlagen, optionales Querformat,
  umfangreiche Barrierefreiheitstests und visuelle Rendering-Snapshots.
* Ereignisgesteuerte Benachrichtigung über Ergebnisfreigabe,
  Genehmigung, Änderung, Frist und Termine nur mit Zustimmung,
  Versandbegrenzung, idempotenter Ausführung und Audit.
* Optionale Kalender- und Organisationsintegration ohne
  harte Abhängigkeit zu deaktivierten Modulen.

## Testplan

`test_survey_pdf.py` prüft A4-Seitenmaße, Textauslesbarkeit,
Mehrseitigkeit, vollständige CSV-Feldabdeckung (inklusive Namen und
Kommentaren) sowie die Gleichheit der bestehenden Exportberechtigungen.

`test_poll_receipt.py` prüft dauerhafte Bestätigung, eigene
Terminanzeige nach Ende, kalenderfähigen persönlichen Link und
kontoübergreifende Wiedererkennung ohne Browser-Cookie.

Vor jeder Zusammenführung vollständige Testsuite mit
`test_live.py`, `test_live_quiz.py`, `test_survey_workspace.py`,
`test_my_surveys.py`, den bestehenden Browserprüfungen sowie
Berechtigungs- und Anonymitätsregressionen ausführen. Produktiver
Rollout wird gesondert durchgeführt; ein GitHub-Merge ist kein
automatisches Deployment.


## Kompakter A4-Ergebnisexport (Folgeausbau)

Der vertrauliche PDF-Export von Formular- und Terminumfragen ist auf eine
**kompakte Ergebnisübersicht mit möglichst nur einer A4-Seite** ausgerichtet.
Ein Seitenlimit, das Ergebnisse abschneidet, existiert bewusst nicht.

* **Kein künstlicher Detailanhang mehr:** Der bisher erzwungene Seitenumbruch
  vor den Teilnehmerdaten entfällt. Ein kurzer Titel, eine zweispaltige
  Informationszeile und verdichtete Ergebnis- und Detailtabellen nutzen den
  Platz einer Hochformat-A4-Seite besser aus.
* **Terminumfragen:** Oben stehen alle Terminoptionen mit Nr., Datum/Uhrzeit,
  Rangfolge und einem farbigen Balken wie in der Webansicht. Die anschließende
  Antwortmatrix hat **Teilnehmende als Zeilen, Termine als nummerierte
  Spalten**; die Spaltennummern verweisen direkt auf die Terminübersicht.
  **Grün = Ja, Gelb = Wenn nötig, Rot = Nein.** Die Hintergrundfarben
  werden stets durch ausgeschriebene Antworttexte ergänzt und sind
  nicht die einzige Information. Namen, E-Mails, Antwortzeit, Summenzeilen
  und Kommentare des bestehenden CSV-Exports bleiben enthalten.
* **Formularumfragen:** Antworten je Frage mit schmalen Balken sowie direkt
  anschließend eine kompakte Feld-/Werte-Tabelle pro Teilnahme. Wiederholte
  große Überschriften, überflüssige Abstände und die separate Anhang-Titelseite
  entfallen. Personen- und Freitextdaten bleiben vollständig enthalten.
* **Große Erhebungen:** Viele Personen oder Terminvorschläge erzeugen
  automatisch weitere A4-Seiten. Terminspalten werden in nummerierte
  Gruppen aufgeteilt; Namen und Antworten werden vollständig wiederholt,
  wo dies für die Lesbarkeit erforderlich ist. Sehr lange Freitexte und
  Geodaten werden als über Seiten umbrechbare Absätze ausgegeben.
  Es werden keine Zellen, Teilnehmer, Kommentare oder CSV-Spalten abgeschnitten.
* **Corporate Design:** Organisationsname/-primärfarbe und zulässiges
  Rasterlogo bleiben erhalten, ebenso Vertraulichkeitsvermerk, Datum
  und fortlaufende Seitennummerierung. Die Farbkategorien entsprechen
  den Webklassen Bootstrap Success / Warning / Danger:
  **#198754 / #FFC107 / #DC3545**. Farbige Zellen haben zusätzlich
  eine helle Hintergrundtönung für den Ausdruck.

Die bestehende API, der geschützte Download, die Berechtigungen und die
CSV-/JSON-Dateien bleiben unverändert. Der Bericht ist ein
**vertraulicher Managementexport**, kein frei zugänglicher Teilnehmerauszug.
Bei normalen kurzen Umfragen wird eine Seite mit einem automatisierten
PDF-Seitenzahltest verlangt; bei sehr langen Inhalten geht
**Vollständigkeit vor einer Ein-Seiten-Garantie**.

Zusätzliche Regressionen prüfen eine A4-Seite für kleine Beispielumfragen,
tatsächliche Farbgebung, alle CSV-Spalten und -Werte, Unicode,
Vertraulichkeit, Berechtigungsschutz und mehrseitige Texte.
