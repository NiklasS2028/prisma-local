# -*- coding: utf-8 -*-
"""
test_blockC_dom.py
------------------
DOM-Tests für Block C (Statistik-Tab) via Playwright gegen den laufenden
Server. Prüft die Zähl-Regeln Ende-zu-Ende durch die echte Oberfläche:

  - Konvertieren allein zählt NICHT - erst Download/Kopie (und nur einmal)
  - Re-Analyse desselben Prompts zählt nicht doppelt, geänderter Text schon
  - Statistik-Tab rendert (DE/EN), Meilensteine, Donut, Format-Balken
  - Reset-Button mit zweistufiger Sicherheitsabfrage
  - Screenshots des Tabs in beiden Themes

Aufruf:  python tests/test_blockC_dom.py
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


def upload_txt(page, name="stats_smoke.txt"):
    path = os.path.join(FIXTURES, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("Testtext für die Statistik-Zählung.\n\n\n\nMit etwas Ballast.")
    page.click("#tabConv")
    page.set_input_files("#fileInput", path)
    page.wait_for_selector(".result.show", timeout=10000)


def test_convert_counts_only_on_use(page):
    """Konvertieren zählt nicht - erst die Kopie. Und nur EINMAL pro Ergebnis."""
    server_reset()
    upload_txt(page)
    assert server_stats()["files_converted"] == 0, \
        "Konvertierung wurde gezählt, obwohl das Ergebnis nie genutzt wurde"
    page.click("#copyBtn")
    page.wait_for_timeout(400)
    assert server_stats()["files_converted"] == 1, "Kopie hat nicht gezählt"
    # Mehrfaches Kopieren + Download desselben Ergebnisses: bleibt 1
    page.click("#copyBtn")
    page.wait_for_timeout(400)
    page.click("#downloadBtn")
    page.wait_for_timeout(600)
    s = server_stats()
    assert s["files_converted"] == 1, \
        f"Dasselbe Ergebnis wurde mehrfach gezählt ({s['files_converted']})"
    assert s["format_counts"]["txt"] == 1
    assert s["tokens_saved_total"] >= 0


def test_second_conversion_counts_again(page):
    server_reset()
    upload_txt(page, "stats_a.txt")
    page.click("#copyBtn")
    page.wait_for_timeout(400)
    upload_txt(page, "stats_b.txt")
    page.click("#downloadBtn")
    page.wait_for_timeout(600)
    assert server_stats()["files_converted"] == 2, \
        "Zweites Ergebnis wurde nicht separat gezählt"


def test_prompt_counted_once_per_content(page):
    """Re-Analyse desselben Textes zählt nicht doppelt, neuer Text schon."""
    server_reset()
    page.click("#tabTrainer")
    page.click("#demoWeak")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    page.wait_for_timeout(400)
    assert server_stats()["prompts_analyzed"] == 1
    # Denselben Text erneut analysieren -> bleibt 1
    page.click("#analyzeBtn")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    page.wait_for_timeout(400)
    assert server_stats()["prompts_analyzed"] == 1, \
        "Re-Analyse desselben Prompts wurde doppelt gezählt"
    # Geänderter Text -> zählt
    page.click("#demoStrong")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    page.wait_for_timeout(400)
    s = server_stats()
    assert s["prompts_analyzed"] == 2
    assert s["score_buckets"]["red"] == 1 and s["score_buckets"]["green"] == 1
    assert s["best_score"] == 90


def test_stats_tab_renders(page):
    server_reset()
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 1000, "format": "pdf"})
    requests.post(BASE + "/stats/count_prompt", json={"score": 90, "ampel": "gruen"})
    page.click("#tabStats")
    page.wait_for_timeout(1400)  # fetch + countUp
    assert page.locator("#pageTitle").inner_text() == "Deine Arbeit in Zahlen."
    assert page.locator("#statFiles").inner_text() == "1"
    assert page.locator("#statPrompts").inner_text() == "1"
    assert page.locator("#statTokens").inner_text() == "1.000"  # de-DE-Format
    assert "Seiten" in page.locator("#statPages").inner_text()
    assert "geschätzt" in page.locator("#statPages").inner_text(), \
        "Seiten-Übersetzung nicht als Schätzung gekennzeichnet"
    assert "geschätzt" in page.locator("#statCost").inner_text().lower() or \
           "Schätzung" in page.locator("#statCost").inner_text(), \
        "Kostenangabe nicht als Schätzung gekennzeichnet"
    assert page.locator("#statBest").inner_text() == "90"
    assert "grün" in page.locator("#bucketLine").inner_text()
    assert "✓ 1" in page.locator("#msList").inner_text(), "Meilenstein '1 erreicht' fehlt"
    assert "10" in page.locator("#msList").inner_text(), "Nächster Meilenstein fehlt"
    assert "PDF" in page.locator("#formatBars").inner_text()
    # Transparenz-Satz sichtbar im Tab
    priv = page.locator("#statsPrivacy").inner_text()
    assert "nur" in priv and "Zahlen" in priv and page.locator("#statsPrivacy").is_visible()


def test_stats_tab_english(page):
    server_reset()
    requests.post(BASE + "/stats/count_prompt", json={"score": 48, "ampel": "gelb"})
    page.click('#langToggle .lang-btn[data-lang="en"]')
    page.click("#tabStats")
    page.wait_for_timeout(1400)
    assert page.locator("#pageTitle").inner_text() == "Your work in numbers."
    assert "yellow" in page.locator("#bucketLine").inner_text()
    assert "never leave" in page.locator("#statsPrivacy").inner_text()
    assert page.locator("#tabStats").inner_text() == "Stats"


def test_reset_two_step(page):
    server_reset()
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 10, "format": "csv"})
    page.click("#tabStats")
    page.wait_for_timeout(800)
    btn = page.locator("#statsResetBtn")
    original_label = btn.inner_text()
    # Erster Klick: nur scharf schalten, noch kein Reset
    btn.click()
    assert btn.inner_text() != original_label, "Sicherheitsabfrage fehlt"
    assert server_stats()["files_converted"] == 1, "Erster Klick hat schon zurückgesetzt!"
    # Zweiter Klick: Reset
    btn.click()
    page.wait_for_timeout(600)
    assert server_stats()["files_converted"] == 0, "Reset hat nicht gewirkt"
    assert page.locator("#statFiles").inner_text() == "0", "Anzeige nicht aktualisiert"


def test_empty_state(page):
    server_reset()
    page.click("#tabStats")
    page.wait_for_timeout(800)
    assert page.locator("#statBest").inner_text() == "–", \
        "Bester Score muss ohne Analysen leer sein"
    line = page.locator("#bucketLine").inner_text()
    assert "Noch keine" in line, f"Leerzustand des Donuts fehlt: {line}"


def test_screenshots_stats_both_themes(page):
    server_reset()
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 84000, "format": "pdf"})
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 12000, "format": "docx"})
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 4000, "format": "xlsx"})
    for score, ampel in ((29, "rot"), (48, "gelb"), (90, "gruen"), (81, "gruen")):
        requests.post(BASE + "/stats/count_prompt", json={"score": score, "ampel": ampel})
    for theme in ("light", "dark"):
        page.click(f'#themeToggle .lang-btn[data-theme="{theme}"]')
        page.click("#tabStats")
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOTS, f"{theme}_stats.png"), full_page=True)
        assert os.path.getsize(os.path.join(SHOTS, f"{theme}_stats.png")) > 10000
    server_reset()


ALL_TESTS = [
    test_convert_counts_only_on_use,
    test_second_conversion_counts_again,
    test_prompt_counted_once_per_content,
    test_stats_tab_renders,
    test_stats_tab_english,
    test_reset_two_step,
    test_empty_state,
    test_screenshots_stats_both_themes,
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
