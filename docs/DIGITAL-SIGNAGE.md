# TAKT Digital Signage – Fach- und Implementierungsspezifikation

Stand: 11.11.2026. Verbindliche Interviewentscheidungen **1–7 = D**; weitere Entscheidungen gemäß ausdrücklichem Auftrag des Auftraggebers jeweils in der umfassenden empfohlenen Variante. Ziel ist eine modular aufbaubare, datenschutzfreundliche Digital-Signage-Plattform mit besonders guter UI.

## Fachliches Zielbild

- **Bildschirme:** Türschilder, Termin- und Raumübersichten, Mitarbeitersuche, Fachbereichs-/Dienstleistungswegweiser, Empfangsmonitore, Info-Playlists, interaktive Touchterminals und Notfallanzeigen.
- **Gestaltung:** visuelles Studio, vordefinierte Templates, Drag-and-drop, Widgetbibliothek, mehrsprachige und responsive Darstellung, vererbte Org-Designsysteme mit Logos/Wappen, freie Farben, Vorlagen, bedingte Widgets, Rotation, Versionierung, Live-Vorschau, Redaktion/Freigaben.
- **Gebäudemodell:** zentrale Dienststätte/PortalLocation → Gebäude → Geschoss → Zimmer → optional Arbeitsplatz. Mehrere Büros je Person; getrennte Datenschutzfreigabe für öffentlich angezeigte Personendaten. Anknüpfung an Org und Ressourcen, später SVG-Pläne, Eingänge, Aufzüge, Wegegraph und barrierefreie Routen.
- **Kalender:** einheitliche Projektion aus TAKT-Kalendern, Ressourcenbuchungen, Sitzungen und Terminen ohne Replikation personenbezogener Informationen. Displaystatus und freie Slots, optional Buchung/Check-in über ausdrücklich authentifizierte Bedienung.
- **Zugriff:** public / revocable expiring bearer links / authenticated admin / devices with separate rotating credentials. Öffentlich stets Datenminimierung, insbesondere keine Teilnehmer- oder Kontaktinformationen und keine implizite Leseberechtigung auf interne Kalender.
- **Betrieb:** Browser-Kiosk als Mindeststandard; optionale native Player Windows/Linux/Android/Raspberry Pi, eigene Geräteidentität, Heartbeats, Zeitpläne, Offline-Fallback mit sichtbarem Aktualitätsstatus, Fernsteuerung nur wo vom Player unterstützt, Störungen/Audit/Notfallübersteuerung.

## In diesem Initial-PR implementiert

| Thema | Status |
|---|---|
| Modulschalter (standardmäßig aus), Navigation, eigener Permission-Key, Modulkarte, Domain-Policy | Implementiert |
| Zentrales relationales Gebäude-/Etagen-/Raummodell mit optionalen FKs auf bereits vorhandene Orte, Organisationen, Ressourcen/Kalender | Implementiert (additive Tabellen) |
| Mitarbeiter/Büro-M:N Zuordnung mit separatem public-Opt-in | Implementiert (Verwaltungsmaske) |
| Bildschirme, Layout/Theme-Schema, Widgetallowlist, Studio mit Drag-&-Drop und Preview | Implementiert als erste UI-Version |
| Responsive standalone Displays: Raumstatus, Tagesbelegung, Raumagenda, freigegebene Mitarbeiter, Wegweiserziele, Infotext | Implementiert |
| Live-Daten aus bestätigten Ressourcenbuchungen | Implementiert: datensparsam nur belegt bei öffentlichen Screens |
| Public, private und linkgeschützte Anzeigen mit Widerruf und 1–90 Tagen Laufzeit | Implementiert, Token nur als Hash gespeichert |
| „Link an mich mailen“ über TAKT-Notify-Queue mit Rate Limit | Implementiert |
| Eigene Gerätebearer und Heartbeat-API + Revocation | Implementiert als Player-Schnittstellen-Grundlage |
| Geschützte Preview mit Same-Origin-Framepolicy | Implementiert |
| Sicherheits-/Routentests | Hinzugefügt; CI-Ausführung erforderlich |

## Offene Erweiterungen (jeweils als eigenständige Issues)

- #322: Altprofile validiert migrieren; Org-weite Gebäudestammverwaltung statt nur Signage-Bereich; Grundriss-Upload/SVG, Wegknoten, Etagenrouting, Barrierefreiheit; Arbeitsplätze und Fachbereiche fachlich modellieren.
- #323: Voller Canvas-/Grid-Editor inkl. Layern, Snap, Undo/Redo, gespeicherte Entwürfe, Freigabe, Versionen, geplante Playlists, Medienverwaltung und komplexere Widget-Datenbindung.
- #324: Alle Kalenderquellen mit Quellberechtigungen, Ressourcenintervalle über Mitternacht, Check-in/Auth/No-show und Zeitplan-Konfliktmanagement; kein Schreiben aus öffentlichen Kiosks.
- #325: Interaktive Suchindizes für Dienstleistungen, Fachbereiche, Termin-/Besucher-Check-in, echte Routingengine, mobile QR-Routen, Sprachumschaltung, optionale KI-Suche nur in explizit freigegebenen Daten.
- #326: Empfängerfreigaben über Konto-E-Mail hinaus; Gerätebindung, Token-Rotation, SSO-Policy, Auditierung, Reverse-Proxy-Log-Redaction (Bearer-URL-Pfade sind sonst potentiell zugriffsprotokolliert), ergänzende Sicherheitsprüfungen.
- #327: Pairing-Codes, nativer Player, Fleet-Automationen, Offline-Caches mit Datenhaltungs-/TTL-Regeln, Telemetrie, Ausfallalarme, Fernkommandos, zentraler Notfallkanal.
- #328: Skalierungs- und Browsermatrix, visuelle Regression, WCAG-Audit, E2E im Kiosk, Rollback-/Upgrade-Dokumentation, Domains/Proxymonitoring und Security-Freigabe.

## Datenschutz und Sicherheitsprinzipien

- **Keine automatische Veröffentlichung:** neue Displays starten intern und sind standardmäßig nicht öffentlich; öffentliche und per Link abrufbare Ressourcentitel bleiben selbst bei aktivierter Titeloption anonymisiert. Private Termintitel benötigen zusätzlich eine bestehende Ressourcen-Leseberechtigung. Besucher-/Mitarbeiterverzeichnis nur mit gesondertem Flag pro Zuordnung.
- **Minimalprinzip:** Mitarbeiter-Privatprofil `profile_data_enc` wird niemals im Kiosk gelesen. Buchungsnamen, E-Mail-Adressen und andere Kontaktinformationen gelangen nicht in die Projektion.
- **Secrets:** Link- und Geräteschlüssel werden kryptografisch zufällig erzeugt, nur gehasht persistiert und bei Erzeugung einmalig sichtbar. Revocation/Expiry/Modulabschaltung werden serverseitig erzwungen.
- **Betrieb:** System- und Reverse-Proxy-Zugriffslogs dürfen geschützte Linkpfade nicht langfristig speichern; Logmaskierung ist vor öffentlichem Produktionsbetrieb ein **Pflichtpunkt**. Bis dahin geschützte Linkverteilung auf interne Testumgebungen begrenzen. Kein Einbetten fremder Webseiten in Displays.
- **Visuelles Studio:** nur Allowlist-Widgets und syntaktisch validierte Hexfarben; keine nutzereingebetteten Skripte. CSRF und Portal-RBAC bei allen Verwaltungsänderungen; Preview nur für Berechtigte.
- **Offline-/Notfallfunktionen:** erst produktiv aktivieren, wenn Fallback, Aktualitätskennzeichnung und sicherheitskritisches Überschreiben durchgängig getestet sind.

## Betrieb & erste Schritte

1. Modul **Digital Signage** unter Admin → Module aktivieren (initial aus).
2. Benutzerrecht **Digital Signage gestalten** berechtigten Konten zuweisen; Admin darf bereits verwalten.
3. Unter **Digital Signage** eine Anzeige aus Vorlage erzeugen und im Studio Farben, Widgets, Raum-/Ressourcenverknüpfung und Sichtbarkeit pflegen.
4. Ein öffentliches Display unter `/signage/view/<ID>` oder ein geschütztes Display über einen per Mail/Einmalausgabe erzeugten Link öffnen. Geteilte Links lassen sich im Studio einzeln widerrufen.
5. Standorte über bereits existierende zentrale Orte, Gebäude/Geschosse/Räume über die Signage-Verwaltung verknüpfen. Für öffentlich sichtbare Mitarbeiter Zuordnung explizit freigeben.
6. Optional eigenes Signage-Domain-Mapping unter Admin → Domains; nur die freigegebenen öffentlichen Anzeigepfade werden über die Domain zugänglich.

### Erweiterungskontrakt für zukünftige Module

Jeder neue Fachbereich benötigt einen expliziten Eintrag in `main.MODULES`, eine Entscheidung in `modhosts.MODULE_PUBLIC` oder `PORTAL_ONLY`, passende Moduldefault-Settings, Benutzerrechte, Navigation und Modulkarte. `test_domains.py` muss diese Zuordnung CI-seitig erzwingen. Zugang über Proxy-Hosts darf niemals interne `/signage/*/edit`-Pfade freigeben. Eine zentrale Register-Lösung bleibt nach Issue #328 weiterzuentwickeln.
