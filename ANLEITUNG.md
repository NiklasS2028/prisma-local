# KI-Werkstatt — Anleitung

Zwei lokale Werkzeuge in einem, erreichbar über Tabs:

1. **Datei-Konverter**: Datei rein (PDF, Word, Excel …), token-effizientes
   Format raus (Markdown oder CSV), passend verpackt für dein KI-Modell
   (Claude → XML-Tags, GPT → Markdown-Delimiter, Gemini → Markdown-Struktur).
2. **Prompt-Trainer**: Prompt einfügen, ehrliche Struktur-Bewertung
   (rot/gelb/grün) mit Erklärungen und Beispielen bekommen — plus eine
   Vorlage im richtigen Format für dein Modell. **Lern-Werkzeug, keine KI:**
   Es prüft mit klaren Regeln und zeigt dir, was fehlt. Die [Fragen in
   Klammern] der Vorlage beantwortest du selbst — genau dabei lernst du.

Läuft komplett auf deinem Rechner — kein Prompt und keine Datei geht ins Internet.

---

## Was du brauchst

Python 3.9+ (hast du schon, weil Claude Code läuft).

## Einmalige Einrichtung

Öffne PowerShell im Ordner `token-konverter` und installiere die Pakete:

```powershell
pip install flask pdfplumber python-docx openpyxl markitdown tiktoken pdf2image pytesseract
```

`tiktoken` ist optional, aber empfohlen: Damit wird die Token-Zahl **exakt**
gezählt (wie GPT/Claude es intern tun). Ohne tiktoken nutzt das Tool
automatisch eine Schätzung (~4 Zeichen pro Token).

### OCR für Bild-PDFs (optional, aber sehr nützlich)

Manche PDFs enthalten keinen echten Text, sondern nur **Bilder** der Seiten
(z. B. Präsentationen, die als Bild exportiert wurden, oder Scans). Solche
Dateien sind riesig und für ein LLM extrem teuer, weil jede Seite als Bild
verarbeitet werden muss. Das Tool erkennt das automatisch und wandelt die
Bilder per **OCR** (Texterkennung) in schlanken Text um.

Dafür brauchst du zwei Zusatzprogramme (einmalig):

**1. Tesseract** (die eigentliche Texterkennung):
- Windows-Installer: https://github.com/UB-Mannheim/tesseract/wiki
- Bei der Installation die deutschen + englischen Sprachdaten mit auswählen.
- Merke dir den Installationspfad (meist `C:\Program Files\Tesseract-OCR`).

**2. poppler** (wandelt PDF-Seiten in Bilder um):
- Windows-Download: https://github.com/oschwartz10612/poppler-windows/releases
- ZIP entpacken, z. B. nach `C:\poppler`.

**Danach die beiden zum PATH hinzufügen** (damit Windows sie findet):
- Windows-Suche → „Umgebungsvariablen bearbeiten" → „Umgebungsvariablen"
- Bei „Path" (unter Benutzervariablen) → „Bearbeiten" → „Neu" und diese
  zwei Pfade eintragen:
  - `C:\Program Files\Tesseract-OCR`
  - `C:\poppler\Library\bin` (oder wo die `pdftoppm.exe` liegt)
- PowerShell einmal schließen und neu öffnen, dann `python app.py` neu starten.

Wenn OCR nicht eingerichtet ist, funktioniert das Tool trotzdem — es zeigt bei
Bild-PDFs dann nur einen Hinweis statt eines Ergebnisses. Alle anderen
Dateitypen (Text-PDF, Word, Excel …) brauchen kein OCR.

## Starten

```powershell
python app.py
```

Dann im Browser öffnen: **http://localhost:8770**

Beenden: im PowerShell-Fenster `Strg + C`.

---

## Benutzen

1. Datei in die Fläche ziehen (oder klicken und auswählen).
2. Optional den Schalter **„XML-Tags fürs LLM"** anmachen.
3. Ergebnis ansehen: Wie viele Tokens gespart wurden, Vorschau, Notiz.
4. **Herunterladen** oder **In Zwischenablage** kopieren.

---

## Was passiert unter der Haube (kurz)

| Datei-Typ        | Wird zu   | Warum                                                    |
|------------------|-----------|----------------------------------------------------------|
| PDF (Fliesstext) | Markdown  | Kopf-/Fusszeilen raus, Struktur billig kodiert           |
| PDF (Tabellen)   | CSV       | Daten gehören in CSV — bis zu 3× weniger Tokens als HTML  |
| PDF (nur Bilder) | Markdown  | OCR wandelt Bild-Seiten in schlanken Text (spart massiv) |
| Word (.docx)     | Markdown  | Überschriften/Listen/Tabellen → natives Markdown         |
| Excel (.xlsx)    | CSV       | effizientestes Tabellenformat                            |
| CSV / TXT        | bereinigt | ist schon gut, nur aufgeräumt                            |
| PowerPoint       | Markdown  | Text pro Folie extrahiert                                |

**Ehrliche Anzeige:** Bei schon-sauberen Dateien (z. B. eine kurze Word-Datei
ohne Layout-Müll) kann die optimierte Version *leicht mehr* Tokens haben, weil
Markdown-Struktur (`#`, `|`) selbst ein paar Tokens kostet. Das Tool zeigt das
ehrlich an (gelbe Zahl), statt eine Ersparnis vorzutäuschen. Der große Gewinn
kommt bei mehrseitigen PDFs mit wiederkehrenden Kopf-/Fusszeilen.

**XML-Tags:** Kosten ein paar Tokens extra, helfen dem Modell aber, das
Dokument sauber von deiner Aufgabe zu trennen. Anthropic empfiehlt sie für
Claude; GPT und Gemini verstehen sie auch.

---

## Erweitern (Ideen für später)

- Mehrere Dateien auf einmal (Batch)
- Direkt-Button „an Claude Code übergeben"
- Eigene Regeln pro Firma/Projekt (z. B. bestimmte Fusszeilen immer entfernen)
