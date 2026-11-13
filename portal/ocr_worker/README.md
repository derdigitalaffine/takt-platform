# TAKT Ortsrecht – MarkItDown + Tesseract (optionaler Offline-Worker)

**Stand:** Erster testbarer OCR-Slice von #427 und #430, keine automatische Veröffentlichung. Teil der übergeordneten Rechtstext-Architektur #120 / #428. Die vorhandenen Rechtstexte werden nicht automatisch verändert.

## Was ist implementiert?

1. Berechtigte Redakteure laden Originaldateien unter `/laws-assistant` hoch. Das Original wird als unveränderter Binärinhalt mit SHA-256, zufälligem Speicherschlüssel und Eigentümerbindung gespeichert.
2. Bei PDF/DOCX und Bildern erscheint **Lokale Texterkennung starten**. Die Webanwendung legt lediglich ein kleines JSON-Manifest im auf den OCR-Bereich beschränkten Queue-Ordner ab. Sie führt weder Tesseract noch MarkItDown in einem Uvicorn-Prozess aus.
3. Der **optionale** Docker-Service `law-ocr` verarbeitet nacheinander die Dokumente vollständig offline:
   - **MarkItDown 0.1.9**, ohne Plugins oder LLM-Client: strukturnahe Markdown-Umwandlung von DOCX und digitalen PDF-Dateien (Überschriften, Listen, Tabellen, soweit erkennbar).
   - **PyMuPDF**: pro PDF-Seite Ermittlung, ob eine brauchbare native Textebene vorhanden ist.
   - **Tesseract (deu / deu+eng)**: gescannte PDF-Seiten sowie PNG, JPEG, TIFF und WEBP. TSV liefert Wortpositionen und Erkennungskonfidenz.
   - **Gemischte PDFs**: Originalseitenreihenfolge und Herkunft von nativem Text / Tesseract sind im Ergebnis getrennt nachweisbar. Der Text wird **nicht automatisch geglättet**. Für Hybrid-PDFs stehen noch nicht alle von MarkItDown erkannten Layoutmerkmale seitenbezogen zur Verfügung.
4. Der Worker schreibt ausschließlich ein begrenztes JSON-Ergebnis zurück. Die Webanwendung kontrolliert Job-ID und **SHA-256 des Originals**, übernimmt den Text als **ungeprüften Entwurf** und zeigt Qualitätswarnungen sowie Seiteninformationen im Review-Dialog.
5. Erst eine separate, bewusst bestätigte menschliche Aktion übernimmt einen vom Redakteur kontrollierten Text in einen **neuen, unveröffentlichten** `LawText`. Keine KI/OCR ändert `planned_md`, `published` oder bestehende Rechtsfassungen.

## Installation

Im Repository-Stammordner, nach vorhandener TAKT-Installation:

```bash
# optionaler Dienst, kein Internetzugang zur Laufzeit
docker compose --profile ocr up -d --build law-ocr

# Status nur lokal am Container:
docker compose --profile ocr ps law-ocr
docker compose --profile ocr logs --tail=100 law-ocr
```

**Wichtig:** Die Portaldaten liegen wie bisher unter `${CONFIG}/portal`. Der OCR-Container sieht ausschließlich diese schmalen Unterverzeichnisse:

- `law-ai-originals` – **read-only**, nur hochgeladene Originale.
- `law-ai-ocr-queue` – JSON-Aufträge, keine Portal-Datenbank.
- `law-ai-ocr-results` – JSON-Vorschläge, keine Publikationsrechte.

Er besitzt **kein Netzwerk**, keine Portal-Schlüssel und keine anderen Volumes. Zusätzlich: `no-new-privileges`, `cap_drop=ALL`, schreibgeschütztes Root-Dateisystem, Prozess-/Speicher-/CPU-Limits und ein flüchtiges `/tmp`. Der Dienst kann bei Bedarf mit `docker compose --profile ocr stop law-ocr` ausgeschaltet werden; bestehende Portal- und Rechtstextfunktionen bleiben nutzbar.

Derzeit ist die Dateieigentümer-/Container-Nutzertrennung noch über die eng begrenzten Bind-Mounts und Linux-Capabilities realisiert; ein eigener UID/GID- und Host-MAC-/SELinux-Plan ist vor einer hochregulierten Mehrmandanteninstallation gesondert zu prüfen.

## Sicherheit und Datenqualität

- Maximal 25 MiB Original, 120 PDF-/Bildseiten, 12 Millionen Pixel je Bildseite, 75 Sekunden OCR pro Seite, 2 MiB extrahierter Markdown-Text. Begrenzte TSV-Wortkoordinaten und Ergebnisgröße.
- Keine URL-Konvertierung, Office-Makros, MarkItDown-Plugins oder Cloud-/LLM-Anbieter im Worker. **MarkItDown selbst ist kein OCR-Modell** und ersetzt Tesseract nicht.
- SHA-256 schützt gegen Vertauschen einer Originaldatei. Es ist keine digitale Signatur, keine beweiskräftige Bekanntmachung und keine Rechtswirksamkeitsprüfung.
- Tesseract-Konfidenzen sind technische Schätzwerte, keine Garantie juristischer Texttreue. Unsichere Seiten und kritische Stellen (Zahlen, Fristen, Negationen, Tabellen) bleiben prüfbedürftig.
- Kein direktes Schreiben in Fachmodule; Entwurfsübernahme nur nach CSRF, ACL und ausdrücklich gesetztem Bestätigungsfeld.
- Eine neue Übernahme darf **keine** bereits publizierte Norm automatisch verändern. Bestehende Funktionen zum manuellen Veröffentlichen sind **noch nicht** durch das geplante separate Vier-Augen-Rollensystem aus #120/#428 ersetzt.
- Die asynchrone Queue benutzt atomare Dateinamen und Wiederaufnahme von unvollendeten Aufträgen bei Worker-Neustart. Sie bietet noch kein verteiltes Leasing über mehrere Worker und keine garantierte Echtzeit-Fortschrittsanzeige je Seite; deshalb zunächst nur **eine** OCR-Worker-Replik betreiben.

## Tests

```bash
cd portal
python -m pytest -q tests/test_law_ocr_worker.py tests/test_law_ocr_queue.py tests/test_law_ai_staging.py
```

Diese Tests erfordern kein Tesseract und kein MarkItDown im Portalprozess: Sie prüfen die isolierte Worker-API mit kontrollierten Fakes sowie den echten Web-/Datenbankpfad. Vor produktiver OCR-Nutzung sind zusätzlich echte Scan-PDFs, Fraktur, Gebührenverzeichnisse und DOCX-Tabellen in einem rechtmäßig verwendbaren Referenzkorpus zu prüfen sowie ein Build-/E2E-Smoke des OCR-Images auszuführen.

## Weiter offen

- Fraktur-Sprachpakete/Profile, OCR-Qualitätsbenchmark und komplette Layout-/Tabellenlokalisierung.
- Modulspezifische `laws_edit`-/`laws_review`-/`laws_publish`-Rechte, amtliche Bekanntmachungsnachweise und echte Vier-Augen-Freigabe (#120, #428).
- Gesonderte KI-Agenten für Metadaten, Satzungsgliederung und Texttreue (nur nach Quellenprüfung, #429).
- Nachweissichere Retention-/Löschpläne, Betriebsfreigabe und erweiterte Queue-Leases (#431).

**Keine dieser noch offenen Funktionen wird in diesem PR als produktiv fertig ausgewiesen.**
