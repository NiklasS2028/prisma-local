# -*- coding: utf-8 -*-
"""
test_privacy.py (Suite 9)
-------------------------
Wacht über das Kernversprechen "läuft komplett lokal, nichts verlässt den PC".

  Statisch (ohne Server):
    - index.html lädt NICHTS von http(s)-Zielen (src=/href=/url(...)).
    - Kein fetch() auf eine absolute http(s)-URL.
    - app.py/converter.py/prompt_trainer.py importieren weder requests
      noch urllib (URLs als reiner TEXT, z.B. in Fehlermeldungen, sind ok).
    - Die gebündelten Fonts liegen als echte woff2 vor (Magic Bytes),
      samt OFL-Lizenztexten.

  Live (Server muss laufen):
    - Playwright blockiert ALLE Nicht-localhost-Requests; die Seite lädt
      trotzdem vollständig und document.fonts.check() bestätigt alle drei
      Familien -> die Schriften kommen wirklich von /static/fonts/.

Aufruf:  python tests/test_privacy.py
"""

import os
import re
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8770"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHOTS = os.path.join(HERE, "screenshots")
os.makedirs(SHOTS, exist_ok=True)

FONT_DIR = os.path.join(ROOT, "static", "fonts")
FONT_FILES = ["SpaceGrotesk-var.woff2", "JetBrainsMono-var.woff2",
              "Fraunces-var.woff2"]
OFL_FILES = ["OFL-SpaceGrotesk.txt", "OFL-JetBrainsMono.txt",
             "OFL-Fraunces.txt"]


def _read(name):
    with open(os.path.join(ROOT, name), "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# STATISCHE CHECKS
# ---------------------------------------------------------------------------

def test_index_has_no_external_loads():
    """Nur LADE-Konstrukte zählen (src=, href=, url(...)) - URLs als
    bloßer Text (z.B. in Hinweisen) sind erlaubt."""
    html = _read("index.html")
    hits = re.findall(
        r"""(?:src|href)\s*=\s*["']https?://[^"']+["']"""
        r"""|url\(\s*["']?https?://[^)]+\)""",
        html, re.IGNORECASE)
    assert not hits, f"index.html lädt von extern: {hits}"


def test_index_fetch_only_relative():
    html = _read("index.html")
    hits = re.findall(r"""fetch\(\s*["'`]https?://[^"'`]+""", html)
    assert not hits, f"fetch() auf absolute URL: {hits}"
    # Positivprobe: die bekannten relativen fetch-Ziele existieren weiterhin
    assert "fetch('/convert'" in html and "fetch('/stats')" in html, \
        "Erwartete relative fetch()-Aufrufe fehlen - Test prüft ins Leere"


def test_backend_no_network_imports():
    """Das Backend selbst darf keine HTTP-Clients importieren.
    (tests/ nutzt requests bewusst - gegen localhost.)"""
    for name in ("app.py", "converter.py", "prompt_trainer.py"):
        src = _read(name)
        hits = re.findall(
            r"^\s*(?:import\s+(?:requests|urllib)\b"
            r"|from\s+(?:requests|urllib)\b)",
            src, re.MULTILINE)
        assert not hits, f"{name} importiert HTTP-Client: {hits}"


def test_fonts_bundled_and_valid():
    for fname in FONT_FILES:
        path = os.path.join(FONT_DIR, fname)
        assert os.path.isfile(path), f"{fname} fehlt in static/fonts/"
        with open(path, "rb") as f:
            head = f.read(4)
        size = os.path.getsize(path)
        assert head == b"wOF2", f"{fname}: keine woff2-Datei (Magic {head!r})"
        assert 5000 < size < 200000, f"{fname}: unplausible Größe {size}"
    for lname in OFL_FILES:
        path = os.path.join(FONT_DIR, lname)
        assert os.path.isfile(path), f"{lname} fehlt in static/fonts/"
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        assert "SIL OPEN FONT LICENSE" in text.upper(), \
            f"{lname}: kein OFL-Lizenztext"


def test_index_references_local_fonts():
    html = _read("index.html")
    for fname in FONT_FILES:
        assert f"/static/fonts/{fname}" in html, \
            f"@font-face-Verweis auf {fname} fehlt in index.html"
    assert "fonts.googleapis.com" not in html, "Google-Fonts-Link noch drin"
    assert "fonts.gstatic.com" not in html, "gstatic-Preconnect noch drin"


# ---------------------------------------------------------------------------
# LIVE-CHECK: SEITE OHNE INTERNET, FONTS TROTZDEM DA
# ---------------------------------------------------------------------------

def test_fonts_load_with_network_blocked():
    from playwright.sync_api import sync_playwright

    blocked = []

    def route_handler(route):
        url = route.request.url
        if url.startswith(BASE) or "://localhost" in url or "://127.0.0.1" in url:
            route.continue_()
        else:
            blocked.append(url)
            route.abort()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for theme in ("light", "dark"):
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            ctx.route("**/*", route_handler)
            page = ctx.new_page()
            page.goto(BASE)
            page.click(f'#themeToggle .lang-btn[data-theme="{theme}"]')
            page.wait_for_timeout(300)
            page.evaluate("document.fonts.ready")
            # check() mit einem tatsächlich deklarierten Gewicht; load()
            # vorher, weil z.B. Fraunces im dunklen Theme nirgends benutzt
            # wird und der Browser sie sonst (korrekt) nie anfordert.
            for spec in ('500 16px "Space Grotesk"',
                         '500 16px "JetBrains Mono"',
                         '600 16px "Fraunces"'):
                page.evaluate(f"document.fonts.load('{spec}')")
                page.wait_for_timeout(200)
                ok = page.evaluate(f"document.fonts.check('{spec}')")
                assert ok, f"[{theme}] Schrift nicht geladen: {spec}"
            shot = os.path.join(SHOTS, f"{theme}_konverter.png")
            page.screenshot(path=shot, full_page=True)
            assert os.path.getsize(shot) > 10000
            ctx.close()
        browser.close()

    # Beweisführung: es darf schlicht KEIN externer Request versucht worden
    # sein - nicht nur "abgewehrt", sondern gar nicht erst gestellt.
    assert not blocked, f"Seite hat externe Requests versucht: {blocked}"


ALL_TESTS = [
    test_index_has_no_external_loads,
    test_index_fetch_only_relative,
    test_backend_no_network_imports,
    test_fonts_bundled_and_valid,
    test_index_references_local_fonts,
    test_fonts_load_with_network_blocked,
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
    print(f"\n{passed} bestanden, {failed} fehlgeschlagen.")
    sys.exit(1 if failed else 0)
