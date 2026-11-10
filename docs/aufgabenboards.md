# Aufgabenboards

„Meine Aufgaben“ bietet Liste, Kalender und Zeitachse. Der Link „Aufgabenboards“ und der gleichnamige Menüpunkt führen zum einzigen Bereich für eigene und geteilte Boards. Die frühere zweite Boarddarstellung in der Aufgabenübersicht entfällt. Alte Links mit `view=board` leiten auf `view=list` weiter und behalten Suche, Perspektive und Filter. Gespeicherte Ansichten werden beim nächsten Aufruf entsprechend übernommen. Bestehende Board-URLs und Favoriten-IDs bleiben gültig. Der sichtbare Produktname verwendet „Aufgabenboards“; technische IDs bleiben aus Kompatibilitätsgründen erhalten.

## Spalten bearbeiten

Boardverwalter klicken auf den Spaltennamen, die Spaltenart oder das Zahnrad im Kopf. Das Zahnrad erscheint bei Hover und Tastaturfokus, auf Touchgeräten dauerhaft. Der native aufklappbare Editor funktioniert auch ohne JavaScript. Er bearbeitet Name, Statuszuordnung und Position; leere Spalten können dort gelöscht werden. Mitarbeitende und Leser erhalten keine Verwaltungssteuerelemente.

Abbrechen und Escape verwerfen den lokalen Spaltenentwurf. Während ein Entwurf offen ist, pausiert die automatische Aktualisierung. Ungespeicherte Spaltenänderungen werden auch durch andere Aktionen oder manuelles Aktualisieren nicht stillschweigend überschrieben. Fehler lassen die Eingaben stehen. Die bestehende Boardversion schützt vor parallelen Änderungen.

## Spalten und Aufgabenstatus

- **Ohne Status:** reine Organisation. Anlegen, Zuordnen und Verschieben ändern den Aufgabenstatus nicht. Spätere Statusänderungen an der Aufgabe lassen die Karte in dieser Spalte.
- **Statusspalte im Statusboard:** Beim Ablegen wird der zugeordnete Status über die bestehenden Aufgabenregeln angefordert. Checklisten, Abhängigkeiten, Freigaben und Bearbeitungsrechte gelten weiter. Eine notwendige Freigabe kann statt „Erledigt“ den tatsächlichen Status „Wartet auf Freigabe“ erzeugen.
- **Freie Organisation:** alle Spalten organisieren Karten unabhängig vom Aufgabenstatus. Eine gespeicherte Statuszuordnung wird angezeigt, aber beim Verschieben nicht angewendet.
- Änderungen einer Spaltenzuordnung ändern keine Aufgabenstatus. Bestehende Aufgaben in Statusspalten werden nach tatsächlichem Status angezeigt, soweit eine passende Spalte existiert. Ohne passende Zuordnung bleibt die Karte erreichbar; ihr tatsächlicher Status ist immer sichtbar.
- Mehrere Spalten mit gleichem Status sind möglich. Die bewusst gewählte Zielspalte bleibt erhalten.
- Verknüpfte Umfragen/Fachinhalte können organisatorisch verschoben werden. Ihr Status stammt aus der Quelle und wird im Original geändert; dessen Zugriffsrechte werden weiter geprüft.

Der untere Karteneditor bietet für native Aufgaben eine Statusauswahl mit erlaubten Übergängen. Rückgaben, die einen Kommentar verlangen, bleiben in der ausführlichen Aufgabenbearbeitung. Fehler setzen die Auswahl auf den tatsächlichen vorherigen Kartenstand zurück und zeigen eine verständliche Meldung.

„Rückgängig“ nach Drag-and-drop speichert ursprüngliche Spalte, Position und Aufgabenstatus. Auch der Rückweg verwendet die bestehenden Rechte und Statusregeln; er umgeht keine Freigaben oder Checklisten.

## Speicherung und Tests

Eine statuslose Spalte verwendet den leeren String im bestehenden `TaskBoardColumn.status`. Aufgaben behalten einen gültigen Aufgabenstatus. Es gibt keine Datenbankmigration und keine Erweiterung von Verwaltungsrechten.

Backendtests decken gemischte Spalten, Erstellen/Zuordnen/Verschieben, Statuswechsel, doppelte Zuordnungen, Versionskonflikte, Rechte, Fachquellen und Rückgängig ab. Der erweiterte Browserlauf prüft Maus, Tastatur und Touch, ungespeicherte Eingaben, blockierte Abschlüsse, mobile Darstellung und die vorhandenen Board-Funktionen. Der Aufgaben-Browserlauf prüft die Weiterleitung der ehemaligen zweiten Boardansicht.

## Kompakte Karten und Bearbeitung

Karten zeigen den Titel (höchstens zwei Zeilen), Kartentyp, bis zu drei Labels und kompakte Hinweise auf Status, Frist, Priorität und Zuständigkeit. Große Status-/Prioritätsauswahlen und offene Aktionsformulare stehen im Karteneditor. Die sechs nativen Kartentypen **Aufgabe, Checkliste, Idee, Notiz, Entscheidung und Meilenstein** sind Darstellungsarten einer bestehenden Aufgabe. Rechte, Zuständigkeit, Freigaben, Fristen und Statusregeln gelten unverändert. Kartentyp und optionaler Farbstreifen gehören zur jeweiligen Boardzuordnung; dieselbe Aufgabe kann in einem anderen Board anders dargestellt werden. Fachquellen behalten ihren eigenen Inhaltstyp und ihre Originalbearbeitung.

- **Titel anklicken:** Mitarbeitende bearbeiten ihn direkt auf der Karte. Enter speichert, Shift+Enter fügt einen Zeilenumbruch ein, Escape/Abbrechen verwirft den lokalen Entwurf. Aktualisieren und andere Speicheraktionen überschreiben einen offenen Titelentwurf nicht. Leser öffnen die Detailansicht.
- **Bleistift oder freie Kartenfläche:** Ein Mantine-Drawer fährt vom unteren Bildschirmrand ein. Dort stehen Beschreibung, Kartentyp, Farbstreifen, Labels, Zuständigkeit, Frist, Priorität, Status, Checkliste, Dateien, Kommentare, Verlauf und Verschieben/Entfernen bereit. Der Bleistift erscheint bei Hover/Fokus und dauerhaft auf Touchgeräten.
- **Kleine Inhaltsbadges:** Beschreibung, Checklistenfortschritt, Kommentarzahl und Anhangszahl öffnen jeweils ein eigenes Mantine-Modal. Details werden erst beim Öffnen nachgeladen; entfernte Kommentare/Dateien zählen nicht mit. Das Modal enthält einen direkten Weg zum Karteneditor. Fachzugriff und Boardmitgliedschaft werden bei jedem Abruf erneut geprüft.

Karten und Dialoge übernehmen Portal-Schrift, Markenfarbe und Hell-/Dunkelmodus. Escape, Fokusbindung, Fokusrückgabe, reduzierte Bewegung und mobile Ansichten werden unterstützt. Der Editor hält Textentwürfe beim Schließen im Arbeitsspeicher dieses Seitenaufrufs; ein vollständiges Neuladen verwirft sie. Veraltete Aufgabenversionen werden weiterhin abgewiesen. Erfolgreiches Speichern mit anschließendem Ladefehler wird ausdrücklich als gespeichert gemeldet; unklare Speicherantworten werden nicht automatisch wiederholt.

### Frontend und Prüfung

Die neue Kartenoberfläche verwendet lokal gebündeltes React/Mantine, ohne CDN oder zusätzliche Laufzeitdienste. Quellen liegen unter `portal/ui`. Erstellen: `npm ci --prefix portal/ui` und `npm run build --prefix portal/ui`. Die erzeugten Dateien unter `portal/app/static/board-ui.*` sowie die mitgelieferten Mantine-Dateien gehören ins Repository. Ohne JavaScript führen die kompakten Kartentitel zur Originalaufgabe bzw. Fachquelle; der native Spalteneditor bleibt bedienbar.

Backendtests prüfen Kartentypen, boardbezogene Darstellung, Validierung, Versionskonflikte, geschützte Detailabrufe und Badge-Zählungen. Die Zählungen werden mit drei Sammelabfragen statt je Karte geladen. Der Browserlauf prüft Titelbearbeitung, Entwurfserhalt, Badge-Modals, unteren Editor, Statusregeln, Kommentare, Uploads, Rechte, Maus/Touch, Rückgängig, Dunkelmodus und ein synthetisches Board mit 48 Karten.

### Einführung und Rückfallweg

Die bestehende additive Schemaergänzung fügt `task_board_cards.card_type` (Standard `task`) und `cover_color` (Standard leer) hinzu. Ein Test prüft die wiederholbare Ergänzung einer alten Kartentabelle; vorhandene Zuordnungen, Positionen und Freigaben bleiben dabei erhalten. Es erfolgt keine fachliche Datenmigration. Alle lokalen Prüfungen verwenden temporäre synthetische Daten; Produktion wurde nicht geöffnet oder geändert.

Vor einer Veröffentlichung Staging mit vorhandenen Boards, Sicherung und Rückfall auf den bisherigen Programmstand prüfen. Zum Rückfall vorherige Templates/Skripte und Routen wiederherstellen; die beiden zusätzlichen Spalten können bestehen bleiben und werden vom alten Stand ignoriert. Neue Darstellungsarten erscheinen dann wieder als gewöhnliche Aufgaben. Verbleibende Einschränkung: Kartentypen sind keine eigenständigen Fachprozesse; Textentwürfe werden nicht über ein Neuladen hinweg gespeichert.
