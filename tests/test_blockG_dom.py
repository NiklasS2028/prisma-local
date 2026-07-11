# -*- coding: utf-8 -*-
"""
test_blockG_dom.py (Suite 10)
-----------------------------
DOM-Tests für Block G gegen den laufenden Server.

  G.1: Sticky-Ergebnisleiste im Konverter - der Download-Button ist ohne
       Scrollen durch die Vorschau erreichbar, bleibt beim Scrollen im
       Viewport, ist im Leerzustand unsichtbar, hat einen deckenden
       Theme-Hintergrund und verursacht keinen Horizontal-Sprung.
  G.2: "Ordner öffnen"-Button in Leiste und Ausgaben-Karte (DE/EN).

Aufruf:  python tests/test_blockG_dom.py
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

VIEWPORT = {"width": 1280, "height": 900}


def fresh_page(browser):
    ctx = browser.new_context(viewport=dict(VIEWPORT), accept_downloads=True)
    page = ctx.new_page()
    page.goto(BASE)
    return page


def upload_long_txt(page, name="blockg_lang.txt"):
    """Erzeugt eine Datei, deren Vorschau deutlich über den Viewport
    hinausragt - sonst gäbe es nichts, woran die Leiste kleben müsste."""
    path = os.path.join(FIXTURES, name)
    line = "Dies ist eine lange Vorschauzeile für den Sticky-Test von Block G."
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(f"Absatz {i}: {line}" for i in range(1, 60)))
    page.click("#tabConv")
    page.set_input_files("#fileInput", path)
    page.wait_for_selector(".result.show", timeout=10000)
    page.wait_for_timeout(300)


def rect(page, selector):
    return page.evaluate(
        f"() => {{ const r = document.querySelector('{selector}')"
        f".getBoundingClientRect();"
        f" return {{top: r.top, bottom: r.bottom, height: r.height}}; }}")


def bar_in_viewport(page):
    r = rect(page, "#convActions")
    return r["top"] >= 0 and r["bottom"] <= VIEWPORT["height"] and r["height"] > 0


# ---------------------------------------------------------------------------
# G.1: STICKY-ERGEBNISLEISTE
# ---------------------------------------------------------------------------

def test_bar_reachable_without_scroll(page):
    """Direkt nach der Konvertierung (ohne zu scrollen) ist die Leiste im
    Viewport, obwohl die Vorschau weit darüber hinausragt."""
    upload_long_txt(page)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(200)
    preview = rect(page, "#preview")
    assert preview["bottom"] > VIEWPORT["height"], \
        "Vorschau ragt nicht über den Viewport - Test prüft ins Leere"
    assert bar_in_viewport(page), \
        f"Leiste ohne Scrollen nicht erreichbar: {rect(page, '#convActions')}"
    assert page.locator("#downloadBtn").is_visible()


def test_bar_stays_while_scrolling(page):
    upload_long_txt(page)
    for fraction in (0.25, 0.6, 1.0):
        page.evaluate(
            f"window.scrollTo(0, document.body.scrollHeight * {fraction})")
        page.wait_for_timeout(200)
        assert bar_in_viewport(page), \
            f"Leiste bei Scroll-Position {fraction} aus dem Viewport"


def test_bar_absent_when_empty(page):
    page.click("#tabConv")
    assert not page.locator("#convActions").is_visible(), \
        "Leiste sichtbar, obwohl kein Ergebnis vorliegt"
    # Nach 'Neue Datei' (Reset) wieder unsichtbar
    upload_long_txt(page, "blockg_reset.txt")
    page.click("#convResetBtn")
    page.wait_for_timeout(300)
    assert not page.locator("#convActions").is_visible(), \
        "Leiste klebt nach Reset fest"


def test_bar_background_opaque_both_themes(page):
    """Deckender Hintergrund aus der Theme-Variable - in BEIDEN Themes
    darf nichts durchscheinen (Alpha 1, keine transparente Fläche)."""
    upload_long_txt(page)
    for theme in ("light", "dark"):
        page.click(f'#themeToggle .lang-btn[data-theme="{theme}"]')
        page.wait_for_timeout(200)
        bg = page.evaluate(
            "getComputedStyle(document.querySelector('#convActions'))"
            ".backgroundColor")
        assert bg.startswith("rgb(") or ", 1)" in bg, \
            f"[{theme}] Leisten-Hintergrund nicht deckend: {bg}"
        body_bg = page.evaluate(
            "getComputedStyle(document.body).backgroundColor")
        assert bg == body_bg, \
            f"[{theme}] Leiste nutzt nicht die Theme-Fläche: {bg} vs {body_bg}"


def test_no_horizontal_jump_with_result(page):
    """wrap.x bleibt über Ergebnis/Theme/Sprache identisch (blockD-Regel)."""
    def wrap_x():
        return page.locator(".wrap").bounding_box()["x"]

    positions = {"leer": wrap_x()}
    upload_long_txt(page)
    positions["mit Ergebnis"] = wrap_x()
    page.click('#themeToggle .lang-btn[data-theme="dark"]')
    positions["dunkel"] = wrap_x()
    page.click('#langToggle .lang-btn[data-lang="en"]')
    positions["EN"] = wrap_x()
    baseline = positions["leer"]
    drift = {k: v for k, v in positions.items() if abs(v - baseline) > 0.5}
    assert not drift, f"Horizontal-Sprung: {drift} (Basis {baseline})"


def test_screenshots_result_both_themes(page):
    upload_long_txt(page)
    page.evaluate("window.scrollTo(0, 0)")
    for theme in ("light", "dark"):
        page.click(f'#themeToggle .lang-btn[data-theme="{theme}"]')
        page.wait_for_timeout(400)
        shot = os.path.join(SHOTS, f"{theme}_konverter_result.png")
        page.screenshot(path=shot)  # Viewport-Shot: zeigt die klebende Leiste
        assert os.path.getsize(shot) > 10000


# ---------------------------------------------------------------------------
# G.2: "ORDNER OEFFNEN"-BUTTON
# ---------------------------------------------------------------------------

def test_open_folder_buttons_bilingual(page):
    """Je ein Button in der Ergebnisleiste und in der Ausgaben-Karte,
    Texte folgen der UI-Sprache."""
    upload_long_txt(page, "blockg_folder.txt")
    bar_btn = page.locator("#convActions .open-folder-btn")
    assert bar_btn.count() == 1 and bar_btn.is_visible(), \
        "Button fehlt in der Ergebnisleiste"
    assert bar_btn.inner_text() == "Ordner öffnen"
    page.click("#tabStats")
    page.wait_for_timeout(600)
    card_btn = page.locator("#panel-stats .open-folder-btn")
    assert card_btn.count() == 1 and card_btn.is_visible(), \
        "Button fehlt in der Ausgaben-Karte"
    page.click('#langToggle .lang-btn[data-lang="en"]')
    page.wait_for_timeout(200)
    assert card_btn.inner_text() == "Open folder"
    page.click("#tabConv")
    assert bar_btn.inner_text() == "Open folder"


def test_open_folder_click_posts(page):
    """Klick feuert POST /outputs/open - abgefangen per Route-Intercept,
    damit im Testlauf kein echtes Explorer-Fenster aufgeht."""
    posts = []

    def intercept(route):
        posts.append(route.request.method)
        route.fulfill(status=200, content_type="application/json",
                      body='{"ok": true}')

    page.route("**/outputs/open", intercept)
    upload_long_txt(page, "blockg_click.txt")
    page.click("#convActions .open-folder-btn")
    page.wait_for_timeout(400)
    assert posts == ["POST"], f"Kein/falscher Request: {posts}"


ALL_TESTS = [
    test_bar_reachable_without_scroll,
    test_bar_stays_while_scrolling,
    test_bar_absent_when_empty,
    test_bar_background_opaque_both_themes,
    test_no_horizontal_jump_with_result,
    test_screenshots_result_both_themes,
    test_open_folder_buttons_bilingual,
    test_open_folder_click_posts,
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
    requests.post(BASE + "/stats/reset", timeout=10)
    print(f"\n{passed} bestanden, {failed} fehlgeschlagen.")
    sys.exit(1 if failed else 0)
