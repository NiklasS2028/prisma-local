# -*- coding: utf-8 -*-
"""
test_block3_dom.py
------------------
DOM-Tests für Block 3 (index.html) via Playwright gegen den laufenden
Server auf http://localhost:8770. Vorher starten:  python app.py

Geprüft wird:
  - Sprach-Toggle DE/EN inkl. localStorage-Persistenz (kiw_lang)
  - Demo-Buttons (schwach/mittel/stark, sprachabhängig, Kalibrierung 29/48/90)
  - hinweis-Info-Box bei "Hunde" + verstecktem Vorlagen-Bereich
  - Re-Analyse-Button "In Eingabe übernehmen"
  - ui_lang wird an /analyze_prompt geschickt (englische Check-Titel)
  - "universal" heißt jetzt "Anderes"/"Other"
  - Konverter-Regression (txt-Upload durchläuft die UI)

Aufruf:  python tests/test_block3_dom.py
"""

import os
import sys
import traceback

BASE = "http://localhost:8770"
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
os.makedirs(FIXTURES, exist_ok=True)


def fresh_page(browser):
    """Neue Seite mit leerem localStorage (Sprachwahl zurückgesetzt)."""
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(BASE)
    page.evaluate("localStorage.removeItem('kiw_lang')")
    page.reload()
    return page


def test_default_german(page):
    assert page.locator("#pageTitle").inner_text() == "Datei rein, effizientes Format raus."
    assert page.locator("#tabTrainer").inner_text() == "Prompt-Trainer"
    assert page.locator('#langToggle .lang-btn[data-lang="de"]').get_attribute("class").count("sel")


def test_language_toggle_and_persistence(page):
    page.click('#langToggle .lang-btn[data-lang="en"]')
    assert page.locator("#pageTitle").inner_text() == "File in, efficient format out."
    assert page.locator("#tabTrainer").inner_text() == "Prompt Trainer"
    assert page.evaluate("localStorage.getItem('kiw_lang')") == "en"
    # Persistenz: Reload behält Englisch
    page.reload()
    assert page.locator("#pageTitle").inner_text() == "File in, efficient format out."
    # zurück auf Deutsch
    page.click('#langToggle .lang-btn[data-lang="de"]')
    assert page.locator("#pageTitle").inner_text() == "Datei rein, effizientes Format raus."


def test_universal_label(page):
    page.click('#tabTrainer')
    label = page.locator('#ptModels [data-m="universal"]').inner_text()
    assert label == "Anderes", f"universal-Button heißt '{label}' statt 'Anderes'"
    page.click('#langToggle .lang-btn[data-lang="en"]')
    label = page.locator('#ptModels [data-m="universal"]').inner_text()
    assert label == "Other", f"universal-Button (EN) heißt '{label}' statt 'Other'"
    page.click('#langToggle .lang-btn[data-lang="de"]')


def test_jargon_free_gpt_hint(page):
    page.click('#tabTrainer')
    page.click('#ptModels [data-m="gpt"]')
    hint = page.locator("#ptModelHint").inner_text()
    assert "Delimiter" not in hint, f"Jargon 'Delimiter' noch im Hint: {hint}"
    assert "Abschnitte" in hint, f"Neuer GPT-Hint fehlt: {hint}"
    page.click('#ptModels [data-m="claude"]')


def test_demo_buttons_calibration(page):
    page.click('#tabTrainer')
    expected = {"demoWeak": ("29", "rot"), "demoMedium": ("48", "gelb"),
                "demoStrong": ("90", "gruen")}
    for btn_id, (score, ampel) in expected.items():
        page.click(f"#{btn_id}")
        page.wait_for_selector(".pt-result.show", timeout=5000)
        page.wait_for_timeout(1200)  # countUp-Animation abwarten
        got_score = page.locator("#scoreBig").inner_text()
        got_class = page.locator("#scoreBig").get_attribute("class")
        assert got_score == score, f"{btn_id}: Score {got_score}, erwartet {score}"
        assert ampel in got_class, f"{btn_id}: Ampel-Klasse '{got_class}', erwartet {ampel}"


def test_demo_buttons_language_dependent(page):
    page.click('#tabTrainer')
    page.click('#langToggle .lang-btn[data-lang="en"]')
    page.click("#demoWeak")
    val = page.locator("#promptInput").input_value()
    assert "dogs" in val, f"Englischer Demo-Prompt fehlt: {val}"
    page.wait_for_selector(".pt-result.show", timeout=5000)
    # ui_lang=en wurde mitgeschickt -> englische Check-Titel
    titles = page.locator(".check-title").all_inner_texts()
    assert any("Clear task" in t for t in titles), f"Check-Titel nicht englisch: {titles}"
    page.click('#langToggle .lang-btn[data-lang="de"]')
    page.click("#demoWeak")
    val = page.locator("#promptInput").input_value()
    assert "hunde" in val.lower(), f"Deutscher Demo-Prompt fehlt: {val}"


def test_hinweis_box_and_hidden_template(page):
    page.click('#tabTrainer')
    page.fill("#promptInput", "Hunde")
    page.click("#analyzeBtn")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    # Info-Box sichtbar mit dem hinweis-Text
    assert page.locator("#ptHinweis").is_visible(), "hinweis-Box wird nicht angezeigt"
    hint = page.locator("#ptHinweis").inner_text()
    assert "Verb" in hint, f"hinweis-Text unerwartet: {hint}"
    # Vorlagen-Bereich (samt Kopier-Button) komplett versteckt
    assert not page.locator("#tplSection").is_visible(), \
        "Vorlagen-Bereich sichtbar trotz leerem Template"


def test_reanalyze_button(page):
    page.click('#tabTrainer')
    page.click("#demoStrong")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    assert page.locator("#tplSection").is_visible(), "Vorlagen-Bereich fehlt"
    tpl = page.locator("#tplOut").inner_text()
    assert "<task>" in tpl, f"Claude-Vorlage ohne <task>: {tpl[:120]}"
    page.click("#reanalyzeBtn")
    val = page.locator("#promptInput").input_value()
    assert "<task>" in val, "Vorlage wurde nicht in die Eingabe übernommen"
    # Lernschleife schließen: erneut analysieren funktioniert
    page.click("#analyzeBtn")
    page.wait_for_selector(".pt-result.show", timeout=5000)


def test_reanalyze_check1_template_roundtrip(page):
    """Re-Analyse-Check 1: Vorlage landet in der Eingabe und die erneute
    Analyse der (noch unausgefüllten) Vorlage läuft fehlerfrei durch."""
    page.click('#tabTrainer')
    page.click("#demoWeak")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    tpl = page.locator("#tplOut").inner_text()
    page.click("#reanalyzeBtn")
    assert page.locator("#promptInput").input_value() == tpl, \
        "Eingabefeld enthält nicht exakt die Vorlage"
    page.click("#analyzeBtn")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    assert page.locator("#scoreBig").inner_text() != "", "Re-Analyse liefert kein Ergebnis"


def test_reanalyze_check2_learning_loop_improves_score(page):
    """Re-Analyse-Check 2: Die Lernschleife wirkt. Schwacher Prompt (29/rot)
    -> Vorlage übernehmen -> Platzhalter ausfüllen (wie ein Nutzer es täte)
    -> erneut analysieren -> Score springt auf grün (90)."""
    page.click('#tabTrainer')
    page.click("#demoWeak")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    page.wait_for_timeout(1200)
    assert page.locator("#scoreBig").inner_text() == "29", "Ausgangsscore nicht 29"
    page.click("#reanalyzeBtn")
    assert "<task>" in page.locator("#promptInput").input_value(), "Vorlage fehlt in der Eingabe"
    # Nutzer füllt die [Platzhalter-Fragen] aus und konkretisiert die Aufgabe
    filled = (
        "<role>\nDu bist ein erfahrener Hundetrainer.\n</role>\n\n"
        "<context>\nIch schreibe einen Blogartikel für meinen Hunde-Blog, "
        "Zielgruppe sind Ersthundebesitzer.\n</context>\n\n"
        "<task>\nSchreibe einen 300-Wörter-Überblick über die 5 wichtigsten "
        "Punkte der Welpenerziehung.\n</task>\n\n"
        "<format>\nAls nummerierte Liste mit je 2-3 Sätzen pro Punkt.\n</format>"
    )
    page.fill("#promptInput", filled)
    page.click("#analyzeBtn")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    page.wait_for_timeout(1200)
    score = int(page.locator("#scoreBig").inner_text())
    klass = page.locator("#scoreBig").get_attribute("class")
    assert score >= 75, f"Lernschleife hebt den Score nicht auf grün (Score {score})"
    assert "gruen" in klass, f"Ampel nicht grün: {klass}"


def test_hinweis_hidden_after_normal_prompt(page):
    page.click('#tabTrainer')
    page.click("#demoMedium")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    assert not page.locator("#ptHinweis").is_visible(), \
        "hinweis-Box klebt nach normalem Prompt fest"


def test_converter_regression(page):
    txt_path = os.path.join(FIXTURES, "ui_smoke.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("Kurzer Testtext für die Konverter-Oberfläche.\n\n\n\nMit Leerzeilen.")
    page.click("#tabConv")
    page.set_input_files("#fileInput", txt_path)
    page.wait_for_selector(".result.show", timeout=10000)
    chips = page.locator("#meta").inner_text()
    assert "MARKDOWN" in chips, f"Format-Chip fehlt: {chips}"
    preview = page.locator("#preview").inner_text()
    assert "Testtext" in preview, "Vorschau leer"


ALL_TESTS = [
    test_default_german,
    test_language_toggle_and_persistence,
    test_universal_label,
    test_jargon_free_gpt_hint,
    test_demo_buttons_calibration,
    test_demo_buttons_language_dependent,
    test_hinweis_box_and_hidden_template,
    test_reanalyze_button,
    test_reanalyze_check1_template_roundtrip,
    test_reanalyze_check2_learning_loop_improves_score,
    test_hinweis_hidden_after_normal_prompt,
    test_converter_regression,
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
    print(f"\n{passed} bestanden, {failed} fehlgeschlagen.")
    sys.exit(1 if failed else 0)
