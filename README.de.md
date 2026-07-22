# Prisma

🌐 [English](README.md) · **Deutsch**

![Lizenz: MIT](https://img.shields.io/badge/license-MIT-blue)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![Tests: 211 bestanden](https://img.shields.io/badge/tests-211%20passing-brightgreen)
![100% lokal](https://img.shields.io/badge/privacy-100%25%20lokal-blueviolet)

Prisma ist eine lokale Browser-Oberfläche mit drei Werkzeugen für die Arbeit mit KI-Modellen: einem **Datei-Konverter**, der PDF, Word, Excel, CSV, TXT und PowerPoint in token-effiziente Formate wandelt, einem **Prompt-Trainer**, der die Struktur deiner Prompts regelbasiert bewertet und dir beim Lernen hilft, und einer **Statistik**, die deine Ersparnis zeigt. **Alles läuft komplett lokal auf deinem Rechner** — es gibt keine einzige externe Verbindung, keine Datei und kein Prompt verlässt deinen PC. Ein eigener Test (`tests/test_privacy.py`) beweist das bei jedem Testlauf.

| Helles Theme (Standard) | Dunkles Theme |
|---|---|
| ![Konverter, helles Theme](docs/konverter-hell.png) | ![Konverter, dunkles Theme](docs/konverter-dunkel.png) |

| Prompt-Trainer | Statistik |
|---|---|
| ![Prompt-Trainer](docs/trainer-hell.png) | ![Statistik](docs/statistik-hell.png) |

## Was die Werkzeuge können

1. **Datei-Konverter**: Dokumente werden zu strukturiertem Markdown (Überschriften und Tabellen inklusive), reine Datentabellen zu CSV — verpackt passend für dein KI-Modell (Claude → XML-Tags, GPT → Markdown-Abschnitte, Gemini → klare Gliederung). Bild-PDFs und gemischte PDFs (Text + Scans) werden automatisch per **OCR** erkannt, seitenweise, damit nichts verloren geht. Du kannst **mehrere Dateien gleichzeitig** reinziehen (bis zu 20): sie werden nacheinander in eine Listenansicht mit Status pro Datei konvertiert, und die erfolgreichen lädst du als **eine ZIP** herunter (jede Datei trägt ihre eigene ID durch die ganze Kette, Vertauschung ist damit ausgeschlossen); fehlgeschlagene Dateien bleiben klar markiert und wandern nie in den Download. Bei einer einzelnen Datei erscheint weiterhin die gewohnte Ergebnisleiste mit Download, **„Ordner öffnen"**, Kopieren und „Neue Datei", die beim Scrollen sichtbar bleibt.
2. **Prompt-Trainer**: bewertet die **Struktur** eines Prompts mit nachvollziehbaren Regeln (bewusst **keine KI**), zeigt, wie viele der geprüften Kriterien dein Prompt erfüllt („X von 7 Kriterien erfüllt"; gezählt wird nur, was auf deinen Prompt zutrifft), mit Ampel, erklärt jeden Check mit ✗/✓-Beispielen und baut eine modellspezifische Vorlage mit [Platzhalter-Fragen], die du selbst ausfüllst — genau dabei lernst du. Mit Demo-Buttons, Live-Analyse beim Tippen und Lernschleife.
3. **Statistik**: bearbeitete Dateien, analysierte Prompts, gesparte Tokens (mit Seiten- und Kostenschätzung, klar als Schätzung gekennzeichnet), deine häufigsten Schwachstellen (wie oft jedes Kriterium gerissen wurde), Meilensteine, Format-Nutzung — und ein Bereich „Ausgaben verwalten" zum Aufräumen.

**Sprachen:** Oberfläche auf Deutsch und Englisch (Umschalter oben rechts, die Wahl wird gespeichert); auch die Ergebnis-Hinweise des Konverters und alle Fehlermeldungen folgen der gewählten Sprache. Der Prompt-Trainer erkennt zusätzlich die Sprache deines Prompts und baut die Vorlage in dieser Sprache.

**Design:** Zwei Themes, umschaltbar oben rechts (☀/☾): hell (Editorial-Stil, Standard) und dunkel („Neon-Werkstatt"). Die Wahl wird gespeichert.

## Installation (Windows)

Voraussetzung: [Python 3.12](https://www.python.org/downloads/) (bei der Installation „Add python.exe to PATH" anhaken). Entwickelt und getestet mit Python 3.12; ältere Versionen sind ungetestet.

**Am einfachsten:** Doppelklick auf `install.bat` (einmalig).
**Manuell:** `pip install -r requirements.txt`

> **Hinweis zur Windows-Sicherheitswarnung:** Beim ersten Start von `install.bat`/`start.bat` kann Windows „Unbekannter Herausgeber" anzeigen. Das ist bei unsignierten Skripten normal — über „Weitere Informationen" → „Trotzdem ausführen" geht es weiter. Der komplette Quellcode liegt offen in diesem Ordner.

### OCR für Bild-PDFs (optional)

Für PDFs, die nur aus gescannten Seiten bestehen, braucht es einmalig zwei Zusatzprogramme:

```powershell
winget install -e --id UB-Mannheim.TesseractOCR
winget install -e --id oschwartz10612.Poppler
```

Prisma findet beide automatisch an den üblichen Installationsorten — kein PATH-Eintrag nötig. **Text-PDFs und alle anderen Formate funktionieren auch ohne OCR.** Fehlt eine Abhängigkeit, stürzt nichts ab: Die App liefert statt eines Ergebnisses eine verständliche Schritt-für-Schritt-Anleitung, was zu installieren ist.

## Start

Doppelklick auf `start.bat` (der Browser öffnet sich automatisch) oder:

```powershell
python app.py
```

Dann **http://localhost:8770** öffnen — beenden mit `Strg + C`. Der Server läuft auf Port 8770 und bindet ausschließlich auf 127.0.0.1; er ist aus dem Netzwerk nicht erreichbar.

Falls sich die Statistik einmal seltsam verhält: Prisma mit der Umgebungsvariable `PRISMA_DEBUG=1` starten — dann entsteht neben der App ein Diagnose-Log (`stats_debug.log`), das jeden Stats-Lese- und Schreibzugriff festhält.

## Wo landen die Ergebnisse?

Jedes Konvertierungs-Ergebnis wird im Projektordner unter `outputs/` abgelegt — der Button **„Ordner öffnen"** (in der Ergebnisleiste und im Statistik-Tab unter „Ausgaben verwalten") führt direkt dorthin.

Der Browser-Download („Datei herunterladen") ist eine **zusätzliche Kopie**; wohin sie gespeichert wird, bestimmt eine **Browser-Einstellung**, nicht Prisma — eine lokale Web-App kann den Download-Ort nicht wählen. Wenn du einen festen Zielordner willst: in den Browser-Einstellungen den Download-Speicherort festlegen bzw. „Vor jedem Download fragen" ausschalten.

## Datenschutz

- **Keine externen Verbindungen.** Auch die Schriften sind lokal gebündelt (`static/fonts/`). Die Test-Suite `tests/test_privacy.py` lädt die Seite mit komplett blockiertem Internet und schlägt fehl, sobald irgendein externer Request auch nur versucht wird.
- **Statistik speichert ausschließlich Zahlen** — lokal in `stats.json`, keine Inhalte, keine Dateinamen, keine Prompt-Texte. Im Statistik-Tab jederzeit auf Null zurücksetzbar.
- **Konvertierungsergebnisse** liegen unverschlüsselt im Ordner `outputs/` (damit Downloads auch später funktionieren). Über „Ausgaben verwalten" im Statistik-Tab lassen sie sich jederzeit komplett löschen. Hochgeladene Originale werden sofort nach der Konvertierung gelöscht; Reste eines harten Absturzes räumt der nächste Serverstart weg.

## Ehrlichkeit & bekannte Grenzen

Der Anspruch ist nicht „es geht nie etwas verloren", sondern: **es geht nichts stillschweigend verloren.** Was nicht extrahiert werden kann, wird im Ergebnis-Hinweis benannt. Prinzipbedingt: Word-Fußnoten/Textboxen und eingebettete PDF-Bilder werden nicht übernommen (die App sagt es dazu), Excel-Formeln ohne gespeichertes Ergebnis erscheinen als Formel-String, und die Token-Zählung ist ohne `tiktoken` eine deklarierte Schätzung.

## Tests

211 Tests in 16 Suiten, die ihre Testdateien selbst konstruieren (zusätzlich benötigt: `reportlab`, `playwright`). `test_block1`, `test_block2` und `test_blockI_batch` nutzen den Code direkt bzw. den Flask-Testclient; für alle anderen muss der Server laufen (`python app.py`):

```powershell
python tests/test_block1.py        # Konverter-Kern (PDF/DOCX/XLSX/PPTX)
python tests/test_block2.py        # Prompt-Trainer (Regeln + Kalibrierung)
python tests/smoke_http.py         # Endpunkt-Smoke inkl. Statistik
python tests/test_block3_dom.py    # Browser-UI (Sprache, Demos, Lernschleife)
python tests/test_blockB_dom.py    # Themes + WCAG-Kontraste
python tests/test_blockC_stats.py  # Statistik-Backend (nur Zahlen, atomar, Origin)
python tests/test_blockC_dom.py    # Statistik-UI + Zählregeln + Ausgaben-Verwaltung
python tests/test_blockD_dom.py    # Layout-Stabilität + Konverter-Reset
python tests/test_privacy.py       # Null externe Verbindungen (Beweis)
python tests/test_blockG_dom.py    # Ergebnisleiste + Ordner-öffnen-Button
python tests/test_blockH_dom.py    # Fehleranzeige (klare Meldung + ausklappbares Detail)
python tests/test_pdf_robust.py    # PDF-Robustheit (Bounding-Box-Artefakte, seitenweise OCR)
python tests/test_pdf_struct.py    # PDF-Struktur (Überschriften/Tabellen im Markdown)
python tests/test_blockI_batch.py  # Batch-Konvertierung (eigene IDs, keine Vertauschung, ZIP, Limit)
python tests/test_notes_lang.py    # Lokalisierte Konverter-Hinweise (de/en, ui_lang-Kette)
python tests/test_errors_lang.py   # Lokalisierte Fehlermeldungen (de/en, Sprachkanäle)
```

## Lizenz

Der Code steht unter **MIT** — siehe [LICENSE](LICENSE). Die gebündelten Schriften (Space Grotesk, JetBrains Mono, Fraunces) stehen unter der **SIL Open Font License**; die Lizenztexte liegen in `static/fonts/`.
