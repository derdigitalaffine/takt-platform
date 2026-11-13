# Digitales Verbandbuch – V1, Installation und Freigabe

> **Stand 13.11.2026.** Vertrauliche Fachfunktion nach DGUV Vorschrift 1 § 24 Abs. 6.
> Technischer Merge **ist keine** Rechts-, Datenschutz-, Security- oder Produktivfreigabe.

## Was V1 abdeckt

- Zentrale Modulverwaltung (Default **OFF**), Navigation, Modul-Domain-Regel `PORTAL_ONLY`, getrennte Benutzerfachrechte `verbandbuch_capture` und `verbandbuch_review`.
- Standortverzeichnis mit verbindlicher Anbindung an TAKT-Organisationen. Zusätzlich standortbezogene Grants; kein Fachzugriff allein durch globale Adminrechte. Eine fachliche Einsicht erfordert **beide**: personenbezogenes Reviewrecht und gültiges Standortmandat.
- QR-Button pro Standort verwendet den globalen TAKT-Dialog: einheitliche Vorschau, SVG/PNG/JPG, A4-Druckaushang. Standort ist signiert, QR vermittelt **keine** Berechtigung und enthält **keine** Gesundheitsdaten.
- Mobil optimiertes Pflichtformular: betroffene Person, Unfallort/-zeit, Unfallhergang, Verletzung/Erkrankung, Erste-Hilfe-Zeit/-Maßnahme, Ersthelfende, optional Zeugen und Personenkreis.
- Separate Fachtabellen; medizinische Dokumentation ausschließlich als mit einem separaten Fernet-Schlüssel verschlüsseltes JSON. Keine Ablage in `FormResponse`, KI/RAG, allgemeinen Workflows, Aufgaben, DMS, E-Mail oder Suche.
- Neutrale Empfangsquittung, standortgebundene Fachablage, protokollierte Einsicht und Druckansicht, unveränderliche ursprüngliche Fassung und verschlüsselte Berichtigungsversionen, Löschsperre mit Begründung, 5-Jahres-Frist pro Eintrag, tägliche Löschung abgelaufener ungesperrter Fälle.
- Öffentliche und anonyme Eingaben, Uploads, SMS/E-Mail mit Falldetails, Offline-Verfügbarkeit und anzeigepflichtige Arbeitsunfälle sind bewusst **nicht** freigeschaltet; dafür existieren eigene spezifizierte Folgeaufgaben.

## Betriebsparameter

`docker-compose.yml` reicht diese separaten Variablen an den Portalcontainer weiter:

```env
VERBANDBUCH_ENCRYPTION_KEY=
VERBANDBUCH_PRODUCTION_APPROVED=0
```

Fachschlüssel einmalig separat generieren:

```sh
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Schlüssel in der gesicherten Secret-Verwaltung hinterlegen; getrennt von `PORTAL_SECRET_KEY` aufbewahren und bei Wiederherstellung **nicht verlieren**. Schlüsselverlust bedeutet, dass bestehende Einträge nicht mehr entschlüsselt werden können. Schlüsselwechsel/Rotation ist ein Folge-Gate; nie bestehende Einträge durch blindes Neusetzen des Keys aussperren.

Für lokale Tests wird `VERBANDBUCH_PRODUCTION_APPROVED=1` mit synthetischen Daten verwendet. Diese Flagge ist **kein Nachweis** einer genehmigten DSFA oder Rechtsgrundlage. In der Produktion den Schalter `VERBANDBUCH_PRODUCTION_APPROVED=0` belassen, bis verantwortliche Stellen dokumentiert freigeben.

## Freigabe vor Echtbetrieb

1. Rechtsgrundlage für Verarbeitung besonderer personenbezogener Daten nach Art. 9 DSGVO, Zweckbindung und Verzeichnis von Verarbeitungstätigkeiten dokumentiert; DSB einbezogen, DSFA-Vorprüfung durchgeführt, ggf. DSFA abgeschlossen.
2. Fachverantwortung, Betriebsarzt/Fachkraft für Arbeitssicherheit und Personalvertretung nach den geltenden Vorschriften beteiligen; Standort-/Arbeitgebergrenzen prüfen.
3. Separates Key-Management und Schlüsselrotation, verschlüsselte Backups, sicherer Restore-Drill mit Datenminimierung und Backup-Löschkonzept nachgewiesen. Der aktuelle SQLite-Speicher befindet sich im gemeinsamen DB-Volume; er ist logisch getrennt, **nicht** auf einer eigenständig verschlüsselten Datenbank. Für hohen Schutzbedarf separate physische Verschlüsselung/DB prüfen.
4. Fachzugriffe einschließlich abgelehnter Direktlinks, Review-Mandate, Admin-Ausnahme, CSRF und Audit, HTTPS, Session-MFA, Pentest und Logging ohne sensible Inhalte geprüft.
5. Löschfristen/Legal-Holds samt Prüfung und spätere Freigabe/Aufhebung, Auskunfts-/Berichtigungsrechte, Ausdruck-/Exportverfahren, offene Sonderfälle festlegen.
6. UX-/Barrierefreiheitstest einschließlich mobiler Geräte sowie Prüfung, dass QR-Aushänge keine Zugangserweiterung enthalten.

Erst danach: `VERBANDBUCH_PRODUCTION_APPROVED=1` setzen, Fachrechte bewusst vergeben und Modul unter **Administration → Module** einschalten. Nicht allein aufgrund dieses Dokuments aktivieren.

## Sicherheitshinweise / Grenzen

- Die verschlüsselten fachlichen Datentabellen liegen auf der aktuellen Portal-SQLite-Instanz. Verschlüsselte Nutzlast schützt Inhalte bei gewöhnlicher SQL-Ansicht, aber weder Metadaten noch kompromittierte Application-Server-Prozesse. Strengere physische Trennung und Key-Rotation müssen vor flächendeckendem sensiblen Betrieb gesondert nachgewiesen werden.
- Standard-Administratoren können Standorte und Grants konfigurieren, aber ohne `verbandbuch_review` **und** standortbezogenen Review-Grant keine Akte öffnen; Selbstvergabe von Review-Grants über das Fachmodul wird blockiert. Für absolute Trennung der Rollen ist unabhängige Berechtigungsfreigabe zu etablieren.
- QR-Ziele sind nur angemeldeten Konten mit Standort-Grant zugänglich. Gastzugriff/Externe bleiben aus.
- Berichtigung legt jeweils eine zusätzliche verschlüsselte Vollfassung an, statt den ursprünglichen Datensatz zu überschreiben; sensible Änderungsgründe werden verschlüsselt.
- Aufbewahrungslauf löscht primäre Daten, Fassungsversionen und fallgebundene Zugriffsaudits; Audit-/Backup- und Restore-Nachweise bedürfen eigener Freigabe und Aufbewahrungsabwägung. Löschprotokoll enthält keinen medizinischen Text.
- Kein medizinischer Fall wird über die allgemeinen TAKT-KI- und Suchen-Endpunkte verfügbar gemacht.

## Tests

```sh
cd portal && python -m pip install -r requirements.txt pytest
python -m pytest -q tests/test_verbandbuch.py tests/test_domains.py
```

Gesamtsuite: `cd portal && python -m pytest -q tests`.

Weitere fachliche Anforderungen: ursprüngliche Spezifikation in Branch `planning/personalratswahl-verbandbuch-2026-11`, Verbandsbuch-Epic #386 und V01–V15.
