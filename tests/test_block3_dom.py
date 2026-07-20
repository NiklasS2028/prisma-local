# -*- coding: utf-8 -*-
"""
test_block3_dom.py
------------------
DOM-Tests für Block 3 (index.html) via Playwright gegen den laufenden
Server auf http://localhost:8770. Vorher starten:  python app.py

Geprüft wird:
  - Sprach-Toggle DE/EN inkl. localStorage-Persistenz (kiw_lang)
  - Demo-Buttons (schwach/mittel/stark, sprachabhängig; Kriterien-Anzeige
    schwach 1/6 rot, mittel 3/6 gelb, stark 5/6 grün)
  - "X von N": Nenner 6 ohne / 7 mit Transformationsverb
  - Clear-Button leert Eingabe + Ergebnis, ohne zu zählen
  - Live-Analyse aktualisiert die Anzeige OHNE Stats-Request
    (Request-Mitschnitt); leeres Feld leert das Ergebnis
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

import requests

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
    """Kriterien-Regel: schwach 1/6 rot, mittel 3/6 gelb, stark 5/6 grün.
    Alle drei Demos ohne Transformationsverb -> Nenner 6."""
    page.click('#tabTrainer')
    expected = {"demoWeak": ("1", "rot"), "demoMedium": ("3", "gelb"),
                "demoStrong": ("5", "gruen")}
    for btn_id, (met, ampel) in expected.items():
        page.click(f"#{btn_id}")
        page.wait_for_selector(".pt-result.show", timeout=5000)
        page.wait_for_timeout(1200)  # countUp-Animation abwarten
        got_met = page.locator("#scoreBig").inner_text()
        got_class = page.locator("#scoreBig").get_attribute("class")
        assert got_met == met, f"{btn_id}: {got_met} erfüllt, erwartet {met}"
        assert ampel in got_class, f"{btn_id}: Ampel-Klasse '{got_class}', erwartet {ampel}"
        assert page.locator("#scoreMax").inner_text() == "VON 6", \
            f"{btn_id}: Nenner-Anzeige '{page.locator('#scoreMax').inner_text()}'"
    sub = page.locator("#scoreSub").inner_text()
    assert "5 von 6 Kriterien erfüllt" in sub, f"Kriterien-Beschriftung: {sub}"


def test_denominator_seven_with_transform(page):
    """Transformationsprompt -> 7 geprüfte Kriterien in der Anzeige."""
    page.click('#tabTrainer')
    page.fill("#promptInput", "Verbessere diesen Text.")
    page.click("#analyzeBtn")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    page.wait_for_timeout(1200)
    assert page.locator("#scoreMax").inner_text() == "VON 7", \
        f"Nenner-Anzeige: {page.locator('#scoreMax').inner_text()}"
    assert "von 7 Kriterien" in page.locator("#scoreSub").inner_text()


def test_clear_button_clears_without_counting(page):
    """E2: Clear leert Eingabe + Ergebnis und zählt nichts."""
    requests.post(BASE + "/stats/reset", timeout=10)
    page.click('#tabTrainer')
    page.click("#demoWeak")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    before = requests.get(BASE + "/stats", timeout=10).json()["prompts_analyzed"]
    page.click("#clearBtn")
    assert page.locator("#promptInput").input_value() == "", "Eingabe nicht geleert"
    assert not page.locator(".pt-result.show").count(), "Ergebnis nicht geleert"
    page.wait_for_timeout(600)
    after = requests.get(BASE + "/stats", timeout=10).json()["prompts_analyzed"]
    assert after == before, "Clear-Button hat gezählt"
    # EN-Label
    page.click('#langToggle .lang-btn[data-lang="en"]')
    assert page.locator("#clearBtn").inner_text() == "Clear"
    page.click('#langToggle .lang-btn[data-lang="de"]')
    assert page.locator("#clearBtn").inner_text() == "Leeren"


def test_live_analysis_updates_without_stats_request(page):
    """E4: Tippen aktualisiert die Anzeige nach ~400 ms Debounce, schickt
    aber KEINEN Stats-Request; erst der Analyze-Klick zählt."""
    requests.post(BASE + "/stats/reset", timeout=10)
    page.click('#tabTrainer')
    counted = []
    page.on("request",
            lambda req: counted.append(req.url)
            if "/stats/count_prompt" in req.url else None)
    page.fill("#promptInput", "Erklär mir Photosynthese für mein Studium")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    page.wait_for_timeout(400)
    assert page.locator("#scoreBig").inner_text() == "1", "Live-Anzeige fehlt"
    assert counted == [], f"Live-Analyse hat Stats-Requests geschickt: {counted}"
    assert requests.get(BASE + "/stats", timeout=10).json()["prompts_analyzed"] == 0
    # Der Klick ist das einzige Zählsignal
    page.click("#analyzeBtn")
    page.wait_for_timeout(800)
    assert len(counted) == 1, f"Analyze-Klick: {len(counted)} Requests statt 1"
    assert requests.get(BASE + "/stats", timeout=10).json()["prompts_analyzed"] == 1


def test_live_analysis_empty_field_clears(page):
    """E4: Feld leeren -> Ergebnis verschwindet ohne Fehlermeldung."""
    page.click('#tabTrainer')
    page.fill("#promptInput", "Erklär mir Photosynthese für mein Studium")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    page.fill("#promptInput", "")
    page.wait_for_timeout(700)
    assert not page.locator(".pt-result.show").count(), \
        "Ergebnis bleibt trotz leerem Feld stehen"
    assert not page.locator("#ptStatus.show").count(), \
        "Fehlermeldung flackert bei leerem Feld während Live-Analyse"


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
    """Re-Analyse-Check 2: Die Lernschleife wirkt. Schwacher Prompt (1/6 rot)
    -> Vorlage übernehmen -> Platzhalter ausfüllen (wie ein Nutzer es täte)
    -> erneut analysieren -> Anzeige springt auf grün (5/6)."""
    page.click('#tabTrainer')
    page.click("#demoWeak")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    page.wait_for_timeout(1200)
    assert page.locator("#scoreBig").inner_text() == "1", "Ausgangswert nicht 1/6"
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
    met = int(page.locator("#scoreBig").inner_text())
    klass = page.locator("#scoreBig").get_attribute("class")
    assert met >= 5, f"Lernschleife hebt die Kriterienzahl nicht (nur {met} erfüllt)"
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
    test_denominator_seven_with_transform,
    test_clear_button_clears_without_counting,
    test_live_analysis_updates_without_stats_request,
    test_live_analysis_empty_field_clears,
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
