# -*- coding: utf-8 -*-
"""
test_pdf_struct.py (Suite 13)
-----------------------------
Block C (PDF-Struktur): Referenz-Fixtures + Baseline + (ab C2) Struktur-Tests.

C1: Fuenf Referenz-Fixtures werden programmatisch gebaut (reportlab, wie bei
Block B nicht als Binaerdatei eingecheckt). Die SOLL-Struktur steht pro
Fixture als SOLL_*-Konstante im Code und wird von den C2-C4-Tests als
Erwartung benutzt. Der Baseline-Modus zeigt den Ist-Output des heutigen
extract_pdf inkl. tokens_before/after (Messgrundlage fuer C2-C4).

Geometrie-Prinzip der Fixtures:
  - Blocksatz wird ECHT gesetzt: jede Zeile ausser der letzten wird ueber
    Wortabstand exakt auf die Satzspiegelbreite gestreckt (beide Raender
    buendig) - so wie es ein Satzprogramm tut.
  - Flattersatz-Umbrueche, die spaeter verbunden werden sollen, sind
    LAYOUT-ERZWUNGEN: das erste Wort der Folgezeile haette nicht mehr in
    die Zeile gepasst. Das wird im Builder per assert bewiesen, damit die
    Fixtures keine unrealistische Geometrie behaupten.

Aufruf:  python tests/test_pdf_struct.py             (Tests)
         python tests/test_pdf_struct.py --baseline  (Ist-Aufnahme C1)
"""

import os
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# converter.py liegt eine Ebene hoeher
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from converter import convert_file  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
os.makedirs(FIXTURES, exist_ok=True)

# ---------------------------------------------------------------------------
# SATZSPIEGEL (alle Fixtures identisch)
# ---------------------------------------------------------------------------

A4_PT = (595.27, 841.89)
LEFT = 72            # linker Rand
RIGHT = 523          # rechte Kante des Satzspiegels
WIDTH = RIGHT - LEFT  # 451 pt Satzspiegelbreite
BODY_FONT = "Helvetica"
BODY_SIZE = 11
LEADING = 14         # Zeilenabstand INNERHALB eines Absatzes
PARA_GAP = 10        # ZUSAETZLICHER Abstand zwischen Absaetzen (Blockgrenze)


def _w(text, font=BODY_FONT, size=BODY_SIZE):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    return stringWidth(text, font, size)


def _draw_par_justified(c, lines, y, font=BODY_FONT, size=BODY_SIZE,
                        leading=LEADING):
    """Blocksatz-Absatz: jede Zeile ausser der letzten wird ueber den
    Wortabstand exakt auf WIDTH gestreckt (beide Raender buendig)."""
    for i, line in enumerate(lines):
        natural = _w(line, font, size)
        assert natural <= WIDTH + 0.5, f"Zeile breiter als Satzspiegel: {line!r}"
        t = c.beginText(LEFT, y)
        t.setFont(font, size)
        if i < len(lines) - 1 and line.count(" "):
            t.setWordSpace((WIDTH - natural) / line.count(" "))
        t.textOut(line)
        c.drawText(t)
        y -= leading
    return y


def _draw_par_justified_segments(c, seg_lines, y, size=BODY_SIZE,
                                 leading=LEADING):
    """Wie _draw_par_justified, aber jede Zeile ist eine Liste von
    (text, font)-Segmenten - fuer fett gedruckte WOERTER im Fliesstext."""
    for i, segs in enumerate(seg_lines):
        natural = sum(_w(s, f, size) for s, f in segs)
        n_spaces = sum(s.count(" ") for s, _ in segs)
        assert natural <= WIDTH + 0.5, f"Zeile breiter als Satzspiegel: {segs!r}"
        t = c.beginText(LEFT, y)
        if i < len(seg_lines) - 1 and n_spaces:
            t.setWordSpace((WIDTH - natural) / n_spaces)
        for s, f in segs:
            t.setFont(f, size)
            t.textOut(s)
        c.drawText(t)
        y -= leading
    return y


def _draw_par_ragged(c, lines, y, font=BODY_FONT, size=BODY_SIZE,
                     leading=LEADING):
    """Flattersatz-Absatz: Zeilen linksbuendig, rechter Rand frei."""
    c.setFont(font, size)
    for line in lines:
        c.drawString(LEFT, y, line)
        y -= leading
    return y


def _draw_grid_table(c, y_top, rows, col_w=150, row_h=24,
                     font=BODY_FONT, size=10):
    """Tabelle mit sichtbaren Gitterlinien (das, was pdfplumber per
    find_tables sicher erkennt). Gibt die y-Position UNTER der Tabelle
    zurueck."""
    n_r, n_c = len(rows), len(rows[0])
    xs = [LEFT + i * col_w for i in range(n_c + 1)]
    ys = [y_top - i * row_h for i in range(n_r + 1)]
    c.setLineWidth(0.75)
    for yl in ys:
        c.line(xs[0], yl, xs[-1], yl)
    for xl in xs:
        c.line(xl, ys[-1], xl, ys[0])
    c.setFont(font, size)
    for r, row in enumerate(rows):
        for k, cell in enumerate(row):
            c.drawString(xs[k] + 6, ys[r] - row_h + 8, cell)
    return ys[-1]


# ---------------------------------------------------------------------------
# FIXTURE a) BLOCKSATZ MIT SILBENTRENNUNG
# ---------------------------------------------------------------------------
# Zwei Absaetze Blocksatz. Absatz 1 endet in Zeile 1 auf "Silben-" und die
# Folgezeile beginnt klein ("trennung") -> normales Kompositum. Absatz 2
# endet in Zeile 1 auf "E-" und die Folgezeile beginnt gross ("Mail-...")
# -> Bindestrich-Wort, der Bindestrich muss BLEIBEN.

A_PAR1 = [
    "Die automatische Verarbeitung grosser Dokumente verlangt eine saubere Silben-",
    "trennung am Zeilenende, weil zusammengesetzte Woerter sonst mitten im Wort",
    "zerfallen und die Suche nach Begriffen fehlschlaegt.",
]
A_PAR2 = [
    "Fuer Rueckfragen erreichen Sie unser Team jederzeit ueber die zentrale E-",
    "Mail-Adresse des Supports, die im Anhang dieses Schreibens genannt wird.",
]

# SOLL nach Block C: ein Absatz = EINE Zeile, Silbentrennung aufgeloest.
SOLL_A = [
    "Die automatische Verarbeitung grosser Dokumente verlangt eine saubere "
    "Silbentrennung am Zeilenende, weil zusammengesetzte Woerter sonst mitten "
    "im Wort zerfallen und die Suche nach Begriffen fehlschlaegt.",
    "",
    "Fuer Rueckfragen erreichen Sie unser Team jederzeit ueber die zentrale "
    "E-Mail-Adresse des Supports, die im Anhang dieses Schreibens genannt wird.",
]


def build_blocksatz_pdf(path):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=A4_PT)
    y = 780
    y = _draw_par_justified(c, A_PAR1, y)
    y -= PARA_GAP
    y = _draw_par_justified(c, A_PAR2, y)
    c.showPage()
    c.save()


# ---------------------------------------------------------------------------
# FIXTURE b) FLATTERSATZ
# ---------------------------------------------------------------------------
# Absatz 1: der Umbruch nach Zeile 1 ist layout-erzwungen (das folgende Wort
# "auseinandergezogen," haette nicht mehr gepasst - Builder beweist das per
# assert). SOLL: Zeile 1+2 verbunden.
# Absatz 2: Zeile 1 endet WEIT vor dem rechten Rand (~28 % der Breite) und
# ohne Satzschlusszeichen, die Folgezeile beginnt klein. Text-Signale sagen
# "verbinden", die Geometrie sagt "nein". SOLL: Umbruch BLEIBT - das ist der
# bewusst dokumentierte Preis der konservativen Regel (Geometrie UND Text).

B_PAR1 = [
    "Der Flattersatz laeuft am rechten Rand unruhig aus und die Zeilen werden niemals",
    "auseinandergezogen, die Wortabstaende bleiben dadurch immer gleich breit.",
]
B_PAR2 = [
    "Eine auffaellig kurze Zeile",
    "gefolgt von einer laengeren Fortsetzung, die neu ansetzt.",
]

SOLL_B = [
    "Der Flattersatz laeuft am rechten Rand unruhig aus und die Zeilen werden "
    "niemals auseinandergezogen, die Wortabstaende bleiben dadurch immer "
    "gleich breit.",
    "",
    "Eine auffaellig kurze Zeile",
    "gefolgt von einer laengeren Fortsetzung, die neu ansetzt.",
]


def build_flatter_pdf(path):
    from reportlab.pdfgen import canvas
    # Beweis der Fixture-Geometrie: Umbruch in Absatz 1 ist erzwungen,
    # Zeile 1 von Absatz 2 ist eindeutig "kurz".
    first_next_word = B_PAR1[1].split()[0]
    assert _w(B_PAR1[0]) <= WIDTH, "B_PAR1[0] passt nicht in den Satzspiegel"
    assert _w(B_PAR1[0]) + _w(" " + first_next_word) > WIDTH, \
        "Fixture-Fehler: Umbruch in B_PAR1 waere nicht layout-erzwungen"
    assert _w(B_PAR2[0]) < 0.5 * WIDTH, \
        "Fixture-Fehler: B_PAR2[0] soll eine eindeutig kurze Zeile sein"
    c = canvas.Canvas(path, pagesize=A4_PT)
    y = 780
    y = _draw_par_ragged(c, B_PAR1, y)
    y -= PARA_GAP
    y = _draw_par_ragged(c, B_PAR2, y)
    c.showPage()
    c.save()


# ---------------------------------------------------------------------------
# FIXTURE c) ADRESSBLOCK MITTEN IM DOKUMENT
# ---------------------------------------------------------------------------
# Blocksatz-Absatz, dann ein Adressblock aus 4 kurzen Zeilen (ein Block mit
# normalem Zeilenabstand!), dann wieder Blocksatz. SOLL: die Absaetze werden
# je EINE Zeile, die 4 Adresszeilen bleiben EXAKT 4 Zeilen.

C_INTRO = [
    "Wir bedanken uns fuer die gute Zusammenarbeit im vergangenen Geschaeftsjahr",
    "und senden Ihnen die angeforderten Unterlagen mit separater Post zu.",
]
C_ADDRESS = [
    "Beispiel & Partner GmbH",
    "Musterstrasse 12",
    "44135 Dortmund",
    "Deutschland",
]
C_CLOSE = [
    "Bei Fragen zu den Unterlagen stehen wir Ihnen selbstverstaendlich gerne zur",
    "Verfuegung und beraten Sie ausfuehrlich zu allen weiteren Schritten.",
]

SOLL_C = [
    "Wir bedanken uns fuer die gute Zusammenarbeit im vergangenen "
    "Geschaeftsjahr und senden Ihnen die angeforderten Unterlagen mit "
    "separater Post zu.",
    "",
    "Beispiel & Partner GmbH",
    "Musterstrasse 12",
    "44135 Dortmund",
    "Deutschland",
    "",
    "Bei Fragen zu den Unterlagen stehen wir Ihnen selbstverstaendlich gerne "
    "zur Verfuegung und beraten Sie ausfuehrlich zu allen weiteren Schritten.",
]


def build_adresse_pdf(path):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=A4_PT)
    y = 780
    y = _draw_par_justified(c, C_INTRO, y)
    y -= PARA_GAP
    y = _draw_par_ragged(c, C_ADDRESS, y)
    y -= PARA_GAP
    y = _draw_par_justified(c, C_CLOSE, y)
    c.showPage()
    c.save()


# ---------------------------------------------------------------------------
# FIXTURE d) AUFZAEHLUNGSLISTE
# ---------------------------------------------------------------------------
# Einleitungszeile plus vier Listenpunkte (zwei mit Bullet, zwei mit
# Bindestrich). SOLL: jede Zeile bleibt eine eigene Zeile, kein Heading.

D_LINES = [
    "Die folgenden Punkte sind vor der Freigabe zu pruefen:",
    "• Vollstaendigkeit der eingereichten Unterlagen",
    "• Fristen und Zustaendigkeiten der Abteilungen",
    "- Budgetfreigabe durch die Projektleitung",
    "- Abschliessende Dokumentation im Archiv",
]

SOLL_D = list(D_LINES)  # unveraendert, zeilenweise


class FixtureSkipped(Exception):
    """Fixture kann auf dieser Maschine nicht gebaut werden. Die Meldung
    erklaert den Grund; der Runner ueberspringt statt kryptisch zu scheitern."""


def _bullet_font():
    """Das Bullet '•' liegt bei den eingebauten Type1-Fonts auf Code 127
    der reportlab-WinAnsi-Variante - pdfminer dekodiert das zu '(cid:127)'.
    Ein eingebetteter TTF-Font schreibt eine ToUnicode-Map, dann kommt das
    Bullet sauber als '•' wieder heraus (so erzeugen es echte PDFs auch)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    tried = []
    for name, fname in (("FixtureArial", r"C:\Windows\Fonts\arial.ttf"),
                        ("FixtureSegoe", r"C:\Windows\Fonts\segoeui.ttf")):
        tried.append(fname)
        if os.path.isfile(fname):
            try:
                pdfmetrics.registerFont(TTFont(name, fname))
                return name
            except Exception:
                continue
    raise FixtureSkipped(
        "Fixture d (Liste) uebersprungen: kein TTF-Font fuer das "
        "Bullet-Zeichen gefunden (gesucht: " + ", ".join(tried) + ").")


def build_liste_pdf(path):
    from reportlab.pdfgen import canvas
    font = _bullet_font()
    c = canvas.Canvas(path, pagesize=A4_PT)
    y = 780
    y = _draw_par_ragged(c, D_LINES[:1], y, font=font)
    y -= PARA_GAP
    _draw_par_ragged(c, D_LINES[1:], y, font=font)
    c.showPage()
    c.save()


# ---------------------------------------------------------------------------
# FIXTURE e) MISCHDOKUMENT: TITEL + 2 ABSCHNITTE + FLIESSTEXT + 3x3-TABELLE
# ---------------------------------------------------------------------------
# Titel gross/fett (22 pt), zwei Abschnittsueberschriften mittelgross/fett
# (14 pt), Fliesstext 11 pt. Im ersten Absatz ist EIN WORT fett gesetzt
# ("deutlich") - das darf NIE zum Heading werden. Nach dem zweiten Absatz
# eine 3x3-Tabelle mit sichtbaren Gitterlinien, danach ein Schlusssatz
# (pinnt die Tabellenposition im Textfluss fest).

E_TITLE = "Jahresbericht der Beispiel GmbH"
E_HEAD1 = "Wirtschaftliche Entwicklung"
E_HEAD2 = "Kennzahlen und Ausblick"
E_BOLD_WORD = "deutlich"
E_PAR1_SEGS = [
    [("Das abgelaufene Geschaeftsjahr brachte der Gesellschaft ein ", BODY_FONT),
     (E_BOLD_WORD, "Helvetica-Bold")],
    [("verbessertes Ergebnis, obwohl die Rahmenbedingungen im Kernmarkt weiterhin",
      BODY_FONT)],
    [("angespannt blieben und die Kosten spuerbar gestiegen sind.", BODY_FONT)],
]
E_PAR2 = [
    "Die wichtigsten Kennzahlen der beiden letzten Geschaeftsjahre sind in der",
    "folgenden Uebersicht zusammengefasst und kurz erlaeutert.",
]
E_TABLE = [
    ["Kennzahl", "2024", "2025"],
    ["Umsatz in Mio Euro", "100", "120"],
    ["Gewinn in Mio Euro", "10", "15"],
]
E_CLOSE = "Alle Angaben ohne Gewaehr und ohne Anspruch auf Vollstaendigkeit."

SOLL_E = [
    "# Jahresbericht der Beispiel GmbH",
    "",
    "## Wirtschaftliche Entwicklung",
    "",
    "Das abgelaufene Geschaeftsjahr brachte der Gesellschaft ein deutlich "
    "verbessertes Ergebnis, obwohl die Rahmenbedingungen im Kernmarkt "
    "weiterhin angespannt blieben und die Kosten spuerbar gestiegen sind.",
    "",
    "## Kennzahlen und Ausblick",
    "",
    "Die wichtigsten Kennzahlen der beiden letzten Geschaeftsjahre sind in "
    "der folgenden Uebersicht zusammengefasst und kurz erlaeutert.",
    "",
    "| Kennzahl | 2024 | 2025 |",
    "| --- | --- | --- |",
    "| Umsatz in Mio Euro | 100 | 120 |",
    "| Gewinn in Mio Euro | 10 | 15 |",
    "",
    "Alle Angaben ohne Gewaehr und ohne Anspruch auf Vollstaendigkeit.",
]


def build_misch_pdf(path):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=A4_PT)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(LEFT, 780, E_TITLE)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(LEFT, 736, E_HEAD1)
    y = _draw_par_justified_segments(c, E_PAR1_SEGS, 712)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(LEFT, y - 18, E_HEAD2)
    y = _draw_par_justified(c, E_PAR2, y - 42)
    y_below = _draw_grid_table(c, y - 12, E_TABLE)
    c.setFont(BODY_FONT, BODY_SIZE)
    c.drawString(LEFT, y_below - 24, E_CLOSE)
    c.showPage()
    c.save()


ALL_FIXTURES = [
    ("a_blocksatz", "struct_blocksatz.pdf", build_blocksatz_pdf, SOLL_A),
    ("b_flatter", "struct_flatter.pdf", build_flatter_pdf, SOLL_B),
    ("c_adresse", "struct_adresse.pdf", build_adresse_pdf, SOLL_C),
    ("d_liste", "struct_liste.pdf", build_liste_pdf, SOLL_D),
    ("e_misch", "struct_misch.pdf", build_misch_pdf, SOLL_E),
]


def _build_all():
    """Baut alle Fixtures. Nicht baubare (fehlender Font) werden mit klarer
    Meldung uebersprungen statt die Suite zu reissen."""
    built = []
    for key, fname, builder, soll in ALL_FIXTURES:
        path = os.path.join(FIXTURES, fname)
        try:
            builder(path)
        except FixtureSkipped as e:
            print(f"        SKIP {key}: {e}")
            continue
        built.append((key, path, soll))
    return built


# ---------------------------------------------------------------------------
# C1: FIXTURES SIND VALIDE UND KONVERTIEREN HEUTE FEHLERFREI
# ---------------------------------------------------------------------------
# Die eigentlichen Struktur-SOLLs werden erst mit C2-C4 zu Tests. C1 pinnt
# nur fest: die Fixtures bauen, konvertieren ok, landen im Markdown-Zweig
# und verlieren keinen Inhalt (Anker-Woerter vorhanden).

_ANCHORS = {
    "a_blocksatz": ["Silben-", "trennung", "E-", "Mail-Adresse"],
    "b_flatter": ["Flattersatz", "auseinandergezogen", "kurze Zeile"],
    "c_adresse": ["Beispiel & Partner GmbH", "Musterstrasse 12",
                  "44135 Dortmund", "Deutschland"],
    "d_liste": ["Vollstaendigkeit", "Budgetfreigabe", "Archiv"],
    "e_misch": [E_TITLE, E_HEAD1, E_HEAD2, "Umsatz in Mio Euro", "120",
                E_CLOSE],
}


def test_c1_fixtures_convert_ok():
    for key, path, _soll in _build_all():
        r = convert_file(path)
        assert r["ok"], f"{key}: Konvertierung fehlgeschlagen: {r.get('error')}"
        assert r["target_format"] == "markdown", \
            f"{key}: landet nicht im Markdown-Zweig ({r['target_format']})"
        assert r["was_ocr"] is False, f"{key}: darf kein OCR ausloesen"
        for anchor in _ANCHORS[key]:
            assert anchor in r["output_text"], \
                f"{key}: Anker '{anchor}' fehlt im Output"


# ---------------------------------------------------------------------------
# C2 FUNDAMENT: ZEILEN-RECORDS SIND ZEILENIDENTISCH MIT extract_text()
# ---------------------------------------------------------------------------
# Auf diesem Assert ruht der gesamte Annotations-Ansatz: die Strukturlogik
# arbeitet auf extract_text_lines()-Zeilen, raw_text (Messbasis) kommt aus
# extract_text(). Nur wenn beide zeilenidentisch sind, ist die Annotation
# eine 1:1-Anreicherung und kein zweiter Extraktionspfad.

def _consistency_corpus():
    """Alle Struktur-Fixtures + kapitel.pdf + optionale echte PDFs
    (newmont*), plus alle weiteren bereits erzeugten Fixture-PDFs."""
    import glob
    paths = [p for _, p, _ in _build_all()]
    from test_block1 import build_chapter_pdf
    kapitel = os.path.join(FIXTURES, "kapitel.pdf")
    build_chapter_pdf(kapitel)
    paths.append(kapitel)
    for pattern in ("newmont*.pdf", "Newmont*.pdf"):
        paths.extend(glob.glob(os.path.join(FIXTURES, pattern)))
    for extra in glob.glob(os.path.join(FIXTURES, "*.pdf")):
        if extra not in paths:
            paths.append(extra)
    return paths


def test_c2_line_records_match_extract_text():
    import pdfplumber
    for path in _consistency_corpus():
        with pdfplumber.open(path) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                try:
                    txt = page.extract_text() or ""
                    joined = "\n".join(
                        l["text"] for l in page.extract_text_lines())
                except Exception:
                    # kaputte Seiten sind Sache von Suite 11, nicht dieses
                    # Konsistenz-Tests
                    continue
                assert joined == txt, (
                    f"FUNDAMENT GEBROCHEN: {os.path.basename(path)} Seite "
                    f"{page_no}: extract_text_lines() weicht von "
                    f"extract_text() ab")


# ---------------------------------------------------------------------------
# C2: UEBERSCHRIFTEN (konservativ) - konkrete Zeilen, nicht "enthaelt ein #"
# ---------------------------------------------------------------------------

def _convert_fixture(fname_key):
    for key, fname, builder, _soll in ALL_FIXTURES:
        if key == fname_key:
            path = os.path.join(FIXTURES, fname)
            builder(path)
            r = convert_file(path)
            assert r["ok"], f"{key}: {r.get('error')}"
            return r
    raise AssertionError(f"unbekanntes Fixture {fname_key}")


def test_c2_misch_headings_exact():
    """Fixture e: Titel wird #, beide Abschnitte werden ## - und sonst
    NICHTS. Reihenfolge bleibt."""
    r = _convert_fixture("e_misch")
    lines = r["output_text"].split("\n")
    assert "# Jahresbericht der Beispiel GmbH" in lines, lines
    assert "## Wirtschaftliche Entwicklung" in lines, lines
    assert "## Kennzahlen und Ausblick" in lines, lines
    headings = [l for l in lines if l.startswith("#")]
    assert headings == ["# Jahresbericht der Beispiel GmbH",
                        "## Wirtschaftliche Entwicklung",
                        "## Kennzahlen und Ausblick"], \
        f"Falsche oder zusaetzliche Headings: {headings}"
    assert (lines.index("# Jahresbericht der Beispiel GmbH")
            < lines.index("## Wirtschaftliche Entwicklung")
            < lines.index("## Kennzahlen und Ausblick")), \
        "Heading-Reihenfolge entspricht nicht dem Dokument"


def test_c2_bold_word_in_body_never_heading():
    """Die selbst gefundene Falle: 'deutlich' ist fett IM Fliesstext.
    Die Zeile muss unveraendert und ohne #-Praefix im Output stehen."""
    r = _convert_fixture("e_misch")
    lines = r["output_text"].split("\n")
    body_line = ("Das abgelaufene Geschaeftsjahr brachte der Gesellschaft "
                 "ein deutlich")
    assert body_line in lines, \
        f"Fliesstext-Zeile mit fettem Wort fehlt oder wurde veraendert"
    for h in (l for l in lines if l.startswith("#")):
        assert E_BOLD_WORD not in h, \
            f"Fettes Wort im Fliesstext wurde zum Heading: {h}"


def test_c2_plain_fixtures_byte_identical():
    """Fixtures a-d: exakt NULL Headings, Output byteidentisch zur
    C1-Baseline (die Heading-Logik fasst diese Dokumente nicht an)."""
    expected = {
        "a_blocksatz": "\n".join(A_PAR1 + A_PAR2),
        "b_flatter": "\n".join(B_PAR1 + B_PAR2),
        "c_adresse": "\n".join(C_INTRO + C_ADDRESS + C_CLOSE),
        "d_liste": "\n".join(D_LINES),
    }
    for key, want in expected.items():
        try:
            r = _convert_fixture(key)
        except FixtureSkipped as e:
            print(f"        SKIP {key}: {e}")
            continue
        assert r["output_text"] == want, (
            f"{key}: Output weicht von der C1-Baseline ab:\n"
            f"---IST---\n{r['output_text']}\n---SOLL---\n{want}")


def test_c2_kapitel_headings_and_stripping_intact():
    """Echte Mehrseiten-PDF (kapitel.pdf): 'Kapitel 1'-'Kapitel 5' werden
    genau EINE Ebene (#), Kopf-/Fusszeilen-Entfernung arbeitet unveraendert,
    die Zeile in der Seitenmitte bleibt Fliesstext."""
    from test_block1 import build_chapter_pdf
    path = os.path.join(FIXTURES, "kapitel.pdf")
    build_chapter_pdf(path)
    r = convert_file(path)
    assert r["ok"], r.get("error")
    lines = r["output_text"].split("\n")
    for n in range(1, 6):
        assert f"# Kapitel {n}" in lines, \
            f"'# Kapitel {n}' fehlt als exakte Zeile"
    headings = [l for l in lines if l.startswith("#")]
    assert len(headings) == 5, f"Zusaetzliche Headings erkannt: {headings}"
    assert "Interner Vermerk 99" in lines, \
        "Zeile in Seitenmitte fehlt oder wurde veraendert"
    assert "Vertraulich - Beispiel GmbH" not in r["output_text"], \
        "Kopfzeile wurde nach der Stripper-Anpassung nicht mehr entfernt"
    assert "Seite 1 von 5" not in r["output_text"], \
        "Fusszeile wurde nach der Stripper-Anpassung nicht mehr entfernt"
    assert "10 wiederkehrende" in r["note"], \
        f"Stripper-Note veraendert: {r['note']}"


# ---------------------------------------------------------------------------
# BASELINE-MODUS (C1-Ist-Aufnahme): Output + Token-Zahlen aller Fixtures
# ---------------------------------------------------------------------------

def print_baseline():
    entries = _build_all()
    # kapitel.pdf als realistischste vorhandene Mehrseiten-PDF mitmessen
    # (5 Seiten, Kopf-/Fusszeilen) - wird von Suite test_block1 erzeugt.
    kapitel = os.path.join(FIXTURES, "kapitel.pdf")
    if os.path.isfile(kapitel):
        entries.append(("real_kapitel", kapitel, None))
    for key, path, _soll in entries:
        r = convert_file(path)
        print("=" * 74)
        print(f"FIXTURE {key}  ({os.path.basename(path)})")
        print(f"  ok={r['ok']}  format={r.get('target_format')}  "
              f"method={r.get('token_method')}")
        print(f"  tokens_before={r.get('tokens_before')}  "
              f"tokens_after={r.get('tokens_after')}  "
              f"saved={r.get('tokens_saved')} ({r.get('percent_saved')}%)")
        print(f"  note: {r.get('note')}")
        print("-" * 74)
        print(r.get("output_text", ""))
        print()


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

ALL_TESTS = [
    test_c1_fixtures_convert_ok,
    test_c2_line_records_match_extract_text,   # Fundament zuerst
    test_c2_misch_headings_exact,
    test_c2_bold_word_in_body_never_heading,
    test_c2_plain_fixtures_byte_identical,
    test_c2_kapitel_headings_and_stripping_intact,
]

if __name__ == "__main__":
    if "--baseline" in sys.argv:
        print_baseline()
        sys.exit(0)
    passed, failed = 0, 0
    for test in ALL_TESTS:
        name = test.__name__
        try:
            test()
            print(f"  PASS  {name}")
            passed += 1
        except Exception:
            print(f"  FAIL  {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} bestanden, {failed} fehlgeschlagen.")
    sys.exit(1 if failed else 0)
