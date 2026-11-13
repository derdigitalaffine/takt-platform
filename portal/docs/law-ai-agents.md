# TAKT Ortsrecht – mehrstufige LLM-Redaktionsagenten

**Stand:** Implementierungsstand für #429 und #430. Ergänzt die Original-/OCR-Pipeline (#435, #438) mit **MarkItDown 0.1.9, PyMuPDF und Tesseract**. KI-Analyse und fachliche Veröffentlichung bleiben konsequent getrennt.

## Wie die Analyse startet

1. In **Administration → KI** müssen unter *Agenten und Modellzuweisungen* die Aufgaben `law_structure`, `law_metadata`, `law_verify` **explizit** mit aktiven freigegebenen Providern und Modellen belegt sein. Anders als ein allgemeiner Chat verwendet die Ortsrecht-Prüfung absichtlich **keinen stillen Standardprovider**.
2. Ortsrecht- und KI-Modul müssen aktiviert sein. Bearbeiter benötigen beide Rechte: `laws` und `ai_chat`. Nur die Eigentümerin/der Eigentümer eines Importentwurfs darf ihn KI-analysieren und die Ergebnisse sehen.
3. Nach Markdown-/Textimport oder OCR-Abschluss einen eigenen Entwurf unter **`/laws-assistant`** öffnen. Die KI erhält **nur den zuvor extrahierten Markdown-/Textvorschlag**, nicht das binäre Original, und ruft keine externe Websuche und kein Fachtool auf.
4. Die drei tatsächlich konfigurierten Serveradressen, Providernamen und Modelle werden **vor dem Start sichtbar** angezeigt. Mit der ausdrücklichen Zustimmungscheckbox wird nur diese einzelne Analyseautorisation erteilt.
5. Nach Analyse: vorgeschlagene **Gliederung**, **Stammdaten** (jeweils wortgetreue Belegstelle) und **Prüfhinweise** ansehen. Einfach-/Expertenmodus steuert die Präsentation. Die Übernahme einzelner Metadaten ins Formular erfolgt **nur durch Klick**, ebenso optionale inhaltsneutral zu prüfende Markdown-Überschriftenformatierung.

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
- Pro Schritt max. 70 Sekunden Netzwerklaufzeit, max. 3.072 generierte Tokens; keine Multi-Provider-Fallbacks, keine autonom ausgeführten Aktionen, kein Chatkontext.
- Eingabe maximal **120.000 Zeichen**; Modellkontext je Stufe maximal **19.000 Zeichen**. Bei langen Dokumenten werden nur Anfangs-/Endstellen, Gliederungsüberschriften und Risikostellen übergeben. Der Befund zeigt ausdrücklich **Teilanalyse / Stichprobe**. Er darf nicht als vollständige rechtliche Prüfung verstanden werden.
- Der asynchrone Task startet automatisch mit dem Portal. **Anders als der abgeschottete MarkItDown-/Tesseract-OCR-Container** findet die LLM-Orchestrierung derzeit im Portalprozess statt; sie führt dort aber keine schwere OCR aus. Horizontale Skalierung, umfassende Leases und separater KI-Worker bleiben spätere Betriebsaufgaben.

## Fehler, Widerruf und Datenschutz

- Berechtigungen, aktive Module, Quelltext-SHA und drei Modellprofile werden **vor jeder einzelnen Stufe** erneut geprüft.
- Benutzer können einen noch nicht abgeschlossenen Prüfauftrag abbrechen. Das verhindert weitere Agentenschritte und das Speichern eines erfolgreich abgeschlossenen Befunds; eine bereits versandte Anfrage ist jedoch **nicht rückholbar**.
- Gescheiterte / abgebrochene Aufträge verändern weder `LawText`, geplante Fassung noch Veröffentlichungsstatus. Ein neuer Auftrag ist nach ausdrücklicher Zustimmung möglich.
- Nur validierte, auf den Quelltext belegte strukturierte Ergebnisse und Modellkennungen werden gespeichert; **keine Rohprompts, fremden Chats, API-Keys oder unvalidierten LLM-Rohantworten** im Analyseprotokoll.
- Rechtlich erforderliche Aufbewahrungsfristen, technische Löschfristen, Backup, 4-Augen-Prüfung und echte Nachweise der amtlichen Bekanntmachung sind weiterhin in #120, #428 und #431 gesondert zu klären. Der vorhandene Editor darf nicht mit einer fachlichen Veröffentlichungsgenehmigung verwechselt werden.

## Tests

```bash
cd portal
python -m pytest -q tests/test_law_ai_agents.py tests/test_law_ai_staging.py tests/test_law_ocr_queue.py
```

Die Agententests verwenden **Fake-LLM-Modelle** und senden keine echten Daten; geprüft werden getrennte Modellrouten, JSON-Schemas, erfundene Belegstellen, Rollenkontrolle, Providerwechsel, Quelltext-Fingerabdruck und Nichtveröffentlichung. Die gesamte Portal-Suite und die vorhandenen OCR-Image-Smokes bleiben Merge-Gates.

## Nicht Bestandteil dieses Slices

- Direkte multimodale OCR-Korrektur `law_ocr_vision` mit rechtssicherer Bildübermittlung.
- Vollständige Dokumentabdeckung unabhängig von Kontextlänge, juristischer Synopsenprüfung und Verifikation rechtsverbindlicher Fassungen.
- Automatische Rechtskraftprüfung oder KI-gesteuerte Veröffentlichung – **ausdrücklich nicht erlaubt**.
- Eigenständiger horizontal skalierter LLM-Prozess mit fortgeschrittenem Rate-/Kostenbudget.
