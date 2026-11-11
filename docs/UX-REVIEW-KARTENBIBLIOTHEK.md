# UX-Review Kartenbibliothek

- **Rolle und Aufgabe:** Personen mit `maps_admin` ergänzen passende freie Kartenquellen ohne Kenntnis der technischen Dienstadressen.
- **Hauptaktion:** Quelle → Ebenen auswählen → ausgewählte Ebenen ergänzen. Die Ergänzung aktiviert und veröffentlicht nichts automatisch.
- **Zustände:** Trefferzahl und Filter, keine Treffer, unterstützte Ebenen, keine kompatible Ebene, Quelle ausgefallen, fehlendes Recht, leere/zu große/ungültige Auswahl, erfolgreiche Übernahme und bereits vorhandene Ebene.
- **Normalfall:** Nach Gebiet/Thema suchen, Dienst öffnen, Ebenen auswählen, importieren und danach aktivieren/freigeben.
- **Abbruch und Fehler:** Zur Bibliothek zurück; bei Quellausfall erneut abfragen; bei Ausfall während Übernahme Auswahl behalten; bei geänderter Dienstbeschreibung erneut auswählen; bei Dubletten bestehende Einträge beibehalten.
- **Mobil:** Kartenraster wird einspaltig, Formularfelder umbrechen; Ebene, Kennung und Beschreibung bleiben sichtbar. Kein horizontaler Tabellenzwang im neuen Ablauf.
- **Tastatur und Namen:** Native Suchfelder, Selects, Checkboxes, beschriftete Buttons; sichtbarer gemeinsamer Fokus. Treffer- und Auswahlzahlen als Status. Checkboxbeschriftung ist klickbar. Prüfung mit vollständigem Screenreader bleibt offen.
- **Verborgene Informationen:** Dienstadressen stehen weiterhin im bestehenden Layereditor. Auswahl zeigt Ebenenkennung und Beschreibung. Nur unterstützte Ebenen innerhalb des Katalogumfangs werden angeboten.
- **Erhalt:** Suchen in Ebenen löscht keine Auswahl. Netzwerkfehler bei der Übernahme erhalten die Auswahl. Die Quellfilter werden beim Rücksprung aus der Ebenenauswahl derzeit zurückgesetzt.
- **Konsistenz:** Bestehende Karten, Formulare, Buttons, semantische Themevariablen, Administrationsrechte und CSRF-Prüfung. Keine zusätzliche Frontend-Bibliothek.
