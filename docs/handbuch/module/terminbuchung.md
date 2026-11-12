# Terminbuchung

**TAKT-Benutzeranleitung · aktualisiert: November 2026**

[← Alle Anleitungen](../../BENUTZERHANDBUCH.md) · [Grundlagen & Anmeldung](../grundlagen.md) · [Admin-Handbuch](../../ADMIN-HANDBUCH.md)

> **Wozu?** Buchungsseiten für Sprechstunden, Gespräche und Besuche einrichten.
>
> **Für wen?** Berechtigte Anbieter von Buchungsterminen und Gäste über Buchungslinks.

**Im Portal öffnen:** `/bookings` (sofern für dich freigeschaltet). Wenn du den Eintrag nicht siehst, nutze **Module entdecken** oder frage nach deinen Rechten.

## Schnellstart: So gehst du vor

1. Öffne **Terminbuchung** und lege eine Buchungsseite mit Anlass, Dauer und Kontaktweg an.
2. Definiere Sprechzeiten, Pausen und gegebenenfalls Ausnahmetage.
3. Veröffentliche die Buchungsseite und teile den Link.
4. Prüfe eingegangene Termine; Gäste können nach angebotenen Regeln bestätigen, verschieben oder absagen.
5. Kontrolliere den Kalenderabgleich, bevor du Zeitfenster öffentlich freigibst.

**Wichtig:** Interne Kalenderinhalte und Sperrzeiten werden nicht zu frei einsehbaren Personaldaten. Prüfe organisationsweite Schließtage und Zuständigkeiten.

## Praxisbeispiel: Eine Bürgersprechstunde anbieten

**Ausgangslage:** Eine Organisationseinheit bietet an zwei Wochentagen persönliche Gespräche zu je 30 Minuten an.

1. Lege eine Buchungsseite mit einem verständlichen Titel, dem Ort und einer Kontaktmöglichkeit an.
2. Stelle die **Dauer je Termin** ein und plane einen ausreichenden Puffer für die Nachbereitung ein.
3. Hinterlege die tatsächlichen Sprechzeiten. Ergänze Ausnahmen für Urlaub, Fortbildungen und Schließtage, soweit diese Funktion für die Buchungsseite verfügbar und eingerichtet ist.
4. Prüfe, ob die Seite öffentlich gelistet oder nur über persönliche Einladungen erreichbar sein soll. Für vertrauliche Gespräche ist eine kontrollierte Einladung oft geeigneter.
5. Öffne den Buchungslink testweise wie ein Gast. Prüfe lesbare Beschreibungen, auswählbare Zeiten und den Ablauf der Bestätigung.
6. Veröffentliche und teile erst danach die Buchungsseite. Kontrolliere neue Termine regelmäßig in der Terminliste.
7. Bei einer Verhinderung verschiebe oder storniere den betroffenen Termin über die vorgesehene Aktion, damit die Benachrichtigung korrekt ausgelöst werden kann.

## Vor der Veröffentlichung: kurze Kontrolle

- Sind Dauer, Puffer, Fristen und Kapazität passend eingestellt?
- Sind Feiertage, lokale Schließtage und individuelle Ausnahmen berücksichtigt? Organisationsbezogene Schließtage nur dann als automatisch berücksichtigt ansehen, wenn die konkrete Seite dies anzeigt beziehungsweise die Integration aktiv ist.
- Wird ein öffentlicher Link wirklich benötigt, oder reichen persönliche Einladungen?
- Stimmen Ort, Videokonferenzoption und Kontaktangaben?
- Ist klar, wer die Buchungen betreut und bei Abwesenheit vertreten kann?

## Typische Fragen und Lösungen

| Beobachtung | Mögliche Ursache und nächster Schritt |
|---|---|
| Gäste sehen keine freien Zeiten | Zeitbereiche, Buchungsfrist, Kapazität und Ausnahmen prüfen; belegte Zeiten werden nicht erneut angeboten. |
| Ein Gast möchte verschieben | Den Verwaltungslink aus der Bestätigung verwenden oder eine berechtigte Person um Bearbeitung bitten. Fristen beachten. |
| Ein Feiertag ist buchbar | Die konkreten Ausnahmen und gegebenenfalls organisationsweite Schließtage kontrollieren; nicht von einer automatischen Übernahme ausgehen. |
| Kolleg:innen sollen mithelfen | Die abgestuften Freigaben im Bereich **Im Portal freigeben** verwenden; Bearbeitung nur mit angemessener Stufe. |
| Termine fehlen im externen Kalender | Abo-Link und Aktualisierungsintervall des Kalenderprogramms prüfen. Den vertraulichen Abo-Link nicht öffentlich weitergeben. |

## Ausführliche Bedienung

Die folgenden ausführlicheren Arbeitsschritte stammen aus dem bisherigen Handbuch und wurden passend zu diesem Modul zusammengestellt.

## Terminbuchung (z. B. Vorstellungsgespräche)

Menü **Terminbuchung** (Recht „Terminbuchung“). Sie reservieren einen Zeitraum – etwa „Dienstag 9–12 Uhr und Donnerstag 13–16 Uhr“ –, und Bewerber:innen, Bürger:innen oder Kolleg:innen buchen darin **selbst** ein freies Zeitfenster. Wie Microsoft Bookings oder Calendly, aber auf dem eigenen Server.

### Buchungsseite anlegen

1. **Neue Buchungsseite**, Titel (z. B. „Vorstellungsgespräche Sachbearbeitung Bauamt“), Beschreibung, Ort.
2. **Zeitfenster** festlegen:

   | Einstellung | Bedeutung |
   |---|---|
   | Dauer je Termin | z. B. 45 Minuten |
   | Pause danach | Puffer zwischen zwei Gesprächen, z. B. 15 Minuten (zum Notieren, Lüften, Vorbereiten) |
   | Plätze je Termin | 1 = Einzeltermin; mehr z. B. für Infoveranstaltungen |
   | Buchbar bis … Stunden vorher | kurzfristige Buchungen verhindern |
   | Absagen/Verschieben bis … Stunden vorher | danach nur noch direkt bei Ihnen |
   | Erinnerung … Stunden vorher | automatische Erinnerungsmail an den Gast (0 = keine) |
   | Termine je Person | wie viele anstehende Termine eine E-Mail-Adresse gleichzeitig haben darf |
   | Nur mit persönlicher Einladung | **empfohlen für Vorstellungsgespräche**: nur Eingeladene können buchen |
   | Mehrere Terminarten anbieten | erweiterter Umfang: Terminarten mit eigener Dauer, zuständigen Kolleg:innen und Sprechzeiten – Bürger:innen wählen erst das Thema, dann den Termin; auf Wunsch Bestätigung vor dem Termin |
   | Öffentlich unter „Termine buchen“ zeigen | die Seite erscheint im öffentlichen Verzeichnis `/b`, auf der Startseite und in der Suche – z. B. für Bürgersprechstunden |
   | Als Videokonferenz | für jede Buchung entsteht ein eigener, geschützter Konferenzraum; der Gast bekommt seinen Einwahllink (Recht „Videokonferenzen“ nötig) |
   | Telefonnummer verlangen, Zusatztext | z. B. „Bitte bringen Sie Ihre Zeugnisse mit“ |

3. **Anlegen und Zeiten festlegen**.

### Zeitbereiche im Kalender festlegen

Im Wochenkalender **mit der Maus über einen Tag ziehen** – der Bereich wird grün und automatisch in Termine geteilt (bei 45 Minuten + 15 Minuten Pause von 9 bis 12 Uhr: 9:00, 10:00, 11:00). **Klick auf einen grünen Bereich** entfernt ihn (gebuchte Termine darin bleiben). Mittagspause: einfach zwei Bereiche ziehen. Mit den Pfeilen blättern Sie wochenweise, „Tag“ und „Monat“ wechseln die Ansicht.

Alternativ unter dem Kalender **„Zeitbereich per Formular hinzufügen“** – mit **wöchentlicher Wiederholung**, z. B. für eine feste Sprechstunde jeden Dienstag.

### Einladen und teilen

- **Persönlich einladen:** Bewerber:innen einfach zeilenweise eintragen – „Erika Mustermann <erika@example.org>“, „adresse; Name“ oder nur die Adresse; auch zwei Spalten aus Excel lassen sich einfügen. Dazu Benutzer:innen oder Gruppen. Jede Person bekommt eine Mail mit ihrem Link; Name und Adresse sind beim Buchen vorausgefüllt. In der Liste sehen Sie, wer schon gebucht hat; **„Ohne Termin erinnern“** hakt nach.
- **Link zur Buchung** für alle (z. B. für eine offene Sprechstunde) – mit QR-Code und Kurzlink.

### Buchen (Sicht der Gäste)

Link öffnen, oben einen Tag antippen, eine freie Uhrzeit wählen, Name und E-Mail (ggf. Telefon, Nachricht) eintragen, **Termin verbindlich buchen**. Der Gast bekommt sofort eine Bestätigung mit **Kalendereintrag** und einem Link, über den er den Termin **verschieben** oder **absagen** kann (bis zur eingestellten Frist). Belegte Zeitfenster verschwinden automatisch; doppelt buchen ist ausgeschlossen.

### Terminliste, Export und Kalender-Abo

Unter dem Kalender steht die **Terminliste**:

- **Filter:** Status (anstehend, vergangen, abgesagt, alle), Zeitraum von/bis, Suche nach Name, E-Mail, Telefon oder Nachricht, Sortierung. Zusätzlich lassen sich die Spalten anklicken und das Suchfeld der Tabelle nutzen.
- **Aktionen je Termin:** Videokonferenz betreten (bei Online-Terminen), Verwaltungslink des Gastes kopieren, **verschieben** (der Gast bekommt einen neuen Kalendereintrag), **absagen** mit Begründung (das Zeitfenster wird wieder frei).
- **Export (gefiltert):** **iCal** (in Outlook & Co. importieren), **CSV** (Excel), **JSON** (Fachverfahren), **Markdown** (Tabelle für Wiki, Protokoll oder Ticket). Exportiert wird genau die gefilterte Liste.
- **Im eigenen Kalender abonnieren:** „Abo-Link erzeugen“ – in Outlook unter *Kalender hinzufügen › Aus dem Internet* einfügen. Neue Buchungen erscheinen dann automatisch. Der Link ist geheim (enthält Namen und Kontaktdaten) und lässt sich erneuern oder abschalten.

Über „…“ oben: Buchungen **pausieren**, **neuen Link** erzeugen, **Kopie** anlegen (z. B. für die nächste Ausschreibung) oder **löschen** (anstehenden Gästen wird auf Wunsch abgesagt).

---

---

## Terminumfragen und Buchungsseiten teilen

Wie Formulare lassen sich auch Terminumfragen und Buchungsseiten **im Portal mit Kolleg:innen teilen** – etwa mit dem Auswahlgremium eines Bewerbungsverfahrens oder der Vertretung im Urlaub. Ganz unten auf der Umfrage bzw. Buchungsseite: **Im Portal freigeben**, Personen und/oder Gruppen wählen, Berechtigung festlegen, **Freigeben**.

| Stufe | Terminumfrage | Buchungsseite |
|---|---|---|
| **1 – Ergebnisse einsehen** | Abstimmungsergebnis, Teilnehmende, CSV-Export | Kalender (nur lesend), Terminliste, Exporte |
| **2 – Einladen** | zusätzlich Personen einladen, erinnern, Abstimmungslink verwalten | zusätzlich Personen zum Buchen einladen, Buchungslink und QR-Code |
| **3 – Bearbeiten** | zusätzlich Vorschläge und Einstellungen ändern, Termin festlegen, Teilnehmende entfernen | zusätzlich Zeitbereiche und Einstellungen, Kalender-Abo, Termine verschieben/absagen, Seite löschen |

Die Stufe lässt sich in der Liste jederzeit ändern, das ✕ entfernt die Freigabe. Bekommt eine Person über ihre Gruppe und direkt unterschiedliche Stufen, gilt die höhere. Freigaben verwalten nur Sie als Besitzer:in (und Admins).

**Was die Kolleg:innen sehen:** In **Terminumfragen** bzw. **Terminbuchung** erscheint der Bereich **„Mit mir geteilt“** – auch wenn sie selbst keine Umfragen oder Buchungsseiten anlegen dürfen. Ein Hinweis oben zeigt, von wem geteilt wurde und mit welcher Stufe; Knöpfe, die die Stufe nicht erlaubt, sind ausgeblendet. Mails an Gäste und Teilnehmende (Bestätigungen, Hinweise auf neue Buchungen) laufen weiter über Sie.

---

## Hilfe, Rechte und weiterführende Informationen

- [Allgemeine Bedienung, Sicherheit und Problemlösung](../grundlagen.md)
- [Übersicht aller Module](../../BENUTZERHANDBUCH.md)
- Für administrative Einstellungen: [Admin-Handbuch](../../ADMIN-HANDBUCH.md)

> **Hinweis:** Alle Funktionen hängen von den aktivierten Modulen, deiner Rolle und den einzelnen Freigaben ab. Für externe Gäste gelten nur die ausdrücklich angebotenen Zugangswege.

## Für Blöde erklärt:

Du willst, dass andere einen freien Gesprächstermin bei dir buchen können?

1. **Terminbuchung** öffnen und eine Buchungsseite anlegen.
2. Dauer und verfügbare Zeitfenster festlegen.
3. Buchungsregeln und Angaben prüfen.
4. Buchungslink teilen.
5. Eingehende Buchungen in der Terminliste ansehen und Änderungen rechtzeitig mitteilen.

**Merksatz:** Nur Zeiten freigeben, in denen du wirklich Zeit hast.
