# TAKT Wissensmanagement

**Status:** Umsetzung in Phasen. Interviewentscheidungen 1–16 und empfohlene technische
Fortsetzung: [Epic #296](https://github.com/derdigitalaffine/takt-platform/issues/296).
Die P2-Redaktionsausbaustufe ergänzt den Grundbaustein. Die geplante Prozess- und KI-Suite ist weiterhin nicht vollständig umgesetzt.

## Aktivierung

Admin → Module → **Wissensmanagement** einschalten (Standard: aus).
Benutzerrechte separat zuweisen: \`knowledge_read\` (Lesen),
\`knowledge_edit\` (Entwürfe), \`knowledge_publish\` (zweite Freigabeperson),
\`knowledge_manage\` (Raum anlegen), \`knowledge_ai\` (für zukünftige
gesonderte KI-Freigaben; **aktuell kein automatischer Index**).
Auch mit KI-Modul aus funktionieren Räume, Artikel, Suche, Versionierung und Freigabe.

## Datenmodell und Autorisierung

\`knowledge_spaces\` referenziert eine bestehende Organisationseinheit oder
ist ohne Organisationsbindung zunächst nur für Admins/direkt Berechtigte sichtbar.
\`knowledge_articles\` enthält getrennte bearbeitbare Entwürfe und freigegebene
Inhalte. \`knowledge_grants\` bildet pro Raum oder Artikel direkte Nutzer-,
Gruppen- oder Organisationsregeln (allow/deny) ab. Verweigern gewinnt auch gegen
geerbte Erlaubnis; für nicht freigegebene Artikel reicht Lesen allein nicht aus.
Ein eingeschränkter Artikel ignoriert allgemeine Raumfreigaben, nicht aber
explizite Sperren. Nutzer benötigen zusätzlich das passende **globale** Fachrecht.
Administratoren können ACLs auch nach einem versehentlichen Entzug reparieren.

Org-Zugang folgt aktiver Mitgliedschaft bzw. dem fachlichen, vererbbaren
Organisationsrollen-Scope, **nicht** der generellen Einsicht in Benutzerprofile.
Die Berechtigung wird bei jeder Listen-/Detail-/Schreiboperation neu geprüft.
Der Modulgate sperrt auch bestehende Links nach Deaktivierung. Bereits gespeicherte
Inhalte bleiben dabei erhalten.

Im dritten Bauabschnitt erfolgt **delegierte Raumverwaltung**: Ein Nutzer mit
dem **globalen** Recht `knowledge_manage` und einer aktuellen, ausdrücklich
erteilten Raum-Verwaltungsfreigabe (oder als Raum-Eigentümer) darf den eigenen
Bereich verwalten. Die Fachadministration darf **ausschließlich Lesen und
Bearbeiten** für aktive Personen mit **direkter** Mitgliedschaft in genau dieser
Organisationseinheit freigeben, sperren oder zurücknehmen. Sie darf weder
Fachfreigaben, KI-Rechte noch andere Verwalter vergeben; auch keine
Gruppen-, Organisations- oder Artikelregeln ändern. Die zentrale Administration
behält die weitreichende Kontrolle und die Wiederherstellung nach Sperren.
Der Zugriff ist serverseitig abgesichert; bloße UI-Ausblendung reicht nie.

Die Rechtevorschau `/wissen/raum/<id>/verwaltung` erklärt die zum
Abfragezeitpunkt wirksamen Raumrechte für jeweils sichtbare Personen;
die verbindliche Entscheidung trifft immer dieselbe `knowledge.allowed()`-
Logik. Artikel können zusätzliche Sperren, Entwurfs- und Freigaberegeln haben.
Globale Benutzer- und Gruppenverzeichnisse dürfen delegierte Redakteure
nicht durchsuchen. Erweiterte Artikelrechte und eine artikelspezifische
Rechtevorschau bleiben der zentralen Administration bzw. einem Folgeausbau
vorbehalten.
Zugriffsentscheidungen dürfen niemals über bloße Navigationsausblendung erfolgen.

## Redaktionsprozess in P1

1. Berechtigte Person legt einen Raum und darin einen Artikel an.
2. Der Artikel startet als Entwurf. Änderungen erzeugen eine versionierte Momentaufnahme.
3. Die Redaktion reicht ihn zur Prüfung ein; Rückgabe zum Entwurf ist möglich.
4. Nur eine **andere** Person mit Veröffentlichungsrecht darf den geprüften
   Beitrag freigeben. Veröffentlichte Beiträge werden nicht direkt überschrieben: Ein separater,
   berechtigungsgeschützter Änderungsentwurf wird bearbeitet, verglichen und
   erst nach unabhängiger Freigabe zur neuen veröffentlichten Fassung.
5. Änderungen von Zugriffsrechten werden als metadatenbasierte Ereignisse protokolliert.
   Es gibt keinen öffentlichen Zugriff und keinen automatischen KI-Export.

## Sicherheitsgrenzen und noch offene Arbeiten

- **KI/RAG:** Wissensartikel werden *nicht* dem bisherigen globalen
  \`AIKnowledge\`-Index zugemischt. Zuerst muss eine Objekt-ACL-geprüfte,
  widerrufbare Quellenintegration mit Provider-/Index-Freigabe folgen (#299,
  #196, #219). Die bloße Anzeige von „KI-Freigabe“ ist **keine Indexierung**.
- **Prozessnotationen:** BPMN/CMMN/DMN/EPK und Prozessrekonstruktion sind
  geplante Ausbaustufen (#300, #301), noch keine Editoren.
- **Governance:** P2 enthält voneinander getrennte Änderungsentwürfe,
  revisionsbezogene Historie, Wiedervorlagen, delegierte Raumverwaltung,
  konfigurierbare Prüfpersonen und Fachquellverweise. Zeitgesteuerte
  Versandkanäle und Wissenstransfer bleiben Aufgaben von #298 / #302.
- **Suche:** Der Einstieg verwendet berechtigungsgefiltertes SQL-Textmatching
  mit begrenzter Kandidatenanzahl. Später folgen FTS/Hybrid-Vektor und
  indizierte Zugriffsfilter für große Datenbestände.
- **Betrieb:** Keine externen Text-/Embedding-Dienste oder automatischen
  Mitarbeiterinterviews. Vor einer Aktivierung solcher Funktionen sind
  Datenschutz, Personalvertretung, Dienstvereinbarung und Aufbewahrungsfristen
  gesondert zu prüfen.
- **Inhaltspflege:** Freigegebene Texte bleiben während einer Überarbeitung
  unverändert. Nach fachlicher Freigabe wird eine neue Fassung angelegt;
  frühere Versions-Snapshots bleiben erhalten. Einfache Prüfbestätigungen
  ändern nur geprüfte Metadaten. Löschen/Exportieren ist bewusst weiterhin
  nicht implementiert; Aufbewahrungsregeln und Backup-/Restore-Gates folgen.
- **Regelwerksverbindlichkeit:** Die Stufen „offiziell freigegeben“ und
  „verbindliche Regelung“ sind vorbereitet, bleiben in dieser Phase jedoch
  über das Wissensformular gesperrt. Es entsteht keine Dienstanweisung ohne
  einen gesonderten, zuständigen Regelwerksfreigabeprozess.

## Tests

\`portal/tests/test_knowledge.py\` testet Modul-Deaktivierung, Organisations-
isolation, Entwurfsvertraulichkeit, expliziten Entzug, Vier-Augen-Freigabe,
Versionskonflikte und CSRF-Sperre. Der Gesamtportal-Testlauf muss ebenfalls grün
sein, bevor ein PR gemergt wird.


## P2 – sichere Redaktionsfortsetzung, Vorlagen und Wiedervorlagen

- **Dokumenteditor:** Der modulare, visuelle Blockeditor wird auf den
  vorhandenen Markdown-Feldern aufgebaut (Artikel, Prozessbeschreibungen und
  getrennte Änderungsentwürfe). Absätze, Überschriften, Aufzählungen,
  nummerierte Listen, Checklisten, Zitate, Hinweise, Links, Code und Tabellen
  werden als individuell bearbeitbare Blöcke dargestellt. Blöcke lassen
  sich anlegen, duplizieren, entfernen und per Pfeiltasten, Alt+Pfeil oder
  Drag-and-drop verschieben. Die zugängliche Markdown-Ansicht ist jederzeit
  verfügbar und bleibt ohne JavaScript vollständig bedienbar.
- **Datenhaltung und Sicherheit:** Der Blockeditor speichert weiterhin
  ausschließlich das vorhandene Feld `body_md` und benötigt keine
  Datenbankmigration, keinen KI-Provider und kein neues API.
  Bei jedem Wechsel in die visuelle Ansicht bleiben unveränderte Teile
  des Markdown-Quelltexts **bytegenau** erhalten, einschließlich fremder
  Erweiterungen, Codeblöcken und Leerzeilen. Komplexe Strukturen lassen sich
  als `Markdown-Original` editieren, nicht stillschweigend löschen. Eine
  bewusste Neuanordnung normalisiert lediglich die Leerzeilen zwischen
  den verschobenen Blöcken. Aufwändigere Rich-Text-Inlines bearbeitet man
  weiterhin in Markdown innerhalb des jeweiligen Inhaltsblocks.
- **Ausgabe:** Der serverseitige Markdown-Renderer lässt rohes HTML
  deaktiviert, rendert jetzt zusätzlich einfache Markdown-Tabellen.
  Der Client erzeugt keine ausführbaren HTML-Abschnitte und gestattet bei
  neuen Links nur HTTPS, HTTP, Mailto oder lokale Pfade. Die vorhandene
  Vorschau prüft CSRF, Rechte und Modulschalter weiterhin serverseitig.
- **Veröffentlichte Fassungen:** Die Tabelle `knowledge_amendments` hält
  pro Artikel den aktuellen Änderungsentwurf. `knowledge_amendment_revisions`
  enthält jede Entwurfs-/Statusänderung. Leser sehen weiterhin ausschließlich
  `knowledge_articles`; Änderungsentwürfe und Textvergleiche sind ausschließlich
  für jeweils berechtigte Bearbeiter/Freigebende erreichbar.
- **Freigabe:** Nur eine andere berechtigte Person als Entwurfsverfasser
  **und** letzte Bearbeitung darf den eingereichten Vorschlag freigeben.
  Versionsabgleich verhindert, dass ein veralteter Entwurf eine parallel
  publizierte Fassung überschreibt. Veröffentlichung erzeugt eine neue
  `knowledge_revisions`-Momentaufnahme und behält vorherige Fassungen.
- **Wissensqualität:** `authority`, `review_due_on`, `last_reviewed_at`
  und `published_at` werden mit einer idempotenten, additiven Migration
  nachgerüstet. Prüfrechte gelten je Objekt. Für neu veröffentlichte Artikel
  wird ein Standard-Prüftermin ein Jahr später vorgeschlagen. Ein berechtigter,
  unabhängiger Prüfer kann Stufe und Termin später erneut bestätigen.
  Verbindliche Dienstanweisungen werden dadurch nicht eigenmächtig erlassen.
- **Datenfluss:** Aus Wissensartikeln erfolgt weiterhin **keine** automatische
  Übernahme in KI-/RAG-Indizes, kein externer API-Aufruf, keine Mitarbeiteransprache.
- **Abgrenzung:** Der visuelle Blockeditor ist ein blockbasierter,
  Markdown-kompatibler Editor, aber kein freies HTML-/Layout-Canvas und
  keine Rich-Text-WYSIWYG-Oberfläche für alle möglichen Plugins.


## P2 – delegierte Fachredaktion und Prüfungsübersicht

- Der Wissensraum zeigt einen **Rechte verwalten**-Einstieg nur bei
  berechtigtem Managementzugriff. Statt numerischer Personen-IDs gibt es
  eine Suche und Auswahlliste mit maximal 120 Treffern pro Suchlauf,
  auf direkte Mitglieder des Fachbereichs begrenzt.
- Ein zweites, getrenntes Verfahren ermöglicht Admins die Vergabe an
  Gruppen und andere Organisationseinheiten. Die entsprechenden globalen
  Rechte bleiben zusätzlich erforderlich.
- `/wissen/pruefungen` stellt berechtigten Personen mit
  `knowledge_publish` eine **aktuell ACL-geprüfte** Übersicht zur
  Verfügung: neue Beiträge in Prüfung, Änderungsentwürfe, fällige und
  innerhalb von 30 Tagen anstehende Reviews. Beiträge, die die
  prüfende Person selbst fachlich verfasst hat, werden nicht als
  freigebbar angeboten.
- Persönliche Prüfhinweise können im Portal aktiviert werden.
  Es gibt keine automatischen E-Mails, Intervieweinladungen oder
  personenbezogenen Leistungskennzahlen.
- **Tests:** Organisationsisolierung, Rechteentzugswirkung, verbotene
  delegierte Rechteausweitung, CSRF, Review-Filter und Modulabschaltung.


## Browser- und JavaScript-Prüfungen des Blockeditors

- `portal/tests/test_knowledge_blocks_client.js`: verlustfreie
  Roundtrips inklusive CRLF, Codefences, Spezialsyntax, Roh-HTML,
  sichere Linkziele, Checklisten, Tabellenänderungen und Neuordnung.
- `portal/tests/browser/knowledge_blocks_smoke.py`: echte Bedienung
  im Chromium (Moduswechsel, editierbare Blöcke, Tabelle, Checkliste,
  Tastaturverschiebung, sichere Formularübertragung, Verweigerung
  gefährlicher Links und mobile Bildschirmbreite).
- `portal/tests/test_knowledge.py`: Markdown-Tabellenausgabe und
  Schutz vor untrusted HTML, zusätzlich alle bisherigen serverseitigen
  Autorisierungs-, CSRF-, Versions- und Vier-Augen-Tests.
- Auslösung im CI-Job `tasks-browser` zusätzlich zu allen bisherigen
  Tests. Ein PR darf bei Fehlern nicht gemergt werden.

## Fällige Prüfungen und laufende Überarbeitungen

Die Prüfungsübersicht zeigt Wiedervorlagen bis einschließlich 30 Tage im
Voraus. Überfällige Termine stehen zuerst. TAKT verwendet den lokalen
Portal-Kalendertag und kennzeichnet heute fällige Beiträge gesondert. Die
Seitengröße wird erst nach der Rechteprüfung angewendet. Auch ältere Beiträge
mit einem fälligen Termin bleiben dadurch auffindbar.

Bei einer Prüfbestätigung kann die prüfende Person einen neuen Termin ab heute
setzen oder das Datumsfeld leeren, um die Wiedervorlage zu entfernen. Eine
Bestätigung ändert nur die Qualitäts- und Terminmetadaten der aktuellen
Fassung. Ein laufender Änderungsentwurf auf dieser Fassung kann weiter
bearbeitet und nach der Vier-Augen-Prüfung veröffentlicht werden.

Für die Freigabe verwenden Prüfungsübersicht, Artikelseite und Statuswechsel
dieselben Regeln zu Zugriffsrechten und Mitwirkung an der Fassung.
Parallele Änderungen an derselben Version führen zu einem Konflikt mit
Aufforderung zum Neuladen. Die Übersicht arbeitet ohne Versand oder KI.

## Quellverweise aus den Fachmodulen

Auf aktuellen Rechtstexten, Umläufen, Ablageeinträgen und
Bearbeitungsprozessen öffnet **Wissensverweise** die berechtigten,
veröffentlichten Wissensartikel zum jeweiligen Objekt. Die Fachredaktion
kann dort den Markdown-Verweis kopieren und in einen Wissensentwurf einfügen.
Der Verweis durchläuft dieselbe Versionierung und Freigabe wie der übrige
Artikeltext. Er lässt sich im visuellen Editor als gewöhnlicher Link
bearbeiten.

TAKT speichert im Wissensartikel die Referenz. Bezeichnung und Ziel werden
erst beim Anzeigen oder Öffnen mit der aktuellen Berechtigung im Fachmodul
aufgelöst. Ablageverweise verwenden eine allgemeine Linkbezeichnung.
Deaktivierte Module, gelöschte Quellen und Rechteentzüge führen zu „Quelle
nicht verfügbar“. Der Erstellungszeitpunkt der Quelle schützt den Verweis
vor der Wiederverwendung einer numerischen ID. Rückverweise zeigen nur
veröffentlichte, aktuell lesbare Artikel. Gast- und Einbettungsansichten
bieten keinen Einstieg zu diesen Verweisen.

Die Fachmodule bleiben für ihre Fassungen und Regeln zuständig. Ein Verweis
folgt dem aktuellen Objektstand. Er erzeugt weder eine Kopie noch eine
Kenntnisnahme oder eine KI-Indizierung.

## Anzahl der fachlichen Freigaben je Raum

Die zentrale Administration wählt in der Raumverwaltung eine oder zwei
unabhängige Prüfpersonen. Beim Einreichen übernimmt TAKT die aktuell
geltende Anzahl für diese Fassung. Bereits eingereichte Fassungen behalten
ihre Vorgabe. Nach einer Rückgabe und erneuten Einreichung beginnt die
Prüfung mit der dann gültigen Raumregel.

Jede beteiligte Prüfperson braucht weiterhin das globale Freigaberecht und
die aktuellen Objekt- und Organisationsrechte. Wer an der Fassung
mitgewirkt hat, darf keine Stimme für sie abgeben. TAKT zählt jede berechtigte
Person einmal. Wenn vor der Veröffentlichung Rechte entzogen werden,
berücksichtigt TAKT die betreffende Stimme bei der Veröffentlichung nicht.
Während der Prüfung eines Änderungsentwurfs bleibt die bisherige Fassung
veröffentlicht.

Die Freigabehistorie speichert die Versionsnummer, den Zeitpunkt und die
interne Benutzerzuordnung. Beim Löschen eines Benutzerkontos wird diese
Zuordnung entfernt. Die fachlichen Entscheidungen enthalten keinen
Artikeltext. Die bestehende Aufbewahrung von Wissensfassungen und der
gesonderte Freigabeprozess für verbindliche Regelungen gelten weiterhin.

## Persönliche Hinweise auf fällige Wissensprüfungen

Prüfberechtigte können in der Prüfungsübersicht einen persönlichen
Portalhinweis einschalten. Er erscheint in **Wissen** und **Meine Aufgaben**,
wenn mindestens eine für die Person prüfbare Wiedervorlage heute fällig
oder überfällig ist. Beim Seitenaufruf prüft TAKT die aktuellen Rechte.
Der Hinweis enthält keine Artikeldaten und legt keine Aufgabe an.
Die Voreinstellung ist aus. Es werden keine Nachrichten versandt.

Die Wiedervorlage einer veröffentlichten Fassung darf nur eine unabhängige
Person bestätigen. Wer an der aktuell veröffentlichten Fassung
mitgewirkt hat, erhält für diese Fassung
keinen Prüfhinweis und kann die Bestätigung nicht ausführen.
