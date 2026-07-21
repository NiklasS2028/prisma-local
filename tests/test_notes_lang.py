# -*- coding: utf-8 -*-
"""
test_notes_lang.py
------------------
Tests für Block H (Notes-Lokalisierung, lang-Parameter).

Geprüft wird:
  - DE-Default: convert_file ohne lang liefert die unveränderten deutschen
    Notes (Rückwärtskompatibilität; zusätzlich bleiben alle Alt-Suiten
    unangepasst grün)
  - EN-Notes pro Dateityp-Pfad (txt, csv, xlsx inkl. Formel-Hinweis, docx,
    pptx inkl. Sprechernotizen-Hinweis, Text-PDF inkl. Struktur-Note und
    Kopf-/Fusszeilen, Tabellen-PDF inkl. Begleittext, Bild-PDF/OCR)
  - Singular/Plural der Struktur-Note in DE und EN
  - ocr_error-Anleitungstexte (Tesseract fehlt) lokalisiert
  - ungültiger/fehlender lang-Wert fällt auf 'de'
  - HTTP: /convert und /convert-batch reichen ui_lang durch
  - DOM-Ende-zu-Ende: UI auf DE -> DE-Note, UI auf EN -> EN-Note

Aufruf:  python tests/test_notes_lang.py   (Server auf :8770 muss laufen)
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

from converter import (convert_file, _structure_note, _removed_note,
                       _ocr_pages)  # noqa: E402
from test_block1 import (build_formula_xlsx, build_order_docx,
                         build_notes_pptx, build_plain_text_pdf,
                         build_table_pdf_with_text, _make_text_image,
                         A4_PT)  # noqa: E402

BASE = "http://localhost:8770"
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
os.makedirs(FIXTURES, exist_ok=True)


def _txt_fixture(name="notes_lang.txt"):
    path = os.path.join(FIXTURES, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("Zeile eins mit Inhalt.\n\n\n\nZeile zwei mit Inhalt.")
    return path


def _csv_fixture():
    path = os.path.join(FIXTURES, "notes_lang.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("Name,Wert\nAlpha,1\n")
    return path


def _image_pdf_fixture():
    path = os.path.join(FIXTURES, "notes_lang_bild.pdf")
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    c = canvas.Canvas(path, pagesize=A4_PT)
    img = _make_text_image(["NOTES LANG TEST 4242"])
    c.drawImage(ImageReader(img), 0, 0, width=A4_PT[0], height=A4_PT[1])
    c.showPage()
    c.save()
    return path


# ---------------------------------------------------------------------------
# DE-DEFAULT UND VALIDIERUNG
# ---------------------------------------------------------------------------

def test_de_default_unchanged():
    """Ohne lang-Argument: exakt die alte deutsche Note (wortgleich)."""
    r = convert_file(_txt_fixture())
    assert r["ok"]
    assert r["note"] == ("Textdatei bereinigt (ueberfluessige Leerzeilen "
                         "und Whitespace entfernt)."), r["note"]


def test_invalid_lang_falls_back_to_de():
    """Nur 'de'/'en' sind gültig - alles andere fällt auf 'de'."""
    path = _txt_fixture()
    for bad in ("fr", "EN", "", None, 42):
        r = convert_file(path, lang=bad)
        assert r["ok"]
        assert r["note"].startswith("Textdatei bereinigt"), \
            f"lang={bad!r}: {r['note']}"


# ---------------------------------------------------------------------------
# EN-NOTES PRO DATEITYP-PFAD
# ---------------------------------------------------------------------------

def test_en_txt_note():
    r = convert_file(_txt_fixture(), lang="en")
    assert r["note"] == ("Text file cleaned up (superfluous blank lines "
                         "and whitespace removed)."), r["note"]


def test_en_csv_note():
    r = convert_file(_csv_fixture(), lang="en")
    assert "most efficient data format" in r["note"], r["note"]


def test_en_xlsx_note_with_formula_hint():
    path = os.path.join(FIXTURES, "notes_lang.xlsx")
    build_formula_xlsx(path)
    r = convert_file(path, lang="en")
    assert "Excel data exported as CSV" in r["note"], r["note"]
    assert "1 formula cell(s) without a cached result" in r["note"], r["note"]


def test_en_docx_note():
    path = os.path.join(FIXTURES, "notes_lang.docx")
    build_order_docx(path)
    r = convert_file(path, lang="en")
    assert "Word structure (headings, lists, tables)" in r["note"], r["note"]


def test_en_pptx_note_with_speaker_hint():
    path = os.path.join(FIXTURES, "notes_lang.pptx")
    build_notes_pptx(path)
    r = convert_file(path, lang="en")
    assert "PowerPoint slides converted to Markdown" in r["note"], r["note"]
    assert "1 slide(s) contain speaker notes" in r["note"], r["note"]


def test_en_text_pdf_note_with_structure_and_removed():
    """Text-PDF: EN-Grundnote + Kopf-/Fusszeilen-Teil + Removed-Liste."""
    path = os.path.join(FIXTURES, "notes_lang_std.pdf")
    build_plain_text_pdf(path)
    r = convert_file(path, lang="en")
    note = r["note"]
    assert ("PDF body text cleaned up as Markdown." in note
            or "PDF body text extracted" in note), note
    assert "recurring header/footer lines removed" in note, note
    assert " Removed: " in note, note
    assert "Entfernt:" not in note and "Kopf-" not in note, \
        f"Deutsche Fragmente in EN-Note: {note}"


def test_en_table_pdf_note_with_companion():
    path = os.path.join(FIXTURES, "notes_lang_tabelle.pdf")
    build_table_pdf_with_text(path)
    r = convert_file(path, lang="en")
    assert r["target_format"] == "csv"
    assert "converted to CSV" in r["note"], r["note"]
    assert "Accompanying text outside the tables" in r["note"], r["note"]


def test_en_image_pdf_ocr_note():
    r = convert_file(_image_pdf_fixture(), lang="en")
    assert r["ok"] and r["was_ocr"] is True
    assert "IMAGE PDF recognized via OCR" in r["note"], r["note"]
    assert "BILD-PDF" not in r["note"], f"Deutsche Fragmente: {r['note']}"


# ---------------------------------------------------------------------------
# STRUKTUR-NOTE SINGULAR/PLURAL + HELFER
# ---------------------------------------------------------------------------

def test_structure_note_singular_plural():
    assert _structure_note(1, 1, 1, lang="en") == (
        "1 heading detected, 1 table carried over, "
        "1 line break joined into a paragraph.")
    assert _structure_note(2, 3, 4, lang="en") == (
        "2 headings detected, 3 tables carried over, "
        "4 line breaks joined into paragraphs.")
    # DE bleibt wortgleich zum alten Stand
    assert _structure_note(1, 0, 2) == (
        "1 Überschrift erkannt, 2 Zeilenumbrüche zu Absätzen verbunden.")
    assert _structure_note(0, 0, 0, lang="en") == ""


def test_removed_note_en():
    text = _removed_note(["a", "b", "c", "d", "e"], lang="en")
    assert text.startswith(" Removed: '"), text
    assert "(+1 more patterns)" in text, text
    # DE unverändert
    assert " Entfernt: " in _removed_note(["x"]), _removed_note(["x"])


def test_ocr_error_texts_localized():
    """Tesseract 'fehlt' (gepatcht) -> Anleitung in der jeweiligen Sprache."""
    import pytesseract
    orig = pytesseract.get_tesseract_version

    def boom():
        raise RuntimeError("im Test deaktiviert")

    pytesseract.get_tesseract_version = boom
    try:
        _, err_de = _ocr_pages("egal.pdf", [1], lang="de")
        _, err_en = _ocr_pages("egal.pdf", [1], lang="en")
    finally:
        pytesseract.get_tesseract_version = orig
    assert "Das Programm 'Tesseract' wurde nicht gefunden." in err_de, err_de
    assert "The 'Tesseract' program was not found." in err_en, err_en


# ---------------------------------------------------------------------------
# HTTP: ui_lang WIRD DURCHGEREICHT (auch Batch), VALIDIERUNG
# ---------------------------------------------------------------------------

def _post_convert(path, ui_lang=None):
    data = {"target_model": "none"}
    if ui_lang is not None:
        data["ui_lang"] = ui_lang
    with open(path, "rb") as f:
        r = requests.post(BASE + "/convert", timeout=30,
                          files={"file": (os.path.basename(path), f)},
                          data=data)
    return r.json()


def test_http_convert_ui_lang():
    path = _txt_fixture("notes_lang_http.txt")
    assert _post_convert(path)["note"].startswith("Textdatei bereinigt")
    assert _post_convert(path, "en")["note"].startswith("Text file cleaned up")
    assert _post_convert(path, "hax")["note"].startswith("Textdatei bereinigt")


def test_http_batch_ui_lang():
    path = _txt_fixture("notes_lang_batch.txt")
    with open(path, "rb") as f:
        r = requests.post(BASE + "/convert-batch", timeout=30,
                          files={"files": (os.path.basename(path), f)},
                          data={"target_model": "none", "ui_lang": "en"})
    d = r.json()
    assert d["ok"]
    assert d["results"][0]["note"].startswith("Text file cleaned up"), \
        d["results"][0]["note"]


# ---------------------------------------------------------------------------
# DOM-ENDE-ZU-ENDE (Playwright)
# ---------------------------------------------------------------------------

def dom_test_note_language(page):
    """UI auf DE -> DE-Note; UI auf EN -> EN-Note (echte Oberfläche).
    Zwischen den Uploads 'Neue Datei', damit das alte Ergebnis weg ist und
    der zweite Upload (anderer Dateiname) sicher ein change-Event feuert."""
    path_de = _txt_fixture("notes_lang_dom_de.txt")
    path_en = _txt_fixture("notes_lang_dom_en.txt")
    page.click("#tabConv")
    page.set_input_files("#fileInput", path_de)
    page.wait_for_selector(".result.show", timeout=10000)
    assert "Textdatei bereinigt" in page.locator("#note").inner_text(), \
        page.locator("#note").inner_text()
    page.click("#convResetBtn")
    page.wait_for_timeout(200)
    assert not page.locator(".result.show").count(), "Reset wirkt nicht"
    page.click('#langToggle .lang-btn[data-lang="en"]')
    page.set_input_files("#fileInput", path_en)
    page.wait_for_selector(".result.show", timeout=10000)
    assert "Text file cleaned up" in page.locator("#note").inner_text(), \
        page.locator("#note").inner_text()
    page.click('#langToggle .lang-btn[data-lang="de"]')


ALL_TESTS = [
    test_de_default_unchanged,
    test_invalid_lang_falls_back_to_de,
    test_en_txt_note,
    test_en_csv_note,
    test_en_xlsx_note_with_formula_hint,
    test_en_docx_note,
    test_en_pptx_note_with_speaker_hint,
    test_en_text_pdf_note_with_structure_and_removed,
    test_en_table_pdf_note_with_companion,
    test_en_image_pdf_ocr_note,
    test_structure_note_singular_plural,
    test_removed_note_en,
    test_ocr_error_texts_localized,
    test_http_convert_ui_lang,
    test_http_batch_ui_lang,
]

DOM_TESTS = [
    dom_test_note_language,
]

if __name__ == "__main__":
    passed, failed = 0, 0
    for test in ALL_TESTS:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {test.__name__}")
            traceback.print_exc()
            failed += 1

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for test in DOM_TESTS:
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            page.goto(BASE)
            try:
                test(page)
                print(f"  PASS  {test.__name__}")
                passed += 1
            except Exception:
                print(f"  FAIL  {test.__name__}")
                traceback.print_exc()
                failed += 1
            finally:
                ctx.close()
        browser.close()

    print(f"\n{passed} bestanden, {failed} fehlgeschlagen.")
    sys.exit(1 if failed else 0)
