# -*- coding: utf-8 -*-
"""
test_pdf_robust.py (Suite 11)
-----------------------------
Regressionstests für Block H (PDF-Robustheit). Anlass: eine valide,
öffentlich publizierte PDF (Newmont Investor Presentation, Oktober 2025)
starb komplett an einer pdfplumber-Exception, weil eine Tabellen-Box um
~6e-05 Punkt über den Seitenrand ragte (Rundungsartefakt des erzeugenden
Programms, in realen PDFs alltäglich):

    ValueError: Bounding box (...) is not fully within parent page
    bounding box (0, 0, 960, 540)

Die Fixtures werden selbst konstruiert (reportlab) und reproduzieren exakt
diese Exception-Klasse. Liegt zusätzlich die echte Newmont-Datei als
tests/fixtures/newmont*.pdf vor, wird sie mitgeprüft.

Aufruf:  python tests/test_pdf_robust.py
"""

import glob
import os
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# converter.py liegt eine Ebene höher
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from converter import convert_file  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
os.makedirs(FIXTURES, exist_ok=True)

# Folien-Format wie im Original-Fall (PowerPoint-Export, 960x540 Punkt)
SLIDE = (960, 540)
# Überhang in der Größenordnung des Original-Fehlers (~6e-05 Punkt)
EPS = 6.1035e-05


# ---------------------------------------------------------------------------
# FIXTURE-BAUER
# ---------------------------------------------------------------------------

def _draw_title_page(c, title="Newmont",
                     sub="Investor Presentation October 2025",
                     line3="Free cash flow and portfolio update"):
    """Text-Deckblatt mit den Ankern des Original-Falls."""
    c.setFont("Helvetica-Bold", 28)
    c.drawString(60, 460, title)
    c.setFont("Helvetica", 18)
    c.drawString(60, 420, sub)
    c.drawString(60, 390, line3)
    c.showPage()


def _draw_overhang_table_page(c):
    """Seite mit Tabelle, deren oberste Gitterlinie um EPS über den
    Seitenrand ragt -> pdfplumber-Tabellen-Box mit negativem top.
    Vor Block H tötete genau das die gesamte Datei."""
    c.setFont("Helvetica", 12)
    c.drawString(60, 500, "Kennzahlen im Ueberblick:")
    xs = [100, 400, 700]
    ys = [SLIDE[1] + EPS, 300, 100]  # oberste Linie KNAPP über der Seite
    c.setLineWidth(1)
    for y in ys:
        c.line(xs[0], y, xs[-1], y)
    for x in xs:
        c.line(x, ys[-1], x, ys[0])
    c.setFont("Helvetica", 14)
    c.drawString(120, 400, "Free cash flow")
    c.drawString(420, 400, "1.6 Mrd USD")
    c.drawString(120, 180, "Produktion")
    c.drawString(420, 180, "5.5 Moz Gold")
    c.showPage()


def build_boxrand_pdf(path):
    """Nachbau des Newmont-Falls: Text-Deckblatt + Folgeseite, auf der eine
    Tabellen-Box minimal über den Seitenrand ragt."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=SLIDE)
    _draw_title_page(c)
    _draw_overhang_table_page(c)
    c.save()


def build_three_text_pages_pdf(path):
    """Drei normale Textseiten mit eindeutigen Ankern. Seite 2 ist gross
    gesetzt, damit die OCR-Rettung sie zuverlässig lesen kann."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=SLIDE)
    c.setFont("Helvetica", 16)
    c.drawString(60, 460, "ERSTE SEITE: Einleitung mit Anker ALPHA-111.")
    c.drawString(60, 430, "Weiterer Fliesstext, damit die Seite als Textseite gilt.")
    c.showPage()
    c.setFont("Helvetica-Bold", 40)
    c.drawString(60, 400, "KENNZAHL SIEBEN 7777")
    c.setFont("Helvetica-Bold", 30)
    c.drawString(60, 300, "ZWEITE SEITE BETA")
    c.showPage()
    c.setFont("Helvetica", 16)
    c.drawString(60, 460, "DRITTE SEITE: Fazit mit Anker GAMMA-333.")
    c.drawString(60, 430, "Auch diese Seite traegt genug echten Text.")
    c.showPage()
    c.save()


# ---------------------------------------------------------------------------
# PATCH-HELFER (simulieren deterministisch defekte Seiten / fehlende OCR)
# ---------------------------------------------------------------------------

class _break_pages:
    """Kontextmanager: pdfplumber-Textextraktion wirft für die angegebenen
    Seitennummern eine Exception (simuliert eine defekte Seite - die echte
    Bounding-Box-Exception der Randtabelle ist seit H.1 gefixt und steht
    daher nicht mehr als natürlicher Auslöser zur Verfügung)."""

    def __init__(self, page_numbers):
        self.page_numbers = set(page_numbers)

    def __enter__(self):
        import pdfplumber.page as pp
        self._cls = pp.Page
        self._orig = pp.Page.extract_text
        broken, orig = self.page_numbers, self._orig

        def patched(page_self, *a, **kw):
            if page_self.page_number in broken:
                raise ValueError("Simulierter Seitendefekt (Test)")
            return orig(page_self, *a, **kw)

        pp.Page.extract_text = patched
        return self

    def __exit__(self, *exc):
        self._cls.extract_text = self._orig
        return False


class _no_ocr:
    """Kontextmanager: schaltet die OCR-Rettung ab (als wären Tesseract/
    poppler nicht installiert)."""

    def __enter__(self):
        import converter
        self._orig = converter._ocr_pages
        converter._ocr_pages = lambda path, pages, lang="de": (
            {}, "Texterkennung im Test deaktiviert.")
        return self

    def __exit__(self, *exc):
        import converter
        converter._ocr_pages = self._orig
        return False


# ---------------------------------------------------------------------------
# H.1: DIE BOUNDING-BOX-EXCEPTION KILLT DIE DATEI NICHT MEHR
# ---------------------------------------------------------------------------

def test_h1_overhang_bbox_survives():
    """Der reproduzierte Original-Fall konvertiert ohne Exception, der
    Inhalt BEIDER Seiten (inkl. der Problemseite) ist vollständig da."""
    path = os.path.join(FIXTURES, "boxrand.pdf")
    build_boxrand_pdf(path)
    r = convert_file(path)
    assert r["ok"], f"Konvertierung fehlgeschlagen: {r.get('error')}"
    out = r["output_text"]
    for anchor in ("Newmont", "Investor Presentation", "Free cash flow"):
        assert anchor in out, f"Anker '{anchor}' fehlt im Ergebnis"
    # Inhalt der Problemseite selbst (nicht nur des Deckblatts)
    assert "Kennzahlen" in out, "Text der Seite mit der Randtabelle fehlt"
    assert "Bounding box" not in r.get("note", ""), \
        "Rohe pdfminer/pdfplumber-Meldung sickert in die Note durch"


def test_h1_real_newmont_if_present():
    """Optional: liegt die echte Newmont-PDF in tests/fixtures/, muss auch
    sie sauber konvertieren. Fehlt sie, gilt der konstruierte Nachbau."""
    candidates = glob.glob(os.path.join(FIXTURES, "newmont*.pdf")) + \
        glob.glob(os.path.join(FIXTURES, "Newmont*.pdf"))
    if not candidates:
        print("        (Hinweis: keine echte newmont*.pdf in tests/fixtures/, "
              "Nachbau-Fixture deckt den Fall ab)")
        return
    r = convert_file(candidates[0])
    assert r["ok"], f"Echte Newmont-PDF scheitert weiterhin: {r.get('error')}"
    out = r["output_text"]
    assert "Newmont" in out, "Anker 'Newmont' fehlt im Ergebnis der echten Datei"


# ---------------------------------------------------------------------------
# H.2: EINE KAPUTTE SEITE REISST DIE DATEI NICHT MEHR MIT
# ---------------------------------------------------------------------------

def test_h2_broken_page_rescued_by_ocr():
    """Defekte Seite 2 zwischen intakten Seiten: wird per OCR gerettet,
    Reihenfolge bleibt, Note benennt die Rettung. Kein Fehler."""
    path = os.path.join(FIXTURES, "defekt_mitte.pdf")
    build_three_text_pages_pdf(path)
    with _break_pages({2}):
        r = convert_file(path)
    assert r["ok"], f"Datei starb an EINER defekten Seite: {r.get('error')}"
    out = r["output_text"]
    assert "ALPHA-111" in out, "Intakte Seite 1 fehlt"
    assert "GAMMA-333" in out, "Intakte Seite 3 fehlt"
    assert "7777" in out, "Defekte Seite 2 wurde nicht per OCR gerettet"
    assert out.index("ALPHA-111") < out.index("7777") < out.index("GAMMA-333"), \
        "Seiten-Reihenfolge nach der Rettung falsch"
    assert "gerettet" in r["note"], \
        f"Note benennt die OCR-Rettung nicht: {r['note']}"
    assert "2" in r["note"], f"Note nennt die Seitennummer nicht: {r['note']}"


def test_h2_broken_page_skipped_without_ocr():
    """Defekte Seite ohne OCR-Rettung: Ergebnis enthält die intakten Seiten
    plus ACHTUNG-UNVOLLSTÄNDIG-Markierung - kein Komplettausfall."""
    path = os.path.join(FIXTURES, "defekt_mitte.pdf")
    build_three_text_pages_pdf(path)
    with _break_pages({2}), _no_ocr():
        r = convert_file(path)
    assert r["ok"], f"Datei starb trotz intakter Seiten: {r.get('error')}"
    out = r["output_text"]
    assert "ALPHA-111" in out and "GAMMA-333" in out, "Intakte Seiten fehlen"
    assert "7777" not in out, "Testaufbau kaputt: Seite 2 haette fehlen muessen"
    assert "ACHTUNG - UNVOLLSTÄNDIG" in r["note"], \
        f"Fehlende Seite nicht markiert: {r['note']}"
    assert "übersprungen" in r["note"], \
        f"Note erklaert das Ueberspringen nicht: {r['note']}"
    assert "2" in r["note"], f"Note nennt die Seitennummer nicht: {r['note']}"


def test_h2_all_pages_broken_clean_400():
    """Scheitern ALLE Seiten (und OCR kann nichts retten), bleibt es ein
    sauberer Fehler - mit verständlicher Meldung, die rohe technische
    Meldung nur im separaten Detail-Feld."""
    path = os.path.join(FIXTURES, "defekt_alle.pdf")
    build_three_text_pages_pdf(path)
    with _break_pages({1, 2, 3}), _no_ocr():
        r = convert_file(path)
    assert not r["ok"], "Komplett unlesbare PDF lieferte faelschlich ok=True"
    assert "Keine der 3 Seite(n)" in r["error"], \
        f"Fehlermeldung nicht verstaendlich: {r['error']}"
    assert "Texterkennung" in r["error"], \
        f"Fehlermeldung erwaehnt den OCR-Versuch nicht: {r['error']}"
    assert "Simulierter Seitendefekt" not in r["error"], \
        "Rohe technische Meldung steht im Hauptfehler"
    assert "Simulierter Seitendefekt" in r.get("error_detail", ""), \
        f"Technischer Grund fehlt im Detail-Feld: {r.get('error_detail')}"


def test_h2_intact_pdf_unchanged():
    """Regression: eine voll intakte PDF laeuft unveraendert durch
    (kein OCR, keine Markierungen, keine defekten Seiten)."""
    path = os.path.join(FIXTURES, "defekt_keine.pdf")
    build_three_text_pages_pdf(path)
    r = convert_file(path)
    assert r["ok"], f"Intakte PDF scheitert: {r.get('error')}"
    out = r["output_text"]
    assert "ALPHA-111" in out and "7777" in out and "GAMMA-333" in out
    assert r["was_ocr"] is False, "Intakte Text-PDF darf kein OCR ausloesen"
    assert "ACHTUNG" not in r["note"] and "gerettet" not in r["note"], \
        f"Falsche Markierung an intakter PDF: {r['note']}"


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

ALL_TESTS = [
    test_h1_overhang_bbox_survives,
    test_h1_real_newmont_if_present,
    test_h2_broken_page_rescued_by_ocr,
    test_h2_broken_page_skipped_without_ocr,
    test_h2_all_pages_broken_clean_400,
    test_h2_intact_pdf_unchanged,
]

if __name__ == "__main__":
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
