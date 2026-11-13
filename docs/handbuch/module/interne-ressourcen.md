# Interne Ressourcen – Inventar, Lager und dienstliche Buchungen

Das Modul **Interne Ressourcen** ist eine eigenständige TA​KT-Anwendung für den internen Materialpool. Es ist **nicht Teil der externen Räume- und Vermietungsverwaltung** und wird nur angemeldeten, berechtigten Personen angezeigt. Grundlage der Navigation, des Logins und des Rollenmodells sind die [Grundlagen](../grundlagen.md).

## Schnellstart

1. Im Hauptmenü unter **Zusammenarbeit → Interne Ressourcen** den eigenen Modulbereich öffnen (direkter Pfad: `/interne-ressourcen`).
2. Im **Katalog** nach Material, Inventarnummer oder Lagerort suchen und gegebenenfalls nach Kategorie filtern.
3. Auf **Zeitraum reservieren** klicken, Start, Ende, Menge und Zweck angeben. Die Voransicht zeigt freie Stückzahlen; beim Absenden kontrolliert der Server den Bestand erneut.
4. Unter **Reservierungen** eigene Buchungen verfolgen, einen Kalendereintrag (`.ics`) laden oder eine noch nicht ausgegebene Buchung stornieren.
5. Die Lagerverantwortlichen bestätigen die **Ausgabe** und erfassen die **Rücknahme**; noch ausgegebenes Material bleibt blockiert, auch nach dem ursprünglich vorgesehenen Rückgabezeitpunkt.

## Unterschied zur öffentlichen Ressourcenbuchung

| Externe Räume & Vermietung | Interne Ressourcen |
|---|---|
| Hauptmenü **Termine & Veranstaltungen → Räume & Vermietung** | Hauptmenü **Zusammenarbeit → Interne Ressourcen** |
| Räume, öffentlich buchbare Plätze und vermietbare Ausstattung | Dienstlich benötigte Beamer, Leinwände, Pavillons, Fahrzeuge, Mobiliar, Werkzeuge |
| Mietpreise, Kaution, externe Buchende möglich | Keine Preise, Zahlungen, externe Buchungen oder öffentlichen Links |
| Schalter `module_resources` | Eigener Schalter `module_internal_assets` |
| Recht `resources` und ressourcenspezifische Freigaben | Rechte `internal_assets_book` und `internal_assets_manage` |

## Inventar und Lagerorte verwalten

Personen mit **Interne Ressourcen: verwalten** können Inventargegenstände mit Kategorie, Stückzahl, Lagerort, Inventarnummer, optionalem Fahrzeugkennzeichen und internen Hinweisen erfassen. Lagerorte werden zentral gepflegt, z. B. `Rathaus / Keller / Regal B`. Der Bestand lässt sich ändern, aber nicht unter eine schon reservierte/ausgegebene/gesperrte Spitzenlast reduzieren. Gegenstände können deaktiviert werden.

## Wochenplan und Sperrzeiten

Unter **Materialplan** ist der kleinste freie Tagesbestand je Gegenstand sichtbar; eine stundenweise genauere Prüfung erfolgt im Buchungsformular. Wartungssperren verhindern die Buchung des betroffenen Bestands. Ausgegebene Gegenstände bleiben bis zur realen Rückgabe belegt, nicht nur bis zum geplanten Buchungsende.

## Ausgabe, Rücknahme, Historie

Im internen Katalog sehen verwaltende Personen aktuelle Reservierungen, ausgegebene Bestände und die Historie. Aus- und Rückgaben werden mit Zeit und optionalem Hinweis protokolliert. Für Buchende werden fremde personenbezogene Buchungsdetails nicht im Katalog angezeigt.

## Berechtigungen und Moduleinstellung

Administratoren schalten **Interne Ressourcen** unter **Verwaltung → Module** getrennt von **Räume & Vermietung** an oder ab. Die zwei Zugriffsrechte vergeben sie in der Benutzerverwaltung. Das Recht `resources` für die externe Vermietung **berechtigt nicht automatisch** zum internen Gerätepool. Umgekehrt benötigt ein reiner Gerätepool-Buchender keine Rechte für die externe Vermietung. Administratoren haben im eigenen Modul Verwaltungszugriff.

Beim Abschalten bleiben alle Buchungen und Bestände erhalten; die Seiten und alten Verweise sind bis zur Reaktivierung nicht erreichbar. Bestehende Links unter `/resources/intern` werden nur für weiterhin berechtigte Nutzer auf die neue Adresse weitergeleitet.

## Für Blöde erklärt:

**Extern mieten?** → Räume & Vermietung. **Intern Beamer oder Pavillon brauchen?** → Interne Ressourcen. Gerät suchen → Zeitraum wählen → reservieren → abholen → nach dem Einsatz zurückgeben. Wenn du nichts siehst, prüfe den Modulschalter und deine beiden internen Berechtigungen.
