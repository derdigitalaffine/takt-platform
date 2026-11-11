# Terminbuchung ↔ Kalender ↔ E-Mail: verbindliche TAKT-Spezifikation

Stand: 11.11.2026. Nutzerentscheidungen: Interviews Q1–Q5 jeweils D; auf Auftrag
„Mach alles wie empfohlen“ werden Q6–Q12 mit der umfassendsten Variante ohne
weitere Rückfragen fortgeführt. Diese Datei trennt **bereits implementierte**
Funktionen von **verbleibenden Folgepunkten**.

## Leitprinzipien

1. **Eine Quelle für Termine:** Die Buchung (`Booking`) ist führend. Kalender
   sind live gefilterte, lesende Projektionen, keine zweiten Buchungsdatensätze.
2. **Schrittweise einrichten:** Standardkonfiguration ist für kleine Teams
   brauchbar; Organisationen können Ausnahmen, Fristen, Datenschutz und
   Empfängerregeln pro Seite und Terminart schrittweise ausbauen.
3. **Berechtigungen pro Ereignis:** Buchungsseitenrechte, direkte Zuweisung,
   Organisationsrechte und Terminart-Privatsphäre gelten bei jedem Abruf.
   Berechtigung zum Anzeigen eines Kalenders allein reicht nicht für Bürgerdaten.
4. **Externe Zugänge:** CalDAV/ICS über bereits vorhandene Tokens/Geräteberechtigungen;
   von Haus aus nur Zeiträume als „Belegt“. Optional eine nicht-sensitive
   Terminart, niemals Gästename, E-Mail, Telefon, Freitext oder Bearbeitungstoken.
5. **Verbindliche Nachrichten:** Anfrage ist nicht Bestätigung. Bestätigung,
   Verschiebung und Absage erhalten eindeutige Betreffzeilen, Kalender-ID,
   Version, `REQUEST`/`CANCEL` sowie einen zugänglichen persönlichen Link.
   Keine automatischen Zusagen gegenüber dem Gast, bevor tatsächlich bestätigt.
6. **Zeitfenster atomar:** Nach Verfügbarkeit, Vorlauf, Zuständigkeit, Urlaub,
   privaten Konflikten und Zeitpuffer wird unmittelbar vor dem Speichern
   transaktional erneut geprüft. Bereits gebuchte Termine ändern sich
   nicht stillschweigend.

## Kalender und Rechte

| Rolle | Interne Anzeige | Externe Anzeige | Aktion |
| --- | --- | --- | --- |
| Direkt zuständige Person | Name, Anliegen, Status, Zeit; bei sensibler Art ggf. nur Belegt | Standardmäßig Belegt | Eigene Anfrage bestätigen |
| Besitzer:in/Bearbeiter:in der Buchungsseite | Gemäß Seite/Terminart vollständige Details | Standardmäßig Belegt | Über Buchungsmodul bearbeiten |
| Berechtigtes Team ohne Detailrechte | Belegt | Belegt | Kein Zugriff auf Personendaten |
| Fremde Person | Kein Ereignis | Kein Ereignis | Keine |
| Vertretung | Nur nach tatsächlichem, aktuell gültigem Delegationsrecht | Nur Belegt | Bestehende Fachberechtigungen |

Die persönlichen Mitarbeitenden- und Teamansichten erfordern zusätzlich eine
explizite Quellen-/Organisationsfilterung, ohne Vertraulichkeitsstufen zu erweitern.

## Verfügbarkeit

Basis: Sprechzeiten/gebuchte Slots/Ausnahmen/Feiertage/bestätigte Abwesenheiten.
Optional pro Buchungsseite: eigene private freie Kalender und eigene TAKT-
Besprechungen als blockierende Intervalle. `TRANSPARENT` und `CANCELLED`
blockieren nicht. Fachkalender „Terminbuchungen“ werden nicht als zweite
Konfliktquelle gezählt; bereits bestehende `Booking`-Belegungen werden separat
geprüft. Erweiterungsziel: konfigurierbare gemeinsame Kalender, Teamkapazitäten,
Organisationseinheiten und gewichtete Qualifikations-/Prioritätsregeln.

## Benachrichtigungslifecycle

| Ereignis | Gast | Zuständige | Kalender |
| --- | --- | --- | --- |
| Neue unverbindliche Anfrage | Empfang mit eindeutiger Kennzeichnung | Bearbeitungshinweis | Intern „angefragt“, extern ggf. TENTATIVE |
| Bestätigung | Verbindliche Bestätigung und ICS | Statusbenachrichtigung | Stable UID, REQUEST |
| Terminverschiebung | Neue und bisherige Zeit, aktualisierte ICS | Neu Zuständige und bei Änderung vorige Person | Erhöhte SEQUENCE, kein Duplikat |
| Absage | Unmissverständlicher Storno, ggf. ICS | Betroffene Personen | CANCEL und Live-Entfernung |
| Erinnerung | Vorlauf der Buchungsseite | Später individuell konfigurierbar | Keine neue Buchung |
| Vertretung | Hinweis und gültige Kontaktadresse | Berechtigt nach Organisations-/Abwesenheitslogik | Kein übernommener Detailzugriff ohne Berechtigung |

Textvorlagen bleiben administrativ editierbar. Das zentrale Branding wird als
HTML-Mailrahmen angewandt; keine externen Schriften, Bilder oder Tracker. Die
Vorschau verwendet ausschließlich Beispieldaten, Content-Security-Policy und
No-Store.

## In PR #344 umgesetzt

- Additive Datenbankmigration und Settings je Buchungsseite für Konfliktquellen,
  Kalender-Sichtbarkeit und optionale interne ICS-Dateien.
- Datenschutzstufe je Terminart; feste externe Reduktion mit optionalem
  nicht-sensitiven Terminart-Label.
- Fachprojektion für persönlich zugeteilte Buchungen auch ohne umfassende
  Buchungsseitenfreigabe; sicherer Kalender-Link und direkte Bestätigung bei
  entsprechender Zuständigkeit.
- Entdoppelte Videobesprechungen, Status-Markierung und Farben in der
  monatlichen Kalenderansicht.
- Kalenderkonflikte gegen persönliche freie Kalender und eigene Meetings im
  einfachen und erweiterten Modus, auch bei finaler Buchungsprüfung.
- Gewichtete faire Zuordnung anhand bislang gebuchter Minuten in der Woche.
- Verbesserte Mail-Lifecycle-Vorlagen, HTML-Statuskarten, E-Mail-Vorschau und
  zuverlässigere iTIP-Daten; optional datensparsame ICS für Mitarbeitende.
- Benachrichtigung bei bisheriger Zuständigkeit nach Umverteilung.

## Noch offene Ausbaustufen (nicht als fertig ausgeben)

- #345: Kompetenz- und Organisationsknoten, Regelvererbung, Gewichte und
  Vertretungsausnahmen bei der Provider-Zuordnung.
- #346: E-Mail-Vorlagenvererbung, Zustellmatrix, Tagesdigest, Eskalation,
  Nachvollziehbarkeit, Versandprüfungen zum tatsächlichen Versandzeitpunkt.
- #347: Team-/Personen-/Bereichsfilter, auswählbare gemeinsam genutzte
  Konfliktquellen, erweiterte Kalenderaktionen und Geräteintegration.

## Qualitätssicherung

Regressionsprüfungen betreffen API, Kalender-Web, ICS, CalDAV, abgesagte und
angefragte Termine, alte personalisierte Templates, Einladungslinks,
Sommer-/Winterzeit, Freitexte, Zugriffsentzug, Datenschutz/HTML-Escaping,
Migrations-Wiederholbarkeit und doppelte gleichzeitige Buchungsversuche.
Vor Merge komplette Portal-CI sowie CodeQL berücksichtigen.
