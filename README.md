# Prisma

**Deutsch** | [English below](#english)

Prisma ist eine lokale Browser-Oberfläche mit drei Werkzeugen für die
Arbeit mit KI-Modellen: einem **Datei-Konverter**, der PDF, Word, Excel,
CSV, TXT und PowerPoint in token-effiziente Formate wandelt, einem
**Prompt-Trainer**, der die Struktur deiner Prompts regelbasiert bewertet
und dir beim Lernen hilft, und einer **Statistik**, die deine Ersparnis
zeigt. **Alles läuft komplett lokal auf deinem Rechner** — es gibt keine
einzige externe Verbindung, keine Datei und kein Prompt verlässt deinen PC.
Ein eigener Test (`tests/test_privacy.py`) beweist das bei jedem Testlauf.

| Helles Theme (Standard) | Dunkles Theme |
|---|---|
| ![Konverter, helles Theme](docs/konverter-hell.png) | ![Konverter, dunkles Theme](docs/konverter-dunkel.png) |

| Prompt-Trainer | Statistik |
|---|---|
| ![Prompt-Trainer](docs/trainer-hell.png) | ![Statistik](docs/statistik-hell.png) |

## Was die Werkzeuge können

1. **Datei-Konverter**: Fließtext wird Markdown, Tabellen werden CSV —
   verpackt passend für dein KI-Modell (Claude → XML-Tags, GPT →
   Markdown-Abschnitte, Gemini → klare Gliederung). Bild-PDFs und
   gemischte PDFs (Text + Scans) werden automatisch per **OCR** erkannt,
   seitenweise, damit nichts verloren geht.
2. **Prompt-Trainer**: bewertet die **Struktur** eines Prompts mit
   nachvollziehbaren Regeln (bewusst **keine KI**), zeigt einen Score
   (0-100) mit Ampel, erklärt jeden Check mit ✗/✓-Beispielen und baut eine
   modellspezifische Vorlage mit [Platzhalter-Fragen], die du selbst
   ausfüllst — genau dabei lernst du. Mit Demo-Buttons und Lernschleife.
3. **Statistik**: bearbeitete Dateien, analysierte Prompts, gesparte
   Tokens (mit Seiten- und Kostenschätzung, klar als Schätzung
   gekennzeichnet), Score-Verteilung, Meilensteine, Format-Nutzung —
   und ein Bereich „Ausgaben verwalten" zum Aufräumen.

**Sprachen:** Oberfläche auf Deutsch und Englisch (Umschalter oben rechts,
die Wahl wird gespeichert). Der Prompt-Trainer erkennt zusätzlich die
Sprache deines Prompts und baut die Vorlage in dieser Sprache.

**Design:** Zwei Themes, umschaltbar oben rechts (☀/☾): hell
(Editorial-Stil, Standard) und dunkel („Neon-Werkstatt"). Die Wahl wird
gespeichert.

## Installation (Windows)

Voraussetzung: [Python 3.9+](https://www.python.org/downloads/)
(bei der Installation „Add python.exe to PATH" anhaken).

**Am einfachsten:** Doppelklick auf `install.bat` (einmalig).
**Manuell:** `pip install -r requirements.txt`

> **Hinweis zur Windows-Sicherheitswarnung:** Beim ersten Start von
> `install.bat`/`start.bat` kann Windows „Unbekannter Herausgeber"
> anzeigen. Das ist bei unsignierten Skripten normal — über „Weitere
> Informationen" → „Trotzdem ausführen" geht es weiter. Der komplette
> Quellcode liegt offen in diesem Ordner.

### OCR für Bild-PDFs (optional)

Für PDFs, die nur aus gescannten Seiten bestehen, braucht es einmalig
zwei Zusatzprogramme:

```powershell
winget install -e --id UB-Mannheim.TesseractOCR
winget install -e --id oschwartz10612.Poppler
```

Prisma findet beide automatisch an den üblichen Installationsorten — kein
PATH-Eintrag nötig. **Text-PDFs und alle anderen Formate funktionieren
auch ohne OCR.** Fehlt eine Abhängigkeit, stürzt nichts ab: Die App
liefert statt eines Ergebnisses eine verständliche Schritt-für-Schritt-
Anleitung, was zu installieren ist.

## Start

Doppelklick auf `start.bat` (der Browser öffnet sich automatisch) oder:

```powershell
python app.py
```

Dann **http://localhost:8770** öffnen — beenden mit `Strg + C`.
Der Server läuft auf Port 8770 und bindet ausschließlich auf 127.0.0.1;
er ist aus dem Netzwerk nicht erreichbar.

## Datenschutz

- **Keine externen Verbindungen.** Auch die Schriften sind lokal
  gebündelt (`static/fonts/`). Die Test-Suite `tests/test_privacy.py`
  lädt die Seite mit komplett blockiertem Internet und schlägt fehl,
  sobald irgendein externer Request auch nur versucht wird.
- **Statistik speichert ausschließlich Zahlen** — lokal in `stats.json`,
  keine Inhalte, keine Dateinamen, keine Prompt-Texte. Im Statistik-Tab
  jederzeit auf Null zurücksetzbar.
- **Konvertierungsergebnisse** liegen unverschlüsselt im Ordner
  `outputs/` (damit Downloads auch später funktionieren). Über
  „Ausgaben verwalten" im Statistik-Tab lassen sie sich jederzeit
  komplett löschen. Hochgeladene Originale werden sofort nach der
  Konvertierung gelöscht; Reste eines harten Absturzes räumt der
  nächste Serverstart weg.

## Ehrlichkeit & bekannte Grenzen

Der Anspruch ist nicht „es geht nie etwas verloren", sondern: **es geht
nichts stillschweigend verloren.** Was nicht extrahiert werden kann, wird
im Ergebnis-Hinweis benannt. Prinzipbedingt: Word-Fußnoten/Textboxen und
eingebettete PDF-Bilder werden nicht übernommen (die App sagt es dazu),
Excel-Formeln ohne gespeichertes Ergebnis erscheinen als Formel-String,
die Konverter-Hinweise sind bewusst noch einsprachig Deutsch, und die
Token-Zählung ist ohne `tiktoken` eine deklarierte Schätzung.

## Tests

106 Tests in 9 Suiten, die ihre Testdateien selbst konstruieren
(zusätzlich benötigt: `reportlab`, `playwright`). Für alle außer den
ersten beiden muss der Server laufen (`python app.py`):

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
```

## Lizenz

Der Code steht unter **MIT** — siehe [LICENSE](LICENSE).
Die gebündelten Schriften (Space Grotesk, JetBrains Mono, Fraunces)
stehen unter der **SIL Open Font License**; die Lizenztexte liegen in
`static/fonts/`.

---

<a name="english"></a>

# Prisma — English

Prisma is a local browser UI with three tools for working with AI models:
a **file converter** that turns PDF, Word, Excel, CSV, TXT and PowerPoint
into token-efficient formats, a **prompt trainer** that rates the
structure of your prompts with transparent rules and helps you learn, and
a **statistics** tab that shows your savings. **Everything runs entirely
on your machine** — there is not a single external connection; no file
and no prompt ever leaves your PC. A dedicated test
(`tests/test_privacy.py`) proves this on every test run.

## What the tools do

1. **File Converter**: prose becomes Markdown, tables become CSV —
   wrapped to fit your AI model (Claude → XML tags, GPT → Markdown
   sections, Gemini → clear structure). Image PDFs and mixed PDFs
   (text + scans) are detected automatically and processed with **OCR**,
   page by page, so nothing gets lost.
2. **Prompt Trainer**: rates the **structure** of a prompt with
   transparent rules (deliberately **no AI**), shows a score (0-100) with
   a traffic light, explains every check with ✗/✓ examples and builds a
   model-specific template with [placeholder questions] you fill in
   yourself — that's exactly how you learn.
3. **Statistics**: files processed, prompts analyzed, tokens saved (with
   page and cost estimates, clearly labelled as estimates), score
   distribution, milestones, format usage — plus a "Manage outputs"
   section for cleaning up.

**Languages:** German and English UI (toggle in the top right, the choice
is remembered). The Prompt Trainer additionally detects your prompt's
language and builds the template in that language.

**Design:** two themes, toggled in the top right (☀/☾): light (editorial
style, default) and dark ("neon workshop"). Your choice is remembered.

## Installation (Windows)

Requires [Python 3.9+](https://www.python.org/downloads/)
(check "Add python.exe to PATH" during setup).

**Easiest:** double-click `install.bat` (once).
**Manually:** `pip install -r requirements.txt`

> **Note on the Windows security warning:** on first launch of
> `install.bat`/`start.bat`, Windows may show "Unknown publisher". This
> is normal for unsigned scripts — click "More info" → "Run anyway".
> The full source code is right here in this folder.

### OCR for image PDFs (optional)

PDFs consisting only of scanned pages need two extra programs (one-time):

```powershell
winget install -e --id UB-Mannheim.TesseractOCR
winget install -e --id oschwartz10612.Poppler
```

Prisma finds both automatically in the usual install locations — no PATH
entry needed. **Text PDFs and all other formats work without OCR.** If a
dependency is missing, nothing crashes: instead of a result, the app
returns clear step-by-step instructions on what to install.

## Start

Double-click `start.bat` (the browser opens automatically) or:

```powershell
python app.py
```

Then open **http://localhost:8770** — quit with `Ctrl + C`.
The server runs on port 8770 and binds to 127.0.0.1 only; it is not
reachable from the network.

## Privacy

- **No external connections.** Even the fonts are bundled locally
  (`static/fonts/`). The test suite `tests/test_privacy.py` loads the
  page with the internet fully blocked and fails if any external request
  is even attempted.
- **Statistics store nothing but numbers** — locally in `stats.json`:
  no content, no file names, no prompt texts. Resettable to zero in the
  stats tab at any time.
- **Conversion results** are stored unencrypted in the `outputs/` folder
  (so downloads keep working later). The "Manage outputs" section in the
  stats tab deletes them all at any time. Uploaded originals are removed
  immediately after conversion; leftovers from a hard crash are cleaned
  up on the next server start.

## Honesty & known limitations

The promise is not "nothing is ever lost" but: **nothing is lost
silently.** Whatever cannot be extracted is named in the result note.
Inherent limits: Word footnotes/text boxes and embedded PDF images are
not carried over (the app tells you), Excel formulas without a cached
result appear as the formula string, the converter's result notes are
deliberately still German-only, and token counting without `tiktoken`
is a declared estimate.

## Tests

106 tests in 9 suites that construct their own test files (additionally
required: `reportlab`, `playwright`). All except the first two need the
server running (`python app.py`) — see the German section for the list.

## License

The code is **MIT**-licensed — see [LICENSE](LICENSE).
The bundled fonts (Space Grotesk, JetBrains Mono, Fraunces) are licensed
under the **SIL Open Font License**; the license texts live in
`static/fonts/`.
