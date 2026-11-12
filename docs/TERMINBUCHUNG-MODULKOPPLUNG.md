# Terminbuchung – E-Mail-Darstellung, Schließtage und Modulkopplung

## Bürger-E-Mails

Die Terminbuchung behält die bestehende zentrale Mail-Queue, SMTP-Konfiguration,
eigene Vorlagen und das Erscheinungsbild der Organisation bei. Die Nachricht ist
immer als lesbarer Plaintext **und** als responsives HTML verfügbar.

Bei Terminbestätigungen, Verschiebungen und Absagen mit Kalenderdatei wird
die iMIP-Struktur nach der erprobten CalConnect-Empfehlung aufgebaut:

- `multipart/mixed`
  - `multipart/alternative`: `text/plain`, `text/html` (ggf. mit eingebettetem Logo)
  - `text/calendar;method=REQUEST|CANCEL` (RFC 6047)
  - `application/ics` als Kalenderdatei

Damit ist die gestaltete HTML-Nachricht ein eigenständiger Nachrichtenkörper,
nicht nur eine Alternative hinter dem Kalenderteil. Das verringert die Gefahr,
dass Mailprogramme die Gestaltung durch eine generische ICS-Vorschau ersetzen.
Persönliche Verwalten-Links bleiben nur in berechtigten Gastmails; Mitarbeiter-ICS
enthalten keine Gast-Zugriffstokens. Ältere individuell angepasste Vorlagen behalten
ihre Texte und erhalten, soweit Terminangaben darin erkannt werden, ebenfalls
eine gestaltete Übersicht.

Normen und Empfehlungen:
- https://www.rfc-editor.org/rfc/rfc6047
- https://standards.calconnect.org/docs/cc-r-18003-2019.html

## Schließtage in Sprechzeiten

Für erweiterte Terminarten werden neben manuell eingetragenen Ausnahmen,
gesetzlichen Feiertagen und genehmigten Abwesenheiten auch zentrale
`leave_closures` aus dem Kalender-/Urlaubsbereich berücksichtigt.

- Bezugsorganisation ist die **primäre aktive Organisationseinheit der Person,
  die die Buchungsseite erstellt hat**, nicht die einer zufällig zugewiesenen
  Vertretung oder des aktuell für einen Termin ausgewählten Mitarbeitenden.
- Bei Erstellung wird die Org-ID im bestehenden `integration_json` fixiert.
  Wenn ein Dritter die Seite später übernimmt, ändert sich die Quelle nicht.
- Für bestehende Buchungsseiten ohne gespeicherte Ersteller-Org gilt als
  kompatibler Fallback die aktive primäre Organisationseinheit der aktuellen
  besitzenden Person.
- Schließtage der aktiven Eltern-/Vorfahreneinheiten gelten ebenfalls; die
  Schließtage benachbarter Einheiten werden nicht übernommen.
- Die Funktion ist standardmäßig an, aber je Buchungsseite in
  **Einstellungen** und **Terminarten → Ausnahmen** abschaltbar.
- Die kommenden Schließzeiten sind im Ausnahmebereich lesend sichtbar.
- Schließtage blockieren die neue Slotvergabe und die erneute Prüfung beim
  Abschluss; bereits gebuchte Termine bleiben unverändert.
- Ohne aktive Org-Zuordnung entstehen keine zusätzlichen Sperrtage.

## Modulabhängigkeiten: Empfehlung

TAKT sollte **explizite harte Abhängigkeiten** nur dort verwenden, wo ein
Modul ohne ein anderes fachlich unmöglich betrieben werden kann. Beispiel:
Online-Anträge setzen bereits den Formularserver voraus.

Fachlich getrennte Bereiche benötigen **optionale Integrationsverträge**, keine
automatische Modulaktivierung:

| Funktion | Abhängigkeit | Verhalten bei Deaktivierung |
| --- | --- | --- |
| Bürger-Terminbuchung | Keine harte Abhängigkeit auf Kalender/Urlaub | Buchen, Ändern, E-Mails und ICS funktionieren |
| Feiertage | Zentrale Feiertagsregeln | Unabhängig vom Kalender-Modul gültig |
| Org-Schließtage, Urlaubsabwesenheiten | Optional `module_calendars` | Werden nicht als neue Buchungssperre ausgewertet |
| Persönliche Kalenderkonflikte | Optional `module_calendars` | Prüfung entfällt, gespeicherte Einstellungen bleiben erhalten |
| Kalendereinbindung von Buchungen | Optional `module_calendars` | Keine Kalender-Links; Buchungsseite funktioniert |
| Vertretungshinweise/-Mailkopien | Optional Kalender/Urlaub | Ohne das Modul keine Weiterleitung anhand inaktiver Urlaubs-/Vertretungsdaten |
| Organisationszuordnung | Zentrale TAKT-Kerndaten | Ohne Zuordnung kein Organisations-Sperrtag; manuelle Zuweisung bleibt nutzbar |

Architekturvorschlag für weiteren Ausbau: Jedes registrierte Modul deklariert
`requires` (unabdingbar), `integrates_with` (optional) und
`offers` (bereitgestellte Fähigkeit). Die Adminoberfläche kann deaktivierte
Integrationen kenntlich machen; CI muss wichtige Kombinationen
aktiviert/deaktiviert testen. Kein automatisches Einschalten anderer Module
ohne transparente Entscheidung der Administratoren.

### Qualitätssicherung

Regressionstests prüfen die vollständige MIME-Struktur inklusive ICS, HTML-
Gestaltung trotz alten Vorlagen, Rechteunabhängigkeit von neuen Org-Sperrtagen,
Eltern- und Geschwisterzuordnung, Opt-out, kopierte Buchungsseiten und
Verfügbarkeit bei deaktiviertem Kalender-/Urlaubsmodul.
