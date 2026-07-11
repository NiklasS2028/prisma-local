# -*- coding: utf-8 -*-
"""
test_blockB_dom.py
------------------
DOM-Tests für Block B (helles Prisma-Theme + Theme-Toggle) via Playwright
gegen den laufenden Server auf http://localhost:8770.

Geprüft wird:
  - Erster Besuch -> helles Theme (Default), data-theme am <html>
  - Toggle hell/dunkel inkl. localStorage-Persistenz (prisma_theme)
  - WCAG-Kontrast der kritischen Paare in BEIDEN Themes (berechnet aus
    computed styles, keine Behauptung): Fließtext, gedimmter Text,
    Vorschau-/Code-Flächen, Chips, Ampel-Score, ✗/✓-Beispielboxen, Info-Box
  - Screenshots beider Themes (Konverter + Trainer) nach tests/screenshots/

Aufruf:  python tests/test_blockB_dom.py
"""

import os
import re
import sys
import traceback

# Windows-Konsole läuft oft mit cp1252 - UTF-8 erzwingen, damit ✗/✓ druckbar sind
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8770"
HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "screenshots")
os.makedirs(SHOTS, exist_ok=True)


# --- WCAG-Kontrast aus computed styles berechnen ---------------------------

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


def fresh_page(browser):
    """Neue Seite mit komplett leerem localStorage (Erstbesuch)."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.goto(BASE)
    return page


def set_theme(page, theme):
    page.click(f'#themeToggle .lang-btn[data-theme="{theme}"]')
    page.wait_for_timeout(150)


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

def test_default_is_light(page):
    """Erster Besuch (leerer localStorage) -> helles Theme."""
    theme = page.evaluate("document.documentElement.dataset.theme")
    assert theme == "light", f"Default-Theme ist '{theme}', erwartet 'light'"
    bg = style(page, "body", "background-color")
    assert _parse_rgb(bg) == (250, 248, 244), f"Heller Hintergrund fehlt: {bg}"
    sel = page.locator('#themeToggle .lang-btn[data-theme="light"]').get_attribute("class")
    assert "sel" in sel, "Hell-Button nicht als aktiv markiert"


def test_toggle_and_persistence(page):
    set_theme(page, "dark")
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert _parse_rgb(style(page, "body", "background-color")) == (11, 13, 18), \
        "Dunkler Hintergrund fehlt nach Umschalten"
    assert page.evaluate("localStorage.getItem('prisma_theme')") == "dark"
    # Persistenz über Reload
    page.reload()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark", \
        "Theme-Wahl überlebt den Reload nicht"
    # und zurück
    set_theme(page, "light")
    assert page.evaluate("localStorage.getItem('prisma_theme')") == "light"
    assert _parse_rgb(style(page, "body", "background-color")) == (250, 248, 244)


def test_dark_theme_unchanged(page):
    """Das dunkle Theme behält seine bisherigen Kernfarben (kein Rückbau)."""
    set_theme(page, "dark")
    assert _parse_rgb(style(page, "body", "background-color")) == (11, 13, 18)
    assert _parse_rgb(style(page, "body", "color")) == (234, 238, 245)
    assert _parse_rgb(style(page, "#preview", "background-color")) == (10, 12, 16), \
        "Code-Fläche im dunklen Theme verändert"


def test_light_serif_heading(page):
    set_theme(page, "light")
    font = style(page, "#pageTitle", "font-family")
    assert "Fraunces" in font or "Georgia" in font, \
        f"Serif-Überschrift fehlt im hellen Theme: {font}"
    set_theme(page, "dark")
    font = style(page, "#pageTitle", "font-family")
    assert "Space Grotesk" in font, f"Dunkles Theme muss Space Grotesk behalten: {font}"


def _render_trainer_result(page):
    page.click("#tabTrainer")
    page.click("#demoWeak")
    page.wait_for_selector(".pt-result.show", timeout=5000)
    page.wait_for_timeout(1300)


def _render_converter_result(page):
    fixtures = os.path.join(HERE, "fixtures")
    os.makedirs(fixtures, exist_ok=True)
    path = os.path.join(fixtures, "theme_smoke.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("Testtext für die Theme-Kontrastprüfung.")
    page.click("#tabConv")
    page.set_input_files("#fileInput", path)
    page.wait_for_selector(".result.show", timeout=10000)
    page.wait_for_timeout(400)


def _check_contrasts(page, theme):
    """Kritische Text/Hintergrund-Paare: >=4.5 normal, >=3 grosse Schrift."""
    set_theme(page, theme)
    _render_trainer_result(page)
    pairs = [
        # (Beschreibung, fg-Selector, bg-Selector, Mindest-Kontrast)
        ("Fließtext auf Seite", "body", "body", 4.5),
        ("gedimmter Text auf Karte", "#ptModelHint", ".card", 4.5),
        ("Score-Zahl (rot, groß) auf Score-Karte", "#scoreBig", ".score-card", 3.0),
        ("Check-Feedback auf Karte", ".check-fb", ".check", 4.5),
        ("✗-Beispielbox", ".ex-row.bad", ".ex-row.bad", 4.5),
        ("✓-Beispielbox", ".ex-row.good", ".ex-row.good", 4.5),
        ("Vorlagen-Vorschau (Code-Fläche)", "#tplOut", "#tplOut", 4.5),
    ]
    problems = []

    def check(name, fg_css, bg_css, minimum):
        ratio = contrast(fg_css, bg_css)
        if ratio < minimum:
            problems.append(f"[{theme}] {name}: {ratio:.2f} < {minimum} ({fg_css} auf {bg_css})")
        else:
            print(f"        [{theme}] {name}: Kontrast {ratio:.2f} (min {minimum})")

    for name, fg_sel, bg_sel, minimum in pairs:
        fg = style(page, fg_sel, "color")
        bg = style(page, bg_sel, "background-color")
        # Bei transparentem Hintergrund den Body-Hintergrund nehmen
        if "0)" in bg.replace(" ", "") and "rgba" in bg:
            bg = style(page, "body", "background-color")
        check(name, fg, bg, minimum)

    # Primär-Button hat einen VERLAUF als Hintergrund (background-color ist
    # transparent) -> Schriftfarbe gegen BEIDE Verlaufs-Endfarben prüfen.
    GRAD_STOPS = {
        "dark": ["rgb(52, 245, 162)", "rgb(56, 224, 255)"],
        "light": ["rgb(30, 58, 95)", "rgb(47, 94, 151)"],
    }
    btn_ink = style(page, "#analyzeBtn", "color")
    for stop in GRAD_STOPS[theme]:
        check(f"Button-Text auf Verlaufsfarbe {stop}", btn_ink, stop, 3.0)
    # Konverter-Chips zusätzlich
    _render_converter_result(page)
    fg = style(page, ".chip", "color")
    bg = style(page, ".chip", "background-color")
    ratio = contrast(fg, bg)
    if ratio < 4.5:
        problems.append(f"[{theme}] Chip: {ratio:.2f} < 4.5")
    else:
        print(f"        [{theme}] Chip: Kontrast {ratio:.2f} (min 4.5)")
    fg = style(page, "#note", "color")
    bg = style(page, "#note", "background-color")
    ratio = contrast(fg, bg)
    if ratio < 4.5:
        problems.append(f"[{theme}] Ergebnis-Note: {ratio:.2f} < 4.5")
    else:
        print(f"        [{theme}] Ergebnis-Note: Kontrast {ratio:.2f} (min 4.5)")
    assert not problems, "Kontrast-Probleme:\n" + "\n".join(problems)


def test_contrast_light(page):
    _check_contrasts(page, "light")


def test_contrast_dark(page):
    _check_contrasts(page, "dark")


def test_screenshots_both_themes(page):
    """Screenshots beider Themes für den Bericht (Konverter + Trainer)."""
    for theme in ("light", "dark"):
        set_theme(page, theme)
        _render_converter_result(page)
        page.screenshot(path=os.path.join(SHOTS, f"{theme}_konverter.png"), full_page=True)
        _render_trainer_result(page)
        page.screenshot(path=os.path.join(SHOTS, f"{theme}_trainer.png"), full_page=True)
    for theme in ("light", "dark"):
        for tab in ("konverter", "trainer"):
            p = os.path.join(SHOTS, f"{theme}_{tab}.png")
            assert os.path.getsize(p) > 10000, f"Screenshot leer: {p}"


ALL_TESTS = [
    test_default_is_light,
    test_toggle_and_persistence,
    test_dark_theme_unchanged,
    test_light_serif_heading,
    test_contrast_light,
    test_contrast_dark,
    test_screenshots_both_themes,
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
