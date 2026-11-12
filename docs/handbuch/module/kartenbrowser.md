# Kartenbrowser

**TAKT-Benutzeranleitung · aktualisiert: November 2026**

[← Alle Anleitungen](../../BENUTZERHANDBUCH.md) · [Grundlagen & Anmeldung](../grundlagen.md) · [Admin-Handbuch](../../ADMIN-HANDBUCH.md)

> **Wozu?** Karten, Adressen, Flurstücke und freigegebene Fachlayer betrachten.
>
> **Für wen?** Alle mit Zugriff auf die freigegebene Karte; Fachlayer nur nach Freischaltung.

**Im Portal öffnen:** `/karte` (sofern für dich freigeschaltet). Wenn du den Eintrag nicht siehst, nutze **Module entdecken** oder frage nach deinen Rechten.

## Schnellstart: So gehst du vor

1. Öffne den **Kartenbrowser** und suche eine Adresse oder verschiebe die Karte.
2. Schalte benötigte Hintergrundkarten und freigegebene Fachlayer ein.
3. Nutze die Objekt- und Flurstückinformationen entsprechend den freigeschalteten Datenquellen.
4. Teile nur dafür vorgesehene öffentliche Ansichten oder Links.

**Wichtig:** Kartendaten können unverbindliche Fachinformationen enthalten. Geodaten und Eigentumsangaben nicht ohne Rechtsgrundlage weitergeben.

## Ausführliche Bedienung

Die folgenden ausführlicheren Arbeitsschritte stammen aus dem bisherigen Handbuch und wurden passend zu diesem Modul zusammengestellt.

## Kartenbrowser

Menü **Kartenbrowser** (oder `/karte`, auch ohne Anmeldung).

- **Links die Seitenleiste:** oben die **Suche** nach Orten und Adressen (z. B. „Rathaus Otterberg“ oder „Hauptstraße 5, Katzweiler“ – Vorschläge anklicken oder mit ↓ und Enter wählen) und nach Koordinaten (z. B. `49.49, 7.77` oder `UTM 32 412345 5483210`), darunter die **Grundkarte** (basemap.de, OpenStreetMap …) und die **Ebenen** nach Gruppen. Häkchen schaltet eine Ebene ein; dann erscheinen ein Regler für die **Deckkraft** und – bei Zeitreihen (WMS-T) – ein **Zeitregler**. Mit ⠿ ändern Sie die Reihenfolge, ☰ zeigt die **Legende**.
- **Klick in die Karte** zeigt Sachinformationen der eingeschalteten Fachdaten und die Koordinate.
- **Zeichnen & messen** (Seitenleiste): **Punkt**, **Linie** oder **Fläche** wählen und in die Karte klicken. Während des Zeichnens stehen Länge bzw. Fläche oben in der Karte; **Doppelklick** oder **Fertig** beendet, bei Flächen auch ein Klick auf den ersten Punkt. Rücktaste (oder ↶) nimmt den letzten Punkt zurück, Esc bricht ab. Jede Zeichnung erscheint in der Liste: Namen eintippen, Farbe wählen, 🔍 springt hin, 🗑 löscht. Ein Klick auf eine Zeichnung wählt sie aus – ihre Eckpunkte lassen sich dann mit der Maus verschieben. **GeoJSON** lädt die Zeichnungen herunter (z. B. für QGIS), **GeoJSON laden** holt welche in die Karte.
- **Werkzeuge unten:** Kartenbild als PNG speichern, Link zu diesem Ausschnitt kopieren.
- Rechts: Zoomen, nach Norden ausrichten, **eigener Standort**, Vollbild. Unten links stehen die Koordinaten unter dem Mauszeiger in WGS84 und UTM 32.

**Mit dem Recht „Karten“** zusätzlich:

1. **Layer hinzufügen**: Art (WMS/WMS-T, WFS, WMTS) wählen, Adresse des Dienstes eintragen, **Dienst abfragen**, gewünschte Layer anhaken, **Ausgewählte hinzufügen**. Kachelvorlagen mit `{z}/{x}/{y}` gehen auch ohne Abfrage.
2. **Speichern** (Diskette): Titel, Beschreibung und auf Wunsch **öffentlicher Link**. Gespeichert werden Ausschnitt, Grundkarte, Ebenen mit Deckkraft und Zeit, Ihre eigenen Layer und Ihre **Zeichnungen** (auch in geteilten und eingebetteten Karten sichtbar).
3. **Meine Karten**: gespeicherte Karten öffnen, Link kopieren, **Einbettungscode** für Webseiten kopieren, öffentlichen Link abschalten, löschen.

---

---

## Karten: öffentliche Flurstücksauskunft und eigene Dienste

Im Kartenbrowser unter `/karte` wählen Sie **Flurstücke suchen**. Suchen Sie nach Gemarkung und optional Flur, Zähler/Nenner oder dem vollständigen Flurstückskennzeichen. Ein Kartenklick fragt öffentliche ALKIS-Daten für Rheinland-Pfalz ab. Die Ergebnisliste zeigt die verfügbaren Angaben, unter anderem Kennzeichen, Gemarkung, amtliche Fläche, Lage und Nutzung. Eigentümerdaten werden nicht geladen.

Mit **Auswählen und markieren** übernehmen Sie mehrere Flurstücke. Auswahl und Abrufzeitpunkt bleiben beim Speichern der Karte erhalten. CSV und JSON enthalten die gewählten Angaben; **Drucken / PDF** öffnet eine Druckansicht, die über den Browser als PDF gespeichert werden kann. Das Kartenbild ist eine Orientierungshilfe und kein maßstäblicher oder beglaubigter Katasterauszug. Innenflächen bleiben erhalten; eine gemessene Fläche kann von der amtlichen Fläche abweichen.

Alle angemeldeten Portalnutzer können **Layer hinzufügen** und Karten speichern. Öffentliche Besucher können Auskünfte ansehen, aber keine Dienste hinzufügen. Der Quellenkatalog bietet DTK5 RP farbig/grau, LiKa, ALKIS, Verwaltungsgrenzen und Bebauungspläne für Otterbach/Otterberg. Die DTK5 ist die aktuelle amtliche topographische Karte; die Flurstücksgrenzen liefert LiKa beziehungsweise ALKIS als zusätzliche Ebene. Eigene öffentliche WMS/WFS/WMTS-Dienste werden im erweiterten Bereich über ihre Dienstadresse abgefragt. Nicht unterstützte Koordinatensysteme werden kenntlich gemacht.

Im **einfachen Modus** stehen Auskunft, Grundkarten und Ebenen im Vordergrund. Im erweiterten Modus kommen Zeichenwerkzeuge hinzu. Dienste mit Zeitdimension erhalten eine Zeitauswahl; ein Zeitvergleich ist noch nicht enthalten.

Unter **Meine Karten** kann der Eigentümer eine Karte intern für einzelne Benutzer oder Gruppen freigeben. Diese dürfen ansehen und eine eigene Kopie speichern. Öffentliche Links sind eine getrennte, bewusst zu aktivierende Freigabe und können abgeschaltet oder erneuert werden. Interne Systemebenen werden ohne Anmeldung nicht ausgeliefert.

**Karten löschen:** Eigentümer:innen und Admins verschieben eigene Karten einschließlich Zeichnungen, Ebenenauswahl und Flurstückssammlung für **30 Tage** in den Papierkorb. Währenddessen funktionieren interne Freigaben und öffentliche Links nicht. Wiederherstellung macht die Karte zunächst privat: frühere interne Freigaben ausdrücklich bestätigen und einen öffentlichen Link neu erzeugen. Alte öffentliche Links bleiben ungültig.

Formularersteller können bei Kartenfeldern mit erlaubten Flächen **Öffentliche Flurstücke suchen und übernehmen** aktivieren. Ausgewählte Flächen werden mit Kennzeichen, Quelle und Abrufzeit in der Antwort gespeichert und über die bestehenden Antrags- und Ablagewege weitergeführt. JSON und die Geometriespalte der CSV erhalten diese Angaben. Die Anzahl der Teilflächen zählt gegen das Limit des Feldes. Übernommene Katasterflächen lassen sich nicht durch Ziehen von Eckpunkten verfälschen; freie Zeichnungen bleiben verfügbar.

## Hilfe, Rechte und weiterführende Informationen

- [Allgemeine Bedienung, Sicherheit und Problemlösung](../grundlagen.md)
- [Übersicht aller Module](../../BENUTZERHANDBUCH.md)
- Für administrative Einstellungen: [Admin-Handbuch](../../ADMIN-HANDBUCH.md)

> **Hinweis:** Alle Funktionen hängen von den aktivierten Modulen, deiner Rolle und den einzelnen Freigaben ab. Für externe Gäste gelten nur die ausdrücklich angebotenen Zugangswege.

## Für Blöde erklärt:

Du suchst eine Adresse, ein Flurstück oder Informationen auf der Karte?

1. **Kartenbrowser** öffnen.
2. Nach Adresse oder dem gewünschten Ort suchen.
3. Zur richtigen Stelle zoomen.
4. Benötigte Kartenebene beziehungsweise Fachinformation auswählen.
5. Angaben sorgfältig prüfen und bei rechtlich wichtigen Fragen die zuständige Fachstelle einbeziehen.

**Merksatz:** Eine Kartenanzeige ist hilfreich, aber nicht automatisch ein amtlicher Nachweis für jede Fragestellung.
