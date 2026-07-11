"""
converter.py
------------
Kern-Logik des Token-Konverters.

Aufgabe: Nimmt eine Datei (PDF, DOCX, XLSX, CSV, TXT, PPTX) und wandelt sie
in das token-effizienteste Format um:
  - Fliesstext / Dokumente  -> Markdown
  - Tabellen / Daten        -> CSV

Zaehlt die Tokens der Roh-Extraktion vs. der optimierten Version, damit du
die Ersparnis siehst. Fuegt auf Wunsch XML-Tags im Anthropic-Stil hinzu.

Diese Datei hat KEINE Server-Logik - sie ist reine Konvertierung, damit du
sie auch einzeln in anderen Projekten wiederverwenden kannst.
"""

import io
import os
import csv
import re
import glob

# ---------------------------------------------------------------------------
# WINDOWS-PFADE FUER OCR-PROGRAMME AUTOMATISCH FINDEN
# ---------------------------------------------------------------------------
# Tesseract und poppler tragen sich unter Windows nicht immer in den PATH ein.
# Damit OCR trotzdem laeuft, suchen wir sie an den ueblichen Installationsorten.
# So muss der Nutzer am PATH nichts aendern.

def _find_tesseract():
    """Sucht die tesseract.exe an den ueblichen Windows-Orten. None falls nicht da."""
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
        os.path.expanduser(r"~\AppData\Local\Tesseract-OCR\tesseract.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None  # nicht gefunden -> pytesseract versucht dann den PATH


def _find_poppler_bin():
    """Sucht den poppler 'bin'-Ordner (mit pdftoppm.exe). None falls nicht da."""
    # Typische Installationsmuster von winget/manuell. '*' faengt die Version.
    patterns = [
        r"C:\Program Files\poppler*\Library\bin",
        r"C:\Program Files\poppler*\bin",
        r"C:\poppler*\Library\bin",
        r"C:\poppler*\bin",
        os.path.expanduser(r"~\AppData\Local\Microsoft\WinGet\Packages\oschwartz10612.Poppler*\**\bin"),
        os.path.expanduser(r"~\AppData\Local\Programs\poppler*\Library\bin"),
    ]
    for pat in patterns:
        matches = glob.glob(pat, recursive=True)
        for m in matches:
            # nur akzeptieren, wenn pdftoppm.exe wirklich drin liegt
            if os.path.isfile(os.path.join(m, "pdftoppm.exe")):
                return m
    return None  # nicht gefunden -> pdf2image versucht dann den PATH


# Einmal beim Import ermitteln
_TESSERACT_PATH = _find_tesseract()
_POPPLER_PATH = _find_poppler_bin()


# ---------------------------------------------------------------------------
# TOKEN-ZAEHLUNG
# ---------------------------------------------------------------------------
# Wir versuchen tiktoken (exakte Zaehlung, wie GPT/Claude sie intern nutzen).
# Falls tiktoken nicht verfuegbar ist (z.B. kein Internet beim ersten Start),
# fallen wir automatisch auf die bewaehrte Schaetzung ~4 Zeichen = 1 Token
# zurueck. Diese Regel wird in der Forschung fuer Englisch genutzt; fuer
# Deutsch liegt sie leicht daneben, ist aber fuer Vergleiche voellig ok.

_TIKTOKEN_ENC = None
_TIKTOKEN_TRIED = False


def _get_encoder():
    """Laedt tiktoken einmalig; gibt None zurueck falls nicht moeglich."""
    global _TIKTOKEN_ENC, _TIKTOKEN_TRIED
    if _TIKTOKEN_TRIED:
        return _TIKTOKEN_ENC
    _TIKTOKEN_TRIED = True
    try:
        import tiktoken
        _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _TIKTOKEN_ENC = None
    return _TIKTOKEN_ENC


def count_tokens(text: str) -> dict:
    """
    Zaehlt Tokens. Gibt ein dict zurueck mit:
      - count:  Anzahl Tokens
      - method: 'tiktoken' (exakt) oder 'estimate' (Schaetzung)
    """
    if not text:
        return {"count": 0, "method": "exact"}
    enc = _get_encoder()
    if enc is not None:
        return {"count": len(enc.encode(text)), "method": "tiktoken"}
    # Fallback: ~4 Zeichen pro Token
    return {"count": max(1, round(len(text) / 4)), "method": "estimate"}


# ---------------------------------------------------------------------------
# HILFSFUNKTIONEN
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Entfernt typischen Extraktions-Muell, der nur Tokens frisst."""
    if not text:
        return ""
    # Windows-Zeilenumbrueche vereinheitlichen
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Mehr als 2 Leerzeilen -> genau 2 (Absatztrennung bleibt erhalten)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trailing-Whitespace pro Zeile entfernen
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # Fuehrende/abschliessende Leerzeilen weg
    return text.strip()


def _rows_to_csv(rows) -> str:
    """Wandelt eine Liste von Zeilen (Listen) in einen CSV-String um."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        # None-Zellen zu leerem String machen
        writer.writerow(["" if c is None else str(c).strip() for c in row])
    return buf.getvalue().strip()


# ---------------------------------------------------------------------------
# EXTRAKTOREN PRO DATEITYP
# ---------------------------------------------------------------------------
# Jeder Extraktor gibt ein dict zurueck:
#   raw_text:     was rohe Extraktion liefern wuerde (fuer Token-Vergleich)
#   converted:    optimierter Inhalt (Markdown oder CSV)
#   target_format: 'markdown' oder 'csv'
#   note:         kurze Erklaerung fuer die Anzeige

def _strip_repeating_headers_footers(pages_lines):
    """
    Entfernt Zeilen, die auf vielen Seiten identisch wiederkehren
    (typische Kopf-/Fusszeilen wie 'Seite X', Firmennamen, Copyright).
    Das ist echter, entfernbarer Token-Muell in mehrseitigen PDFs.

    pages_lines: Liste von Seiten, jede Seite eine Liste von Zeilen.
    Rueckgabe: (bereinigter_text, anzahl_entfernter_zeilen)
    """
    from collections import Counter

    n_pages = len(pages_lines)
    if n_pages < 2:
        # Bei 1 Seite gibt es keine "Wiederholung" -> nichts entfernen
        flat = "\n".join("\n".join(p) for p in pages_lines)
        return flat, 0

    # Zeilen zaehlen, die auf mehreren Seiten exakt gleich vorkommen.
    # Wir normalisieren Ziffern zu '#', damit 'Seite 1' und 'Seite 2'
    # als dasselbe Muster erkannt werden.
    def normalize(line):
        return re.sub(r"\d+", "#", line.strip())

    # Kopf-/Fusszeilen sind typischerweise KURZ. Lange Zeilen sind Inhalt
    # und duerfen niemals entfernt werden, auch wenn sie zufaellig doppelt
    # vorkommen. Grenze: max. 80 Zeichen.
    MAX_HEADER_LEN = 80

    counter = Counter()
    for page in pages_lines:
        # pro Seite nur eindeutige Zeilen zaehlen (sonst zaehlt Wiederholung
        # innerhalb einer Seite mit)
        seen = set()
        for line in page:
            if len(line.strip()) > MAX_HEADER_LEN:
                continue  # zu lang -> sicher Inhalt, nicht zaehlen
            norm = normalize(line)
            if norm and norm not in seen:
                seen.add(norm)
                counter[norm] += 1

    # Ein Muster gilt nur dann als Kopf/Fusszeile, wenn es auf FAST ALLEN
    # Seiten vorkommt (>=80%). Das schuetzt vor Fehlalarmen.
    threshold = max(2, n_pages * 0.8)
    junk_patterns = {norm for norm, cnt in counter.items() if cnt >= threshold}

    removed = 0
    cleaned_pages = []
    for page in pages_lines:
        kept = []
        for line in page:
            # nur kurze Zeilen ueberhaupt als Kandidat betrachten
            if len(line.strip()) <= MAX_HEADER_LEN and normalize(line) in junk_patterns:
                removed += 1
                continue
            kept.append(line)
        cleaned_pages.append(kept)

    flat = "\n".join("\n".join(p) for p in cleaned_pages)
    return flat, removed


def _ocr_pdf(path: str):
    """
    Wandelt eine Bild-PDF per OCR (Texterkennung) in Text um.
    Wird nur aufgerufen, wenn pdfplumber keinen Text findet.

    Rueckgabe: (text, fehler)
      - Bei Erfolg: (erkannter_text, None)
      - Bei fehlendem Tesseract o.ae.: ("", verstaendliche_fehlermeldung)

    Braucht das Programm 'Tesseract' auf dem Rechner sowie die Python-Pakete
    pdf2image und pytesseract. Fehlt etwas, geben wir eine klare Anleitung
    zurueck statt abzustuerzen.
    """
    # Pakete pruefen
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        return "", (
            "Fuer Bild-PDFs wird OCR benoetigt. Bitte installiere die Pakete:\n"
            "  pip install pdf2image pytesseract\n"
            "und das Programm Tesseract (siehe ANLEITUNG.md, Abschnitt OCR)."
        )

    # Falls wir Tesseract am Standardpfad gefunden haben, pytesseract dorthin zeigen.
    # (Damit ist kein PATH-Eintrag noetig.)
    if _TESSERACT_PATH:
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_PATH

    # Tesseract-Programm pruefen (pytesseract ruft es intern auf)
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return "", (
            "Das Programm 'Tesseract' wurde nicht gefunden.\n"
            "Windows: Installer von https://github.com/UB-Mannheim/tesseract/wiki\n"
            "oder per winget: winget install -e --id UB-Mannheim.TesseractOCR\n"
            "Nach der Installation Tool neu starten. Details in ANLEITUNG.md."
        )

    # PDF Seite fuer Seite in Bilder wandeln und erkennen.
    # 150 dpi ist ein guter Kompromiss aus Genauigkeit und Tempo.
    # poppler_path nur mitgeben, wenn wir ihn gefunden haben.
    convert_kwargs = {"dpi": 150}
    if _POPPLER_PATH:
        convert_kwargs["poppler_path"] = _POPPLER_PATH
    try:
        images = convert_from_path(path, **convert_kwargs)
    except Exception as e:
        # Meist fehlt 'poppler' (wird von pdf2image gebraucht)
        return "", (
            f"PDF konnte nicht in Bilder gewandelt werden ({e}).\n"
            "Windows braucht dafuer 'poppler'.\n"
            "Per winget: winget install -e --id oschwartz10612.Poppler\n"
            "Anleitung in ANLEITUNG.md."
        )

    parts = []
    # Sowohl Deutsch als auch Englisch versuchen (viele Dokumente sind gemischt)
    lang = "deu+eng"
    for img in images:
        try:
            txt = pytesseract.image_to_string(img, lang=lang)
        except Exception:
            # Falls das deutsche Sprachpaket fehlt, nur Englisch
            txt = pytesseract.image_to_string(img)
        parts.append(txt)

    return "\n\n".join(parts), None


def extract_pdf(path: str) -> dict:
    """PDF: Text -> Markdown. Wenn ueberwiegend Tabellen -> CSV.
    Wenn kein Text da ist (Bild-PDF), automatisch OCR."""
    import pdfplumber

    pages_lines = []
    all_text_parts = []
    all_tables = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            all_text_parts.append(txt)
            pages_lines.append(txt.split("\n"))
            for table in page.extract_tables():
                if table:
                    all_tables.append(table)

    # raw_text = ungefilterte Extraktion (fuer Token-Vergleich "vorher")
    raw_text = "\n".join(all_text_parts)
    text_len = len(raw_text.strip())

    # --- Bild-PDF-Erkennung ---
    # Wenn ueber alle Seiten praktisch kein Text da ist, ist es eine Bild-PDF
    # (gescannt oder aus Bildern gebaut). Dann greift OCR.
    if text_len < 50:
        ocr_text, ocr_error = _ocr_pdf(path)
        if ocr_error:
            # OCR nicht moeglich -> ehrlich melden statt leeres Ergebnis
            return {
                "raw_text": "",
                "converted": "",
                "target_format": "markdown",
                "note": "BILD-PDF ERKANNT (kein Text enthalten). " + ocr_error,
            }
        md = _clean_text(ocr_text)
        # Bei OCR ist "vorher" der Bild-Fall: Wir schaetzen, was das Modell
        # als Bilder kosten wuerde (grob ~1500 Tokens pro Seite), damit die
        # Ersparnis realistisch die Umwandlung Bild->Text abbildet.
        n_pages = len(pages_lines)
        return {
            "raw_text": ocr_text,
            "converted": md,
            "target_format": "markdown",
            "note": (f"BILD-PDF per OCR erkannt ({n_pages} Seiten, Text war als Bild "
                     f"eingebettet). Als Bild kostet so ein PDF ein Vielfaches an Tokens "
                     f"- als Text ist es jetzt schlank lesbar."),
            "was_ocr": True,
            "n_pages": n_pages,
        }

    # bereinigt: wiederkehrende Kopf-/Fusszeilen raus
    deduped_text, removed_lines = _strip_repeating_headers_footers(pages_lines)
    # Grobe Heuristik: viele Tabellenzeilen + wenig Fliesstext -> Tabellen-PDF
    table_cells = sum(len(r) for t in all_tables for r in t)

    if all_tables and table_cells > 0 and text_len < table_cells * 6:
        # Als Tabellen-Dokument behandeln -> CSV
        # Alle Tabellen untereinander, durch Leerzeile getrennt
        csv_blocks = [_rows_to_csv(t) for t in all_tables]
        converted = "\n\n".join(csv_blocks)
        return {
            "raw_text": raw_text,
            "converted": converted,
            "target_format": "csv",
            "note": "PDF enthaelt ueberwiegend Tabellen -> als CSV konvertiert (token-effizienteste Form fuer Daten).",
        }

    # Standardfall: Fliesstext -> Markdown (kopf-/fusszeilenbereinigt)
    md = _clean_text(deduped_text)
    if removed_lines > 0:
        note = (f"PDF-Fliesstext als Markdown bereinigt. "
                f"{removed_lines} wiederkehrende Kopf-/Fusszeilen entfernt (Token-Muell).")
    else:
        note = "PDF-Fliesstext extrahiert und als sauberes Markdown bereinigt."
    return {
        "raw_text": raw_text,
        "converted": md,
        "target_format": "markdown",
        "note": note,
    }


def extract_docx(path: str) -> dict:
    """Word: Ueberschriften -> Markdown-Headings, Tabellen -> Markdown-Tabellen."""
    import docx

    doc = docx.Document(path)
    md_parts = []
    raw_parts = []

    for para in doc.paragraphs:
        text = para.text.strip()
        raw_parts.append(para.text)
        if not text:
            continue
        style = (para.style.name or "").lower()
        if style.startswith("heading 1") or style == "title":
            md_parts.append(f"# {text}")
        elif style.startswith("heading 2"):
            md_parts.append(f"## {text}")
        elif style.startswith("heading 3"):
            md_parts.append(f"### {text}")
        elif style.startswith("list"):
            md_parts.append(f"- {text}")
        else:
            md_parts.append(text)

    # Tabellen als Markdown-Tabellen anhaengen.
    # Wichtig: die Tabellenzeilen muessen DIREKT untereinander stehen
    # (ein Block mit einfachen Zeilenumbruechen), sonst ist die Markdown-
    # Tabelle ungueltig. Deshalb bauen wir jede Tabelle als einen String.
    for table in doc.tables:
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        raw_parts.append("\n".join("\t".join(r) for r in rows))
        if not rows:
            continue
        header = rows[0]
        table_lines = []
        table_lines.append("| " + " | ".join(header) + " |")
        table_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        for r in rows[1:]:
            # auf Header-Breite normalisieren
            r = (r + [""] * len(header))[: len(header)]
            table_lines.append("| " + " | ".join(r) + " |")
        md_parts.append("\n".join(table_lines))

    converted = _clean_text("\n\n".join(md_parts))
    raw_text = "\n".join(raw_parts)
    return {
        "raw_text": raw_text,
        "converted": converted,
        "target_format": "markdown",
        "note": "Word-Struktur (Ueberschriften, Listen, Tabellen) in natives Markdown uebersetzt.",
    }


def extract_xlsx(path: str) -> dict:
    """Excel: jedes Blatt -> CSV. Daten gehoeren in CSV (am wenigsten Tokens)."""
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    blocks = []
    raw_parts = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            # komplett leere Zeilen ueberspringen
            if row is None or all(c is None for c in row):
                continue
            rows.append(list(row))
        if not rows:
            continue
        csv_text = _rows_to_csv(rows)
        raw_parts.append(csv_text)
        # Blattname als Kommentarzeile, damit man mehrere Blaetter unterscheidet
        if len(wb.worksheets) > 1:
            blocks.append(f"# Blatt: {ws.title}\n{csv_text}")
        else:
            blocks.append(csv_text)

    converted = "\n\n".join(blocks).strip()
    raw_text = "\n\n".join(raw_parts)
    return {
        "raw_text": raw_text,
        "converted": converted,
        "target_format": "csv",
        "note": "Excel-Daten als CSV exportiert - das token-effizienteste Format fuer Tabellen (bis zu 3x weniger als JSON/HTML).",
    }


def extract_csv(path: str) -> dict:
    """CSV ist schon optimal - nur einlesen und leicht saeubern."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    cleaned = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    return {
        "raw_text": content,
        "converted": cleaned,
        "target_format": "csv",
        "note": "CSV ist bereits das effizienteste Datenformat - nur Zeilenumbrueche vereinheitlicht.",
    }


def extract_txt(path: str) -> dict:
    """Reiner Text -> als Markdown bereinigen."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    cleaned = _clean_text(content)
    return {
        "raw_text": content,
        "converted": cleaned,
        "target_format": "markdown",
        "note": "Textdatei bereinigt (ueberfluessige Leerzeilen und Whitespace entfernt).",
    }


def extract_pptx(path: str) -> dict:
    """PowerPoint via MarkItDown -> Markdown."""
    from markitdown import MarkItDown
    md = MarkItDown()
    result = md.convert(path)
    text = result.text_content or ""
    cleaned = _clean_text(text)
    return {
        "raw_text": text,
        "converted": cleaned,
        "target_format": "markdown",
        "note": "PowerPoint-Folien in Markdown umgewandelt (Text pro Folie extrahiert).",
    }


# ---------------------------------------------------------------------------
# MODELLSPEZIFISCHES WRAPPING
# ---------------------------------------------------------------------------

def wrap_for_model(content: str, source_name: str, fmt: str, model: str) -> str:
    """
    Verpackt den Inhalt so, wie es das jeweilige Ziel-Modell am liebsten mag:
      claude -> XML-Tags (offizielle Anthropic-Empfehlung)
      gpt    -> Markdown-Ueberschrift + Triple-Quote-Delimiter (OpenAI-Stil)
      gemini -> schlichte Markdown-Struktur mit Label
      none   -> unveraendert
    Alle Varianten kosten nur wenige Tokens und helfen dem Modell, das
    Dokument sauber von der eigentlichen Aufgabe zu trennen.
    """
    safe_name = os.path.basename(source_name)

    if model == "claude":
        return (f'<document source="{safe_name}" format="{fmt}">\n'
                f"{content}\n"
                f"</document>")

    if model == "gpt":
        return (f'## Dokument: {safe_name} (Format: {fmt})\n'
                f'"""\n{content}\n"""')

    if model == "gemini":
        return (f'**Dokument: {safe_name}** (Format: {fmt})\n\n'
                f'{content}\n\n'
                f'--- Ende des Dokuments ---')

    return content  # "none" oder unbekannt -> pur


def wrap_xml(content: str, source_name: str, fmt: str) -> str:
    """Rueckwaerts-kompatibler Alias (alte Aufrufe -> Claude-Stil)."""
    return wrap_for_model(content, source_name, fmt, "claude")


# ---------------------------------------------------------------------------
# HAUPT-DISPATCHER
# ---------------------------------------------------------------------------

_EXTRACTORS = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".xlsx": extract_xlsx,
    ".xlsm": extract_xlsx,
    ".csv": extract_csv,
    ".txt": extract_txt,
    ".md": extract_txt,
    ".pptx": extract_pptx,
}

SUPPORTED_EXTENSIONS = sorted(_EXTRACTORS.keys())


def convert_file(path: str, add_xml: bool = False, target_model: str = None,
                 original_name: str = None) -> dict:
    """
    Haupteinstieg. Nimmt einen Dateipfad, gibt ein Ergebnis-dict zurueck.
    target_model:  'claude' | 'gpt' | 'gemini' | 'none'
                   (steuert das modellspezifische Wrapping)
    add_xml:       alter Parameter, bleibt aus Kompatibilitaet -
                   True wirkt wie target_model='claude'.
    original_name: echter Dateiname fuers Wrapping (falls der Pfad nur ein
                   temporaerer Name ist, z.B. beim Server-Upload).
      tokens_saved:  Differenz
      percent_saved: Ersparnis in Prozent
      token_method:  'tiktoken' oder 'estimate'
    """
    ext = os.path.splitext(path)[1].lower()
    extractor = _EXTRACTORS.get(ext)
    if extractor is None:
        return {
            "ok": False,
            "error": f"Dateityp '{ext}' wird nicht unterstuetzt. "
                     f"Moeglich: {', '.join(SUPPORTED_EXTENSIONS)}",
        }

    try:
        result = extractor(path)
    except Exception as e:
        return {"ok": False, "error": f"Fehler beim Lesen der Datei: {e}"}

    source_name = os.path.basename(original_name) if original_name else os.path.basename(path)
    converted = result["converted"]
    fmt = result["target_format"]

    # --- Ehrliche Token-Messung ---
    # "vorher": was du zahlst, wenn du die rohe Extraktion ungefiltert ans
    #           LLM gibst (inkl. Extraktions-Muell, doppelte Umbrueche etc.)
    # "nachher": der bereinigte, optimierte Inhalt OHNE XML-Deko.
    after_clean = count_tokens(converted)

    # Sonderfall Bild-PDF (OCR): Hier waere der ehrliche "Vorher"-Wert NICHT
    # der OCR-Text, sondern was das LLM zahlen muesste, um die Seiten als
    # BILDER zu verarbeiten. Hochaufloesende Bildseiten kosten grob ~1500
    # Tokens/Seite. Wir weisen das transparent als Schaetzung aus.
    is_ocr = result.get("was_ocr", False)
    if is_ocr:
        n_pages = result.get("n_pages", 1)
        IMG_TOKENS_PER_PAGE = 1500  # grobe, dokumentierte Groessenordnung
        before_count = n_pages * IMG_TOKENS_PER_PAGE
        before_method = "estimate"  # Bild-Kosten sind immer eine Schaetzung
    else:
        before = count_tokens(result["raw_text"])
        before_count = before["count"]
        before_method = before["method"]

    saved = before_count - after_clean["count"]
    percent = (saved / before_count * 100) if before_count > 0 else 0.0

    # Ziel-Modell bestimmen (add_xml=True bleibt als Alias fuer Claude)
    if target_model is None:
        target_model = "claude" if add_xml else "none"
    if target_model not in ("claude", "gpt", "gemini", "none"):
        target_model = "none"

    # Finale Ausgabe (ggf. modellspezifisch verpackt)
    output_text = converted
    wrap_overhead = 0
    if target_model != "none":
        output_text = wrap_for_model(converted, source_name, fmt, target_model)
        wrap_overhead = count_tokens(output_text)["count"] - after_clean["count"]

    out_ext = ".csv" if fmt == "csv" else ".md"

    return {
        "ok": True,
        "source_name": source_name,
        "target_format": fmt,
        "note": result["note"],
        "output_text": output_text,
        "output_ext": out_ext,
        "tokens_before": before_count,
        "tokens_after": after_clean["count"],   # bereinigt, ohne Wrapping
        "tokens_saved": saved,
        "percent_saved": round(percent, 1),
        "token_method": before_method,
        "was_ocr": is_ocr,
        "target_model": target_model,
        "wrap_overhead": wrap_overhead,          # was das Wrapping extra kostet
        # alte Feldnamen fuer Kompatibilitaet:
        "xml_wrapped": target_model != "none",
        "xml_overhead": wrap_overhead,
        "tokens_final": count_tokens(output_text)["count"],  # inkl. Wrapping
    }
