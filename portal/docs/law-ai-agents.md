# TAKT Ortsrecht – mehrstufige LLM-Redaktionsagenten

**Stand:** Implementierungsstand für #429 und #430. Ergänzt die Original-/OCR-Pipeline (#435, #438) mit **MarkItDown 0.1.9, PyMuPDF und Tesseract**. KI-Analyse und fachliche Veröffentlichung bleiben konsequent getrennt.

## Wie die Analyse startet

1. In **Administration → KI** müssen unter *Agenten und Modellzuweisungen* die Aufgaben `law_structure`, `law_metadata`, `law_verify` **explizit** mit aktiven freigegebenen Providern und Modellen belegt sein. Anders als ein allgemeiner Chat verwendet die Ortsrecht-Prüfung absichtlich **keinen stillen Standardprovider**.
2. Ortsrecht- und KI-Modul müssen aktiviert sein. Bearbeiter benötigen beide Rechte: `laws` und `ai_chat`. Nur die Eigentümerin/der Eigentümer eines Importentwurfs darf ihn KI-analysieren und die Ergebnisse sehen.
3. Nach Markdown-/Textimport oder OCR-Abschluss einen eigenen Entwurf unter **`/laws-assistant`** öffnen. Die KI erhält **nur den zuvor extrahierten Markdown-/Textvorschlag**, nicht das binäre Original, und ruft keine externe Websuche und kein Fachtool auf.
4. Die drei tatsächlich konfigurierten Serveradressen, Providernamen und Modelle werden **vor dem Start sichtbar** angezeigt. Mit der ausdrücklichen Zustimmungscheckbox wird nur diese einzelne Analyseautorisation erteilt.
5. **Einfach** versendet je Stufe eine Anfrage; bei langen Dokumenten verwendet die KI ausdrücklich gekennzeichnete Stichproben. **Erweitert** übermittelt den vollständigen importierten Text in bis zu **10 lückenlos aufeinanderfolgenden Abschnitten** von maximal 14.000 Zeichen an **jeden** der drei Agenten (maximal **30 Modellaufrufe**). Die UI nennt die Anzahl und möglichen Mehrkosten **vor** der Zustimmung.
6. Nach Analyse: vorgeschlagene **Gliederung**, **Stammdaten** (jeweils wortgetreue Belegstelle) und **Prüfhinweise** ansehen. Bei Volltextprüfung erscheinen Abdeckung und die präzisen Textzeichenpositionen. Metadaten und optische Überschriften werden ausschließlich **nach einem zusätzlichen Klick** in den bearbeitbaren Formularentwurf übernommen.

## Agenten und Sicherheitsverträge

| Aufgabe | Erwartete Ausgabe | Verhalten |
|---|---|---|
| `law_structure` | `headings`: exakte Quellzeile + Überschriftenebene | Keine Änderung am Original, keine erfundenen Überschriften; nur optische Vorschläge |
| `law_metadata` | `fields`: zulässiger Feldname, Wert, exakt belegtes Quellzitat | Unbelegte Werte und Statusfelder wie `published` werden verworfen; Daten nur bei tatsächlichem Beleg |
| `law_verify` | `findings`: Schwere, Quellzitat, Grund, Prüfempfehlung | Prüft Auffälligkeiten bei Fristen, Beträgen, Verneinungen und Verweisen; **keine** Rechtswirksamkeitsbehauptung |

Alle Antworten müssen **maschinenlesbare JSON-Objekte** mit eng begrenzten Arrays und Textgrößen liefern. Fremde Tool-/Action-Felder werden nicht weitergereicht. Zitate werden gegen den aktuellen Importtext geprüft; erfundene Fundstellen werden verworfen. Die Originaldatei verbleibt mit SHA-256 im geschützten Ortsrecht-Archiv.

**Wichtig:** Die KI-Zitatprüfung beweist nur, dass eine Passage im *extrahierten* Text vorkommt. Sie ersetzt **nicht** den Abgleich mit dem Original-PDF, Scan, Bekanntmachungsblatt oder sonstigem amtlichen Nachweis.

## Dauerhafte Aufträge und Modelle

- Additives Tabellenmodell `law_ai_analyses`, mit Entwurfs- und Nutzerbezug, Quelltext-Hash, Modus, Start-/Fertigstellungsstatus und **konkretem Modell-/Provider-Snapshot**.
- Drei sequenzielle Schritte in einem **separaten asynchronen Task der Portal-Laufzeit** (nicht im HTTP-Request); ein Auftragsstatus `queued/running/done/failed/cancelled`. Die Verarbeitung schickt Quelltext nur an **die bei der Bestätigung angezeigten Provider**. Wenn ein Profil geändert oder gesperrt wird, bricht der Auftrag sicher ab.
- **Einfach:** drei Modellaufrufe. Im bisherigen Modus wird Text bis 19.000 Zeichen ohne Kürzung analysiert, längere Quellen werden mit klarer Stichprobenkennzeichnung untersucht.
- **Erweitert:** deterministische, quellengetreue Aufteilung in maximal 10 Abschnitte von höchstens 14.000 Zeichen. Aneinandergehängte Abschnitte ergeben **byte-/zeichengenau den ursprünglichen extrahierten Text**, ohne Auslassungen oder eingefügte KI-Markierungen. Je Agent werden alle Abschnitte durchlaufen, maximal 30 Modellaufrufe, strikt sequentiell. Ein Lauf kann bis zu 12 Minuten dauern; ein überschrittenes Zeitbudget führt zu **Fehler statt unvollständig als erfolgreich gekennzeichneter Analyse**.
- Pro Modellaufruf max. 70 Sekunden Netzwerklaufzeit und max. 3.072 generierte Tokens; keine Multi-Provider-Fallbacks, keine autonom ausgeführten Aktionen, kein Chatkontext.
- Eingabe weiterhin maximal **120.000 Zeichen**. Der Volltextmodus verwendet einen Abschnittsrahmen von 14.000 Zeichen; damit entfällt die bisherige Beschränkung auf bloße Kopf-/End-/Risikostichproben. Jedes Zitat wird **im tatsächlich übermittelten Abschnitt** überprüft, mit zugehöriger Abschnittsnummer und Textoffset dauerhaft festgehalten. Bei unklaren mehrfachen Stammdatenwerten wird ein Konflikt angezeigt.
- **Vollständige Textübermittlung bedeutet keineswegs vollständige juristische Prüfung**. Jedes Modell kann Fehler übersehen; Eingangsquelle ist der OCR-/MarkItDown-Text, nicht notwendig eine geprüfte amtliche Fassung. Bei Abbruch, Serverfehler, Änderung von Rechten/Modellen oder fehlender Textabdeckung darf nie ein scheinbar vollständiges Ergebnis entstehen.
- Der asynchrone Task startet automatisch mit dem Portal. **Anders als der abgeschottete MarkItDown-/Tesseract-OCR-Container** findet die LLM-Orchestrierung derzeit im Portalprozess statt; sie führt dort aber keine schwere OCR aus. Horizontale Skalierung, umfassende Leases und separater KI-Worker bleiben spätere Betriebsaufgaben.

## Live-Feedback und Streaming-Modelle

Im KI-Provider unter **Administration → KI** kann Streaming ausdrücklich aktiviert werden (`stream_enabled`). Die Ortsrecht-Agenten erkennen diese vorhandene Provider-Einstellung je zugewiesenem Aufgabenmodell:

- **Streaming aktiv:** Der jeweilige Agent empfängt die OpenAI-kompatible Antwort über `stream_completion()`; die Oberfläche zeigt über eine besitzergeschützte **Server-Sent-Events-Verbindung (SSE)** den Agenten, den Textabschnitt, den Fortschritt, empfangene Zeichen/Antwortteile und die Anzahl bereits quellengeprüfter Vorschläge. Die Streaming-Ausgabe bleibt nur während der Anfrage im Arbeitsspeicher des Workers.
- **Streaming nicht aktiv:** Der Agent nutzt die vorhandene `complete()`-Schnittstelle und dieselbe Fortschrittsanzeige, ohne eine nicht unterstützte Streaming-Fähigkeit zu unterstellen.
- **Sicherheit:** Weder unvollständige JSON-Schnipsel noch ungeprüfte KI-Behauptungen werden im Status-Endpunkt, im SSE-Kanal oder in der Datenbank veröffentlicht. Zunächst sind ausschließlich numerische Fortschrittswerte sichtbar; Vorschlagszahlen werden erst nach Schema- und wörtlicher Fundstellenprüfung erhöht. Rohantworten werden erst nach vollständiger Validierung in die getrennten Ergebnisfelder übernommen.
- **Fallback:** Wenn SSE im Browser oder Reverse-Proxy nicht verfügbar ist, verwendet die Anzeige automatisch den geschützten JSON-Statusabruf. Streaming-Provider, die trotz aktivierter Einstellung kein echtes SSE liefern, verursachen einen klaren Analysefehler: keine automatische Doppelübertragung durch stillen Fallback auf `complete()`.
- **Abbruch und Datenschutz:** Status und SSE prüfen Eigentümer- und KI-Rechte; ein Widerruf, Providerwechsel oder Abbruch unterbindet die weitere Verarbeitung bei der nächsten Streaming-Aktualisierung. Eine bereits versendete externe Anfrage kann nicht rückgängig gemacht werden.
- **Datenbankschema:** Zusätzliche additive, wiederholbare Migration für `law_ai_analyses` erhält alte KI-Befunde und ergänzt nur `progress_total`, `progress_done`, `stream_characters`, `stream_chunks`, `stream_active`, `validated_items`. Die Statusübertragung enthält keinen Rechtstext und keine API-Schlüssel.

Die technische Antwortmenge ist kein Tokenzähler oder eine Garantie für den Aussagewert der KI. **Die Anzeige „Streaming“ bedeutet ausschließlich, dass eine Antwort technisch eintrifft** – sie bestätigt nicht die Richtigkeit des Rechtsdokuments.

## Fehler, Widerruf und Datenschutz

- Berechtigungen, aktive Module, Quelltext-SHA und alle drei Modellprofile werden **vor jedem einzelnen Abschnittsaufruf und bei Rückgabe** erneut geprüft. Änderungen eines KI-Anbieters während einer Verarbeitung blockieren die weitere Übermittlung.
- Benutzer können einen noch nicht abgeschlossenen Prüfauftrag abbrechen. Das verhindert weitere Agentenschritte und das Speichern eines erfolgreich abgeschlossenen Befunds; eine bereits versandte Anfrage ist jedoch **nicht rückholbar**.
- Gescheiterte / abgebrochene Aufträge verändern weder `LawText`, geplante Fassung noch Veröffentlichungsstatus. Ein neuer Auftrag ist nach ausdrücklicher Zustimmung möglich.
- Nur validierte, auf den Quelltext belegte strukturierte Ergebnisse und Modellkennungen werden gespeichert; **keine Rohprompts, fremden Chats, API-Keys oder unvalidierten LLM-Rohantworten** im Analyseprotokoll.
- Rechtlich erforderliche Aufbewahrungsfristen, technische Löschfristen, Backup, 4-Augen-Prüfung und echte Nachweise der amtlichen Bekanntmachung sind weiterhin in #120, #428 und #431 gesondert zu klären. Der vorhandene Editor darf nicht mit einer fachlichen Veröffentlichungsgenehmigung verwechselt werden.

## Tests

```bash
cd portal
python -m pytest -q tests/test_law_ai_agents.py tests/test_law_ai_coverage.py tests/test_law_ai_staging.py tests/test_law_ocr_queue.py
```

Die Agententests verwenden **Fake-LLM-Modelle** und senden keine echten Daten; geprüft werden getrennte Modellrouten, JSON-Schemas, erfundene Belegstellen, Rollenkontrolle, Providerwechsel, Quelltext-Fingerabdruck und Nichtveröffentlichung. Die gesamte Portal-Suite und die vorhandenen OCR-Image-Smokes bleiben Merge-Gates.

## Nicht Bestandteil dieses Slices

- Direkte multimodale OCR-Korrektur `law_ocr_vision` mit rechtssicherer Bildübermittlung.
- Dokumente über 120.000 Zeichen, adaptive oder parallele Kontextverteilung, juristische Synopsenprüfung und Verifikation rechtsverbindlicher Originalfassungen. Die neue Volltextanalyse ist für Texte innerhalb der genannten Obergrenze nutzbar, nicht für beliebig lange Anlagen.
- Automatische Rechtskraftprüfung oder KI-gesteuerte Veröffentlichung – **ausdrücklich nicht erlaubt**.
- Eigenständiger horizontal skalierter LLM-Prozess mit fortgeschrittenem Rate-/Kostenbudget.
