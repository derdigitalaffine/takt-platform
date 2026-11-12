# Formulare

**TAKT-Benutzeranleitung · aktualisiert: November 2026**

[← Alle Anleitungen](../../BENUTZERHANDBUCH.md) · [Grundlagen & Anmeldung](../grundlagen.md) · [Admin-Handbuch](../../ADMIN-HANDBUCH.md)

> **Wozu?** Formulare erstellen, verteilen, ausfüllen und Ergebnisse auswerten.
>
> **Für wen?** Erstellende und Bearbeitende bei Freigabe; Teilnehmende über den jeweiligen Link.

**Im Portal öffnen:** `/forms` (sofern für dich freigeschaltet). Wenn du den Eintrag nicht siehst, nutze **Module entdecken** oder frage nach deinen Rechten.

## Schnellstart: So gehst du vor

1. Wähle **Formulare** und lege ein neues Formular an; verwende die Feldbausteine und bei Bedarf wiederverwendbare Datenblöcke.
2. Prüfe die Vorschau und Pflichtfeldprüfung; KI-Vorschläge sind stets vor Übernahme zu kontrollieren.
3. Entscheide bewusst, wer teilnehmen darf: eingeladene Personen oder öffentliche Teilnahme, sofern unterstützt.
4. Verfolge Einsendungen und berechtigte Auswertungen; lade bei Formularumfragen den **kompakten DIN-A4-Ergebnisbericht** oder CSV herunter.
5. Unter **Zum Ausfüllen** findest du Formulare, die dir zur Bearbeitung zugewiesen wurden.

**Wichtig:** Vertrauliche Teilnehmerdaten sind nur für berechtigte Auswertende sichtbar. Ein Ergebnisbericht ist keine öffentliche Teilnehmerbestätigung.

## Praxisbeispiel: Eine interne Bedarfsabfrage erstellen

**Ausgangslage:** Mehrere Kolleginnen und Kollegen sollen ihren Bedarf an Büromaterial anmelden. Die Antworten dürfen nicht öffentlich sichtbar werden.

1. Lege ein Formular mit einem aussagekräftigen Titel an, beispielsweise **„Büromaterialbedarf – Dezember“**. Ergänze den Zweck und eine Abgabefrist in der Beschreibung.
2. Nutze ein kurzes Textfeld für die Bezeichnung, ein Zahlenfeld für die Menge und bei Bedarf eine Mehrfachauswahl für Materialkategorien. Kennzeichne notwendige Angaben als **Pflichtfeld**.
3. Füge eine optionale Bemerkung hinzu. Frage keine personenbezogenen Daten ab, die für die Bearbeitung nicht erforderlich sind.
4. Prüfe im Vorschaumodus die Reihenfolge, die mobile Darstellung und die Pflichtfeldmeldungen. Probiere auch absichtlich eine unvollständige Eingabe aus.
5. Speichere den Entwurf, konfiguriere die zulässige Teilnahme und gib das Formular erst dann über den vorgesehenen Weg frei.
6. Öffne nach den ersten Einsendungen die Ergebnisansicht. Prüfe die Berechtigungen, bevor du Antworten exportierst oder mit anderen teilst.

**Vor der Freigabe prüfen:** Stimmen Zweck, Empfängerkreis, Datenschutzinformationen, Pflichtfelder und eventuelle Dateiuploads? Der Formularlink allein ist kein Ersatz für eine bewusste Freigabekonfiguration.

## Typische Fragen und Lösungen

| Beobachtung | Was du prüfen solltest |
|---|---|
| Das Formular lässt sich nicht bearbeiten | Bist du Eigentümer:in oder mit ausreichenden Bearbeitungsrechten beteiligt? Ist das Formular noch bearbeitbar? |
| Eine Frage erscheint beim Ausfüllen nicht | Prüfe ihre Sichtbarkeitsbedingung und eventuelle Bedingungen der gesamten Seite. |
| Das Absenden wird abgelehnt | Kontrolliere Pflichtfelder, Eingabegrenzen und Dateien. Fehlermeldungen am betroffenen Feld beachten. |
| Eingaben aus dem eigenen Profil fehlen | Prüfe die freiwillige Zustimmung zur Vorbelegung im Profil und ob der Feldtyp die Vorbelegung unterstützt. |
| Ergebnisse sind für Kolleg:innen nicht sichtbar | Prüfe die ausdrücklich eingerichtete Freigabe; ein Teilnahmelink verleiht keine Auswertungsrechte. |

**Abgrenzung:** Ein normales Formular sammelt Antworten. Für ein formales Verwaltungsverfahren mit Zuständigkeit, Bearbeitungsschritten und Aktenbezug ist gegebenenfalls [Online-Anträge](online-antraege.md) der passendere Einstieg.

## Ausführliche Bedienung

Die folgenden ausführlicheren Arbeitsschritte stammen aus dem bisherigen Handbuch und wurden passend zu diesem Modul zusammengestellt.

## Formulare erstellen

Menü **Formulare** (Recht „Formulare“). Damit bauen Sie Umfragen, Anmeldungen, Abfragen und Anträge – ähnlich wie Microsoft/Google Forms oder Nextcloud Forms, aber auf dem eigenen Server.

### Ein Formular anlegen

1. Oben einen **Titel** eintippen, z. B. „Anmeldung Seniorenausflug 2026“, und **Formular anlegen**.
2. Es öffnet sich der **Baukasten** (Reiter „Fragen“). Ein neues Formular beginnt mit den Fragen „Name“ und „E-Mail-Adresse“, die Sie anpassen oder löschen können.
3. Oben Titel und **Beschreibung** (erscheint über dem Formular; Links werden anklickbar, `**fett**` wird fett).
4. Rechts unter **Bausteine** Fragen und Gliederungselemente hinzufügen. Ein Klick fügt den Baustein **unter dem ausgewählten Element** ein (das ausgewählte Element hat links einen farbigen Rand).
5. **Speichern** (unten). Solange „Ungespeicherte Änderungen“ steht, ist noch nichts gesichert; beim Verlassen der Seite warnt der Browser.

### Bausteine: Fragen

| Baustein | Für | Einstellungen |
|---|---|---|
| **Kurze Antwort** | Name, Ort, kurze Angaben | Text mit Mindest-/Höchstlänge, **E-Mail-Adresse**, **Telefonnummer**, **Webadresse** (HTTP/HTTPS), **Zahl** (kleinster/größter Wert und Schrittweite) oder **eigenes Muster** (regulärer Ausdruck, z. B. `[0-9]{5}` für eine PLZ); Platzhalter und optional eigene Fehlermeldung |
| **Langer Text** | Anmerkungen, Begründungen | Platzhalter, Mindest-/Höchstlänge, optional eigene Fehlermeldung |
| **Einfachauswahl** | genau eine Antwort (Kreise) | Optionen, „Sonstiges“ mit Freitext, zufällige Reihenfolge |
| **Mehrfachauswahl** | mehrere Antworten (Kästchen) | Optionen, „Sonstiges“, zufällige Reihenfolge, mindestens/höchstens wählen |
| **Auswahlliste** | eine Antwort aus einer langen Liste | Optionen, zufällige Reihenfolge |
| **Datum** | Geburtsdatum, Wunschtermin, Zeitpunkt | feste oder relative Grenzen, Vergangenheit/Zukunft mit optional heute, Mindest-/Höchstalter, Abstand zu einem anderen Datumsfeld, **mit Uhrzeit** (aus = nur Datum) |
| **Uhrzeit** | Ankunftszeit | – |
| **Adresse** | Anschrift von Antragsteller:in, Ort eines Vorhabens | **Vollständige Anschrift** (Straße, Hausnummer, PLZ, Ort) oder **nur PLZ und Ort**; **Adresssuche** (beim Tippen erscheinen Vorschläge, ein Klick füllt alle Felder), **Meinen Standort übernehmen** (die Adresse am aktuellen Standort des Geräts), **Ortsteil** anzeigen, **Koordinaten speichern**. Der Ort wird nach Eingabe der PLZ automatisch ermittelt (bei mehreren Orten zur Auswahl). Alle Felder bleiben von Hand änderbar |
| **Lineare Skala** | Zufriedenheit, Bewertung | von 0 oder 1 bis 2–10, Beschriftung links/rechts |
| **Farbe** | Farbwahl | – |
| **Datei-Upload** | Nachweise, Fotos, Anträge | erlaubte Dateiendungen (z. B. `pdf, jpg, png`), größte Datei (bis 20 MB), Anzahl Dateien (bis 10) |
| **Ort in der Karte** | **Punkt:** Ort eines Schadens · **Linie:** Leitungstrasse, Umleitung · **Fläche:** Baufläche, Sondernutzungsfläche – auch kombiniert | **Was darf eingezeichnet werden** (Punkt, Linie, Fläche – beliebig ankreuzen), **wie viele Objekte höchstens**, GPS-Knöpfe beim Einzeichnen (Punkt am Standort, Standort als Eckpunkt), bei einem einzelnen Punkt Felder für Breite/Länge, **Eigenen Standort zusätzlich erfassen** (unabhängig vom Eingezeichneten, wahlweise Pflicht). Länge und Fläche werden automatisch berechnet |

Jede Frage hat einen **Titel**, eine optionale **Beschreibung** (Hilfetext), **Pflichtfeld** (Nein, Ja oder *Nur unter Bedingung …*), die **Breite** (ganze Zeile, zwei Drittel, halb, Drittel – so stehen z. B. PLZ und Ort nebeneinander; auf dem Handy immer ganze Breite) und den Schalter **Nur unter Bedingung anzeigen**.

### Eingaben verständlich prüfen

Die Regeln eines Feldes erzeugen automatisch einen lesbaren Hinweis für Ausfüllende. Optional kann eine eigene Fehlermeldung hinterlegt werden. Die Prüfung im Browser unterstützt die Eingabe; beim Absenden prüft der Server dieselben maßgeblichen Grenzen erneut.

Bei **Datum** feste früheste/späteste Tage oder Grenzen relativ zum heutigen Tag wählen. Relative Werte sind ganze Tage, etwa **−30** für 30 Tage zuvor oder **7** für in sieben Tagen. **Nur Vergangenheit** und **Nur Zukunft** können den heutigen Tag ausdrücklich einschließen. Altersgrenzen beziehen sich auf vollendete Lebensjahre. Über eine sortierte Auswahl kann ein anderes Datumsfeld als Bezug gewählt werden, zum Beispiel Rückreise frühestens am Tag der Hinreise und höchstens 14 Tage später. Abstände verwenden Kalendertage, auch bei Feldern mit Uhrzeit. Maßgeblich ist die Portal-Zeitzone.

Mehrere gesetzte Grenzen gelten gemeinsam. Widersprüchliche Grenzen werden im Baukasten und beim Speichern auf dem Server zurückgewiesen; vorhandene Einstellungen bleiben dabei erhalten. Neue Prüfregeln werden für neue oder tatsächlich geänderte Antworten angewendet; unveränderte historische Angaben und vorhandene Uploads werden dadurch nicht nachträglich ungültig gemacht. Wenn ein Bezugsdatum geändert wird, wird die Beziehung zu abhängigen Datumsfeldern erneut geprüft. Bei Korrekturanforderungen werden diese Felder deshalb automatisch mit geöffnet; die bisherigen Werte bleiben als Vorbelegung sichtbar.

Textlängen, Zahlenbereiche und positive Schrittweiten sowie Auswahl- und Uploadgrenzen ergänzen die Datumsregeln. Dateiendungen, Dateigröße und Anzahl werden weiterhin anhand der Upload-Einstellungen geprüft. Webadressen müssen HTTP oder HTTPS verwenden.

### Bedingungen: Felder ein- und ausblenden

Beispiel: Die Frage „Rasse“ soll nur erscheinen, wenn bei „Haben Sie einen Hund?“ *Ja* gewählt wurde.

1. Frage „Rasse“ anklicken, **Nur unter Bedingung anzeigen** einschalten.
2. Regel wählen: *Haben Sie einen Hund?* · *ist gleich* · *Ja*. Weitere Vergleiche: ist nicht, enthält, ist ausgefüllt, ist leer, größer als, kleiner als.
3. Mit **+ Regel** weitere Regeln hinzufügen und oben festlegen, ob **alle** (UND) oder **eine** (ODER) zutreffen müssen.

Genauso funktioniert **Pflichtfeld › Nur unter Bedingung** (z. B. „Kennzeichen“ Pflicht, wenn „Fahrzeug vorhanden“ = Ja). Auch eine **Neue Seite** kann bedingt sein – dann wird die ganze Seite übersprungen. Im Baukasten zeigen Abzeichen wie „bedingt sichtbar“, welche Fragen Bedingungen haben. Ausgeblendete Felder werden nicht gespeichert und nicht geprüft.

### Datenblöcke: wiederkehrende Feldgruppen

Unter **Bausteine › Datenblöcke** stehen fertige Gruppen von Feldern, z. B. **Antragsteller:in** (Anrede, Vorname, Nachname, Geburtsdatum, Anschrift, Telefon, E-Mail), **Firma**, **Adresse**, **Bankverbindung**, **Hund** (Name, Rasse, Geschlecht, Wurftag, Chipnummer …) und **Fahrzeug**. Ein Klick fügt den Block ein. Er ist **verknüpft**: Ändert jemand den Block in der Bibliothek, ändert er sich in allen Formularen. Im Formular stellen Sie nur Titel, Breite und Bedingung des ganzen Blocks ein; seine Felder können Sie in Bedingungen anderer Fragen verwenden.

Die **Bibliothek** (Menü **Datenblöcke**) sehen alle mit dem Recht „Formulare“; neue Blöcke anlegen und ändern geht mit dem Recht „Formularbausteine“: **Neuer Datenblock**, Name, Symbol und Beschreibung, dann Felder wie im Baukasten zusammenstellen (auch mit Bedingungen innerhalb des Blocks). **Kopieren** erzeugt einen unabhängigen Block, etwa für eine Variante. Die Liste zeigt, in welchen Formularen ein Block steckt; löschen lässt er sich erst, wenn ihn kein Formular mehr verwendet.

**Optionen eingeben:** In das Feld „Neue Option …“ tippen und Enter drücken. Sie können auch eine **ganze Liste einfügen** (z. B. aus Excel kopiert) – jede Zeile wird eine Option. Optionen lassen sich am Griff ⠿ verschieben und mit ✕ entfernen.

### Bausteine: Gliederung

| Baustein | Wirkung |
|---|---|
| **Überschrift** | Große Abschnittsüberschrift mit optionalem Text |
| **Zwischenüberschrift** | Kleinere Überschrift innerhalb eines Abschnitts |
| **Hinweistext** | Ein hervorgehobener Kasten mit Erklärungen, z. B. Datenschutzhinweis |
| **Trennlinie** | Optische Trennung |
| **Neue Seite** | Ab hier beginnt eine neue Seite. Ausfüllende blättern mit **Weiter** und **Zurück**, sehen einen Fortschrittsbalken und können erst weiter, wenn die Pflichtfelder der Seite ausgefüllt sind. Die neue Seite kann einen eigenen Titel und Text haben |

### Anordnen

- **Übersicht behalten:** Nicht ausgewählte Fragen erscheinen kompakt mit Titel, Typ und Abzeichen (Pflicht, Breite, bedingt); ein Klick klappt die Einstellungen auf.
- **Verschieben:** am Griff ⠿ links oben ziehen, oder mit den Pfeilen ↑ ↓.
- **Duplizieren:** Doppel-Symbol – praktisch für ähnliche Fragen.
- **Löschen:** Papierkorb.
- Unten rechts sehen Sie, wie viele Fragen und Seiten das Formular hat.

**Vorschau** (oben) zeigt das Formular genau so, wie Ausfüllende es sehen – nur ohne Absenden.

> Gibt es schon Antworten, können Sie das Formular trotzdem ändern. Bestehende Antworten bleiben erhalten; gelöschte Fragen fehlen danach aber in Auswertung und Export.

### Einstellungen (Reiter „Einstellungen“)

**Teilnahme**

| Einstellung | Wirkung |
|---|---|
| Nimmt Antworten an | Aus = alle Links zeigen „Formular geschlossen“; neue Formulare und Kopien beginnen geschlossen |
| Frist | Danach werden keine Antworten mehr angenommen. Die Frist steht in Einladung und Erinnerung |
| Anonym | Name und E-Mail von Eingeladenen und Angemeldeten werden nicht zur Antwort gespeichert. Sie sehen bei Einladungen nur, *dass* jemand geantwortet hat (für Erinnerungen) |
| Mehrfach ausfüllen | Bei Aktivierung sind wiederholte Antworten über persönliche und öffentliche Links möglich. Sonst erkennt TAKT bereits abgegebene Antworten bei angemeldeten Personen, persönlichen Einladungen und im gleichen Browser, soweit technisch möglich. Ohne Anmeldung oder persönlichen Nachweis ist eine Einmalteilnahme nicht geräteübergreifend garantiert |
| Eingangsbestätigung | Die ausfüllende Person bekommt eine Kopie ihrer Antworten per Mail (bei öffentlichen Links an die Adresse aus der ersten E-Mail-Frage) |
| Text nach dem Absenden | z. B. „Danke! Wir melden uns bis Freitag.“ |
| Zusammenfassung vor dem Absenden | Vor dem Absenden sehen Ausfüllende alle Angaben noch einmal und können einzelne Abschnitte ändern (ab drei Fragen) |

### Formulare schließen, archivieren und löschen

Die Übersicht bietet **Archiv** und **Papierkorb**. Noch nie veröffentlichte, ungenutzte Entwürfe dürfen Eigentümer oder Administration in den Papierkorb verschieben und dort 30 Tage lang wiederherstellen. Danach werden sie durch den Bereinigungsdienst endgültig entfernt.

Veröffentlichte oder bereits verwendete Formulare werden stattdessen **geschlossen und archiviert**. Antworten, Dateien, Einladungen und vorhandene Antragsvorgänge bleiben erhalten. Archivierte Formulare bleiben auswertbar; Formularbearbeitung, neue Einladungen und neue öffentliche Einsendungen sind gesperrt. Bereits eingegangene Antragsvorgänge können weiterhin bearbeitet werden. Zum erneuten Bearbeiten das Formular reaktivieren; die Annahme neuer Antworten anschließend bewusst einschalten.

Geteilte Bearbeitungsrechte erlauben weder die Löschung des Formulars noch seiner Antworten. Diese Aktionen sind Eigentümer und Administration vorbehalten. Das Entfernen eines einzelnen Feldes im Baukasten ist davon getrennt.

**Benachrichtigung bei neuen Antworten**

| Einstellung | Wirkung |
|---|---|
| Bei jeder neuen Antwort eine E-Mail | an Sie und an weitere Adressen, die Sie eintragen (z. B. das Funktionspostfach) |
| Antworten im Text der Mail | die Angaben direkt lesbar in der Mail |
| Anhang CSV / JSON | die Formulardaten als Datei: **CSV** für Excel, **JSON** für Fachverfahren und automatische Weiterverarbeitung |
| nur die neue Antwort / jeweils alle Antworten | einzelne Antwort oder jedes Mal die komplette Tabelle |

Die Einstellungen gelten auch für Online-Anträge. PDF, CSV, JSON und **hochgeladene Originaldateien** sind unabhängig auswählbar. Für die Eingangsbestätigung gibt es eine getrennte Auswahl; die ausfüllende Person erhält ausschließlich ihre eigene Antwort. Bei Anträgen lassen sich PDF-/Bild-Uploads zusätzlich in das Antrags-PDF einbetten.

Anhänge werden beim Eingang und beim Eingang einer Nachforderung versendet. Bei Nachforderungen enthalten CSV/JSON und PDF den aktuellen Stand einschließlich Nachreichungen; Originaldateien stammen nur aus der neuen Nachreichung. „Alle bisherigen Antworten“ betrifft ausschließlich interne CSV-/JSON-Exporte.

Die **gesamte E-Mail darf höchstens 10 MB (10 × 1024 × 1024 Bytes)** umfassen, einschließlich Kodierung, Mailtext und Logo. Größere Anhänge werden durch Downloadlinks ersetzt. Interne Downloads erfordern Anmeldung und Zugriffsrechte; Links für die eigene Antwort gelten **7 Tage**. Originaldateien bleiben im Portal; die befristete Downloadkopie wird danach gelöscht.

CSV enthält den **Formularnamen pro Antwortzeile**, JSON in den Formularinformationen und pro Antwort. Kartenfragen erhalten in CSV zusätzliche Spalten für Breitengrad, Längengrad, GPS-Genauigkeit, den separat erfassten Gerätestandort und vollständiges GeoJSON. JSON enthält alle Geometrien und den Gerätestandort. Koordinaten verwenden WGS84; GeoJSON ordnet sie als Länge, Breite an.

In der Einzelantwort zeigt eine Karte die gespeicherten Punkte, Linien und Flächen. **In Karte anzeigen** öffnet eine größere Ansicht mit allen Objekten. Rot kennzeichnet eingezeichnete Objekte, Blau den Gerätestandort. Auch ältere gespeicherte Koordinatenformate werden gelesen.

---

---

## Formulare verteilen

Reiter **Teilen**.

### Öffentlicher Link

**Öffentlichen Link erzeugen** – jede:r mit dem Link kann ausfüllen, ohne Anmeldung. Daneben:

- **Kopieren**,
- **Kurzlink erzeugen** (mit dem Recht „Kurzlinks“) – öffnet das Kurzlink-Formular schon ausgefüllt,
- **QR-Code** mit Download als SVG, PNG oder JPG – z. B. für einen Aushang,
- **Neuer Link** – der alte funktioniert dann nicht mehr,
- **Abschalten** – nur noch persönliche Einladungen funktionieren.

### Per E-Mail einladen

Wählen Sie **Benutzer:innen**, **Gruppen** (alle aktuellen Mitglieder werden einzeln eingeladen) und/oder tragen Sie **Gäste** mit E-Mail-Adresse ein. **Einladen**.

Jede Person bekommt einen **persönlichen Link**. Damit sehen Sie in der Liste **Eingeladene**, wer schon geantwortet hat. Dort können Sie

- **alle Offenen erinnern** (eine Erinnerungsmail an alle ohne Antwort),
- einzelne Personen erinnern,
- den persönlichen Link kopieren (z. B. wenn die Mail nicht ankam),
- eine Einladung entfernen (der Link funktioniert dann nicht mehr; abgegebene Antworten bleiben).

Wer schon eingeladen ist, wird beim erneuten Einladen übersprungen.

---

---

## Antworten auswerten

Reiter **Antworten** (die Zahl daneben zeigt, wie viele es sind).

- **Zusammenfassung:** zu jeder Frage, wie viele geantwortet haben. Bei Auswahlfragen und Skalen ein **Diagramm**, bei Skalen und Zahlen der **Durchschnitt**, bei Textfragen die neuesten Antworten. „Sonstiges“-Antworten werden darunter aufgelistet.
- **Einzelne Antworten:** Tabelle mit Nummer, Eingang, Person und den ersten Fragen. Ein Klick öffnet die **Einzelansicht** mit allen Angaben und hochgeladenen Dateien zum Herunterladen; mit den Pfeilen blättern Sie zur nächsten Antwort.
- **Export:** **CSV (Excel)** – öffnet sich mit Umlauten korrekt in Excel – oder **JSON**.
- **Löschen:** einzelne Antworten in der Einzelansicht, oder **Alle löschen** (auch die Dateien; Eingeladene können danach erneut antworten).

### Formular kopieren und löschen

Über **„…“** oben rechts: **Kopie anlegen** (ohne Antworten, Einladungen und öffentlichen Link – z. B. für die Anmeldung im nächsten Jahr) oder **Löschen** (mit allen Antworten und Dateien).

**Als Datei exportieren und importieren** – um ein Formular oder einen Online-Antrag an eine andere Verbandsgemeinde weiterzugeben oder auf einen anderen Server umzuziehen:

- **„…“ › Als Datei exportieren …** lädt Fragen und Einstellungen (inkl. Gebühren und Antragsangaben) als JSON-Datei herunter. Per Häkchen kommen dazu:
  - der **verknüpfte Prozess** (bei Online-Anträgen),
  - die **verwendeten Datenblöcke** (ohne Häkchen werden auf dem Zielportal gleichnamige Datenblöcke verwendet, fehlende fallen weg),
  - die **Einsendungen mit hochgeladenen Dateien** – nur für einen Umzug, da personenbezogen; die Datei ist dann ein ZIP.
- **Formulare › Importieren** liest die Datei ein und erkennt selbst, was enthalten ist. Gleichnamige Datenblöcke werden wiederverwendet, fehlende angelegt. Ein mitgelieferter Prozess wird als Entwurf angelegt (nur mit dem Recht *Prozesse*) und muss nach Prüfung veröffentlicht werden.
- Nicht übernommen werden zuständige Personen und Gruppen, Funktionspostfach, Weiterleitungsregeln, Ablage und der öffentliche Link. Das importierte Formular ist zunächst **geschlossen** – nach dem Prüfen unter *Teilen* öffnen.
- Übernommene Anträge behalten Aktenzeichen, Status und Verlauf; neue Anträge zählen die Aktenzeichen weiter. Der Verlauf vermerkt den Import samt Prüfsumme des Quellservers.

---

---

## Formulare mit Kolleg:innen teilen

Sie können ein Formular **im Portal** für Kolleg:innen oder ganze Gruppen freigeben – im Reiter **Teilen**, Kasten **Im Portal freigeben** (nur für die Person, die das Formular angelegt hat, und die Verwaltung).

| Stufe | Darf |
|---|---|
| **1 – Ergebnisse einsehen** | Antworten, Zusammenfassung und Export ansehen |
| **2 – Einladen** | zusätzlich Teilnehmende einladen, erinnern und den öffentlichen Link verwalten |
| **3 – Bearbeiten** | zusätzlich Fragen und Einstellungen ändern, Antworten und das ganze Formular löschen |

Die Stufe lässt sich in der Liste jederzeit ändern oder die Freigabe entfernen. Bei Gruppen gilt die Freigabe für alle, die zum jeweiligen Zeitpunkt Mitglied sind. Geteilte Formulare erscheinen bei den Kolleg:innen unter **Formulare › Mit mir geteilt** – auch wenn sie selbst kein Recht zum Erstellen von Formularen haben.

---

---

## Formulare ausfüllen („Zum Ausfüllen“)

Unter **Formulare › Zum Ausfüllen** stehen alle Formulare, zu denen Sie eingeladen wurden – direkt oder über eine Gruppe – mit Frist und Status. **Ausfüllen** öffnet das Formular.

Beim Ausfüllen (auch für Gäste über einen Link):

- Pflichtfelder sind mit <span style="color:#dc3545">*</span> markiert.
- Bei mehrseitigen Formularen **Weiter** und **Zurück**; oben zeigt die **Schrittanzeige** die Seitennamen – erledigte Seiten lassen sich direkt anklicken.
- Manche Fragen erscheinen erst, wenn eine vorherige Antwort passt (z. B. „Rasse“ nach „Hund: Ja“).
- **Adressen:** Straße eintippen und einen Vorschlag anklicken, oder **Meinen Standort übernehmen** klicken; nach der PLZ wird der Ort ergänzt.
- Ihre Eingaben werden **als Entwurf in Ihrem Browser** gesichert. Schließen Sie das Fenster versehentlich, bietet das Formular beim nächsten Öffnen an, den Entwurf wiederherzustellen (Dateien müssen neu gewählt werden). Auf gemeinsam genutzten Geräten: **Verwerfen** klicken.
- Vor dem Absenden zeigt das Formular auf Wunsch eine **Zusammenfassung** aller Angaben.
- Stimmt eine Angabe nicht (z. B. E-Mail-Adresse), markiert das Formular das Feld und erklärt den Fehler.
- **Absenden** speichert die Antwort; danach erscheint der Dank-Text.

---

## Hilfe, Rechte und weiterführende Informationen

- [Allgemeine Bedienung, Sicherheit und Problemlösung](../grundlagen.md)
- [Übersicht aller Module](../../BENUTZERHANDBUCH.md)
- [Ergebnisberichte und Teilnahmebestätigungen](../../UMFRAGEN-ERGEBNISBERICHTE.md).
- Für administrative Einstellungen: [Admin-Handbuch](../../ADMIN-HANDBUCH.md)

> **Hinweis:** Alle Funktionen hängen von den aktivierten Modulen, deiner Rolle und den einzelnen Freigaben ab. Für externe Gäste gelten nur die ausdrücklich angebotenen Zugangswege.
