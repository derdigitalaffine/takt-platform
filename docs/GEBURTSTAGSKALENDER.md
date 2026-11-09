# Geburtstagskalender – freiwillige Freigabe und Organisationseinstellungen

## Verbindliche Festlegungen (Interview, 09.11.2026)

1. **Pro Organisation konfigurierbar:** Standard ist die gleiche Organisationseinheit; optional direkt verbundene über-/untergeordnete Einheiten oder alle Einheiten derselben Wurzelorganisation. Die Hauptzuordnung der angezeigten Person bestimmt das Regelwerk.
2. **Drei Darstellungen:** read-only Fachquelle im Hauptkalender, eigene Monatsansicht unter /kalender/geburtstage und die nächsten drei Geburtstage auf „Meine Übersicht“.
3. **Persönliche Freigabe:** /profile#birthday mit verschlüsseltem Geburtsdatum und drei Stufen: hidden (Standard), date (ohne Alter), age (mit Alter). Die Freigabe ist unabhängig von der Vorbelegung persönlicher Formularfelder und kann sofort widerrufen werden.
4. **Externe Anbindung:** Pro Organisation steuerbar: private CalDAV-Geräte standardmäßig erlaubt, private widerrufbare ICS-Abonnements standardmäßig aus. Keine öffentlichen Geburtstagskalender; nur bestehende individuelle, schreibgeschützte Gerätedienste.
5. **29. Februar:** Standard in Nicht-Schaltjahren 28. Februar, optional 1. März. In Schaltjahren 29. Februar. Deaktivierte Konten und bei jedem Abruf widerrufene Freigaben oder entfallene Rechte sind ausgeschlossen.

## Sicherheit

Ereignisse werden bei jedem Abruf aus den freiwilligen Profilfeldern und aktuellen Organisationszuordnungen abgeleitet. Das Geburtsjahr wird nicht ausgegeben. Das Alter erscheint nur bei ausdrücklicher Altersfreigabe. Web-, CalDAV- und ICS-Ausgabe werden je Herkunftsorganisation separat freigegeben. Ein normales Kalender-ACL kann die personenbezogenen Zugriffsrechte nicht ausweiten.

Externe Clients können zuvor synchronisierte Daten speichern. Der Widerruf schützt neue Abrufe, löscht jedoch keine bereits gespeicherten Kopien.

## Benutzung

- Persönliche Angabe: Profil → Freiwillige Angaben → Geburtstag & Sichtbarkeit.
- Kalender: Kalender → Geburtstage, außerdem Fachkalender „Geburtstage“ zuschaltbar.
- Dashboard: Meine Übersicht → Nächste Geburtstage.
- Administration: Organisation → Geburtstage oder Geburtstage → Organisationseinstellungen.
- Für CalDAV: die Fachquelle als privaten, schreibgeschützten Kalender hinzufügen und am Gerät wählen.
- Für ICS: sofern freigegeben, über Lesend abonnieren einen individuell widerrufbaren Link erstellen.

## Technische Integration und Abnahme

Es ist keine Schema-Migration erforderlich. birthday_visibility wird in users.profile_data_enc verschlüsselt gespeichert; Organisationseinstellungen in der vorhandenen settings-Tabelle, Schlüssel birthday_<root_id>_*. Der Export und das Löschen freiwilliger Profilangaben behandeln die Freigabe mit. portal/tests/test_birthdays.py prüft Freigabe, Live-ACL, Schaltjahr, externe Kanäle, CSRF und Deaktivierung.
