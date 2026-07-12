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
# RUNNER
# ---------------------------------------------------------------------------

ALL_TESTS = [
    test_h1_overhang_bbox_survives,
    test_h1_real_newmont_if_present,
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
