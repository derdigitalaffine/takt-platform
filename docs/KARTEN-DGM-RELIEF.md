# TAKT Karten: DGM-Geländevorschau mit LoD2 koppeln

## Stand dieser Ausbaustufe

Das Modul **Karten** kann zusätzlich zum amtlichen CityGML-LoD2-Gebäudeausschnitt einen kleinen **DGM-ASCII-XYZ-Ausschnitt** aus Rheinland-Pfalz als tatsächlich triangulierte Geländeoberfläche darstellen. Dach- und Wandgeometrien bleiben über den bereits eingeführten MapLibre-WebGL-Layer sichtbar. Beide Komponenten verwenden dieselbe **relative Darstellungshöhe**: Die orthometrische NH-Höhe der GML/DGM-Werte wird auf die niedrigste Höhe des LoD2-Imports bezogen. Damit bleiben die relativen Höhendifferenzen erhalten, sofern beide Rohdatensätze wirklich DHHN2016 nutzen.

Der Renderer bietet einen **separaten, standardmäßig ausgeschalteten Geländeschalter**, lädt die XYZ-Daten erst nach ausdrücklicher Nutzeraktion und zeigt den Rasterabstand, die Zahl der Flächen und eventuelle Lücken. Der Geländezustand wird nicht stillschweigend mit einem anderen Gebäudemodell kombiniert. Eine visuelle gemeinsame Anhebung über der flachen MapLibre-Grundkartenebene ist möglich, ändert aber die relativen Höhen **nicht**.

## Import und Daten

1. Zuerst einen örtlich begrenzten LoD2-CityGML-Ausschnitt unter **Kartenlayer → LoD2** importieren.
2. Im [GeoShop RLP](https://geoshop.rlp.de/digitale_gelaendemodelle/digitale_gelaendemodelle_dgm.html) einen passenden **DGM-Ausschnitt** beziehen: **ASCII-XYZ** im Lagebezug **ETRS89/UTM32 (EPSG:25832)** und im Höhenbezug **DHHN2016 (EPSG:7837)**. Das XYZ-Format besteht hier aus X, Y, Z pro Zeile und enthält seine CRS-Information selbst nicht.
3. Unter **Kartenlayer → DGM-Geländevorschau** den gemeinsamen amtlichen Lage- und Höhenbezug **ausdrücklich bestätigen** und die Datei (.xyz, .txt oder .asc) importieren.
4. Im Kartenbrowser **LoD2-Dachformen** einschalten und danach **Amtliches DGM-Gelände einblenden** aktivieren. Das Gelände wird in gedecktem Grün, Wände in Grau und Dächer in Ziegelrot dargestellt.
5. Beim Ersetzen der LoD2-Gebäudedatei muss das DGM **neu importiert** werden; die alte Zuordnung wird per SHA-256 automatisch unwirksam.

## Kontrollierbare Schranken

- **Nur kleine lokale Ausschnitte:** maximal 12 MiB XYZ-Upload, 180.000 Eingangspunkte, 1,5 km Kantenlänge, 12.000 triangulierte Geländeflächen und 4 MiB WebGL-JSON. Die konvertierte Flächenzahl wird durch ein begrenztes regelmäßiges Gitter reduziert.
- **Rasterbedingungen:** Gitterweite 1, 2, 5, 10, 25 oder 50 m, vollständig numerische 3D-Koordinaten und rechteckige X-/Y-Rasterstruktur. Nicht unterstützte, widersprüchliche oder sehr große Daten werden verworfen; fehlende Zellen bleiben Löcher und werden nicht durch erfundene Höhen interpoliert.
- **Datenschutz und Zugang:** keine Drittserver-Abfragen durch den Import, keine ZIP-Verarbeitung, Zugriff auf Mesh und Status erst nach Login, Upload und Löschen nur für **maps_admin** mit CSRF, Import-Rate-Limit und atomare, nicht öffentlich gemountete Ablage unter `DATA_DIR/maps3d/dgm-preview.json`.
- **Geometrische Einschränkung:** keine Geoid-Transformation, kein unabhängiger Nachweis des vertikalen CRS aus XYZ, keine amtliche Höhenanalyse oder standortgenaue Bauvorlage. Der Admin muss die Referenzsysteme anhand der offiziellen Produktbeschreibung bestätigen.
- **Darstellung:** lokales trianguliertes 3D-Relief ohne Orthofototextur, nicht mit MapLibre `setTerrain` gleichzusetzen. DGM-Sampler/PNG Terrain-RGB, nahtlose Kacheln, NoData-Masken für weitere Datenquellen und räumliche Aktualisierung sind noch offen.
- **Keine landesweite Verarbeitung:** die öffentlichen 1-km-Kacheln müssen für größere Gebiete künftig als Dienst mit Hintergrundkonvertierung, Caching und LOD aufbereitet werden.

## Abnahme

`tests/test_map_dgm.py` prüft: Höhenursprung mit LoD2, reale Geländeneigung, automatische begrenzte Gitterausdünnung, NoData-Lücken, Rasterfehler, fehlende räumliche Überdeckung, veraltete SHA-Verknüpfungen, atomare Ablage, Anmeldung, Rollen, CSRF und explizite Bestätigung. Die vollständige Testsuite und die vorhandenen Kartenbrowser-Tests müssen vor dem Merge grün sein.

## Amtliche Quellen

- LVermGeo Open Data: https://lvermgeo.rlp.de/geodaten-geoshop/open-data/
- DGM-GeoShop und Formate: https://geoshop.rlp.de/digitale_gelaendemodelle/digitale_gelaendemodelle_dgm.html
- DGM-Metadaten: https://metaportal.rlp.de/gui/pdf/ab69aa3d-e786-41f8-95dc-7b34abb06c41
- MapLibre Custom Layers: https://maplibre.org/maplibre-gl-js/docs/API/interfaces/CustomLayerInterface/

Datenlizenz Deutschland Namensnennung 2.0:
© GeoBasis-DE / LVermGeoRP, dl-de/by-2-0, www.lvermgeo.rlp.de [Daten bearbeitet].

**Issue #433 bleibt offen.** Diese Iteration ergänzt die lokale geländebezogene 3D-Vorschau, nicht den geodätisch zertifizierten oder flächendeckend gestreamten Terrain-Dienst.
