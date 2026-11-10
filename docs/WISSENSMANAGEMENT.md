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
  revisionsbezogene Historie, einen Prüftermin und eingeschränkte fachliche
  Qualitätsstufen. Delegierte Rollen, konfigurierbare mehrstufige Freigaben,
  Erinnerungs-Worker, verknüpfte Dienstanweisungen/Umläufe und Wissenstransfer
  bleiben Aufgaben von #298 / #302.
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

- **Dokumenteditor:** Markdown-Formatierungsleiste und typbezogene Vorlagen
  (Artikel, Prozess, FAQ, Checkliste, Erfahrungswissen) als optionale
  JavaScript-Verbesserung; das Formular bleibt ohne JavaScript verwendbar.
  Der vorhandene Markdown-Renderer wird serverseitig mit deaktiviertem rohem
  HTML ausgeführt; auch die Vorschau prüft CSRF, Fachrechte und den Modulschalter.
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
- **Abgrenzung:** Visueller Blockeditor mit frei sortierbaren Elementen,
  automatisierte Erinnerungen, rollenbasierte ACL-Delegation und
  Quellverknüpfungen sind weiterhin offene Teile des P2-Issues. Die hier
  enthaltene Formatierungsleiste ist ausdrücklich ein Markdown-Editor,
  kein vollwertiger WYSIWYG-Blockeditor.


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
- Keine automatischen E-Mails oder Intervieweinladungen; Reminder-
  Automatisierung ist ein **separater späterer Schritt**. Keine
  personenbezogenen Leistungskennzahlen.
- **Tests:** Organisationsisolierung, Rechteentzugswirkung, verbotene
  delegierte Rechteausweitung, CSRF, Review-Filter und Modulabschaltung.
