# TAKT Personalratswahl – Implementierungsstand und Freigabekriterien

Stand: 13. November 2026. **Feature-Branch; kein produktiver Freigabevermerk.**

## Umgesetzter durchgängiger Wahlfahrplan

1. Wahlvorstand bestellen: Einladungs- und Bestellungsentwürfe, Fachmandate, Nachweise.
2. Wahl vorbereiten: Prüfpunkte, Wählerverzeichnis-Prüfvermerk ohne personenbezogene Wählerlisten, Gruppen- und Sitzverteilungsentwurf.
3. Wahl einleiten: Wahlausschreiben, Bekanntmachung, Dokumentrevisionen.
4. Wahlvorschläge: Entwürfe für Wahlvorschläge, Zustimmungen, Nachfristen und Bekanntgaben.
5. Papierwahl: Wahllokal- und Materialcheck, Stimmzettel und Briefwahlorganisation dokumentieren.
6. Öffentliche Auszählung: ausschließlich aggregierte Stimmen erfassen; Plausibilität prüfen; Listenwahl-Rechenhilfe mit exaktem d’Hondt-Verfahren, Quotientengleichstand ohne automatische Entscheidung; Personenwahl ohne automatische Mandatsvergabe.
7. Ergebnisfeststellung: manuelle Niederschrift, Bestätigung der Erfassungen und fachliche Ergebnisfeststellung.
8. Konstituierende Sitzung: Einladung, Vorsitzwahl, Niederschrift, Aktenübergabe.
9. Archivierung: Übergabeprotokoll und Aufbewahrungsnachweis.

Alle Phasen dokumentieren einen manuellen Nachweis. Eine digitale Phasenmarkierung ist **kein Ersatz** für Beschluss, Originalunterschrift, Bekanntgabe, Fristprüfung oder rechtswirksame Handlung.

## Formularstudio

Die strukturierten Musterorientierungen sind **keine wortgetreue Wiedergabe der amtlichen Landesvordrucke**. Es werden vertrauliche, versionierte Prüfentwürfe erzeugt, wahlbezogen berechtigt und verschlüsselt gespeichert. PDF und bearbeitbare DOCX sind möglich. Ein Abgleich mit den amtlichen, aktuellen Word-Mustern des Innenministeriums ist vor jeder Verwendung zwingend. Unterschriften erfolgen auf Papier, soweit gesetzlich erforderlich.

## Grenzen und vor Produktivfreigabe zu erledigen

- Aktuelle amtliche WOLPersVG, LPersVG und ministerielle Mustervordrucke vollständig juristisch verifizieren und die Muster **feld- und wortlautgetreu** nachbauen; fachlich freigegebenes, versioniertes Regelpaket mit Ablauf- und Fristenberechnung entwickeln.
- Mandate und Dienststellenabgrenzung mit Datenschutz und Personalrat abstimmen; Rollenbesetzung dokumentieren; getrennte Datenhaltung, Zugriffskontrolle und Lösch-/Aufbewahrungsfristen abnehmen.
- Wahlberechtigtenverzeichnis und Kandidaturen mit eigenen datensparsamen Fachobjekten und Einzelberechtigungen ergänzen; Einspruchs- und Wahlvorschlagsprüfung rechtskonform implementieren.
- Gruppenwahl, gemeinsame Wahl, Listenwahl, Personenwahl, Sitzverteilung, Sonderfälle und Losverfahren mit unabhängig geprüften Testfällen und menschlicher Freigabe vollständig abbilden. Die vorhandene d’Hondt-Rechenhilfe deckt **nur** manuell bestätigte Listenstimmen in einer vorgegebenen Sitzanzahl ab.
- Auszählungsrevisionen mit expliziter Ersetzung/Invalidierung und Vier-Augen-Prüfung ergänzen. Derzeit sind bestätigte Zählfassungen unveränderlich und mehrere Runden nicht als Nachzählung verknüpft.
- Einladung, Benachrichtigung, Aushang, Aktenübergabe und konstituierende Sitzung um Zustellnachweise, Teilnehmerrollen, Anwesenheit und Unterzeichnungsprozesse erweitern.
- Modul ist standardmäßig deaktiviert. Keine Onlinewahl oder Integration mit experimentellem Abstimmungsmodul.
- Migrationen und vollständige Test-Suite in einer geeigneten Buildumgebung ausführen. Der GitHub-Connector erlaubt hier Repository-Dateiänderungen, aber keinen lokalen Build/pytest-Lauf; Tests wurden hinzugefügt, **nicht ausgeführt**.
- Vor Freigabe: Datenschutz-Folgenabschätzung prüfen, Sicherheits- und Barrierefreiheitstests, offizielle Vorlagen, technische Dokumentation, Rollback und Deployment-Gate.

## Referenzen

- LPersVG RLP § 29: Konstituierende Sitzung.
- WOLPersVG RLP: Wahlvorstand, Wahlvorschläge, Wahlhandlung, öffentliche Auszählung, Ergebnis und Wahlakten.
- Amtliche Mustervordrucke und aktuelle konsolidierte Landesrechtsfassung über Justizportal RLP / Innenministerium prüfen.
