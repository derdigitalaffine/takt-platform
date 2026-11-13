# TAKT Karten – Masterportal-Benchmark und RLP-Geodatenkatalog

Stand: 13. November 2026.

## Ziel und Architektur

TAKT behält den bestehenden MapLibre-Kern und das Berechtigungsmodell,
die WMS/WMS-T-, WFS-, WMTS-, XYZ- und GeoJSON-Unterstützung, Zeichnen,
Messen, Flurstücksauskunft, Druck und die gespeicherten Nutzerkarten.
Eine erneute Implementierung des Kartenkerns nach Masterportal würde
bestehende Portal-Funktionen und Referenzen unnötig gefährden.

Stattdessen ergänzt diese Iteration einen nutzbaren
**Quellen- und Layerbrowser direkt unter `/karte`**. Amtliche Daten
sind damit nicht mehr ausschließlich über die Adminoberfläche zu finden.

### Vergleich der wichtigsten Masterportal-Funktionen

| Funktion | Stand in TAKT nach dieser Iteration | Weitere Voraussetzungen |
|---|---|---|
| Layerkatalog, Themen, Gebiet, Suche | Öffentliche, durchsuchbare Quellen mit Themen-/Gebietsfilter, Favoriten, Metadaten und Lizenzen | Weitere Anbieter kuratieren |
| Aktivierbare Ebenen | On-demand Capabilities-Abfrage, unterstützte benannte WMS-/WFS-/WMTS-Layer, Mehrfachauswahl | Anbieter muss kompatiblen und erreichbaren Dienst anbieten |
| Aktive Layer, Reihenfolge, Transparenz | Suche, Zähler, aktiver Filter, Sortierung, Deckkraft, Zeit, Legenden, Speichern | Individueller Layer-Swipe weiterhin offen |
| Vektor-Sachinformation, Messung, Zeichnen | Bereits vorhanden, unverändert | Ausbau von Pufferanalyse und Höhenprofilen separat |
| Grundkarten vergleichen | Opt-in Swipe mit synchronisierten MapLibre-Karten, einstellbarer Trennlinie und anderer Grundkarte rechts; kein permanenter zweiter Renderer | Vergleiche beliebiger Fachebenen oder Kartenstände noch offen |
| 3D-Ansicht | 3D-Kameraneigung und optionale Höhen-Extrusion aus vorhandenen GeoJSON/WFS-Gebäudeattributen | Für amtliche LoD2-Dächer zusätzlich CityGML-Konvertierung/3D-Tiles |
| Speichern, Teilen, Export | Bestehende persönliche Karten, sichere Layer-Pfade und Druck bleiben erhalten | Kein hochauflösender serverseitiger Kartenatlas |
| Offene Daten | Erweiterte RLP-Quellen, bundeseinheitliche und länderübergreifende Dienste; OpenRailwayMap | Externe Verfügbarkeit und Lizenzbedingungen gelten |

Vergleichsquelle:
https://www.masterportal.org/en/features/features

### Ergänzung: schnelle Themenwahl und Grundkartenvergleich

- Ein-Tap-Themen (Luftbilder, Kataster, Hochwasser, Umwelt, Bahn, 3D-Gebäude)
  setzen Suche, Region und Favoritenfilter zurück, damit der Nutzer auch mobil
  sofort zu relevanten Quellen gelangt. Auf jeder Quellendetailseite sind
  Originalangebot und Lizenzbedingungen sichtbar.
- Die Vergleichsansicht wird erst auf ausdrücklichen Klick erzeugt. Sie nutzt
  eine zweite MapLibre-Ansicht für eine alternative **Grundkarte**, synchronisiert
  Mittelpunkt, Zoom, Drehung und Neigung mit der Hauptkarte und schneidet die
  rechte Ansicht per Schieberegler zu. Beim Beenden wird der Renderer entfernt.
- Der Kartenvergleich stellt **keinen** vollständigen Masterportal-Layer-Swipe
  dar: die rechte Seite zeigt nur die ausgewählte Grundkarte, während links
  bestehende Fachebenen sichtbar bleiben. Die Funktion benötigt mindestens
  zwei vorhandene kompatible Grundkarten. Ein Extrusions- oder LoD2-Vergleich
  ist nicht Bestandteil dieser Funktion.

### Fachliche Bedienung

- Suche nach Quelle, Region und Fachthema; Ergebnisliste enthält Anbieter,
  Lizenz und Format. Favoriten speichern **nur Quellenschlüssel** lokal,
  niemals Kartenposition, Personen- oder Nutzerdaten.
- Ein Klick auf eine WMS-/WFS-Quelle führt erst dann `GetCapabilities`
  aus. Externe Fehler ergeben Hinweise statt einer defekten Karte.
- Aus der live abgefragten Auswahl werden höchstens zwölf Layer gleichzeitig
  aktiviert; nicht unterstützte Ebenen, zum Beispiel ungeeignete
  Koordinatensysteme, bleiben ausgenommen. Mehrfachaktivierung wird
  unterdrückt. Benutzerspezifische Layer werden über bestehende
  signierte, gegen SSRF abgesicherte Proxy-Pfade geladen.
- Die Bibliothek ergänzt nur die vorhandene Kartenliste; aktive Layer,
  Reihenfolge und Deckkraft bleiben durch die vorhandene Speicherlogik
  persistent. Adminimporte sind wie bisher zunächst inaktiv und privat.
- Öffentliche Besucher erhalten nur Metadaten und freigegebene Layer.
  Als ausdrücklich aktivierbare Ausnahme können sie die kuratierten
  OpenRailwayMap-Overlays auf der öffentlichen, registrierungsfreien
  Kartenansicht nutzen. Kein generischer anonymer Signier-Endpunkt.

## Rheinland-Pfalz: Quellen

**Amtliche WMS/WFS:** DOP20 (20-cm-Luftbilder), historische Luftbilder
mit Zeitdimension, Schummerung 1 m, Höhenlinien, Bodenschätzung,
ATKIS Basis-DLM (WFS) sowie vorhandene topographische Grundkarten,
Liegenschaftskarten, Flurstücke, Grenzen und kommunale
Bebauungspläne. Die technischen Namen werden aus dem jeweiligen
`GetCapabilities` gelesen statt hart codiert. Das Verzeichnis kann
Dienste enthalten, die zeitweise ausfallen, nur bestimmte Maßstäbe
erlauben oder kein EPSG:3857 anbieten.

Quellen und Nachweise:

- https://www.geoportal.rlp.de/mapbender/php/mod_showMetadata.php?id=61675&resource=layer
- https://www.geoportal.rlp.de/mapbender/php/mod_showMetadata.php?id=74200&resource=layer
- https://www.geoportal.rlp.de/mapbender/php/mod_showMetadata.php?id=49358&resource=layer
- https://www.geoportal.rlp.de/mapbender/php/mod_showMetadata.php?id=32876&resource=layer
- https://www.geoportal.rlp.de/mapbender/php/mod_showMetadata.php?id=86762&resource=layer
- https://www.geoportal.rlp.de/spatial-objects/606

**Weitere amtliche RLP-Quellen:** Die Open-Data-Seite verlinkt
zusätzlich den WMS **AFIS RP Festpunktübersicht**, WMS
**Liegenschaften RP**, WFS **ALKIS Punkte**, WFS **ALKIS vereinfacht**
und WFS **Bodenschätzung**. Als kuratierte Einträge sind sie im Browser
verfügbar; die Auswahl lädt die Anbieter-Capabilities erst bei
Nutzeraktion. Die WFS liefern nicht zwingend EPSG:3857 und können bei
ungeeignetem Referenzsystem bewusst als nicht kompatibel abgewiesen
werden; sie sind keine unmittelbare Aussage über Eigentumsverhältnisse.

Quelle: https://lvermgeo.rlp.de/geodaten-geoshop/open-data/
(Amtliche Capabilities-Verweise unter Kataster/Vermessung.)

**3D-Gebäudedaten:** Amtliche LoD1/LoD2-Gebäudemodelle werden
als **CityGML-Download** dokumentiert und direkt mit der amtlichen
3D-Onlineansicht verlinkt. LoD1 sind Blockmodelle, LoD2 enthält
standardisierte Dachformen. Das Katalogobjekt ist vom Typ `download`,
nicht `wms`/ `xyz`; ein Aufruf der üblichen Kachelproxy-Endpunkte
kann diese Daten nicht rendern.

- https://lvermgeo.rlp.de/produktinformationen/geotopografie/3d-geodaten/3d-gebaeudemodell
- https://geoshop.rlp.de/id-3d-gebaeudemodelle/_3d-gebaeudemodelle.html
- https://rlp.plexmap.de/v/RLP-in-3D-neu/

Der GeoShop informiert seit dem 23. Oktober 2026 über eingeschränkte
Verfügbarkeit der 3D-Gebäudemodelle während Wartungsarbeiten.
Für ein natives LoD2-Modell direkt in TAKT wäre eine **separate,
ressourcenbegrenzte Verarbeitung** der rechtmäßig bezogenen
CityGML-Dateien in einen geeigneten 3D-Tiles-/Streaming-Dienst
erforderlich. Dies ist **nicht** Bestandteil dieser Iteration und wird
nicht als bereits funktionierend dargestellt.

**Terrain:** Der DGM1-Bezug wird als Downloadquelle markiert,
keine direkte Gelände-Höhenkachel. Ohne DEM-Vorverarbeitung erhält
die Karte nur eine Kameraneigung, kein echtes Geländerelief.

## OpenRailwayMap

Kuratiert sind die fünf veröffentlichten Stile `standard`, `signals`,
`maxspeed`, `electrification`, `gauge`. Die Tiles sind
**512 × 512 Pixel** und müssen mit korrekter Quellenangabe sowie
angemessener Last verwendet werden. Das ist ein ehrenamtlich
betriebener Best-Effort-Dienst – kein amtlicher, garantierter
Infrastrukturdienst.

Die Overlays werden **nicht automatisch geladen**. Sie sind
ausschließlich auf ausdrücklichen Nutzerklick verfügbar; bei
erhöhter Nutzung oder geschlossenen Enterprise-Anwendungen muss ein
eigener Tile-Dienst vorgesehen werden. **Kein Vorrats-Download,
Massencrawling oder offline Prefetching.** Die öffentliche
Kartenansicht kann die Dienste ohne Registrierung nutzen; im
geprüften Anbieterregelwerk wird dies vorausgesetzt.

Quelle: https://wiki.openstreetmap.org/wiki/DE:OpenRailwayMap/API

## Sicherheit, Migration und Tests

* Öffentlicher Quellenendpunkt führt keine Netzwerkanfragen aus,
  liest keine privaten `MapLayer`/ `UserMap`-Datensätze
  und erfordert kein Benutzerkonto.
* Die serverseitige GetCapabilities-Abfrage ist ausschließlich
  authentifiziert, CSRF-geschützt und begrenzt; die URL wird
  ausschließlich aus dem kuratierten Katalog gelesen.
* Öffentlicher XYZ-Aktivierungspfad akzeptiert nur explizit
  registrierte `orm-*`-Schlüssel. Andere Datenquellen benötigen
  die vorhandene Anmeldung und Signatur.
* Bestehende Layer, Nutzerkarten und gespeicherte Zustände bleiben
  unverändert. Kategorie und optionale `extrude`-Einstellung
  verwenden vorhandenes JSON, keine Migration erforderlich.
* Der Vektor-Extrusionsmodus erlaubt nur numerische und begrenzte
  Höhe (`height`, `height_m`, `measuredHeight` und gegebenenfalls
  `building:levels`). Höhenangaben können fehlen oder fachlich
  ungeeignet sein und ersetzen keine amtlichen LoD2-Dachflächen.
* Regressionstests: `test_map_discovery.py`,
  `test_map_catalog.py`, `test_gis_services.py`,
  `test_maps.py` und die vollständige TAKT-Suite.

Fremde Daten tragen immer die originalen Anbieter-/Lizenzhinweise.
WMS, Luftbilder, Kataster und freiwillige Eisenbahndaten sind
keine rechtsverbindlichen Lagebescheinigungen.
