# -*- coding: utf-8 -*-
"""
test_blockH_dom.py (Suite 12)
-----------------------------
DOM-Tests für Block H.3 (entschärfte Fehleranzeige) gegen den laufenden
Server. Der /convert-Fehlerfall wird per Playwright-Route-Intercept
deterministisch erzeugt (wie in Block G.2) - so braucht der Test keine
echte kaputte PDF auf dem Server.

Geprüft wird:
  - Die verständliche Hauptmeldung wird angezeigt, die rohe technische
    Meldung NICHT (nur in einer eingeklappten Detail-Zeile).
  - Die Detail-Zeile lässt sich ausklappen und zeigt dann den Rohtext.
  - Beschriftung zweisprachig (kiw_lang).
  - Fehler OHNE error_detail: keine Detail-Zeile (bestehendes Verhalten).
  - Kontrast der neuen Elemente in BEIDEN Themes (blockB-Stil, >= 4.5).

Aufruf:  python tests/test_blockH_dom.py
"""

import json
import os
import re
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8770"
HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
os.makedirs(FIXTURES, exist_ok=True)

HUMAN_MSG = ("Keine der 3 Seite(n) dieser PDF konnte gelesen werden - "
             "auch nicht per Texterkennung. Die Datei ist vermutlich beschädigt.")
TECH_MSG = ("Seite 1: Bounding box (0.0, -6.1e-05, 960.0, 539.99) is not "
            "fully within parent page bounding box (0, 0, 960, 540) TECHNIK-987")


# --- WCAG-Kontrast aus computed styles (wie test_blockB_dom) ----------------

def _parse_rgb(css):
    m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", css)
    if not m:
        raise ValueError(f"Unerwartetes Farbformat: {css}")
    return tuple(int(m.group(i)) for i in (1, 2, 3))


def _luminance(rgb):
    def chan(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg_css, bg_css):
    l1 = _luminance(_parse_rgb(fg_css))
    l2 = _luminance(_parse_rgb(bg_css))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def style(page, selector, prop):
    return page.eval_on_selector(
        selector, f"el => getComputedStyle(el).getPropertyValue('{prop}')")


# --- Setup-Helfer ------------------------------------------------------------

def fresh_page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.goto(BASE)
    return page


def _upload_with_error(page, payload):
    """Fängt /convert ab und liefert den gewünschten Fehler zurück."""
    def handler(route):
        route.fulfill(status=400, content_type="application/json",
                      body=json.dumps(payload))
    # Seit Block I haengt der Client ?ui_lang= an die URL - der Mock muss
    # den Query-String mitmatchen (Glob "**/convert" tut das nicht).
    page.route(re.compile(r"/convert\?"), handler)
    path = os.path.join(FIXTURES, "blockh_dummy.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("Inhalt egal - der Request wird abgefangen.")
    page.click("#tabConv")
    page.set_input_files("#fileInput", path)
    page.wait_for_selector("#convStatus.show.error", timeout=5000)
    page.wait_for_timeout(200)


ERROR_WITH_DETAIL = {"ok": False, "error": HUMAN_MSG, "error_detail": TECH_MSG}
ERROR_PLAIN = {"ok": False, "error": "Dateityp '.xyz' nicht unterstuetzt."}


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

def test_human_message_shown_tech_hidden(page):
    """Hauptfehler ist die verständliche Meldung; der Rohtext ist da,
    aber eingeklappt und damit unsichtbar."""
    _upload_with_error(page, ERROR_WITH_DETAIL)
    status_text = page.locator("#convStatus").inner_text()
    assert "vermutlich beschädigt" in status_text, \
        f"Verstaendliche Meldung fehlt: {status_text}"
    det = page.locator("#convStatus details.status-detail")
    assert det.count() == 1, "Detail-Zeile fehlt"
    assert not det.evaluate("el => el.open"), "Details sind nicht eingeklappt"
    assert not page.locator("#convStatus .status-detail-text").is_visible(), \
        "Roher Techniktext ist ohne Ausklappen sichtbar"


def test_detail_expands_on_click(page):
    _upload_with_error(page, ERROR_WITH_DETAIL)
    page.click("#convStatus details.status-detail summary")
    page.wait_for_timeout(150)
    txt = page.locator("#convStatus .status-detail-text")
    assert txt.is_visible(), "Detail-Zeile klappt nicht aus"
    assert "TECHNIK-987" in txt.inner_text(), \
        "Roher Techniktext fehlt in der Detail-Zeile"
    assert "Bounding box" in txt.inner_text()


def test_detail_label_bilingual(page):
    """Beschriftung folgt der UI-Sprache (kiw_lang)."""
    _upload_with_error(page, ERROR_WITH_DETAIL)
    summary = page.locator("#convStatus details.status-detail summary")
    assert summary.inner_text() == "Technische Details", \
        f"DE-Label falsch: {summary.inner_text()}"
    # Sprache wechseln und den Fehler neu erzeugen (Statusmeldungen werden
    # wie bisher zum Zeitpunkt ihres Entstehens beschriftet). Zweite Datei,
    # damit das change-Event des File-Inputs sicher feuert.
    page.click('#langToggle .lang-btn[data-lang="en"]')
    page.wait_for_timeout(200)
    path2 = os.path.join(FIXTURES, "blockh_dummy2.txt")
    with open(path2, "w", encoding="utf-8") as f:
        f.write("Zweiter Dummy fuer den EN-Fall.")
    page.set_input_files("#fileInput", path2)
    page.wait_for_selector("#convStatus.show.error", timeout=5000)
    page.wait_for_timeout(200)
    assert summary.inner_text() == "Technical details", \
        f"EN-Label falsch: {summary.inner_text()}"


def test_error_without_detail_unchanged(page):
    """Fehler ohne error_detail (z.B. falscher Dateityp): keine Detail-Zeile."""
    _upload_with_error(page, ERROR_PLAIN)
    assert "nicht unterstuetzt" in page.locator("#convStatus").inner_text()
    assert page.locator("#convStatus details.status-detail").count() == 0, \
        "Detail-Zeile erscheint faelschlich ohne error_detail"


def test_detail_contrast_both_themes(page):
    """Kontrast von Summary und Rohtext gegen die Fehlerflaeche in BEIDEN
    Themes >= 4.5 (blockB-Stil: aus computed styles berechnet)."""
    _upload_with_error(page, ERROR_WITH_DETAIL)
    page.click("#convStatus details.status-detail summary")
    page.wait_for_timeout(150)
    for theme in ("light", "dark"):
        page.click(f'#themeToggle .lang-btn[data-theme="{theme}"]')
        page.wait_for_timeout(200)
        bg = style(page, "#convStatus", "background-color")
        for sel, name in (
                ("#convStatus details.status-detail summary", "Summary"),
                ("#convStatus .status-detail-text", "Rohtext")):
            fg = style(page, sel, "color")
            ratio = contrast(fg, bg)
            assert ratio >= 4.5, \
                f"[{theme}] {name}: Kontrast {ratio:.2f} < 4.5 ({fg} auf {bg})"


ALL_TESTS = [
    test_human_message_shown_tech_hidden,
    test_detail_expands_on_click,
    test_detail_label_bilingual,
    test_error_without_detail_unchanged,
    test_detail_contrast_both_themes,
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
