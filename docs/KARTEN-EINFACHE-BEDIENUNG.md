# TAKT Karten – einfache Bedienoberfläche

## Ziel

Die bisherige Ansicht hatte mehrere verschachtelte Funktionen gleichzeitig
im Blick: Kartengrundlagen, Fachebenen, Quellensuche, 3D, Kartenvergleich,
Zeichen- und Druckfunktionen. Jetzt wird **das Grundgeschäft zuerst gezeigt**.
Alle bestehenden Kartenfunktionen bleiben erhalten. Der neue Bedienablauf ist
eine reine Präsentationsschicht und ändert **keine** Layer-, Speicher- oder
Berechtigungslogik.

## So bedienst du die Karte

1. **Ort oder Adresse finden.** Oben in der Seitenleiste nach Ort, Straße oder
   Koordinaten suchen. Bei einer Auswahl springt der Kartenausschnitt zum Ziel.
2. **Meine Karte.** Die Startansicht bietet eine einzige
   Grundkarten-Auswahl und eine kompakte Übersicht aller aktuell sichtbaren
   Fachebenen. Eine sichtbare Ebene lässt sich dort mit einem Klick auf
   ihren Namen wieder ausblenden. Andere Ebenen sind weiterhin erreichbar.
3. **Ebenen.** Hier kannst du Fachebenen mit Häkchen einschalten, suchen,
   nach aktiven Ebenen filtern, die Grundkarte detailliert wählen und – auf
   Wunsch – Transparenz, Zeit, 3D-Extrusion und Reihenfolge ändern.
4. **Daten finden.** Der große Quellenkatalog ist ein eigener Bereich.
   Die Suche und Themenchips sind sofort sichtbar, Region, Themenauswahl und
   Favoriten liegen unter **Weitere Filter**. Amtliche Daten werden erst nach
   bewusster Auswahl beim Anbieter abgefragt.
5. **3D und Kartenvergleich.** Diese Spezialfunktionen sind unter
   *Meine Karte* bewusst zunächst eingeklappt. Darin bleiben Schrägansicht,
   Grundkartenvergleich und die lokalen LoD2-/DGM-Schalter erhalten.
6. **Drucken und exportieren.** Druck/PDF/PNG-Möglichkeiten erscheinen erst,
   wenn der eigene Abschnitt aufgeklappt wird. „Speichern“ und „Ausschnitt
   teilen“ bleiben dauerhaft greifbar. „Messen & Zeichnen“ und „Flurstücke“
   bleiben als vorhandene Hauptbereiche unverändert.

## Mobile und Tastatur

- Die drei Unterbereiche „Meine Karte / Ebenen / Daten finden“ haben
  großzügige Touch-Flächen. Im mobilen Bottom-Sheet bleiben bestehende
  Mechanismen zum Vergrößern, Verkleinern und Schließen aktiv.
- Die Unterbereiche unterstützen Tastatur: links/rechts zwischen Tabs,
  Home/Ende zum ersten/letzten. Sichtbarer Fokus ist vorgesehen.
- Keine erneuten MapLibre-Karteninstanzen, keine zusätzliche Geodatenabfrage.
  Bestehende DOM-Elemente werden verschoben, **nicht dupliziert**; Original-IDs
  und Event-Handler bleiben erhalten.
- Ohne die optionale Bedienoberflächen-Erweiterung bleibt die bisherige
  vollständig erreichbare Oberfläche als Fallback vorhanden.

## Administration

Unter **Kartenlayer** befinden sich die selten benötigten 3D-Importe
(CityGML-LoD2 und DGM-XYZ) jetzt zusammen unter
**„3D-Gebäude und Geländemodelle“**. Die Formulare behalten ihre Rollen-
und CSRF-Prüfungen. Die Links
`/admin/maps#lod2-preview` und `/admin/maps#dgm-preview`
öffnen den Abschnitt automatisch.

## Nicht verändert

- Authentifizierungs-, Rechte- und CSRF-Prüfungen
- Quellen- und Layerkatalog, GetCapabilities, Proxy und Caching
- Funktionen für OpenRailwayMap, RLP-Fachdaten und 3D-Visualisierung
- Datenformate, Benutzerkarten, GeoJSON und Flurstückssuche
- MapLibre-Renderer, Mantine-Werkzeuge und Sonderansichten für Rechtstexte

## Technischer Nachweis

Die Source-Assets `static/map-easy-ui.js` und `static/map-easy.css`
werden nach den vorhandenen Karten-Assets geladen.
`tests/browser/map_easy_ui_smoke.py` testet in Chromium:
Startansicht, Tabellen/Layer-ID-Erhalt, Grundkartenauswahl, aktive Fachebenen,
Quellenfilter, Tastatursteuerung, 3D-Aufklappfunktion und mobile Breiten.
Der neue Check läuft verpflichtend in GitHub Actions im Browser-Job.

Die vollständige Portal-Testsuite bleibt als Merge-Voraussetzung gesetzt.
