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

Jede native Aufgabenkarte bietet eine direkte Statusauswahl mit erlaubten Übergängen. Rückgaben, die einen Kommentar verlangen, bleiben in der ausführlichen Aufgabenbearbeitung. Fehler setzen die Auswahl auf den tatsächlichen vorherigen Kartenstand zurück und zeigen eine verständliche Meldung.

„Rückgängig“ nach Drag-and-drop speichert ursprüngliche Spalte, Position und Aufgabenstatus. Auch der Rückweg verwendet die bestehenden Rechte und Statusregeln; er umgeht keine Freigaben oder Checklisten.

## Speicherung und Tests

Eine statuslose Spalte verwendet den leeren String im bestehenden `TaskBoardColumn.status`. Aufgaben behalten einen gültigen Aufgabenstatus. Es gibt keine Datenbankmigration und keine Erweiterung von Verwaltungsrechten.

Backendtests decken gemischte Spalten, Erstellen/Zuordnen/Verschieben, Statuswechsel, doppelte Zuordnungen, Versionskonflikte, Rechte, Fachquellen und Rückgängig ab. Der erweiterte Browserlauf prüft Maus, Tastatur und Touch, ungespeicherte Eingaben, blockierte Abschlüsse, mobile Darstellung und die vorhandenen Board-Funktionen. Der Aufgaben-Browserlauf prüft die Weiterleitung der ehemaligen zweiten Boardansicht.
