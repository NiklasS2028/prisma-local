# -*- coding: utf-8 -*-
"""
test_errors_lang.py
-------------------
Tests für Block I (Fehlertext-Lokalisierung, ui_lang).

Geprüft wird:
  - DE-Default: alle Fehlertexte ohne ui_lang wortgleich zum alten Stand
    (Ausnahmen laut Beschluss: 'unsupported_type' auf die app.py-Fassung
    vereinheitlicht, 'batch_too_many' an T().batchTooMany angeglichen)
  - EN-Fassung pro inventarisiertem Pfad
  - Kanal-Reihenfolge: Form-Feld vor Query-Parameter; Query allein reicht;
    JSON-Body-Feld funktioniert
  - 413 über dem Grössenlimit: Query-Parameter bleibt lesbar (EN belegt)
  - ungültige lang-Werte fallen auf 'de'
  - Origin-403 ist EIN statischer zweisprachiger Text
  - Katalog-Parität: jeder Schlüssel in de UND en, gleiche Platzhalter
  - DOM-Ende-zu-Ende: sichtbarer Fehlerfall (nicht unterstützter Dateityp)
    in beiden Sprachen

Aufruf:  python tests/test_errors_lang.py   (Server auf :8770 muss laufen,
nur für den DOM-Teil - die HTTP-Tests laufen in-process gegen den Testclient)
"""

import io
import os
import re
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as app_module  # noqa: E402
from converter import convert_file, SUPPORTED_EXTENSIONS, _ERRORS  # noqa: E402
from test_pdf_robust import (_break_pages, _no_ocr,
                             build_three_text_pages_pdf)  # noqa: E402

app_module.app.testing = True
CLIENT = app_module.app.test_client()

BASE = "http://localhost:8770"
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
os.makedirs(FIXTURES, exist_ok=True)

EXTS = ", ".join(SUPPORTED_EXTENSIONS)


def _f(name, content="Inhalt egal."):
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    return (io.BytesIO(data), name)


def _post_convert(query="", **form):
    """POST /convert mit optionalen Form-Feldern (auch Datei-Tupel)."""
    return CLIENT.post("/convert" + query, data=form,
                       content_type="multipart/form-data")


# ---------------------------------------------------------------------------
# DE-DEFAULT (Rückwärtskompatibilität, wortgleich)
# ---------------------------------------------------------------------------

def test_de_default_no_file():
    r = _post_convert()
    assert r.status_code == 400
    assert r.get_json()["error"] == "Keine Datei empfangen.", r.get_json()


def test_de_default_unsupported_type_unified():
    """Konsolidierter Text (eine DE-Fassung fuer app.py UND converter.py)."""
    expected = f"Dateityp '.xyz' nicht unterstuetzt. Moeglich: {EXTS}"
    r = _post_convert(file=_f("kaputt.xyz"))
    assert r.get_json()["error"] == expected, r.get_json()
    # converter.py-Direktaufruf liefert denselben Wortlaut (Dublette weg)
    path = os.path.join(FIXTURES, "errors_lang.xyz")
    with open(path, "w", encoding="utf-8") as f:
        f.write("egal")
    assert convert_file(path)["error"] == expected


# ---------------------------------------------------------------------------
# EN PRO PFAD + SPRACHKANÄLE
# ---------------------------------------------------------------------------

def test_en_unsupported_type_form():
    r = _post_convert(file=_f("kaputt.xyz"), ui_lang="en")
    assert r.get_json()["error"] == \
        f"File type '.xyz' not supported. Possible: {EXTS}", r.get_json()


def test_en_no_file_query_only():
    """Query-Parameter allein reicht als Sprachkanal."""
    r = _post_convert(query="?ui_lang=en")
    assert r.get_json()["error"] == "No file received.", r.get_json()


def test_channel_form_beats_query():
    r = _post_convert(query="?ui_lang=de", ui_lang="en")
    assert r.get_json()["error"] == "No file received.", \
        f"Form-Feld muss vor Query gewinnen: {r.get_json()}"
    r = _post_convert(query="?ui_lang=en", ui_lang="de")
    assert r.get_json()["error"] == "Keine Datei empfangen.", \
        f"Form-Feld muss vor Query gewinnen: {r.get_json()}"


def test_channel_json_body_zip_no_files():
    r = CLIENT.post("/download-batch", json={"files": [], "ui_lang": "en"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "No files specified for download.", \
        r.get_json()
    r = CLIENT.post("/download-batch", json={"files": []})
    assert r.get_json()["error"] == \
        "Keine Dateien zum Herunterladen angegeben.", r.get_json()


def test_413_query_lang_de_and_en():
    """Über dem Grössenlimit ist das Formular nicht mehr lesbar - der
    Query-Parameter muss die Sprache trotzdem liefern."""
    orig = app_module.app.config["MAX_CONTENT_LENGTH"]
    app_module.app.config["MAX_CONTENT_LENGTH"] = 1024
    try:
        big = b"x" * 4096
        r = CLIENT.post("/convert", data=big,
                        content_type="multipart/form-data")
        assert r.status_code == 413, r.status_code
        assert r.get_json()["error"].startswith(
            "Datei bzw. Dateien zusammen zu gross"), r.get_json()
        r = CLIENT.post("/convert?ui_lang=en", data=big,
                        content_type="multipart/form-data")
        assert r.status_code == 413, r.status_code
        assert r.get_json()["error"].startswith(
            "File or files together too large"), r.get_json()
    finally:
        app_module.app.config["MAX_CONTENT_LENGTH"] = orig


def test_invalid_lang_falls_back_de():
    for bad in ("fr", "EN", "hax", ""):
        r = _post_convert(query=f"?ui_lang={bad}")
        assert r.get_json()["error"] == "Keine Datei empfangen.", \
            f"ui_lang={bad!r}: {r.get_json()}"


# ---------------------------------------------------------------------------
# BATCH
# ---------------------------------------------------------------------------

def test_batch_no_files_de_en():
    r = CLIENT.post("/convert-batch", data={},
                    content_type="multipart/form-data")
    assert r.get_json()["error"] == "Keine Dateien empfangen.", r.get_json()
    r = CLIENT.post("/convert-batch?ui_lang=en", data={},
                    content_type="multipart/form-data")
    assert r.get_json()["error"] == "No files received.", r.get_json()


def test_batch_too_many_matches_client_wording():
    """DE-Wortlaut jetzt identisch zum Client-Text T().batchTooMany."""
    files = [_f(f"datei{i}.txt") for i in range(app_module.MAX_BATCH_FILES + 1)]
    r = CLIENT.post("/convert-batch", data={"files": files},
                    content_type="multipart/form-data")
    assert r.get_json()["error"] == (
        f"Maximal {app_module.MAX_BATCH_FILES} Dateien gleichzeitig — "
        f"bitte in kleineren Gruppen konvertieren."), r.get_json()
    files = [_f(f"datei{i}.txt") for i in range(app_module.MAX_BATCH_FILES + 1)]
    r = CLIENT.post("/convert-batch?ui_lang=en", data={"files": files},
                    content_type="multipart/form-data")
    assert r.get_json()["error"] == (
        f"At most {app_module.MAX_BATCH_FILES} files at once — "
        f"please convert in smaller groups."), r.get_json()


def test_batch_item_unsupported_en():
    r = CLIENT.post("/convert-batch",
                    data={"files": [_f("kaputt.xyz")], "ui_lang": "en"},
                    content_type="multipart/form-data")
    j = r.get_json()
    assert j["ok"] and j["results"][0]["status"] == "error"
    assert j["results"][0]["error"] == \
        f"File type '.xyz' not supported. Possible: {EXTS}", j["results"][0]


def test_zip_none_found_de_en():
    entries = [{"id": "deadbeef00.md", "name": "x.md"}]
    r = CLIENT.post("/download-batch", json={"files": entries})
    assert r.get_json()["error"] == ("Keine gueltigen Dateien fuer den "
                                     "Download gefunden (evtl. Server neu "
                                     "gestartet)."), r.get_json()
    r = CLIENT.post("/download-batch",
                    json={"files": entries, "ui_lang": "en"})
    assert r.get_json()["error"] == ("No valid files found for download "
                                     "(the server may have been restarted)."), \
        r.get_json()


# ---------------------------------------------------------------------------
# PLAIN-TEXT-404, ORIGIN-403
# ---------------------------------------------------------------------------

def test_download_404_plaintext_de_en():
    r = CLIENT.get("/download/gibtsnicht.md")
    assert r.status_code == 404
    assert r.get_data(as_text=True) == \
        "Datei nicht gefunden (evtl. Server neu gestartet).", r.get_data()
    r = CLIENT.get("/download/gibtsnicht.md?ui_lang=en")
    assert r.get_data(as_text=True) == \
        "File not found (the server may have been restarted).", r.get_data()


def test_origin_403_bilingual():
    """Die 403 hat bewusst keine Kanal-Logik: EIN zweisprachiger Text."""
    r = CLIENT.post("/convert-batch", data={},
                    content_type="multipart/form-data",
                    headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    err = r.get_json()["error"]
    assert "abgelehnt" in err and "rejected" in err, err


# ---------------------------------------------------------------------------
# CONVERTER-FEHLER (UnreadablePdfError, Lesefehler)
# ---------------------------------------------------------------------------

def test_unreadable_pdf_de_en():
    path = os.path.join(FIXTURES, "errors_lang_defekt.pdf")
    build_three_text_pages_pdf(path)
    with _break_pages({1, 2, 3}), _no_ocr():
        r_de = convert_file(path)
        r_en = convert_file(path, lang="en")
    assert not r_de["ok"] and not r_en["ok"]
    assert r_de["error"].startswith("Keine der 3 Seite(n)"), r_de["error"]
    assert r_en["error"] == ("None of the 3 page(s) of this PDF could be "
                             "read - not even via text recognition. The "
                             "file is probably damaged."), r_en["error"]
    # der rohe technische Grund bleibt unuebersetzt im Detail-Feld
    assert "Simulierter Seitendefekt" in r_en.get("error_detail", ""), \
        r_en.get("error_detail")


def test_read_failed_de_en():
    path = os.path.join(FIXTURES, "errors_lang_kaputt.docx")
    with open(path, "wb") as f:
        f.write(b"das ist kein echtes docx")
    r_de = convert_file(path)
    r_en = convert_file(path, lang="en")
    assert not r_de["ok"] and not r_en["ok"]
    assert r_de["error"].startswith("Fehler beim Lesen der Datei:"), \
        r_de["error"]
    assert r_en["error"].startswith("Error reading the file:"), r_en["error"]


# ---------------------------------------------------------------------------
# KATALOG-PARITÄT (deckt auch die nicht auslösbaren Pfade ab, z.B.
# open_windows_only auf einem Windows-Rechner)
# ---------------------------------------------------------------------------

def test_catalog_parity():
    assert set(_ERRORS["de"].keys()) == set(_ERRORS["en"].keys())
    for key in _ERRORS["de"]:
        ph_de = set(re.findall(r"\{(\w+)\}", _ERRORS["de"][key]))
        ph_en = set(re.findall(r"\{(\w+)\}", _ERRORS["en"][key]))
        assert ph_de == ph_en, f"Platzhalter weichen ab bei '{key}'"


# ---------------------------------------------------------------------------
# DOM-ENDE-ZU-ENDE (Playwright, Server auf :8770)
# ---------------------------------------------------------------------------

def dom_test_error_language(page):
    """Sichtbarer Fehlerfall (nicht unterstützter Dateityp) in DE und EN.
    Zweite Datei mit anderem Namen, damit das change-Event sicher feuert."""
    path_de = os.path.join(FIXTURES, "errors_dom_de.xyz")
    path_en = os.path.join(FIXTURES, "errors_dom_en.xyz")
    for p in (path_de, path_en):
        with open(p, "w", encoding="utf-8") as f:
            f.write("Inhalt egal - der Typ ist nicht unterstuetzt.")
    page.click("#tabConv")
    page.set_input_files("#fileInput", path_de)
    page.wait_for_selector("#convStatus.show.error", timeout=10000)
    assert "nicht unterstuetzt" in page.locator("#convStatus").inner_text(), \
        page.locator("#convStatus").inner_text()
    page.click('#langToggle .lang-btn[data-lang="en"]')
    page.wait_for_timeout(200)
    page.set_input_files("#fileInput", path_en)
    page.wait_for_function(
        "document.querySelector('#convStatus').innerText"
        ".includes('not supported')", timeout=10000)
    page.click('#langToggle .lang-btn[data-lang="de"]')


ALL_TESTS = [
    test_de_default_no_file,
    test_de_default_unsupported_type_unified,
    test_en_unsupported_type_form,
    test_en_no_file_query_only,
    test_channel_form_beats_query,
    test_channel_json_body_zip_no_files,
    test_413_query_lang_de_and_en,
    test_invalid_lang_falls_back_de,
    test_batch_no_files_de_en,
    test_batch_too_many_matches_client_wording,
    test_batch_item_unsupported_en,
    test_zip_none_found_de_en,
    test_download_404_plaintext_de_en,
    test_origin_403_bilingual,
    test_unreadable_pdf_de_en,
    test_read_failed_de_en,
    test_catalog_parity,
]

DOM_TESTS = [
    dom_test_error_language,
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
