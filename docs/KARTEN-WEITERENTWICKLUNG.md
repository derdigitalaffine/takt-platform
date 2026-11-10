# Karten: Quellenbibliothek und nächste Produktentscheidungen

Stand: 10. November 2026. Grundlage: Repository-main (`22cf746`) und Interview mit dem Auftraggeber.

## Zielbild

Ein gemeinsamer Kartenarbeitsplatz für Bürger, Mitarbeitende und GIS-erfahrene Personen. Die sichtbaren Aktionen folgen den Rechten. Der zentrale Ablauf lautet: Rechtstext (FNP/Bebauungsplan) öffnen → räumlichen Bezug anzeigen → auswerten/messen/zeichnen → Ergebnis speichern oder teilen. Die Eingangsdaten sind gemischt bzw. noch nicht vollständig bekannt.

## Bereits umgesetzt: Bibliothek in Administration → Kartenlayer

40 kuratierte Quelleneinträge mit Suchfunktion sowie Gebiets- und Themenfiltern. Bundesweite Dienste liefern Grundkarten, Gelände, Natur, Wetter, Klima, Boden und Geologie. Regionale Angebote ergänzen NRW, Bayern, Brandenburg/Berlin, Hessen, Sachsen, Thüringen und Rheinland-Pfalz. Es handelt sich nicht um einen vollständigen Katalog sämtlicher Landesdienste.

Quellen werden nicht beim Seitenaufruf abgefragt. Erst „Ebenen auswählen“ lädt die aktuelle Dienstbeschreibung. Die Auswahl bietet eine Suche und Mehrfachübernahme von bis zu 100 Ebenen. Bereits vorhandene Kombinationen aus Diensttyp, Adresse und Ebenenkennung werden übersprungen. Neue Ebenen bleiben deaktiviert, intern und ohne Einfluss auf die Startgrundkarte. Der Admin aktiviert und veröffentlicht sie anschließend über die vorhandenen Einstellungen.

Quellen-, Lizenz- und Anbieterhinweise werden angezeigt und in die übernommenen Ebenen geschrieben. Die bisherigen kommunalen Plandienste behalten ihren gesonderten Hinweis auf Herausgeberbedingungen. Keine pauschale Neulizenzierung fremder Daten. Bei Dienstfehlern bleibt eine schon getroffene Auswahl für einen neuen Versuch erhalten.

Live wurden die Capabilities aller endgültig enthaltenen Dienste erfolgreich abgefragt und unterstützte Ebenen gefunden. Zwei hessische Angebote ohne EPSG:3857 wurden aus der neuen Bibliothek entfernt. Ein vollständiger visueller und fachlicher Test jeder einzelnen angebotenen Ebene ist damit nicht verbunden. Die ALKIS-Flurstücksauskunft als Suchfunktion bleibt weiterhin RLP-spezifisch; zusätzliche Katasterkarten erweitern nicht automatisch diese Suche.

## Masterportal als Funktionsreferenz

Die [offizielle Funktionsübersicht](https://www.masterportal.org/features/features) nennt unter anderem:

- Strecke/Fläche messen; Punkte, Linien, Flächen, Kreise und Texte zeichnen; KML-Ausgabe.
- Ebenentransparenz, Reihenfolge, Themenkategorien und gesonderte Anzeige aktiver Themen.
- Sachinformationen und Metadaten, Koordinatenwerkzeuge, WFS-Suche und gespeicherte Kartenlinks.
- Pufferanalyse, Zeitregler und Kartenvergleich per Layer Swipe.
- Erweiterungen für Import/Export, Höhenprofile und hochauflösenden Druck.

Ein Teil der Funktionen ist regional spezialisiert oder ein Add-on mit eigenen Voraussetzungen. Masterportal ist eine geeignete fachliche Referenz; eine Übernahme des gesamten Viewers sollte separat gegen den bestehenden MapLibre-Unterbau abgewogen werden.

## Empfohlene Reihenfolge

1. **Plan und Rechtstext verbinden.** Pro Fassung des Rechtstextes den Geltungsbereich, zugehörige Kartenebenen, Anlagen und räumliche Daten pflegen. „Auf Karte anzeigen“ zoomt zum Plan und öffnet eine Informationsansicht mit Titel, Gültigkeit und Rücklink. Umgekehrt führt der Kartenklick zum zugehörigen Rechtstext. Öffentliche Zugriffe müssen die Freigabe von Rechtstext, Dokument und Ebene unabhängig prüfen.
2. **Gemischte Planformate unterstützen.** WMS als Kartenebene, GeoJSON/XPlanung über einen validierten Import. Ein gewöhnliches PDF zunächst als Dokument neben dem eingezeichneten Geltungsbereich. Eine passgenaue Rasterüberlagerung erfordert Georeferenzierung; bloßes Hochladen reicht dafür nicht. Im bestehenden Rechtstextmodul ist „Neue Fassung vorbereiten“ eine zeitliche Versionierung, kein räumlicher Planeditor.
3. **Messen und Zeichnen als eigenständige Werkzeuge.** Punkt, Linie, Polygon, Rechteck, Kreis, Text; Stützpunkte bearbeiten, Objekte verschieben/kopieren, Rückgängig/Wiederholen, Farben und Beschriftung. Geodätische Längen/Flächen, wählbare Einheiten, Umfang, Teilstrecken und Radius. Danach Fangfunktion und Puffer mit geeigneter Geometrieberechnung. Temporäre Messungen und gespeicherte Zeichnungen klar unterscheiden.
4. **Verwertbare Ergebnisse.** Kartenblatt mit Titel, Maßstab, Legende, Quellen, Datum und Zeichnungen. Gespeicherte Ausschnitte und rechtegeprüfte Freigaben; anschließend Planvergleich und Zeitstände. Höhenprofil erst mit einer belastbaren Geländedatenquelle.

## Oberfläche

„Mein Überblick“ und „Aufgaben“ sind die vereinbarten Referenzen: gemeinsamer kompakter Seitenkopf, klare Typografie, ruhige Kartenflächen und einheitliche Aktionen. Der Portalrahmen sowie die Übersicht und Aufgabenliste beruhen auf Bootstrap/Jinja; die Aufgabenboards verwenden inzwischen React und Mantine 9.8.0 (`portal/ui/board.jsx`). Deren Provider übernimmt die Portalschrift und reagiert auf den globalen Hell-/Dunkelmodus. Diese Anbindung ist die konkrete Vorlage für weitere Mantine-Flächen. Die Quellenbibliothek nutzt vorhandene Komponenten und Themevariablen. Eine Mantine-Umstellung des Kartenmoduls ist noch nicht implementiert.

Für den späteren Kartenarbeitsplatz empfehlen sich getrennte Bereiche „Suchen“, „Ebenen“, „Messen & Zeichnen“ und „Sammlung“ mit einer gemeinsamen Objektinformation. Auf Mobilgeräten arbeitet dieselbe Struktur in einer unteren, vergrößerbaren Ablage. Mantine würde die Bedienoberfläche liefern; die eigentliche Kartenfläche kann weiterhin MapLibre rendern. Schrift, Farben, Abstände, Fokus und Dialogverhalten müssen produktweit zusammenpassen.

## Offene Interviewfragen

- Soll bei PDFs zunächst ein Geltungsbereich genügen, oder ist passgenaue Georeferenzierung Pflicht für die erste Version?
- Dürfen Bürger anonym messen/zeichnen und exportieren? Welche Aktionen erfordern Anmeldung, welche ein besonderes Bearbeitungsrecht?
- Welche drei Werkzeuge sind zuerst unverzichtbar: Abstand/Fläche, Kreis/Radius, Beschriftung, Puffer, Fangfunktion, Höhenprofil oder maßstäblicher PDF-Druck?
- Sollen Zeichnungen nur in eigenen Karten leben oder auch als gemeinsame Fachobjekte bearbeitbar sein?

## Ausgewählte Primärquellen

- [BKG TopPlusOpen: Dienst, Nutzung und Quellenvermerk](https://gdz.bkg.bund.de/index.php/default/wms-topplusopen-wms-topplus-open.html)
- [BKG basemap.de: Dienst und Lizenz](https://gdz.bkg.bund.de/index.php/default/wms-basemapde-webraster-wms-basemapde-webraster.html)
- [Bayerische Vermessungsverwaltung: Open Data](https://geodaten.bayern.de/opengeodata/)
- [LGB Brandenburg: Geodienste](https://geobasis-bb.de/lgb/de/geodaten/geodienste/)
- [Hessen: Kartenebenen](https://www.geoportal.hessen.de/article/Kartenebenen/)
- [GeoSN: Luftbildprodukte](https://www.landesvermessung.sachsen.de/luftbild-produkte-4982.html)
- [BfN: Schutzgebiete](https://www.bfn.de/schutzgebiete)
- [DWD: Quellenvermerke](https://www.wettergefahren.de/vorlagen_quellenangabe.html)
