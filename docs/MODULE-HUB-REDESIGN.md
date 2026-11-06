# Modulübersicht – UX-Redesign

**Feature-Branch:** `feat/module-hub-premium` · **Ziel:** `/module` mit vorhandener Serverlogik, ohne neue Fachobjekte.

## Gestaltung und Bedienung

Die Modulübersicht wurde zu einem persönlichen Arbeitsbereich ausgebaut. Ihre Module sind die **bereits serverseitig für die jeweilige Person sichtbaren Modul-Familien**. Individuelle Sidebar-Einstellungen können eine Gruppe ausblenden, aber nicht die Entdeckbarkeit erlaubter Module beeinflussen.

- **Ein ruhiger Einstieg** mit dynamischer Anzahl der verfügbaren Module und bereits gespeicherten Favoriten. Dekorative App-Symbole sind CSS/FontAwesome; keine neue Designbibliothek, keine Bilddownloads.
- **Favoriten als echte Schnellzugriffe:** Dieselben persönlichen `nav_json.fav`-Einträge wie in der Sidebar, einschließlich angehefteter Unterbereiche (beispielsweise „Besprechung planen“). Keine zweite Favoritentabelle und keine abweichende Berechtigungslogik.
- **Suche:** Namen und vorhandene Beschreibungen, Tätigkeiten und Synonyme. Abfrage wie bisher per GET `/module?q=...` inklusive Umlaut-/Akzentnormalisierung. Das Feld ist auf 160 Zeichen begrenzt. Ohne JavaScript bleibt das vollständige Formular nutzbar.
- **Sinnvolle Fachbereiche:** Nur Kategorien, in denen für die Person mindestens ein Modul sichtbar ist. Die Pillen zeigen je Fachbereich die Anzahl **berechtigter** Module und erhalten Suchbegriff und Sortierung. Die Serverantwort prüft jeden Filter unabhängig vom HTML erneut.
- **Sortierung:** Gewohnte Fachbereichsreihenfolge, A–Z oder Favoriten zuerst. Standardauswahl verändert keine URLs oder Fachmodul-Menüs.
- **Module als klare Karten:** Icons, Kurzbeschreibung, typische Aufgaben, direkter Einstieg, optional aufklappbare **nur tatsächlich verfügbare** Unteransichten. Sternbutton behält die bestehende CSRF-geschützte Favoritenverwaltung und das Limit von zwölf Favoriten.
- **Kontext beim Favorisieren:** Die serverseitige Rückleitung bewahrt ausschließlich erlaubte Filter `q`, `category`, `sort` und springt zu `#module-{id}` zurück. Es werden keine vom Client gelieferten externen Redirects akzeptiert.
- **Echte Leerzustände:** Abweichende Hinweise für „keine Treffer“ und „gar keine Module freigeschaltet“.
- **Administration** erscheint nur bei bestehenden effektiven Administrationsrechten, nicht als für andere Personen angedeutetes oder ausgegrautes Modul.

## Design, Zugänglichkeit und Performance

`portal/app/static/module-hub.css` enthält ausschließlich unter `.module-hub` gültige Regeln. Das Design benutzt die vorhandenen Bootstrap-/Takt-Variablen und die persönlichen Werte für Hell/Dunkel und Komfort-/Kompaktdichte.

Semantische Überschriften, benannte Filter, `aria-current` für den Fachbereich, echte Navigationslinks, `aria-pressed` für Favoriten, sichtbarer Tastaturfokus sowie `prefers-reduced-motion` und `forced-colors` gehören zur Oberfläche. Auf schmalen Displays werden Suche, Filter und Kacheln untereinander angeordnet; es gibt keine feste Mindestbreite, die horizontales Scrollen erzwingt. Das Layout ist ohne zusätzliches JavaScript vollständig funktionsfähig.

Die Suche verarbeitet nur die schon existierenden, autorisierten Titel und Beschreibungen in `nav.catalog`. Es gibt **keine zusätzlichen personenbezogenen Datenbankabfragen**, kein Client-API für verborgene Module und keine weitere Abhängigkeit. Der Server sortiert die maximal vorhandenen Modul-Familien – keine Volltextdatenbank und kein neuer Suchindex erforderlich.

## Sicherheit und Rückwärtskompatibilität

Die bestehende `nav.visible(ctx)`-/`nav.catalog(ctx)`-Prüfung bleibt die **einzige** Quelle für Berechtigungen und Modulaktivierung. Nicht aktivierte oder nicht berechtigte Module, ihre versteckten Unteransichten und Admin-Links werden überhaupt nicht gerendert. Die bestehenden Modul-Endpunkte und Deep Links bleiben erhalten.

Auch `POST /nav/pin` lässt künftig neue Favoriten nur zu, wenn der Zielmenüpunkt **aktuell** sichtbar ist. `POST /module/favorite` verwendet weiterhin CSRF und eine serverseitige Liste erlaubter IDs; ungültige Wünsche werden mit HTTP 403 abgewiesen. Persönliche Anpassungen bleiben im bisherigen `User.nav_json`-Feld und beeinflussen keine Fachrechte.

## Prüfmatrix vor Merge

| Prüfung | Nachweis |
| --- | --- |
| Template kompiliert; Status, Gruppen und Suche vorhanden | `portal/tests/test_module_hub.py` |
| Gleiche Rechte, deaktivierte Module unsichtbar, kein Admin-Leak | `test_module_hub.py`, vorhandene `test_nav_menu.py` |
| Favorite in Fachunterseite, Kontext bei Stern-Aktion, keine externen Redirects | `test_module_hub.py` |
| Alte URLs `/module?q=...`, `/module?category=...`, `/module/favorite` | `test_nav_menu.py`, `test_module_hub.py` |
| Desktop, Tablet, Smartphone, Hell/Dunkel, Tastaturfokus | `portal/tests/browser/navigation_ui_smoke.py` |
| Formularsuche ohne JavaScript und ohne verbotene Links | `navigation_ui_smoke.py` |
| Gesamtportal ohne Seiteneffekte | GitHub-CI für Python- und vorhandene Browserjobs |

**Freigabe:** PR bleibt Draft, bis die GitHub-Prüfungen auf dem abschließenden Commit vollständig erfolgreich sind. Ein grüner Lauf auf einem älteren Commit ersetzt die aktuelle Prüfung nicht.

**Grenze:** Die Oberfläche ist keine Systemsuche über Dokumente, Personen oder Fachverfahren. Angezeigt werden ausschließlich die Zugänge, die für das jeweilige Konto bereits freigegeben sind. Eine spätere Änderung der fachlichen Rechte benötigt weiterhin die bestehende Rechteverwaltung.
