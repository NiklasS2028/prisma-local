# KI-Werkstatt

**Deutsch** | [English below](#english)

Zwei lokale KI-Hilfswerkzeuge in einer Browser-Oberfläche — läuft komplett
auf deinem Rechner (`localhost:8770`), keine Datei und kein Prompt verlässt
deinen PC.

1. **Datei-Konverter**: Wandelt PDF, Word, Excel, CSV, TXT und PowerPoint in
   token-effiziente Formate um (Fließtext → Markdown, Tabellen → CSV) und
   verpackt sie passend für dein KI-Modell (Claude → XML-Tags, GPT →
   Markdown-Abschnitte, Gemini → klare Gliederung). Bild-PDFs und gemischte
   PDFs (Text + Scans) werden automatisch per **OCR** erkannt — seitenweise,
   damit nichts verloren geht.
2. **Prompt-Trainer**: Lern-Werkzeug für Einsteiger. Bewertet die
   **Struktur** eines Prompts regelbasiert (bewusst **keine KI**), zeigt
   einen Score (0-100) mit Ampel, erklärt jeden Check mit ✗/✓-Beispielen
   und baut eine modellspezifische Vorlage mit [Platzhalter-Fragen], die du
   selbst ausfüllst — genau dabei lernst du. Mit Demo-Buttons
   (schwach/mittel/stark) und Lernschleife („In Eingabe übernehmen" →
   ausfüllen → erneut analysieren).

**Sprachen:** Die Oberfläche gibt es auf Deutsch und Englisch (Umschalter
oben rechts, die Wahl wird gespeichert). Der Prompt-Trainer erkennt
zusätzlich die Sprache deines Prompts und baut die Vorlage in dieser
Sprache — unabhängig von der UI-Sprache.

## Installation (Windows)

Voraussetzung: [Python 3.9+](https://www.python.org/downloads/)
(bei der Installation „Add python.exe to PATH" anhaken).

**Am einfachsten:** Doppelklick auf `install.bat` (einmalig), danach
Doppelklick auf `start.bat` — der Browser öffnet sich automatisch.

> **Hinweis zur Windows-Sicherheitswarnung:** Beim ersten Start von
> `install.bat`/`start.bat` kann Windows „Unbekannter Herausgeber" oder
> „Der Computer wurde durch Windows geschützt" anzeigen. Das ist bei
> unsignierten Skripten normal — über „Weitere Informationen" →
> „Trotzdem ausführen" geht es weiter. Der komplette Quellcode liegt offen
> in diesem Ordner.

**Manuell:**

```powershell
pip install -r requirements.txt
python app.py
```

Dann im Browser öffnen: **http://localhost:8770** — Beenden mit `Strg + C`.

### OCR für Bild-PDFs (optional, aber sehr nützlich)

Manche PDFs enthalten keinen echten Text, sondern nur Bilder der Seiten
(Scans, als Bild exportierte Präsentationen). Das Tool erkennt das
automatisch — auch bei gemischten PDFs mit Text- und Bildseiten — und
wandelt die Bildseiten per OCR in Text um. Dafür braucht es zwei
Zusatzprogramme (einmalig, am einfachsten per winget):

```powershell
winget install -e --id UB-Mannheim.TesseractOCR
winget install -e --id oschwartz10612.Poppler
```

Das Tool findet beide automatisch an den üblichen Installationsorten —
kein PATH-Eintrag nötig. Ohne OCR funktioniert alles andere trotzdem; bei
Bild-PDFs erscheint dann ein Hinweis mit Anleitung statt eines Ergebnisses.

## Ehrlichkeit & bekannte Grenzen

Der Anspruch des Konverters ist nicht „es geht nie etwas verloren"
(das kann kein Konverter garantieren), sondern: **es geht nichts
stillschweigend verloren.** Was nicht extrahiert werden kann, wird im
Ergebnis-Hinweis benannt. Prinzipbedingte Grenzen:

- **Word (.docx):** Fußnoten, Textboxen und Kopf-/Fußzeilen kann die
  verwendete Bibliothek nicht extrahieren. Der Ergebnis-Hinweis sagt das dazu.
- **PDF:** Eingebettete Bilder und Diagramme werden nicht übernommen (nur
  der Text). Das Tool zählt sie und weist darauf hin.
- **Excel:** Formeln ohne gespeichertes Ergebnis (z. B. aus
  Skript-Pipelines) werden als Formel-String ausgegeben statt als leere
  Zelle — die Datei einmal in Excel öffnen und speichern liefert die Werte.
- **Konverter-Hinweise nur Deutsch:** Die Ergebnis-Hinweise des Konverters
  (nicht des Prompt-Trainers) sind bewusst noch einsprachig Deutsch —
  ein bekannter Kompromiss dieser Version.
- **Token-Zählung:** Mit `tiktoken` exakt, sonst automatisch als Schätzung
  (~4 Zeichen/Token) — die Anzeige deklariert, welche Methode lief. Die
  „Vorher"-Kosten von Bildseiten sind immer eine ausgewiesene Schätzung
  (~1500 Tokens/Seite).

Der Prompt-Trainer nutzt **keine KI**: Er prüft mit nachvollziehbaren
Regeln (Wortgrenzen-Matching) und kann den Inhalt nicht „verstehen" —
das steht auch so in der Oberfläche.

## Tests

Der Ordner `tests/` enthält drei Suiten, die ihre Testdateien selbst
konstruieren (benötigt zusätzlich `reportlab`, `python-pptx`, `playwright`):

```powershell
python tests/test_block1.py    # Konverter (PDF/DOCX/XLSX/PPTX-Fixes)
python tests/test_block2.py    # Prompt-Trainer (Regeln + Kalibrierung)
python tests/test_block3_dom.py  # Browser-UI (erst "python app.py" starten)
```

## Lizenz

MIT — siehe [LICENSE](LICENSE).

---

<a name="english"></a>

# KI-Werkstatt (AI Workshop) — English

Two local AI helper tools in one browser UI — runs entirely on your
machine (`localhost:8770`); no file and no prompt ever leaves your PC.

1. **File Converter**: Converts PDF, Word, Excel, CSV, TXT and PowerPoint
   into token-efficient formats (prose → Markdown, tables → CSV) and wraps
   them to fit your AI model (Claude → XML tags, GPT → Markdown sections,
   Gemini → clear structure). Image PDFs and mixed PDFs (text + scans) are
   detected automatically and processed with **OCR** — page by page, so
   nothing gets lost.
2. **Prompt Trainer**: A learning tool for beginners. Rates the
   **structure** of a prompt with transparent rules (deliberately **no
   AI**), shows a score (0-100) with a traffic light, explains every check
   with ✗/✓ examples and builds a model-specific template with
   [placeholder questions] you fill in yourself — that's exactly how you
   learn. Includes demo buttons (weak/medium/strong) and a learning loop
   ("Use as input" → fill in → re-analyze).

**Languages:** The UI is available in German and English (toggle in the
top right; the choice is remembered). The Prompt Trainer additionally
detects the language of your prompt and builds the template in that
language — independent of the UI language.

## Installation (Windows)

Requires [Python 3.9+](https://www.python.org/downloads/)
(check "Add python.exe to PATH" during setup).

**Easiest:** Double-click `install.bat` (once), then double-click
`start.bat` — the browser opens automatically.

> **Note on the Windows security warning:** On first launch of
> `install.bat`/`start.bat`, Windows may show "Unknown publisher" or
> "Windows protected your PC". This is normal for unsigned scripts —
> click "More info" → "Run anyway". The full source code is right here
> in this folder.

**Manually:**

```powershell
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:8770** in your browser — quit with `Ctrl + C`.

### OCR for image PDFs (optional, but very useful)

Some PDFs contain no real text, just images of the pages (scans,
presentations exported as images). The tool detects this automatically —
including mixed PDFs with both text and image pages — and converts the
image pages to text via OCR. This needs two extra programs (one-time,
easiest via winget):

```powershell
winget install -e --id UB-Mannheim.TesseractOCR
winget install -e --id oschwartz10612.Poppler
```

The tool finds both automatically in the usual install locations — no
PATH entry needed. Everything else works without OCR; for image PDFs
you'll get instructions instead of a result.

## Honesty & known limitations

The converter's promise is not "nothing is ever lost" (no converter can
guarantee that), but: **nothing is lost silently.** Whatever cannot be
extracted is named in the result note. Inherent limitations:

- **Word (.docx):** Footnotes, text boxes and headers/footers cannot be
  extracted by the underlying library. The result note says so.
- **PDF:** Embedded images and charts are not carried over (text only).
  The tool counts them and tells you.
- **Excel:** Formulas without a cached result (e.g. from script
  pipelines) are output as the formula string instead of an empty cell —
  opening and saving the file once in Excel yields the values.
- **Converter notes are German only:** The converter's result notes (not
  the Prompt Trainer) are deliberately still German-only — a known
  trade-off of this version.
- **Token counting:** Exact with `tiktoken`, otherwise an automatic
  estimate (~4 chars/token) — the UI declares which method was used. The
  "before" cost of image pages is always a declared estimate
  (~1500 tokens/page).

The Prompt Trainer uses **no AI**: it checks with transparent,
word-boundary-based rules and cannot "understand" content — the UI says
so, too.

## Tests

The `tests/` folder contains three suites that construct their own test
files (additionally require `reportlab`, `python-pptx`, `playwright`):

```powershell
python tests/test_block1.py    # converter (PDF/DOCX/XLSX/PPTX fixes)
python tests/test_block2.py    # prompt trainer (rules + calibration)
python tests/test_block3_dom.py  # browser UI (start "python app.py" first)
```

## License

MIT — see [LICENSE](LICENSE).
