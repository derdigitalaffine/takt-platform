# TAKT Digital Signage – Fach- und Implementierungsspezifikation

Stand: 11.11.2026. Verbindliche Interviewentscheidungen **1–7 = D**; weitere Entscheidungen gemäß ausdrücklichem Auftrag des Auftraggebers jeweils in der umfassenden empfohlenen Variante. Ziel ist eine modular aufbaubare, datenschutzfreundliche Digital-Signage-Plattform mit besonders guter UI.

## Fachliches Zielbild

- **Bildschirme:** Türschilder, Termin- und Raumübersichten, Mitarbeitersuche, Fachbereichs-/Dienstleistungswegweiser, Empfangsmonitore, Info-Playlists, interaktive Touchterminals und Notfallanzeigen.
- **Gestaltung:** visuelles Studio, vordefinierte Templates, Drag-and-drop, Widgetbibliothek, mehrsprachige und responsive Darstellung, vererbte Org-Designsysteme mit Logos/Wappen, freie Farben, Vorlagen, bedingte Widgets, Rotation, Versionierung, Live-Vorschau, Redaktion/Freigaben.
- **Gebäudemodell:** zentrale Dienststätte/PortalLocation → Gebäude → Geschoss → Zimmer → optional Arbeitsplatz. Mehrere Büros je Person; getrennte Datenschutzfreigabe für öffentlich angezeigte Personendaten. Anknüpfung an Org und Ressourcen, Wegegraph und barrierefreie Routen sind jetzt als additive Fachmodelle vorhanden; SVG-Grundriss-Upload und Lageplan-Overlay bleiben ausstehend.
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
| TAKT-Raumkalender (mit Wiederholungen/Ausnahmen) und bestätigte Ressourcenbuchungen in einer Live-Belegungsprojektion | Implementiert; Kalender wird je Raum mit Quellberechtigung explizit zugeordnet, Titel nur mit interner Quell-ACL |
| Ungespeicherte WYSIWYG-Vorschau mit serverseitigen echten Daten | Implementiert; CSRF-geschützt, ohne Datenbankänderung |
| Unveränderliche Designversionen, Versionskonfliktprüfung und Wiederherstellung ohne Änderungen an Freigaben | Implementiert |
| Indoor-Wegenetz: Wegpunkte, Flure, Aufzüge, Treppen, gerichtete Verbindungen, Dijkstra-Routing und barrierefreie Alternativen | Implementiert; visuelle Grundrissüberlagerung noch ausstehend |
| Bürozuordnungen im persönlichen Profil mit selbst steuerbarer öffentlicher Anzeige | Implementiert; unabhängig von freiwilligen verschlüsselten Profilangaben |
| Sicherer Linkaustausch gegen HttpOnly/Secure-Cookie, widerrufbare Linkfreigaben | Implementiert; Reverse-Proxy-Redaction zusätzlich notwendig |
| Dedizierte Player-Manifest-API (nur erlaubte Projektionen) und Heartbeatstatus | Implementiert; volle Player-Fleet ausstehend |
| Uvicorn-Access-Log-Redaction für Signage-Tokenpfade | Implementiert; Proxy separat absichern |
| Sicherheits-/Routentests | Erweitert; CI für aktuellen Branchabschluss prüfen |

## Offene Erweiterungen (jeweils als eigenständige Issues)

- #322: Altprofile validiert migrieren; Org-weite Gebäudestammverwaltung statt nur Signage-Bereich; Grundriss-Upload/SVG, georeferenzierte Wegpunkte, grafischer Wegenetz-Editor; Arbeitsplätze und Fachbereiche fachlich modellieren.
- #323: Voller Canvas-/Grid-Editor inkl. Layern, Snap, Undo/Redo, separatem Redaktionsentwurf/Freigabe, geplanten Playlists, Medienverwaltung und komplexerer Widget-Datenbindung. Live-Vorschau und technische Designversionen sind bereits umgesetzt.
- #324: Über die umgesetzte Raumkalender-/Ressourcenprojektion hinaus weitere Fachkalenderquellen; Check-in/Auth/No-show, Störungs-/Reinigungsstatus, alternative Räume und Zeitplan-Konfliktmanagement; kein Schreiben aus öffentlichen Kiosks.
- #325: Die jetzt vorhandene Indoor-Routingengine mit echten gerichteten Kanten und barrierefreien Alternativen wird um SVG-Kartenansichten, Fahrstuhl-/Etagenwechselillustration, Dienstleistungs-/Fachbereichssuche, QR-Mobilrouten, Check-in, Mehrsprachigkeit und optionale KI-Suche (nur explizit freigegebene Daten) ergänzt.
- #326: Uvicorn-Logs sind maskiert und geschützte URLs werden gegen Cookies getauscht. Offen: Empfängerfreigaben über Konto-E-Mail hinaus, Geräte-/Token-Rotation, SSO-Policy, umfassende Auditierung, **Reverse-Proxy-Log-Redaction**, ergänzende Sicherheitsprüfungen.
- #327: Pairing-Codes, nativer Player, Fleet-Automationen, Offline-Caches mit Datenhaltungs-/TTL-Regeln, Telemetrie, Ausfallalarme, Fernkommandos, zentraler Notfallkanal.
- #328: Skalierungs- und Browsermatrix, visuelle Regression, WCAG-Audit, E2E im Kiosk, Rollback-/Upgrade-Dokumentation, Domains/Proxymonitoring und Security-Freigabe.

## Datenschutz und Sicherheitsprinzipien

- **Keine automatische Veröffentlichung:** neue Displays starten intern und sind standardmäßig nicht öffentlich; öffentliche und per Link abrufbare Ressourcentitel bleiben selbst bei aktivierter Titeloption anonymisiert. Private Termintitel benötigen zusätzlich eine bestehende Ressourcen-Leseberechtigung. Besucher-/Mitarbeiterverzeichnis nur mit gesondertem Flag pro Zuordnung.
- **Minimalprinzip:** Mitarbeiter-Privatprofil `profile_data_enc` wird niemals im Kiosk gelesen. Buchungsnamen, E-Mail-Adressen und andere Kontaktinformationen gelangen nicht in die Projektion. Mitarbeiter pflegen die öffentliche Sichtbarkeit ihrer zugeordneten Büros im persönlichen TAKT-Profil selbst; eine andere Person kann diese Einstellung dort nicht verändern.
- **Secrets:** Link- und Geräteschlüssel werden kryptografisch zufällig erzeugt, nur gehasht persistiert und bei Erzeugung einmalig sichtbar. Revocation/Expiry/Modulabschaltung werden serverseitig erzwungen.
- **Betrieb:** System- und Reverse-Proxy-Zugriffslogs dürfen geschützte Linkpfade nicht langfristig speichern; Maskierung in Uvicorn ist umgesetzt; **zusätzliche Reverse-Proxy-Logmaskierung ist vor öffentlichem Produktionsbetrieb Pflicht**. Der initiale Aufruf eines per Mail versandten Tokenlinks enthält den Schlüssel trotz anschließendem HTTP-Cookie-Austausch. Bis dahin geschützte Linkverteilung auf interne Testumgebungen begrenzen. Kein Einbetten fremder Webseiten in Displays.
- **Visuelles Studio:** nur Allowlist-Widgets und syntaktisch validierte Hexfarben; keine nutzereingebetteten Skripte. CSRF und Portal-RBAC bei allen Verwaltungsänderungen; Preview nur für Berechtigte.
- **Offline-/Notfallfunktionen:** erst produktiv aktivieren, wenn Fallback, Aktualitätskennzeichnung und sicherheitskritisches Überschreiben durchgängig getestet sind.

## Betrieb & erste Schritte

1. Modul **Digital Signage** unter Admin → Module aktivieren (initial aus).
2. Benutzerrecht **Digital Signage gestalten** berechtigten Konten zuweisen; Admin darf bereits verwalten.
3. Unter **Digital Signage** eine Anzeige aus Vorlage erzeugen; im Studio Farben, Widgets, Raum-/Ressourcenverknüpfung und Sichtbarkeit pflegen. Die Live-Vorschau testet ungespeicherte Anpassungen; spätere Änderungen können über Designversionen wiederhergestellt werden.
4. Ein öffentliches Display unter `/signage/view/<ID>` oder ein geschütztes Display über einen per Mail/Einmalausgabe erzeugten Link öffnen. Geteilte Links lassen sich im Studio einzeln widerrufen.
5. Standorte über zentrale TAKT-Orte, Gebäude/Geschosse/Räume über Signage verknüpfen; Raumkalender nur bei vorhandener Quellfreigabe zuordnen. Mitarbeiter können ihre freigegebenen Bürozuordnungen im eigenen Profil sehen und deren öffentliche Anzeige aktivieren/widerrufen.
6. Für Wegweiser unter Digital Signage ein Wegenetz (Eingänge, Flure, Treppen, Aufzüge, Zielflächen) erfassen; je Wegweiser eine Startposition wählen. Das System berechnet Wege und verfügbare barrierefreie Alternativen.
7. Optional eigenes Signage-Domain-Mapping unter Admin → Domains; nur freigegebene öffentliche Displaypfade werden unter der Domain zugänglich.
8. Gekoppelte Player rufen mit Bearer-Token den schreibgeschützten `/signage/api/device/<ID>/manifest` ab, geben Heartbeats an `/signage/api/device/<ID>/heartbeat` ab und müssen bei Verlust sofort widerrufen werden.

### Erweiterungskontrakt für zukünftige Module

Jeder neue Fachbereich benötigt einen expliziten Eintrag in `main.MODULES`, eine Entscheidung in `modhosts.MODULE_PUBLIC` oder `PORTAL_ONLY`, passende Moduldefault-Settings, Benutzerrechte, Navigation und Modulkarte. `test_domains.py` muss diese Zuordnung CI-seitig erzwingen. Zugang über Proxy-Hosts darf niemals interne `/signage/*/edit`-Pfade freigeben. Eine zentrale Register-Lösung bleibt nach Issue #328 weiterzuentwickeln.

## Passive Wegweiser und Sonderbetrieb

### In Betrieb nehmen

1. In **Standorte, Gebäude und Räume** die Ziele pflegen. Gebäudenamen, Geschossnamen, Ebenen, Zimmernummern, Raumbezeichnungen und die Zugänglichkeit lassen sich an vorhandenen Einträgen korrigieren. Verknüpfte Kalender, Ressourcen und Wegpunkte bleiben dabei erhalten.
2. Für jedes Besucherziel **Raum freigeben** aktivieren. Ein öffentlicher Anzeigename ist optional. Bleibt er leer, folgt der Wegweiser der aktuellen Raumbezeichnung. Die Freigabe gilt für passive Übersichten und Sonderanzeigen. Ein Widerruf entfernt den Raum aus beiden Projektionen.
3. Im Schnellstart **Gebäudeübersicht**, **Geschossübersicht**, **Flurübersicht** oder **Passive Richtungsanzeige** wählen und den Standort einstellen. Die Gebäudeübersicht gruppiert Ziele nach Geschoss. Die Geschossübersicht zeigt Ziele auf dem gewählten Geschoss. Die Flurübersicht zeigt Ziele, die vom Display über Wege im selben Geschoss innerhalb der eingestellten Gehstrecke erreichbar sind. Die Richtungsanzeige kann einen statischen Hinweis mit Pfeil allein oder zusammen mit automatisch gefundenen Zielen zeigen.
4. Für automatische Pfeile den Startpunkt und die Blickrichtung der Besucher vor dem Display im Plan einstellen. Die erste Kante des kürzesten zulässigen Wegs bestimmt die Richtung. Ohne eindeutige erste Richtung erscheint die Ortsangabe allein. Für einzelne Ziele lassen sich Anzeigename, Pfeil, Sortierpriorität und Ausblendung im Normalbetrieb einstellen. Die Option für stufenfreie Wege berücksichtigt die Angaben an Raum, Wegpunkten und Kanten. Eine manuelle Pfeilkorrektur erhält keine automatische Aussage zur Stufenfreiheit.
5. Vorschau am tatsächlichen Bildschirm kontrollieren. Bei vielen Zielen wechselt die Browseranzeige die Seiten ohne Übergangsanimation. Bei reduzierter Bewegung erscheinen alle Zielseiten untereinander. Sichtbarkeit erst nach der Kontrolle auf **Öffentlich** oder **Sicherer Link** setzen.

### Sonderanzeigen einrichten

- Im Editor des betroffenen Displays **Sonderbetrieb** öffnen. Die Vorlagen **Ratssitzung**, **Wahlraum**, **Briefwahlstelle** und **Veranstaltung** liefern einen öffentlichen Standardtitel und eine Vorgabe für die Priorität. Eigene Titel, Hinweise und Zielräume sind frei konfigurierbar. Über den Freigabehaken geht der Eintrag für dieses Display in Betrieb.
- Zeitfenster gelten ab Beginn bis unmittelbar vor Ende. Manuelle Termine werden in Berliner Ortszeit eingegeben. Mehrdeutige oder übersprungene Uhrzeiten bei der Sommerzeitumstellung werden abgewiesen. Die Formularschnittstelle akzeptiert zur eindeutigen Angabe auch ISO-Zeitstempel mit UTC-Offset.
- Alternativ einen berechtigten freien TAKT-Kalender und einen konkreten Termin auswählen. TAKT übernimmt ausschließlich dessen Zeitfenster. Verschiebungen, Serienausnahmen und Löschungen wirken bei der nächsten Abfrage. Eine Serienfreigabe gilt für alle Vorkommen. Beim Abruf werden das Signage-Recht und die Quellberechtigung des freigebenden Kontos erneut geprüft. Kalendertitel, Beschreibungen und Teilnehmende werden aus dieser Quelle nicht veröffentlicht.
- Pro Display gewinnt der gültige Eintrag mit der höchsten Priorität, dann mit dem früheren Beginn, dann der zuerst angelegte Eintrag. Je nach Einstellung ergänzt oder ersetzt er die normale Anzeige. Nach dem Zeitfenster oder Widerruf übernimmt der nächste gültige Eintrag oder der Normalbetrieb.
- Browser fragen bei aktivem Sonderbetrieb und auf passiven Displays alle 30 Sekunden neu ab. Ein Sonderhinweis hat zusätzlich eine kurze Gültigkeit im Browser. Bei abgelaufenem Ersatzbetrieb erscheint bis zur nächsten Antwort ein neutraler Aktualisierungshinweis. Externe Player müssen die Prioritätsentscheidung aus `special` und dessen `valid_until` beachten. Das Manifest liefert zusätzlich `destinations` und `manual_direction`.

### Grenzen und weitere Ausbaustufen

- Die Stammdaten bleiben an die vorhandenen TAKT-Orte, Organisationen, Ressourcen und Kalender angebunden. Ein umfassender zentraler Organisations- und Grundrisseditor, Verschieben und Zusammenführen von Gebäudeteilen, Fachbereichs- und Dienstleistungszuordnungen sowie Importe bleiben in #322 und #325. Die bestehende interaktive Wegweiser-Vorlage behält ihre eigenen Freigaberegeln.
- Sonderanzeigen werden pro Display gepflegt. Displaygruppen, automatische Vorschläge aus separaten Gremien-/Buchungsmodulen, eine Freigabe einzelner Serienvorkommen und ein revisionssicheres Freigabeprotokoll bleiben Ausbaustufen. Die Designhistorie erfasst Gestaltung. Stammdaten, Zielausnahmen und Sonderfreigaben werden separat gepflegt.
- Die Wegweisung setzt vor Ort geprüfte Plankoordinaten, Blickrichtung und korrekt gepflegte Zugänglichkeit voraus. Sie ist für Besucherinformation ausgelegt. Evakuierung, vorgeschriebene Beschilderung und ausfallsicherer Offline-Betrieb gehören zu #327. Für große Installationen, sehr kleine Displays und formale Barrierefreiheitsprüfungen gilt #328.

## Zentrale Sonderbetriebsverwaltung und Gebäude-Assistent

### Schnell zum einsatzfähigen Anzeigesatz

1. **Digital Signage → Gebäudeanzeigen automatisch erzeugen** öffnen, Gebäude auswählen und Gebäude- sowie Geschossübersichten markieren. Optional vorhandene Eingangs-/Flurknoten als weitere Display-Entwürfe übernehmen.
2. TAKT erstellt ausschließlich **private** Anzeigen mit Standort-/Geschossbindung und initialer Designversion. Wiederholtes Ausführen überspringt bereits aus diesem Assistenten erzeugte Anzeigen. Manuell gebaute Displays bleiben unberührt.
3. Die physische Blickrichtung jedes Monitors prüfen und im Studio hinterlegen. **Der Generator errät keine Pfeile**, und automatisch angelegte Anzeigen werden nicht ohne aktive Freigabe öffentlich.
4. In der Raumverwaltung nur solche Ziele veröffentlichen, die tatsächlich für Besucher sichtbar sein dürfen. Der Entzug einer Freigabe wirkt sofort auf die passiven Übersichten und Sonderaktionen.

### Eine Ratssitzung oder Briefwahlstelle zentral ausschildern

1. Unter **Digital Signage → Sonderbetrieb verwalten** Anlass, Gebäude und ausdrücklich freigegebenen Zielraum wählen; anzeigbaren Titel und optionalen Hinweis festlegen.
2. Den Gültigkeitszeitraum selbst eingeben (TAKT interpretiert lokale Zeiten mit Sommerzeitprüfung) oder einen **berechtigten** Termin aus einem freien TAKT-Kalender auswählen. Der Kalendertermin ist ausschließlich eine Zeitquelle: ein vertraulicher Kalendertitel wird **nicht** übernommen.
3. Anzeigebereich wählen: **ganzes Gebäude** (Standard, künftige passende Displays eingeschlossen), **ein Geschoss** (anhand tatsächlicher Displayposition) oder **gezielt ausgewählte Displays**. Bei Gebäude-/Geschossaktionen können einzelne Displays ausgenommen werden.
4. Vorlauf/Nachlauf (je 0–240 Minuten), Darstellungsmodus (besonders hervorgehoben oder Vollbild), Priorität (0–100) und Veröffentlichung einstellen.
5. Mit der **Zeitsimulation** die für jedes Display wirksame Aktion zu einem gewählten Zeitpunkt prüfen. Die Ansicht ist nur für Signage-Berechtigte abrufbar und ändert keine öffentlichen Screens.
6. Bei Ablösung oder Ende des Ereignisses fällt die Anzeige automatisch auf die nächste wirksame Aktion beziehungsweise auf den normalen Gebäude-/Etagenwegweiser zurück.

### Automatische Zuordnung und Sicherheit

- Nur **aktive passive Displays im selben Gebäude** und mit übereinstimmendem Organisationsumfang werden zentral berücksichtigt. Ein Screen mit eigener Sonderanzeige gewinnt bei gleicher Priorität; ansonsten gilt die höchste Priorität.
- Für eine gefundene öffentliche Aktion muss der Zielraum weiterhin **explizit freigegeben** sein. Ein einmal freigegebener Termin begründet **keinen dauerhaften Kalender-Lesezugriff**. Berechtigungen des verantwortlichen Kontos werden beim Abruf erneut geprüft. Ausgeschaltete Displays bleiben abgeschaltet.
- Die zugehörige Browser- und Player-Projektion übernimmt nur den ausdrücklich verfassten öffentlichen Titel/Hinweis, Raumziel und Wegpfeil; keine internen Termintexte, Personen- oder E-Mail-Felder.
- Überlappende **manuelle** Aktionen im selben Gebäude mit gleicher/höherer Priorität erscheinen als Warnung. Für komplexe wiederkehrende Kalendertermine ist eine vollständige grafische Kollisionsmatrix weiterhin eine Ausbaustufe.
- Für ein noch nicht orientiertes Display wird kein Richtungspfeil geraten. Physische Wegweisung muss vor der öffentlichen Freigabe vor Ort gegen den Gebäudeplan geprüft werden.
- Geschützte Freigabelinks benötigen **auch am vorgelagerten Reverse-Proxy** eine Maskierung ihrer initialen Token-URL im Zugriffslog. Ein bloßer Uvicorn-Filter genügt dafür nicht.

### Fachliche Ausbaustufen und bewusste Grenzen

Die nun integrierte Zentrale ermöglicht bereits Freigabe, Zeitsteuerung, Priorität, Gebäudegruppen und sichere Kalenderterminbindung. **Noch nicht vollständig umgesetzt** sind automatische Ereignisvorschläge aus gesonderten Gremien-, Terminbuchungs- oder Fachmodulen ohne explizite Kalenderauswahl, eine echte organisationsweite Vier-Augen-Freigabeworkflow-/Audit-Engine, visuelle SVG-Grundrisse, native Windows/Linux/Android/Raspberry-Pi-Player mit Offlinecache und die ausfallsichere Notfall-/Evakuierungsbeschilderung. Letztere darf erst nach fachlicher Sicherheitsabnahme betrieben werden.


## Geräte-Fleet, Schlüsselrotation und sichere Anzeige bei Verbindungsabbruch

### Einfache Einrichtung

1. **Digital Signage → Display bearbeiten → Geräte & Monitoring:** Ein Gerät mit einem sprechenden Namen (z. B. „Empfang EG“) registrieren. TAKT zeigt den Geräte-Identifier und einen neuen Bearer-Schlüssel **genau einmal** an. Der Schlüssel wird serverseitig nur als SHA-256-Hash gespeichert.
2. Den geheimen Schlüssel **nur in der geschützten Konfiguration des Players** speichern, nie in eine Browser-URL, auf einen QR-Code für Gäste oder in Zugriffsprotokolle schreiben. Für einfache Browserkiosks kann eine öffentliche, ausdrücklich freigegebene Displayansicht ohne Geräte-API verwendet werden.
3. Ein gekoppelter Player ruft `GET /signage/api/device/<ID>/manifest` mit `Authorization: Bearer <SECRET>` ab und sendet periodisch `POST /signage/api/device/<ID>/heartbeat`. Der Heartbeat funktioniert ohne Inhalt; optional ist ein kleiner JSON-Diagnosebericht erlaubt:
   ```json
   {
     "platform": "linux",
     "client_version": "1.2.3",
     "screen_width": 1920,
     "screen_height": 1080,
     "reported_screen_version": 2,
     "diagnostic_code": "ok"
   }
   ```
4. Unter **Digital Signage → Geräte überwachen** sind Online-/Offlinezustand, Displayversion, Auflösung, Plattform und erlaubte Diagnosecodes sichtbar. Der Status aktualisiert sich ohne Verlust der Filtereingabe alle 60 Sekunden. **Online** bedeutet letzter Heartbeat vor höchstens drei Minuten, **verzögert** bis 15 Minuten, danach **offline**.
5. Mit **Schlüssel erneuern** wird ein neuer einmaliger Bearer erstellt; der vorherige Schlüssel ist **sofort ungültig**. Ein gesperrtes Gerät lässt sich nicht wieder aktivieren; hierfür ein neues Gerät registrieren.

### Ausfallregeln im Browserkiosk

- Die eigenständige Displayseite prüft ihre **eigene, authentifizierte/autorisiert gelieferte HTML-Antwort** vor dem nächsten Nachladen. Nur eine Antwort mit dem serverseitigen Header `X-TAKT-Signage: display` gilt als gültiger Anzeigestand. Zugriffsverlust, unerwartete Weiterleitungen und Netzwerkfehler führen nicht zur Ausspielung veralteter Termine.
- Bei Browser-Offline-Ereignis oder fehlgeschlagener Aktualisierung **verdeckt ein vollständig undurchsichtiger Hinweis alle bisherigen Daten**. Bei wiederhergestellter Verbindung lädt der Kiosk neu; er zeigt bis dahin keine möglicherweise überholten Raumbelegungen oder Richtungsanweisungen.
- Diese Sicherheitsanzeige ist bewusst **kein Offline-Cache** und ersetzt keine zugelassene Fluchtweg-/Evakuierungsbeschilderung. Eine unterbrechungsfreie Betriebsart und native Hardware-Player verbleiben in #327.
- Diagnosen werden ausschließlich als enumerierte, nicht-personenbezogene Werte gespeichert. Keine IP-Adressen, Hostnamen, Seriennummern, Fehler-Freitexte, E-Mail-Adressen oder Gerätestandorte aus Telemetrie; höchstens 2 KiB JSON pro Heartbeat. Authentisierung und CSRF sind voneinander getrennt: Geräte-APIs ausschließlich über getrennte Bearer-Secrets; Flottenansicht und Schlüsselrotation nur mit `signage_manage` und CSRF.
- **Sicherheitsgrenze:** Der Online-Status bestätigt den API-Heartbeat, nicht, dass ein realer Monitor eingeschaltet oder korrekt angebracht ist. Ein extern vorgeschalteter Reverse-Proxy muss die initialen tokenisierten URLs von geschützten Links weiterhin im Access-Log maskieren.

### Weiter offene Fleet-Funktionen

Geräte-Registrierung mittels zeitlich begrenzter Pairing-Codes, sichere Geräteinstallation/Shell-Skripte, konfigurierbare Betriebszeiten, native Windows-/Linux-/Android-/Raspberry-Pi-Player, signierter Offline-Cache mit ausdrücklich festgelegter Aktualitätszeit und sichere Fernaktionen bleiben getrennte Ausbaustufen. Ohne sichere Abnahme keine Notfallsteuerung.


## Vorgeschlagene Sonderanzeigen aus vorhandenen TAKT-Kalendern

Die **Sonderbetriebszentrale** zeigt eingehende, eindeutig erkennbare kommunale Veranstaltungen aus lesbaren TAKT-Kalendern als Vorschläge an – ohne zusätzliche Schnittstelle und ohne aktivierte fremde Fachmodule. Unterstützt werden nur konservative Ausdrücke wie **Gemeinderatssitzung**, **Ausschusssitzung**, **Briefwahlstelle**, **Wahllokal**, **Wahlraum** und **Bürgerversammlung**. Eine beliebige „Wahl“ oder interne Besprechung wird bewusst nicht als öffentlicher Wahltermin klassifiziert.

**Bedienablauf:**

1. Admin/Signage-Berechtigte öffnen **Digital Signage → Sonderbetrieb verwalten**. Wenn in den nächsten 45 Tagen aus geeigneten, für sie lesbaren TAKT-Kalendern Termine existieren, erscheinen höchstens zwölf Vorschlagskarten.
2. **Entwurf vorbereiten** verknüpft den Kalendereintrag nur mit dem internen Formular. Der Vorschlag verwendet **ausschließlich die neutrale öffentliche Kategoriebezeichnung**, beispielsweise „Ratssitzung“, niemals automatisch die Originalüberschrift oder Beschreibung.
3. Gebäude, ausdrücklich freigegebener öffentlicher Zielraum, Zeitquelle, Priorität, Verteilungsbereich, Laufzeit und Besuchertext müssen kontrolliert werden. **Die Veröffentlichung bleibt zunächst ausgeschaltet.** Beim Speichern muss sie ausdrücklich aktiviert werden.
4. Bereits für eine Kampagne verwendete Kalendertermine erscheinen nicht mehr als neue Vorschläge. Wiederholungen, abweichende oder gestrichene Serieninstanzen werden durch dieselbe TAKT-Kalenderfunktion behandelt wie auf den bestehenden Raumdisplays.
5. Wird die Lese-Berechtigung des verantwortlichen Kontos später entzogen, sperrt die zentrale Kampagnenprojektion weiterhin die betroffene Veranstaltung. Die neuen Vorschläge schaffen keine zusätzlichen Kalenderrechte und arbeiten auch bei fehlenden Kalendern nicht störend.

**Datenschutz:** Kalenderbeschreibungen, Teilnehmer, E-Mail-Adressen, Standort-Freitexte und vertrauliche Titel werden nicht in öffentliche Anzeigen übernommen. Die Vorschlagskarten sind ausschließlich über die mit `signage_manage` geschützte Administrationsroute erreichbar. Das Erkennungsverfahren ist bewusst erklärbar und verwendet keine externe KI oder Websuche.

**Grenzen:** Die Vorschlagslogik ersetzt keine fachliche Prüfung oder einen echten Sitzungsmanagement-Konnektor; ohne explizite Veröffentlichung darf TAKT keinerlei öffentliche Terminankündigung auslösen. Die Erkennung ist auf eine begrenzte Anzahl vorhandener freier Kalender und Ereignisse beschränkt. Eine spätere fachliche Gremienintegration braucht eigene stabile Schnittstellen und Rechte.
