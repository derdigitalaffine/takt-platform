# TAKT Wissensmanagement

**Status:** Umsetzung in Phasen. Interviewentscheidungen 1–16 und empfohlene technische
Fortsetzung: [Epic #296](https://github.com/derdigitalaffine/takt-platform/issues/296).
Dies ist der **erste vertikale Grundbaustein**, nicht die fertige Prozess-/KI-Suite.

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

Im ersten Bauabschnitt erfolgt **ACL-Bearbeitung nur durch globale Admins**.
Delegierte Managementrechte, erweiterte Rechtevorschau, fachliche Rollen und
Wissensräume ohne Organisationshierarchie werden im nächsten PR ergänzt.
Zugriffsentscheidungen dürfen niemals über bloße Navigationsausblendung erfolgen.

## Redaktionsprozess in P1

1. Berechtigte Person legt einen Raum und darin einen Artikel an.
2. Der Artikel startet als Entwurf. Änderungen erzeugen eine versionierte Momentaufnahme.
3. Die Redaktion reicht ihn zur Prüfung ein; Rückgabe zum Entwurf ist möglich.
4. Nur eine **andere** Person mit Veröffentlichungsrecht darf den geprüften
   Beitrag freigeben. Ein publizierter Stand kann in P1 noch nicht direkt
   überschrieben werden; sichere Änderungsentwürfe für veröffentlichte Fassungen
   folgen mit dem mehrstufigen Redaktionsworkflow in P2.
5. Änderungen von Zugriffsrechten werden als metadatenbasierte Ereignisse protokolliert.
   Es gibt keinen öffentlichen Zugriff und keinen automatischen KI-Export.

## Sicherheitsgrenzen und noch offene Arbeiten

- **KI/RAG:** Wissensartikel werden *nicht* dem bisherigen globalen
  \`AIKnowledge\`-Index zugemischt. Zuerst muss eine Objekt-ACL-geprüfte,
  widerrufbare Quellenintegration mit Provider-/Index-Freigabe folgen (#299,
  #196, #219). Die bloße Anzeige von „KI-Freigabe“ ist **keine Indexierung**.
- **Prozessnotationen:** BPMN/CMMN/DMN/EPK und Prozessrekonstruktion sind
  geplante Ausbaustufen (#300, #301), noch keine Editoren.
- **Governance:** Rollen, Wiedervorlagen, Revisionen mit separaten Freigabe-
  fassungen, verknüpfte Dienstanweisungen/Umläufe und Wissenstransfer folgen
  in #298, #302.
- **Suche:** Der Einstieg verwendet berechtigungsgefiltertes SQL-Textmatching
  mit begrenzter Kandidatenanzahl. Später folgen FTS/Hybrid-Vektor und
  indizierte Zugriffsfilter für große Datenbestände.
- **Betrieb:** Keine externen Text-/Embedding-Dienste oder automatischen
  Mitarbeiterinterviews. Vor einer Aktivierung solcher Funktionen sind
  Datenschutz, Personalvertretung, Dienstvereinbarung und Aufbewahrungsfristen
  gesondert zu prüfen.
- **Inhaltspflege:** Veröffentlichung ist zunächst final; bestehende Beiträge
  sind ohne Lösch-/Überschreibfunktion bewusst geschützt. Vollständige
  Revisions- und Aufbewahrungsregeln einschließlich Export/Backup folgen.

## Tests

\`portal/tests/test_knowledge.py\` testet Modul-Deaktivierung, Organisations-
isolation, Entwurfsvertraulichkeit, expliziten Entzug, Vier-Augen-Freigabe,
Versionskonflikte und CSRF-Sperre. Der Gesamtportal-Testlauf muss ebenfalls grün
sein, bevor ein PR gemergt wird.
