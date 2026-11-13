# TAKT Karten: native LoD2-Vorschau (Issue #433, Ausbaustufe 1)

## Funktionsumfang

Die Kartenadministration kann einen örtlich begrenzten, manuell bezogenen CityGML-Ausschnitt aus Rheinland-Pfalz importieren. TAKT konvertiert echte Dach- und Wandpolygone in ein lokales, dreidimensionales Dreiecksmesh. In der Karte lässt sich dieses Mesh durch eine ausdrücklich aktivierte MapLibre-WebGL-3D-Ebene ein- und ausblenden. Keine neuen JS-/Python-Abhängigkeiten, kein automatischer Download, keine Änderung der bisherigen Layer oder Benutzerkarten.

- Administration: /admin/maps#lod2-preview, Import .gml/.xml und Entfernen.
- Browser: /karte, Button „LoD2-Dachformen in 3D anzeigen“ mit Status/Fehlern.
- Dateiablage: DATA_DIR/maps3d/lod2-preview.json; atomarer Ersatz.
- Authentifizierte Mesh-/Status-Abfrage; Adminberechtigung plus CSRF für Upload/Löschen.
- Importlimits: 4 MiB Datei, 3.500 Polygonflächen, 16.000 Dreiecke, 4 MiB Mesh, nur unterstützte EPSG:25832-Koordinaten.

## Ergänzung: lokales DGM-Relief (Ausbaustufe 2)

Unter [KARTEN-DGM-RELIEF.md](KARTEN-DGM-RELIEF.md) ist nun ein optionaler DGM-XYZ-Import
mit tatsächlichen Geländedreiecken dokumentiert. Es gibt eine gesonderte,
standardmäßig ausgeschaltete Geländeschicht; Dachflächen und DGM werden
**nur bei vom Administrator bestätigtem gemeinsamen DHHN2016-Höhenbezug**
relativ zum selben LoD2-Import-Höhenursprung dargestellt. Diese lokale
Visualisierung ist weiterhin **keine** zertifizierte Höhenreferenz oder
landesweite DGM-Kacheldarstellung.

## Verbindliche Grenzen

Die Darstellung zeigt echte geneigte Dachflächen, ist aber weiterhin eine **lokale Vorschau ohne amtlichen Höhenabgleich**. Die niedrigste Polygonhöhe wird für die Vorschau auf 0 gesetzt. Ein separater kleiner DGM-XYZ-Ausschnitt kann inzwischen optional zusammen mit LoD2 dargestellt werden; eine zertifizierte Höhenumrechnung, ein räumlich gekachelter Datenserver und Hochleistungs-Streaming für ganz RLP fehlen weiterhin. Höhenangaben in der Vorschau dürfen nicht für Vermessungen oder amtliche Entscheidungen verwendet werden.

Nur CityGML mit direkt eingebetteten RoofSurface-/WallSurface-Polygonen und gml:posList-Dreifachkoordinaten wird unterstützt. Polygone mit Innenringen, reine XLink-Geometrien und degenerierte Flächen werden ausgelassen; vollständig fehlende Dach-/Wandgeometrien führen zum Fehler. DTD-/ENTITY-Deklarationen und ZIP werden abgewiesen. Ein fehlgeschlagener Import ersetzt kein zuvor verfügbares Modell.

## Bedienung

1. LoD2-GML offiziell aus dem GeoShop herunterladen. Für die Vorschau eine kleine Datei/Kachel auswählen, die EPSG:25832 deklariert.
2. Unter Kartenlayer → LoD2-3D-Gebäudemodell die Datei hochladen; Status und Anzahl der gerenderten/ausgelassenen Flächen prüfen.
3. Im Kartenbrowser die 3D-Dächer einschalten. Dachflächen sind ziegelrot, Wände grau. Beim ersten Einschalten wird auf den Ausschnitt gezoomt.
4. Mit dem Schalter die Vorschau ausblenden oder administrativ entfernen.

## Weiterarbeit aus #433

- Belastbare CityGML-Konvertierung mit externen Referenzen, Löchern, komplexen Dachformen, mehreren Kacheln und überprüften geodätischen Transformationen.
- Zertifizierter, geoidgerechter DGM-/DHHN2016-Höhenbezug, kachelbasiertes Terrain und fachlich korrekte Höhenprofile (örtliche XYZ-Geländevorschau ist inzwischen getrennt verfügbar).
- Serverseitige räumlich partitionierte Tiles, Fortschrittsanzeige, Abbruch, Cache/Versionen, Multi-Tenancy und Ressourcenlimits für landesweite Bereitstellung.
- Verifizierte Browser-Benchmarks mit einem echten amtlichen RLP-LoD2-Testausschnitt vor produktiver Nutzung großer Datenmengen.

## Quellen und Lizenz

- LVermGeo: https://lvermgeo.rlp.de/produktinformationen/geotopografie/3d-geodaten/3d-gebaeudemodell
- GeoShop: https://geoshop.rlp.de/opendata-geb3dlo.html
- LoD2-Metadaten: https://metaportal.rlp.de/gui/pdf/0b28684d-b2ce-4b0b-b080-928025588c61
- MapLibre custom 3D layer: https://maplibre.org/maplibre-gl-js/docs/API/interfaces/CustomLayerInterface/

Attribution: © GeoBasis-DE / LVermGeoRP, dl-de/by-2-0, www.lvermgeo.rlp.de [Daten bearbeitet].

**Diese Iteration ist eine erste native LoD2-Vorschau, keine Fertigstellung von #433.**
