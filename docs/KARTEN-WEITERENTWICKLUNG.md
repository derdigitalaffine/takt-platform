# Karten: Quellenbibliothek und nächste Produktentscheidungen

Stand 11. November 2026. Grundlage: Repository-main (`22cf746`) und Interview mit dem Auftraggeber.

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

## Kartenarbeitsplatz

Im Rechtstexteditor öffnet „Kartenbezug bearbeiten“ einen Kartenausschnitt zum Zeichnen des Geltungsbereichs. Ein Polygon in WGS84 kann auch als GeoJSON eingegeben werden. Die Redaktion wählt optional eine gespeicherte Karte mit Fachlayern und eine PDF-Anlage des Textes. Im veröffentlichten Rechtstext öffnet „Auf Karte anzeigen“ die Planansicht. Sie zeigt den Geltungsbereich und bietet den Rücksprung zum Rechtstext sowie die PDF-Ansicht daneben. Die Freigaben des Texts, der Karte und der Anlage werden bei jedem Aufruf geprüft.

Frühere Fassungen behalten ihren Geltungsbereich und die Zuordnung zu Karte und Anlage. Verknüpfte Karten und Dateien werden über ihre jeweils aktuellen Freigaben geladen. Ein PDF erscheint neben der Karte. Für eine lagegenaue Überlagerung braucht es georeferenzierte Plandaten, etwa über einen WMS in der verknüpften Karte.

„Messen & Zeichnen“ bietet Strecke, Fläche, Rechteck, Kreis, Punkt und Text. Messwerte erscheinen beim Setzen der Punkte. Stützpunkte von Linien und Flächen können verschoben werden. Die Fangfunktion berücksichtigt Punkte und Grenzen eigener Zeichnungen, ausgewählter Flurstücke und des Geltungsbereichs. Um ausgewählte Punkte lässt sich ein Umkreis mit metrischem Radius zeichnen. Kopieren, Rückgängig und Wiederholen stehen im Werkzeugbereich. Anonyme Besucher arbeiten temporär und können exportieren. Dauerhaftes Speichern setzt eine Anmeldung voraus.

Das Kartenblatt enthält Ausschnitt, Maßstab in der Kartenmitte, Datum, Quellen und die Liste der Zeichnungen mit Messwerten. Der Browser kann es als PDF speichern. Für die angegebene Größe wird mit 100 Prozent Skalierung gedruckt. Im Kartenbereich stehen auch PNG und GeoJSON bereit.

Die Oberfläche nutzt Mantine wie die Aufgabenboards und übernimmt die Portalschrift sowie den Hell-/Dunkelmodus. Die Karte läuft mit MapLibre. Ebenen, Zeichnen, Flurstücke und Planbezug haben eigene Bereiche. Auf dem Handy öffnen sich die Werkzeuge in einer Ablage unter der Karte.

## Ausgewählte Primärquellen

- [BKG TopPlusOpen: Dienst, Nutzung und Quellenvermerk](https://gdz.bkg.bund.de/index.php/default/wms-topplusopen-wms-topplus-open.html)
- [BKG basemap.de: Dienst und Lizenz](https://gdz.bkg.bund.de/index.php/default/wms-basemapde-webraster-wms-basemapde-webraster.html)
- [Bayerische Vermessungsverwaltung: Open Data](https://geodaten.bayern.de/opengeodata/)
- [LGB Brandenburg: Geodienste](https://geobasis-bb.de/lgb/de/geodaten/geodienste/)
- [Hessen: Kartenebenen](https://www.geoportal.hessen.de/article/Kartenebenen/)
- [GeoSN: Luftbildprodukte](https://www.landesvermessung.sachsen.de/luftbild-produkte-4982.html)
- [BfN: Schutzgebiete](https://www.bfn.de/schutzgebiete)
- [DWD: Quellenvermerke](https://www.wettergefahren.de/vorlagen_quellenangabe.html)
