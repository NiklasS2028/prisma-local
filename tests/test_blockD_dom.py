# -*- coding: utf-8 -*-
"""
test_blockD_dom.py
------------------
DOM-Tests für den Statistik-Feinschliff + Block D gegen den laufenden Server.

  Teil 1: Leerzustände im Statistik-Tab (Format-Hinweis statt Nullbalken,
          sanfte Meilenstein-Zeile bei 0) - in DE und EN, Screenshots beide Themes.
  D1:     Kein horizontaler Layout-Sprung beim Umschalten von Sprache und
          Theme - auch nicht, wenn die Scrollbar durch langen Inhalt erscheint.
  D2:     "Neue Datei"-Reset im Konverter: Panel weg, Dropzone frisch,
          zweite Datei läuft sauber durch, Statistik zählt korrekt.

Aufruf:  python tests/test_blockD_dom.py
"""

import os
import sys
import traceback

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8770"
HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
SHOTS = os.path.join(HERE, "screenshots")
os.makedirs(FIXTURES, exist_ok=True)
os.makedirs(SHOTS, exist_ok=True)


def server_stats():
    return requests.get(BASE + "/stats", timeout=10).json()


def server_reset():
    requests.post(BASE + "/stats/reset", timeout=10)


def fresh_page(browser):
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        permissions=["clipboard-read", "clipboard-write"],
        accept_downloads=True,
    )
    page = ctx.new_page()
    page.goto(BASE)
    return page


def upload_txt(page, name):
    path = os.path.join(FIXTURES, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("Inhalt für Block-D-Tests.\n\n\n\nZweite Zeile.")
    page.click("#tabConv")
    page.set_input_files("#fileInput", path)
    page.wait_for_selector(".result.show", timeout=10000)


def wrap_x(page):
    return page.locator(".wrap").bounding_box()["x"]


# ---------------------------------------------------------------------------
# TEIL 1: LEERZUSTAENDE STATISTIK
# ---------------------------------------------------------------------------

def test_format_breakdown_empty_state(page):
    server_reset()
    page.click("#tabStats")
    page.wait_for_timeout(800)
    box = page.locator("#formatBars").inner_text()
    assert "Noch keine Dateien konvertiert." in box, f"DE-Leerhinweis fehlt: {box}"
    assert page.locator(".fmt-row").count() == 0, "Nullbalken trotz Leerzustand"
    # Englisch
    page.click('#langToggle .lang-btn[data-lang="en"]')
    page.wait_for_timeout(300)
    box = page.locator("#formatBars").inner_text()
    assert "No files converted yet." in box, f"EN-Leerhinweis fehlt: {box}"


def test_format_breakdown_appears_with_data(page):
    server_reset()
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 10, "format": "pdf"})
    page.click("#tabStats")
    page.wait_for_timeout(800)
    assert page.locator(".fmt-row").count() == 6, "Balken fehlen trotz Daten"
    assert "Noch keine" not in page.locator("#formatBars").inner_text()


def test_milestone_empty_wording(page):
    server_reset()
    page.click("#tabStats")
    page.wait_for_timeout(800)
    ms = page.locator("#msList").inner_text()
    assert "noch keine" in ms, f"Sanfter Leerzustand fehlt: {ms}"
    assert "nächstes Ziel: 1" not in ms, f"'nächstes Ziel: 1' wirkt verloren: {ms}"
    assert "Download" in ms and "Analyse" in ms, f"Kategorie-Hinweise fehlen: {ms}"
    # Sobald >=1: bestehende Logik
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 10, "format": "pdf"})
    page.click("#tabConv")
    page.click("#tabStats")
    page.wait_for_timeout(800)
    ms = page.locator("#msList").inner_text()
    assert "✓ 1 erreicht" in ms and "nächstes Ziel: 10" in ms, f"Normale Logik kaputt: {ms}"


def test_empty_state_screenshots(page):
    server_reset()
    for theme in ("light", "dark"):
        page.click(f'#themeToggle .lang-btn[data-theme="{theme}"]')
        page.click("#tabStats")
        page.wait_for_timeout(900)
        p = os.path.join(SHOTS, f"{theme}_stats_empty.png")
        page.screenshot(path=p, full_page=True)
        assert os.path.getsize(p) > 10000


# ---------------------------------------------------------------------------
# D1: KEIN HORIZONTALER SPRUNG BEIM UMSCHALTEN
# ---------------------------------------------------------------------------

def test_no_horizontal_jump(page):
    """Die X-Position der zentralen Spalte muss über alle Umschalt-Aktionen
    identisch bleiben - auch wenn die Scrollbar durch langen Inhalt kommt."""
    positions = {}
    positions["start (kurz, hell, de)"] = wrap_x(page)

    # Sprache hin und zurück
    page.click('#langToggle .lang-btn[data-lang="en"]')
    positions["nach EN"] = wrap_x(page)
    page.click('#langToggle .lang-btn[data-lang="de"]')
    positions["zurück DE"] = wrap_x(page)

    # Theme hin und zurück
    page.click('#themeToggle .lang-btn[data-theme="dark"]')
    positions["nach dunkel"] = wrap_x(page)
    page.click('#themeToggle .lang-btn[data-theme="light"]')
    positions["zurück hell"] = wrap_x(page)

    # Langen Inhalt erzeugen -> Scrollbar erscheint
    page.click("#tabTrainer")
    page.click("#demoWeak")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    page.wait_for_timeout(300)
    positions["mit Scrollbar (Trainer-Ergebnis)"] = wrap_x(page)

    # Und dort nochmal beide Umschalter
    page.click('#themeToggle .lang-btn[data-theme="dark"]')
    positions["Scrollbar + dunkel"] = wrap_x(page)
    page.click('#langToggle .lang-btn[data-lang="en"]')
    positions["Scrollbar + EN"] = wrap_x(page)

    baseline = positions["start (kurz, hell, de)"]
    drift = {k: v for k, v in positions.items() if abs(v - baseline) > 0.5}
    for k, v in positions.items():
        print(f"        wrap.x [{k}]: {v:.1f}")
    assert not drift, f"Spalte springt horizontal: {drift} (Basis {baseline})"


# ---------------------------------------------------------------------------
# D2: "NEUE DATEI" / RESET IM KONVERTER
# ---------------------------------------------------------------------------

def test_reset_clears_result(page):
    server_reset()
    upload_txt(page, "blockd_a.txt")
    assert page.locator("#convResult").is_visible()
    page.click("#convResetBtn")
    page.wait_for_timeout(300)
    assert not page.locator("#convResult").is_visible(), "Ergebnis-Panel klebt fest"
    assert page.locator("#preview").inner_text() == "", "Vorschau nicht geleert"
    assert page.locator("#meta").inner_text().strip() == "", "Meta-Chips nicht geleert"
    assert page.eval_on_selector("#fileInput", "el => el.value") == "", \
        "Datei-Input nicht geleert"


def test_reset_then_same_file_again(page):
    """Nach Reset muss auch DIESELBE Datei erneut wählbar sein
    (fileInput.value wurde geleert, sonst feuert 'change' nicht)."""
    upload_txt(page, "blockd_same.txt")
    page.click("#convResetBtn")
    page.wait_for_timeout(200)
    upload_txt(page, "blockd_same.txt")
    assert page.locator("#convResult").is_visible(), "Dieselbe Datei läuft nach Reset nicht"


def test_reset_stats_counting_stays_correct(page):
    """Reset darf die Zählung weder doppeln noch verschlucken."""
    server_reset()
    # Erste Datei: nutzen (Kopie) -> zählt 1, dann Reset
    upload_txt(page, "blockd_b.txt")
    page.click("#copyBtn")
    page.wait_for_timeout(400)
    assert server_stats()["files_converted"] == 1
    page.click("#convResetBtn")
    page.wait_for_timeout(200)
    assert server_stats()["files_converted"] == 1, "Reset selbst darf nicht zählen"
    # Zweite Datei nach Reset: erst bei Nutzung zählen, genau einmal
    upload_txt(page, "blockd_c.txt")
    assert server_stats()["files_converted"] == 1, \
        "Konvertierung nach Reset zählte ohne Nutzung"
    page.click("#copyBtn")
    page.wait_for_timeout(400)
    page.click("#copyBtn")
    page.wait_for_timeout(400)
    assert server_stats()["files_converted"] == 2, \
        f"Zweite Datei falsch gezählt: {server_stats()['files_converted']}"


def test_reset_without_use_never_counts(page):
    """Konvertieren -> Reset OHNE Nutzung: darf nie zählen (auch später nicht)."""
    server_reset()
    upload_txt(page, "blockd_d.txt")
    page.click("#convResetBtn")
    page.wait_for_timeout(200)
    # Buttons des alten Ergebnisses sind weg; Zustand ist verworfen
    assert server_stats()["files_converted"] == 0
    # Nächste Datei zählt regulär bei Nutzung
    upload_txt(page, "blockd_e.txt")
    page.click("#downloadBtn")
    page.wait_for_timeout(600)
    assert server_stats()["files_converted"] == 1


def test_reset_btn_language(page):
    page.click("#tabConv")
    upload_txt(page, "blockd_lang.txt")
    assert page.locator("#convResetBtn").inner_text() == "Neue Datei"
    page.click('#langToggle .lang-btn[data-lang="en"]')
    assert page.locator("#convResetBtn").inner_text() == "New file"


ALL_TESTS = [
    test_format_breakdown_empty_state,
    test_format_breakdown_appears_with_data,
    test_milestone_empty_wording,
    test_empty_state_screenshots,
    test_no_horizontal_jump,
    test_reset_clears_result,
    test_reset_then_same_file_again,
    test_reset_stats_counting_stays_correct,
    test_reset_without_use_never_counts,
    test_reset_btn_language,
]

if __name__ == "__main__":
    from playwright.sync_api import sync_playwright

    passed, failed = 0, 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for test in ALL_TESTS:
            name = test.__name__
            page = fresh_page(browser)
            try:
                test(page)
                print(f"  PASS  {name}")
                passed += 1
            except Exception:
                print(f"  FAIL  {name}")
                traceback.print_exc()
                failed += 1
            finally:
                page.context.close()
        browser.close()
    server_reset()
    print(f"\n{passed} bestanden, {failed} fehlgeschlagen.")
    sys.exit(1 if failed else 0)
