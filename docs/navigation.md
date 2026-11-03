# Portalnavigation

Die interne Navigation verwendet fünf feste Fachbereiche und einen eigenen Administrationseinstieg. `nav.FAMILIES` ordnet jeden vorhandenen Eintrag einem Modul zu. Die stabilen IDs bleiben für persönliche Favoriten erhalten. `ADMIN_SECTIONS` enthält die berechtigten Verwaltungsziele. Ein Inventartest verhindert verwaiste Einträge.

`nav.catalog()` und `nav.build()` verwenden denselben `Ctx` und dieselben bestehenden Sichtbarkeitsprädikate. Der Katalog benötigt keine Abfrage pro Karte. Keine fachliche Routenberechtigung wurde erweitert. Modulabhängigkeiten, direkte Freigaben und gruppenbezogene Zugänge bleiben in den bestehenden Kontextadaptern. Persönliches Ausblenden ist ausschließlich eine Darstellungspräferenz; Suche und Katalog behalten alle erlaubten Ziele.

## Oberflächen

- `/`: persönlicher Tagesüberblick mit Link zum Katalog.
- `/module`: serverseitig durchsuchbare Erklärungen aller verfügbaren Modulfamilien, Kategorieauswahl, Unteransichten und Favoriten. Funktioniert ohne JavaScript.
- `/admin`: nur die vorhandenen Verwaltungsziele der konkreten Person. Auch delegierte Verwaltung ohne Volladmin wird unterstützt.
- Globale Sidebar: Kategorie und Modul. Seltene Aktionen/Unteransichten stehen in der lokalen Modulnavigation, Navigationssuche oder persönlichen Favoriten.
- Breadcrumb: erlaubter Moduleinstieg bzw. Administration. Objektspezifische Pfade bleiben bei den jeweiligen Fachmodulen.

## Präferenzen

`nav_json` und `dashboard_json` bleiben erhalten. IDs und URLs wurden nicht migriert. Die frühere Gruppe `comm` wurde auf Zusammenarbeit und Termine verteilt: ihr bisheriger Ausblendestatus wird bewusst nicht auf beide neuen Bereiche übertragen. Neue Bereiche starten sichtbar. Andere gültige Gruppenpräferenzen und alle Favoriten bleiben erhalten. Persönliche Favoriten auf Unterseiten bleiben verwendbar. Deaktivierte oder unzugängliche Einträge werden bei der Ausgabe gefiltert.

## Prüfung und Einführung

Python-Tests prüfen Inventar, Einzelmarkierung, Favoriten, Gastzugang, Modulabschaltung, Suche und delegierte Administration mit Rechteentzug. Der Chromiumtest prüft die Suche nach Tätigkeiten, ausgeblendete Bereiche, Favoriten, drei Bildschirmbreiten, Hell/Dunkel und die Suche ohne JavaScript.

Vor Freigabe mit Anwendern verbleibt der in Issue #179 beschriebene moderierte Test mit mindestens fünf neuen/erfahrenen Nutzern. Automatisierte Tests ersetzen diesen Verständlichkeitstest nicht. Die Anwendung besitzt weiterhin ihre fachlichen Unteransichten und lokalen Objektpfade; die gemeinsame Navigation ersetzt keine Fachfunktionen.
