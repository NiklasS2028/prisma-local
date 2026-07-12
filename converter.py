"""
converter.py
------------
Kern-Logik des Prisma-Datei-Konverters.

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

# Ueberschriften-Muster, die NIEMALS als Kopf-/Fusszeile entfernt werden
# duerfen - auch wenn sie sich (nach Ziffern-Normalisierung) auf jeder
# Seite "wiederholen". 'Kapitel 1' bis 'Kapitel 5' sind Struktur, kein Muell.
_PROTECTED = re.compile(
    r"^\s*(kapitel|abschnitt|artikel|teil|anhang|"
    r"chapter|section|article|part|appendix)\b",
    re.IGNORECASE,
)


def _removed_note(removed_lines, max_show=4):
    """Formatiert die entfernten Kopf-/Fusszeilen fuer den Hinweistext,
    damit der Nutzer Fehlgriffe sofort sehen kann (Transparenz)."""
    if not removed_lines:
        return ""
    shown = ", ".join(f"'{l}'" for l in removed_lines[:max_show])
    more = ""
    if len(removed_lines) > max_show:
        more = f" (+{len(removed_lines) - max_show} weitere Muster)"
    return f" Entfernt: {shown}{more}."


def _strip_repeating_headers_footers(pages_lines):
    """
    Entfernt Zeilen, die auf vielen Seiten identisch wiederkehren
    (typische Kopf-/Fusszeilen wie 'Seite X', Firmennamen, Copyright).
    Das ist echter, entfernbarer Token-Muell in mehrseitigen PDFs.

    Sicherheitsregeln gegen Inhaltsverlust:
      - Nur die ersten/letzten EDGE Zeilen einer Seite sind Kandidaten
        (Kopf-/Fusszeilen stehen am Seitenrand, Inhalt in der Mitte).
      - Ueberschriften-Muster (_PROTECTED, z.B. 'Kapitel 3') sind tabu.
      - Ziffern werden nur bei kurzen Zeilen (<=40 Zeichen) normalisiert,
        damit 'Seite 1'/'Seite 2' als ein Muster gelten - laengere Zeilen
        muessen exakt uebereinstimmen.

    pages_lines: Liste von Seiten, jede Seite eine Liste von Zeilen.
    Rueckgabe: (bereinigter_text, anzahl_entfernter_zeilen, entfernte_muster)
    """
    from collections import Counter

    n_pages = len(pages_lines)
    if n_pages < 2:
        # Bei 1 Seite gibt es keine "Wiederholung" -> nichts entfernen
        flat = "\n".join("\n".join(p) for p in pages_lines)
        return flat, 0, []

    EDGE = 2            # nur die aeussersten 2 Zeilen oben/unten pruefen
    MAX_HEADER_LEN = 80  # laengere Zeilen sind sicher Inhalt

    def normalize(line):
        s = line.strip()
        if len(s) <= 40:
            return re.sub(r"\d+", "#", s)
        return s

    def is_candidate(idx, page_len, line):
        s = line.strip()
        if not s or len(s) > MAX_HEADER_LEN:
            return False
        if _PROTECTED.match(s):
            return False
        return idx < EDGE or idx >= page_len - EDGE

    counter = Counter()
    for page in pages_lines:
        # pro Seite nur eindeutige Muster zaehlen (sonst zaehlt Wiederholung
        # innerhalb einer Seite mit)
        seen = set()
        for idx, line in enumerate(page):
            if not is_candidate(idx, len(page), line):
                continue
            norm = normalize(line)
            if norm and norm not in seen:
                seen.add(norm)
                counter[norm] += 1

    # Ein Muster gilt nur dann als Kopf/Fusszeile, wenn es auf FAST ALLEN
    # Seiten vorkommt (>=80%). Das schuetzt vor Fehlalarmen.
    threshold = max(2, n_pages * 0.8)
    junk_patterns = {norm for norm, cnt in counter.items() if cnt >= threshold}

    removed = 0
    removed_lines = []
    cleaned_pages = []
    for page in pages_lines:
        kept = []
        for idx, line in enumerate(page):
            if is_candidate(idx, len(page), line) and normalize(line) in junk_patterns:
                removed += 1
                stripped = line.strip()
                if stripped not in removed_lines:
                    removed_lines.append(stripped)
                continue
            kept.append(line)
        cleaned_pages.append(kept)

    flat = "\n".join("\n".join(p) for p in cleaned_pages)
    return flat, removed, removed_lines


def _ocr_pages(path: str, page_numbers):
    """
    Wandelt AUSGEWAEHLTE Seiten eines PDFs per OCR (Texterkennung) in Text um.
    page_numbers: Liste von 1-basierten Seitennummern.

    Rueckgabe: (texte, fehler)
      - texte:  dict {seitennummer: erkannter_text} - kann bei einem Fehler
                auch teilweise gefuellt sein (bereits erkannte Seiten).
      - fehler: None bei Erfolg, sonst eine verstaendliche Fehlermeldung.

    Braucht das Programm 'Tesseract' auf dem Rechner sowie die Python-Pakete
    pdf2image und pytesseract. Fehlt etwas, geben wir eine klare Anleitung
    zurueck statt abzustuerzen.
    """
    # Pakete pruefen
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        return {}, (
            "Fuer Bild-Seiten wird OCR benoetigt. Bitte installiere die Pakete:\n"
            "  pip install pdf2image pytesseract\n"
            "und das Programm Tesseract (siehe README, Abschnitt OCR)."
        )

    # Falls wir Tesseract am Standardpfad gefunden haben, pytesseract dorthin zeigen.
    # (Damit ist kein PATH-Eintrag noetig.)
    if _TESSERACT_PATH:
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_PATH

    # Tesseract-Programm pruefen (pytesseract ruft es intern auf)
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return {}, (
            "Das Programm 'Tesseract' wurde nicht gefunden.\n"
            "Windows: Installer von https://github.com/UB-Mannheim/tesseract/wiki\n"
            "oder per winget: winget install -e --id UB-Mannheim.TesseractOCR\n"
            "Nach der Installation Tool neu starten. Details im README."
        )

    # Nur die angefragten Seiten in Bilder wandeln und erkennen.
    # 150 dpi ist ein guter Kompromiss aus Genauigkeit und Tempo.
    # poppler_path nur mitgeben, wenn wir ihn gefunden haben.
    convert_kwargs = {"dpi": 150}
    if _POPPLER_PATH:
        convert_kwargs["poppler_path"] = _POPPLER_PATH

    texts = {}
    for n in page_numbers:
        try:
            images = convert_from_path(path, first_page=n, last_page=n,
                                        **convert_kwargs)
        except Exception as e:
            # Meist fehlt 'poppler' (wird von pdf2image gebraucht)
            return texts, (
                f"PDF-Seite {n} konnte nicht in ein Bild gewandelt werden ({e}).\n"
                "Windows braucht dafuer 'poppler'.\n"
                "Per winget: winget install -e --id oschwartz10612.Poppler\n"
                "Anleitung im README."
            )
        if not images:
            texts[n] = ""
            continue
        # Sowohl Deutsch als auch Englisch versuchen (viele Dokumente sind gemischt)
        try:
            txt = pytesseract.image_to_string(images[0], lang="deu+eng")
        except Exception:
            # Falls das deutsche Sprachpaket fehlt, nur Englisch
            txt = pytesseract.image_to_string(images[0])
        texts[n] = txt

    return texts, None


class UnreadablePdfError(ValueError):
    """PDF, bei der KEINE Seite lesbar war (auch nicht per OCR).
    Die Exception-Meldung ist die verstaendliche Meldung fuers UI;
    'detail' traegt den rohen technischen Grund (z.B. die pdfminer-
    Exception der ersten kaputten Seite) fuer die Fehlersuche."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


# Ab wie vielen Zeichen extrahierten Texts gilt eine PDF-Seite als "Textseite"?
# Darunter ist es praktisch sicher eine Bild-/Scan-Seite (oder leer).
_PAGE_TEXT_MIN = 15

# Grobe, dokumentierte Groessenordnung: was eine PDF-Seite als BILD an
# Tokens kosten wuerde, wenn man sie direkt ans Modell gibt.
_IMG_TOKENS_PER_PAGE = 1500


def extract_pdf(path: str) -> dict:
    """PDF: Text -> Markdown. Wenn ueberwiegend Tabellen -> CSV.
    Seiten ohne Text (Scans/Bilder) werden EINZELN per OCR erkannt -
    auch in gemischten PDFs (z.B. Text-Deckblatt + gescannter Anhang)."""
    import pdfplumber

    page_texts = []       # extrahierter Text pro Seite (Index 0 = Seite 1)
    extra_texts = []      # Text AUSSERHALB von Tabellen pro Seite (fuer CSV-Zweig)
    all_tables = []
    n_images = 0
    broken_pages = []     # Seiten, deren Extraktion eine Exception warf
    first_error = ""      # technischer Grund der ersten kaputten Seite
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            # JEDE Seite in ihrem eigenen try/except: eine einzelne kaputte
            # Seite (z.B. pdfminer-ValueError) darf nicht mehr die ganze
            # Datei mitreissen. Kaputte Seiten bleiben ohne Text und werden
            # dadurch unten wie Bildseiten behandelt (OCR-Rettung).
            try:
                txt = page.extract_text() or ""
                page_images = len(page.images or [])
                tables_on_page = page.find_tables()
                page_tables = []
                for t in tables_on_page:
                    data = t.extract()
                    if data:
                        page_tables.append(data)
                # Begleittext ausserhalb der Tabellen-Bereiche merken, damit
                # der CSV-Zweig ihn nicht stillschweigend verwirft.
                # strict=False: reale PDFs enthalten Tabellen, deren Box durch
                # Rundungsartefakte um Bruchteile eines Punkts ueber den
                # Seitenrand ragt - pdfplumber (0.11.x) wirft dann per Default
                # ValueError statt still zu beschneiden.
                if tables_on_page:
                    region = page
                    for t in tables_on_page:
                        region = region.outside_bbox(t.bbox, strict=False)
                    extra = region.extract_text() or ""
                else:
                    extra = txt
            except Exception as e:
                broken_pages.append(page_no)
                if not first_error:
                    first_error = f"Seite {page_no}: {e}"
                txt, extra, page_tables, page_images = "", "", [], 0
            page_texts.append(txt)
            extra_texts.append(extra)
            all_tables.extend(page_tables)
            n_images += page_images

    n_pages = len(page_texts)
    # raw_text = ungefilterte Extraktion (fuer Token-Vergleich "vorher")
    raw_text = "\n".join(page_texts)
    text_len = len(raw_text.strip())

    # --- Bild-Seiten-Erkennung: PRO SEITE statt global ---
    # Eine Seite mit praktisch keinem Text ist eine Bild-/Scan-Seite.
    image_pages = [i for i, t in enumerate(page_texts, start=1)
                   if len(t.strip()) < _PAGE_TEXT_MIN]
    text_pages = [i for i in range(1, n_pages + 1) if i not in image_pages]

    # Hinweis auf eingebettete Bilder in Text-PDFs (prinzipbedingt nicht
    # extrahierbar - aber wir sagen es, statt zu schweigen).
    image_note = ""
    if n_images > 0 and text_pages:
        image_note = (f" Hinweis: {n_images} eingebettete(s) Bild(er)/Grafik(en) "
                      f"wurden nicht übernommen (nur Text ist extrahierbar).")

    # ---- Fall 1: reine Bild-PDF (alle Seiten ohne Text) -> komplette OCR ----
    if image_pages and not text_pages:
        ocr_texts, ocr_error = _ocr_pages(path, image_pages)
        if ocr_error and not any(t.strip() for t in ocr_texts.values()):
            if broken_pages and len(broken_pages) == n_pages:
                # ALLE Seiten warfen Exceptions und OCR konnte nichts retten
                # -> sauberer Fehler (HTTP 400) ueber den bestehenden Pfad,
                # mit verstaendlicher Meldung statt roher pdfminer-Exception.
                raise UnreadablePdfError(
                    f"Keine der {n_pages} Seite(n) dieser PDF konnte gelesen "
                    f"werden - auch nicht per Texterkennung. Die Datei ist "
                    f"vermutlich beschädigt.",
                    detail=" | ".join(x for x in (first_error, ocr_error) if x))
            # OCR nicht moeglich -> ehrlich melden statt leeres Ergebnis
            note = "BILD-PDF ERKANNT (kein Text enthalten). " + ocr_error
            if broken_pages:
                note = (f"ACHTUNG - UNVOLLSTÄNDIG: Seite(n) "
                        f"{', '.join(map(str, broken_pages))} konnte(n) nicht "
                        f"gelesen werden und wurde(n) übersprungen. " + note)
            return {
                "raw_text": "",
                "converted": "",
                "target_format": "markdown",
                "note": note,
            }
        ocr_text = "\n\n".join(ocr_texts.get(i, "") for i in image_pages)
        md = _clean_text(ocr_text)
        rescued_broken = [i for i in broken_pages
                          if ocr_texts.get(i, "").strip()]
        if broken_pages and len(broken_pages) == n_pages:
            # Keine echte Bild-PDF, sondern defekte Seiten - ehrlich benennen.
            note = (f"PDF-Seiten ließen sich nicht direkt lesen und wurden "
                    f"per Texterkennung (OCR) gerettet ({n_pages} Seiten).")
        else:
            note = (f"BILD-PDF per OCR erkannt ({n_pages} Seiten, Text war als Bild "
                    f"eingebettet). Als Bild kostet so ein PDF ein Vielfaches an Tokens "
                    f"- als Text ist es jetzt schlank lesbar.")
            if rescued_broken:
                note += (f" Seite(n) {', '.join(map(str, rescued_broken))} "
                         f"ließ(en) sich nicht direkt lesen und wurde(n) per "
                         f"Texterkennung gerettet.")
        if ocr_error:
            missing = [i for i in image_pages if not ocr_texts.get(i, "").strip()]
            note = (f"ACHTUNG - UNVOLLSTÄNDIG: OCR brach ab, Seite(n) "
                    f"{', '.join(map(str, missing))} fehlen im Ergebnis. "
                    + ocr_error + " | " + note)
        return {
            "raw_text": ocr_text,
            "converted": md,
            "target_format": "markdown",
            "note": note,
            "was_ocr": True,
            "n_pages": n_pages,
            # "Vorher" = was die Seiten als BILDER kosten wuerden (Schaetzung)
            "tokens_before_hint": n_pages * _IMG_TOKENS_PER_PAGE,
        }

    # ---- Fall 2: GEMISCHTES PDF (Textseiten + Bildseiten) ----
    if image_pages and text_pages:
        ocr_texts, ocr_error = _ocr_pages(path, image_pages)
        # Seiten in ORIGINAL-Reihenfolge zusammensetzen:
        # Textseiten direkt, Bildseiten aus der OCR.
        assembled = []
        for i in range(1, n_pages + 1):
            if i in ocr_texts and ocr_texts[i].strip():
                assembled.append(ocr_texts[i])
            elif i in image_pages:
                assembled.append("")  # OCR fehlgeschlagen -> Seite fehlt
            else:
                assembled.append(page_texts[i - 1])

        pages_lines = [t.split("\n") for t in assembled]
        deduped_text, removed, removed_patterns = \
            _strip_repeating_headers_footers(pages_lines)
        md = _clean_text(deduped_text)

        ocr_ok = [i for i in image_pages if ocr_texts.get(i, "").strip()]
        ocr_failed = [i for i in image_pages if i not in ocr_ok]
        # Defekte Seiten (Exception im Extraktions-Loop) von echten
        # Bild-Seiten unterscheiden - die Note soll nicht luegen.
        rescued_broken = [i for i in ocr_ok if i in broken_pages]
        image_ok = [i for i in ocr_ok if i not in broken_pages]
        if ocr_failed:
            failed_image = [i for i in ocr_failed if i not in broken_pages]
            failed_broken = [i for i in ocr_failed if i in broken_pages]
            parts = []
            if failed_image:
                parts.append(f"Seite(n) {', '.join(map(str, failed_image))} "
                             f"sind Bild-Seiten und konnten nicht per OCR "
                             f"gelesen werden.")
            if failed_broken:
                parts.append(f"Seite(n) {', '.join(map(str, failed_broken))} "
                             f"konnte(n) nicht gelesen werden und wurde(n) "
                             f"übersprungen.")
            note = (f"ACHTUNG - UNVOLLSTÄNDIG: Gemischtes PDF, aber "
                    + " ".join(parts) + f" {(ocr_error or '')} "
                    f"Die {len(text_pages)} Textseite(n) sind enthalten.")
        else:
            note = f"Gemischtes PDF: {len(text_pages)} Textseite(n) direkt extrahiert."
            if image_ok:
                note += (f" Seite(n) {', '.join(map(str, image_ok))} per OCR "
                         f"erkannt (waren als Bild eingebettet).")
        if rescued_broken:
            note += (f" Seite(n) {', '.join(map(str, rescued_broken))} "
                     f"ließ(en) sich nicht direkt lesen und wurde(n) per "
                     f"Texterkennung gerettet.")
        if removed > 0:
            note += (f" {removed} wiederkehrende Kopf-/Fusszeilen entfernt."
                     + _removed_note(removed_patterns))

        # Korrigierte Token-Rechnung: Textseiten zaehlen als Text,
        # Bildseiten als geschaetzte Bild-Kosten.
        text_raw = "\n".join(page_texts[i - 1] for i in text_pages)
        before_hint = (count_tokens(text_raw)["count"]
                       + len(image_pages) * _IMG_TOKENS_PER_PAGE)
        return {
            "raw_text": "\n".join(assembled),
            "converted": md,
            "target_format": "markdown",
            "note": note,
            "was_ocr": True,
            "n_pages": n_pages,
            "tokens_before_hint": before_hint,
        }

    # ---- Fall 3: normale Text-PDF ----
    pages_lines = [t.split("\n") for t in page_texts]
    # bereinigt: wiederkehrende Kopf-/Fusszeilen raus
    deduped_text, removed, removed_patterns = \
        _strip_repeating_headers_footers(pages_lines)
    # Grobe Heuristik: viele Tabellenzeilen + wenig Fliesstext -> Tabellen-PDF
    table_cells = sum(len(r) for t in all_tables for r in t)

    if all_tables and table_cells > 0 and text_len < table_cells * 6:
        # Als Tabellen-Dokument behandeln -> CSV
        # Alle Tabellen untereinander, durch Leerzeile getrennt
        csv_blocks = [_rows_to_csv(t) for t in all_tables]
        converted = "\n\n".join(csv_blocks)
        note = ("PDF enthält überwiegend Tabellen -> als CSV konvertiert "
                "(token-effizienteste Form für Daten).")
        # DEFENSIV: Fliesstext ausserhalb der Tabellen darf nicht
        # stillschweigend verloren gehen - er kommt als Begleittext dazu.
        companion = _clean_text("\n".join(extra_texts))
        if companion:
            converted = (f"# Begleittext (ausserhalb der Tabellen):\n"
                         f"{companion}\n\n{converted}")
            note += " Begleittext ausserhalb der Tabellen wurde mit übernommen."
        return {
            "raw_text": raw_text,
            "converted": converted,
            "target_format": "csv",
            "note": note + image_note,
        }

    # Standardfall: Fliesstext -> Markdown (kopf-/fusszeilenbereinigt)
    md = _clean_text(deduped_text)
    if removed > 0:
        note = (f"PDF-Fliesstext als Markdown bereinigt. "
                f"{removed} wiederkehrende Kopf-/Fusszeilen entfernt."
                + _removed_note(removed_patterns))
    else:
        note = "PDF-Fliesstext extrahiert und als sauberes Markdown bereinigt."
    return {
        "raw_text": raw_text,
        "converted": md,
        "target_format": "markdown",
        "note": note + image_note,
    }


def extract_docx(path: str) -> dict:
    """Word: Ueberschriften -> Markdown-Headings, Tabellen -> Markdown-Tabellen.
    Wichtig: Absaetze und Tabellen bleiben in ORIGINAL-Reihenfolge
    (frueher landeten alle Tabellen gesammelt am Ende - Bezuege wie
    'die folgende Tabelle' waren damit kaputt)."""
    import docx
    from docx.oxml.text.paragraph import CT_P
    from docx.oxml.table import CT_Tbl
    from docx.text.paragraph import Paragraph
    from docx.table import Table

    doc = docx.Document(path)
    md_parts = []
    raw_parts = []

    def render_paragraph(para):
        text = para.text.strip()
        raw_parts.append(para.text)
        if not text:
            return
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

    def render_table(table):
        # Wichtig: die Tabellenzeilen muessen DIREKT untereinander stehen
        # (ein Block mit einfachen Zeilenumbruechen), sonst ist die Markdown-
        # Tabelle ungueltig. Deshalb bauen wir jede Tabelle als einen String.
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        raw_parts.append("\n".join("\t".join(r) for r in rows))
        if not rows:
            return
        header = rows[0]
        table_lines = []
        table_lines.append("| " + " | ".join(header) + " |")
        table_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        for r in rows[1:]:
            # auf Header-Breite normalisieren
            r = (r + [""] * len(header))[: len(header)]
            table_lines.append("| " + " | ".join(r) + " |")
        md_parts.append("\n".join(table_lines))

    # Ueber die Body-Kinder in Dokument-Reihenfolge laufen:
    # CT_P = Absatz, CT_Tbl = Tabelle. Andere Elemente (z.B. Abschnitts-
    # eigenschaften) sind kein Inhalt und werden uebersprungen.
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            render_paragraph(Paragraph(child, doc))
        elif isinstance(child, CT_Tbl):
            render_table(Table(child, doc))

    converted = _clean_text("\n\n".join(md_parts))
    raw_text = "\n".join(raw_parts)
    return {
        "raw_text": raw_text,
        "converted": converted,
        "target_format": "markdown",
        "note": ("Word-Struktur (Überschriften, Listen, Tabellen) in natives "
                 "Markdown übersetzt - in Original-Reihenfolge. Hinweis: Fußnoten, "
                 "Textboxen und Kopf-/Fußzeilen kann die Word-Bibliothek "
                 "prinzipbedingt nicht extrahieren."),
    }


def extract_xlsx(path: str) -> dict:
    """Excel: jedes Blatt -> CSV. Daten gehoeren in CSV (am wenigsten Tokens).

    Formel-Zellen: Wir lesen das Workbook DOPPELT - einmal mit data_only=True
    (liefert von Excel zwischengespeicherte Rechenergebnisse) und einmal mit
    data_only=False (liefert die Formel-Strings). Bei programmatisch erzeugten
    Dateien existiert kein Ergebnis-Cache; frueher wurden solche Zellen zu
    LEEREN Feldern. Jetzt geben wir stattdessen die Formel selbst aus."""
    import openpyxl

    wb_val = openpyxl.load_workbook(path, data_only=True, read_only=True)
    wb_formula = openpyxl.load_workbook(path, data_only=False, read_only=True)
    blocks = []
    raw_parts = []
    formula_fallbacks = 0

    for ws_val, ws_formula in zip(wb_val.worksheets, wb_formula.worksheets):
        rows = []
        formula_rows = [list(r) for r in ws_formula.iter_rows(values_only=True)]
        for r_idx, row in enumerate(ws_val.iter_rows(values_only=True)):
            cells = list(row) if row is not None else []
            f_row = formula_rows[r_idx] if r_idx < len(formula_rows) else []
            merged = []
            for c_idx, val in enumerate(cells):
                if val is None and c_idx < len(f_row):
                    f_val = f_row[c_idx]
                    # Zelle hat kein zwischengespeichertes Ergebnis, aber
                    # eine Formel -> Formel-String ausgeben statt Leere.
                    if isinstance(f_val, str) and f_val.startswith("="):
                        merged.append(f_val)
                        formula_fallbacks += 1
                        continue
                merged.append(val)
            # komplett leere Zeilen ueberspringen
            if not merged or all(c is None for c in merged):
                continue
            rows.append(merged)
        if not rows:
            continue
        csv_text = _rows_to_csv(rows)
        raw_parts.append(csv_text)
        # Blattname als Kommentarzeile, damit man mehrere Blaetter unterscheidet
        if len(wb_val.worksheets) > 1:
            blocks.append(f"# Blatt: {ws_val.title}\n{csv_text}")
        else:
            blocks.append(csv_text)

    converted = "\n\n".join(blocks).strip()
    raw_text = "\n\n".join(raw_parts)
    note = ("Excel-Daten als CSV exportiert - das token-effizienteste Format "
            "für Tabellen (bis zu 3x weniger als JSON/HTML).")
    if formula_fallbacks > 0:
        note += (f" Hinweis: {formula_fallbacks} Formel-Zelle(n) ohne "
                 f"gespeichertes Ergebnis - die Formel selbst wurde ausgegeben "
                 f"(Datei einmal in Excel öffnen und speichern liefert die Werte).")
    return {
        "raw_text": raw_text,
        "converted": converted,
        "target_format": "csv",
        "note": note,
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

    note = "PowerPoint-Folien in Markdown umgewandelt (Text pro Folie extrahiert)."
    # Fairness-Hinweis: Sprechernotizen landen mit im Output - das ist je
    # nach Datei gewollt oder ueberraschend, deshalb sagen wir es dazu.
    try:
        from pptx import Presentation
        prs = Presentation(path)
        n_notes = sum(
            1 for slide in prs.slides
            if slide.has_notes_slide
            and (slide.notes_slide.notes_text_frame.text or "").strip()
        )
        if n_notes > 0:
            note += (f" Hinweis: {n_notes} Folie(n) enthalten Sprechernotizen - "
                     f"diese sind im Output mit enthalten.")
    except Exception:
        pass  # Hinweis ist optional - Extraktion selbst haengt nicht daran

    return {
        "raw_text": text,
        "converted": cleaned,
        "target_format": "markdown",
        "note": note,
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
    except UnreadablePdfError as e:
        # Verstaendliche Hauptmeldung; der rohe technische Grund kommt
        # separat mit (fuers UI als ausklappbares Detail, nicht als
        # Hauptfehler).
        return {"ok": False, "error": str(e), "error_detail": e.detail}
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

    # Sonderfall OCR (Bild-PDF oder gemischtes PDF): Hier liefert der
    # Extraktor einen ehrlichen "Vorher"-Wert mit (tokens_before_hint):
    #   - reine Bild-PDF: Seiten x ~1500 Tokens (Kosten als Bild)
    #   - gemischtes PDF: Text der Textseiten + Bildseiten x ~1500 Tokens
    # Bild-Kosten sind immer eine Schaetzung, das weisen wir transparent aus.
    is_ocr = result.get("was_ocr", False)
    if "tokens_before_hint" in result:
        before_count = result["tokens_before_hint"]
        before_method = "estimate"
    elif is_ocr:
        # Fallback fuer Extraktoren ohne Hint (sollte nicht vorkommen)
        n_pages = result.get("n_pages", 1)
        before_count = n_pages * _IMG_TOKENS_PER_PAGE
        before_method = "estimate"
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
