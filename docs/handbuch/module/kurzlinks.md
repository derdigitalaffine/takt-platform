# Kurzlinks & QR-Codes

**TAKT-Benutzeranleitung · aktualisiert: November 2026**

[← Alle Anleitungen](../../BENUTZERHANDBUCH.md) · [Grundlagen & Anmeldung](../grundlagen.md) · [Admin-Handbuch](../../ADMIN-HANDBUCH.md)

> **Wozu?** Lange Internetadressen verkürzen und mit QR-Codes teilen.
>
> **Für wen?** Mitarbeitende mit Freischaltung für Kurzlinks.

**Im Portal öffnen:** `/shortlinks` (sofern für dich freigeschaltet). Wenn du den Eintrag nicht siehst, nutze **Module entdecken** oder frage nach deinen Rechten.

## Schnellstart: So gehst du vor

1. Öffne **Kurzlinks** und füge die Zieladresse ein.
2. Wähle einen sprechenden Linknamen und speichere.
3. Erzeuge im Detailbereich bei Bedarf einen QR-Code im angebotenen Dateiformat.
4. Teste Zieladresse und Link vor dem Druck oder Versand; bei Änderungen den Kurzlink bearbeiten bzw. sperren.

**Wichtig:** Kurzlinks und QR-Codes sind keine Berechtigungsschutzsysteme. Gehe mit geheimen Einladungstoken und personenbezogenen Daten sorgfältig um.

## Ausführliche Bedienung

Die folgenden ausführlicheren Arbeitsschritte stammen aus dem bisherigen Handbuch und wurden passend zu diesem Modul zusammengestellt.

## Kurzlinks und QR-Codes

**QR-Code zu jedem öffentlichen Link:** Neben öffentlichen Links steht ein Knopf mit dem QR-Symbol (z. B. Ressourcen-Katalog und Ressourcenseite, Vereinszugang, Antragskatalog, Formulare, Terminumfragen, Buchungsseiten, Abstimmungen, Gastlinks zu Meetings, Karten, Rechtstexte, Zahlungs- und Buchungslinks). Er öffnet einen Dialog mit Vorschau, Download als **SVG, PNG oder JPG**, Größe, Rand, Farben und Fehlerkorrektur. **Aushang:** Überschrift und Hinweis eintragen, „Aushang“ öffnet eine A4-Druckansicht mit Logo, großem QR-Code und Adresse – zum Ausdrucken oder als PDF speichern. QR-Codes gibt es dort nur für Adressen dieses Portals (auch eigene Modul-Domains).

Menü **Kurzlinks** (Recht „Kurzlinks“). Aus einer langen Adresse wird eine kurze, z. B. `https://…/s/sommerfest` – ideal für Aushänge, Flyer, Amtsblatt und Mails.

### Einen Kurzlink anlegen

1. **Neuer Kurzlink**.
2. **Zieladresse** (die lange Adresse) einfügen.
3. Optional ein **Kürzel** wählen, z. B. `sommerfest`. Leer lassen ergibt ein zufälliges Kürzel. Erlaubt sind Buchstaben, Ziffern, `-` und `_`; Groß-/Kleinschreibung spielt keine Rolle.
4. Optional **Titel** und **Schlagwörter** (zum Wiederfinden und Filtern).
5. **Kurzlink erzeugen**.

**Weitere Einstellungen** (aufklappen):

| Einstellung | Wirkung |
|---|---|
| Gültig ab / bis | Vorher bzw. danach leitet der Link nicht weiter, sondern zeigt einen Hinweis (oder die Seite, die die Verwaltung dafür festgelegt hat) |
| Max. Aufrufe | Nach so vielen Aufrufen ist Schluss, z. B. für begrenzte Anmeldungen |
| Art der Weiterleitung | 302 (Standard) zählt jeden Aufruf. 301 merken sich Browser – spätere Aufrufe fehlen dann in der Statistik |
| Parameter weitergeben | `…/sommerfest?quelle=flyer` hängt `quelle=flyer` an das Ziel an. So sehen Sie z. B. auf der Zielseite, woher Besucher kamen |

### Liste, Statistik, Bearbeiten

In der Liste kopiert das Kopiersymbol den Kurzlink. Über das Diagramm-Symbol öffnen Sie einen Link:

- **Statistik:** Aufrufe pro Tag (7, 30, 90 oder 365 Tage), Browser, Betriebssystem, Gerät und die verweisende Seite. Aufrufe von Bots und automatischen Link-Prüfern (z. B. Mailserver, die Links vorab öffnen) werden getrennt gezählt; mit dem Roboter-Knopf blenden Sie sie ein. **Datenschutz:** IP-Adressen werden nicht gespeichert. Die Aufrufe gibt es auch als CSV.
- **Bearbeiten:** Ziel, Kürzel, Gültigkeit usw. ändern oder den Link **deaktivieren**. Achtung: Wer das Kürzel ändert, macht die alte Adresse ungültig – auch gedruckte QR-Codes.
- **Löschen:** Der Link funktioniert danach nicht mehr, das Kürzel ist wieder frei.

### QR-Codes

Bei jedem Kurzlink gibt es den Reiter **QR-Code**, außerdem den freien **QR-Generator** (Knopf oben in der Kurzlink-Liste) für beliebige Adressen oder Texte.

- **Vorschau** erscheint sofort.
- **Größe**, **Rand**, **Farbe** und **Hintergrund** einstellbar. Achten Sie auf Kontrast: dunkler Code auf hellem Grund.
- **Fehlerkorrektur:** höher wählen, wenn der Code verschmutzen kann oder ein Logo darüber geklebt wird.
- **Download als SVG** (für Druck und Grafikprogramme, beliebig vergrößerbar), **PNG** (Web, Office) oder **JPG** (für Programme, die nur JPG annehmen).

Tipp: Für gedruckte QR-Codes immer einen **Kurzlink** verwenden. Der Code wird dadurch einfacher und besser lesbar, und Sie können das Ziel später ändern, ohne neu zu drucken.

---

## Hilfe, Rechte und weiterführende Informationen

- [Allgemeine Bedienung, Sicherheit und Problemlösung](../grundlagen.md)
- [Übersicht aller Module](../../BENUTZERHANDBUCH.md)
- Für administrative Einstellungen: [Admin-Handbuch](../../ADMIN-HANDBUCH.md)

> **Hinweis:** Alle Funktionen hängen von den aktivierten Modulen, deiner Rolle und den einzelnen Freigaben ab. Für externe Gäste gelten nur die ausdrücklich angebotenen Zugangswege.
