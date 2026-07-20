# -*- coding: utf-8 -*-
"""
test_blockC_dom.py
------------------
DOM-Tests für Block C (Statistik-Tab) via Playwright gegen den laufenden
Server. Prüft die Zähl-Regeln Ende-zu-Ende durch die echte Oberfläche:

  - Konvertieren allein zählt NICHT - erst Download/Kopie (und nur einmal)
  - Re-Analyse desselben Prompts zählt nicht doppelt, geänderter Text schon
  - Statistik-Tab rendert (DE/EN), Meilensteine, Schwachstellen-Ranking,
    Format-Balken; Donut und Bester Score existieren nicht mehr
  - Ranking sortiert absteigend, Empty-State statt Null-Balken
  - Ende-zu-Ende: Analyze-Klick aktualisiert das Ranking, Live-Tippen nicht
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
    # Demo schwach: context/specificity/format/role/examples rot;
    # Demo stark: nur examples rot -> examples zählt 2x
    cm = s["criteria_missed"]
    assert cm["context"] == 1 and cm["specificity"] == 1
    assert cm["format"] == 1 and cm["role"] == 1
    assert cm["examples"] == 2
    assert cm["task"] == 0 and cm["input"] == 0


def test_stats_tab_renders(page):
    server_reset()
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 1000, "format": "pdf"})
    requests.post(BASE + "/stats/count_prompt", json={"missed": ["examples"]})
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
    # Schwachstellen-Ranking: das gezählte Kriterium erscheint mit Zähler 1
    bars = page.locator("#weakBars").inner_text()
    assert "Beispiele" in bars, f"Kriterium fehlt im Ranking: {bars}"
    assert "1" in bars, f"Zähler fehlt im Ranking: {bars}"
    assert "✓ 1" in page.locator("#msList").inner_text(), "Meilenstein '1 erreicht' fehlt"
    assert "10" in page.locator("#msList").inner_text(), "Nächster Meilenstein fehlt"
    assert "PDF" in page.locator("#formatBars").inner_text()
    # Transparenz-Satz sichtbar im Tab
    priv = page.locator("#statsPrivacy").inner_text()
    assert "nur" in priv and "Zahlen" in priv and page.locator("#statsPrivacy").is_visible()


def test_stats_tab_english(page):
    server_reset()
    requests.post(BASE + "/stats/count_prompt", json={"missed": ["context"]})
    page.click('#langToggle .lang-btn[data-lang="en"]')
    page.click("#tabStats")
    page.wait_for_timeout(1400)
    assert page.locator("#pageTitle").inner_text() == "Your work in numbers."
    assert page.locator("#weakTitle").inner_text() == "Your most common weak spots"
    assert "Context" in page.locator("#weakBars").inner_text(), \
        "EN-Kriterienname fehlt im Ranking"
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
    """Frisch installiert (alle Zähler 0): Empty-State-Botschaft statt
    sieben Null-Balken."""
    server_reset()
    page.click("#tabStats")
    page.wait_for_timeout(800)
    bars = page.locator("#weakBars").inner_text()
    assert "Noch keine" in bars, f"Empty-State des Rankings fehlt: {bars}"
    assert page.locator("#weakBars .fmt-row").count() == 0, \
        "Null-Balken statt Empty-State"


def _build_image_pdf(path):
    """Reine Bild-PDF (eine Seite Text als Bild) fuer den OCR-Zaehl-Test."""
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 54)
    except OSError:
        font = ImageFont.load_default()
    draw.text((100, 200), "OCR ZAEHLTEST 8888", fill="black", font=font)
    c = canvas.Canvas(path, pagesize=(595.27, 841.89))
    c.drawImage(ImageReader(img), 0, 0, width=595.27, height=841.89)
    c.showPage()
    c.save()


def test_g_ocr_counts_zero_saved_tokens(page):
    """Block G: OCR-Konvertierung zaehlt die Datei, aber 0 gesparte Tokens
    (OCR spart nichts, es ermoeglicht). Nicht-OCR als Gegenprobe."""
    server_reset()
    pdf_path = os.path.join(FIXTURES, "g_ocr_zaehlung.pdf")
    _build_image_pdf(pdf_path)
    page.click("#tabConv")
    page.set_input_files("#fileInput", pdf_path)
    page.wait_for_selector(".result.show", timeout=90000)  # OCR braucht Zeit
    page.click("#copyBtn")
    page.wait_for_timeout(600)
    s = server_stats()
    assert s["files_converted"] == 1, "OCR-Datei wurde nicht gezaehlt"
    assert s["tokens_saved_total"] == 0, \
        f"OCR darf keine Token-Ersparnis zaehlen: {s['tokens_saved_total']}"
    # Gegenprobe: Nicht-OCR-Ersparnis zaehlt weiterhin
    txt_path = os.path.join(FIXTURES, "g_ocr_gegenprobe.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("Zeile mit Inhalt.   \n\n\n\n\n" * 30)  # viel Ballast
    page.set_input_files("#fileInput", txt_path)
    page.wait_for_selector(".result.show", timeout=10000)
    page.click("#copyBtn")
    page.wait_for_timeout(600)
    s = server_stats()
    assert s["files_converted"] == 2
    assert s["tokens_saved_total"] > 0, "Nicht-OCR-Ersparnis fehlt (Gegenprobe)"


def test_g2_pages_singular_plural(page):
    """Block G2: '1 Seite' statt '1 Seiten' (EN: '1 page'), Plural bleibt."""
    server_reset()
    # 500 gesparte Tokens ~ genau 1 Seite
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 500, "format": "txt"})
    page.click("#tabStats")
    page.wait_for_timeout(1200)
    txt = page.locator("#statPages").inner_text()
    assert "1 Seite" in txt, f"Seitenzeile fehlt: {txt}"
    assert "1 Seiten" not in txt, f"Plural-Bug '1 Seiten': {txt}"
    page.click('#langToggle .lang-btn[data-lang="en"]')
    page.wait_for_timeout(400)
    txt = page.locator("#statPages").inner_text()
    assert "1 page" in txt and "1 pages" not in txt, f"EN-Plural-Bug: {txt}"
    # Plural-Fall: 1000 Tokens ~ 2 Seiten
    page.click('#langToggle .lang-btn[data-lang="de"]')
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 500, "format": "txt"})
    page.reload()
    page.click("#tabStats")
    page.wait_for_timeout(1200)
    txt = page.locator("#statPages").inner_text()
    assert "2 Seiten" in txt, f"Plural-Fall kaputt: {txt}"


def test_weak_ranking_sorted(page):
    """F4: sieben Balken (auch input), absteigend sortiert, Zähler dran."""
    server_reset()
    requests.post(BASE + "/stats/count_prompt", json={"missed": ["format", "role"]})
    requests.post(BASE + "/stats/count_prompt", json={"missed": ["format"]})
    requests.post(BASE + "/stats/count_prompt", json={"missed": ["format", "context"]})
    page.click("#tabStats")
    page.wait_for_timeout(800)
    rows = page.locator("#weakBars .fmt-row")
    assert rows.count() == 7, f"{rows.count()} Balken statt 7"
    names = page.locator("#weakBars .fmt-name").all_inner_texts()
    counts = [int(c) for c in page.locator("#weakBars .fmt-count").all_inner_texts()]
    assert names[0] == "Format" and counts[0] == 3, \
        f"Spitzenreiter falsch: {names[0]}/{counts[0]}"
    assert counts == sorted(counts, reverse=True), f"Nicht absteigend: {counts}"
    assert "Material" in names, "input-Kriterium fehlt im Ranking"


def test_donut_and_best_score_removed(page):
    """F2: Donut- und Best-Score-Elemente existieren nicht mehr im DOM."""
    page.click("#tabStats")
    page.wait_for_timeout(400)
    for sel in ("#segRed", "#segYellow", "#segGreen", "#donutTotal",
                "#bucketLine", "#statBest", "#bestTitle", "#bestSub",
                "#donutTitle"):
        assert page.locator(sel).count() == 0, f"Altes Element noch im DOM: {sel}"


def test_e2e_analyze_updates_ranking_live_does_not(page):
    """F4 Ende-zu-Ende: Live-Tippen ändert das Ranking nicht, der
    Analyze-Klick schon."""
    server_reset()
    page.click("#tabTrainer")
    page.fill("#promptInput", "schreib mal irgendwas über hunde oder so")
    page.wait_for_selector(".pt-result.show", timeout=5000)  # Live-Anzeige
    page.wait_for_timeout(500)
    page.click("#tabStats")
    page.wait_for_timeout(800)
    assert "Noch keine" in page.locator("#weakBars").inner_text(), \
        "Live-Tippen hat das Ranking verändert"
    page.click("#tabTrainer")
    page.click("#analyzeBtn")
    page.wait_for_timeout(600)
    page.click("#tabStats")
    page.wait_for_timeout(800)
    bars = page.locator("#weakBars").inner_text()
    assert "Kontext" in bars and page.locator("#weakBars .fmt-row").count() == 7, \
        f"Analyze-Klick hat das Ranking nicht aktualisiert: {bars}"


def outputs_info():
    return requests.get(BASE + "/outputs/info", timeout=10).json()


def test_outputs_manage_two_step(page):
    """Block F.5: 'Ausgaben verwalten' - Anzeige + zweistufiges Löschen,
    erster Klick schaltet nur scharf, Timeout entschärft wieder."""
    requests.post(BASE + "/outputs/clear", timeout=10)
    upload_txt(page, "f5_outputs.txt")   # erzeugt genau eine Ausgabedatei
    assert outputs_info()["count"] == 1
    page.click("#tabStats")
    page.wait_for_timeout(800)
    info_text = page.locator("#outInfo").inner_text()
    assert "1" in info_text and ("B" in info_text or "KB" in info_text), \
        f"Anzahl/Größe fehlen: {info_text}"
    btn = page.locator("#outputsClearBtn")
    original_label = btn.inner_text()
    # Erster Klick: nur scharf schalten, noch nichts löschen
    btn.click()
    assert btn.inner_text() != original_label, "Sicherheitsabfrage fehlt"
    assert outputs_info()["count"] == 1, "Erster Klick hat schon gelöscht!"
    # Timeout: nach 4s wieder entschärft
    page.wait_for_timeout(4300)
    assert btn.inner_text() == original_label, "Timer entschärft nicht"
    assert outputs_info()["count"] == 1
    # Scharf schalten + bestätigen: jetzt wird gelöscht
    btn.click()
    btn.click()
    page.wait_for_timeout(600)
    assert outputs_info()["count"] == 0, "Löschen hat nicht gewirkt"
    empty_text = page.locator("#outInfo").inner_text()
    assert empty_text != info_text and "Keine" in empty_text, \
        f"Leerzustand fehlt: {empty_text}"


def test_outputs_manage_english(page):
    requests.post(BASE + "/outputs/clear", timeout=10)
    page.click('#langToggle .lang-btn[data-lang="en"]')
    page.click("#tabStats")
    page.wait_for_timeout(800)
    assert page.locator("#outTitle").inner_text() == "Manage outputs"
    assert page.locator("#outputsClearBtn").inner_text() == "Delete stored outputs"
    assert "No stored" in page.locator("#outInfo").inner_text()


def test_screenshots_stats_both_themes(page):
    server_reset()
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 84000, "format": "pdf"})
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 12000, "format": "docx"})
    requests.post(BASE + "/stats/count_file", json={"saved_tokens": 4000, "format": "xlsx"})
    for missed in (["context", "format", "role"], ["specificity"],
                   ["examples"], []):
        requests.post(BASE + "/stats/count_prompt", json={"missed": missed})
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
    test_g_ocr_counts_zero_saved_tokens,
    test_g2_pages_singular_plural,
    test_weak_ranking_sorted,
    test_donut_and_best_score_removed,
    test_e2e_analyze_updates_ranking_live_does_not,
    test_outputs_manage_two_step,
    test_outputs_manage_english,
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
