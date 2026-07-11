# -*- coding: utf-8 -*-
"""
smoke_http.py
-------------
HTTP-Smoke-Test aller Endpunkte gegen den laufenden Server (python app.py).

  GET  /                -> UI wird ausgeliefert
  POST /analyze_prompt  -> de/en (ui_lang), prompt_lang, Fehlerfall
  POST /convert         -> txt-Upload, Download-Kette
  GET  /download/<id>   -> Datei kommt zurück

Aufruf:  python tests/smoke_http.py
"""

import os
import sys
import traceback

import requests

BASE = "http://localhost:8770"
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
os.makedirs(FIXTURES, exist_ok=True)


def test_index():
    r = requests.get(BASE + "/", timeout=10)
    assert r.status_code == 200, f"Status {r.status_code}"
    assert "Prisma" in r.text and 'id="langToggle"' in r.text, \
        "index.html unvollständig ausgeliefert"


def test_analyze_de():
    r = requests.post(BASE + "/analyze_prompt", timeout=10, json={
        "prompt": "schreib mal irgendwas über hunde oder so",
        "model": "claude", "ui_lang": "de"})
    d = r.json()
    assert r.status_code == 200 and d["ok"]
    assert d["score"] == 29 and d["ampel"] == "rot", f"Kalibrierung: {d['score']}/{d['ampel']}"
    assert d["prompt_lang"] == "de"


def test_analyze_en_ui():
    r = requests.post(BASE + "/analyze_prompt", timeout=10, json={
        "prompt": "schreib mal irgendwas über hunde oder so",
        "model": "gpt", "ui_lang": "en"})
    d = r.json()
    assert d["ok"]
    titles = [c["titel"] for c in d["checks"]]
    assert "Clear task" in titles, f"ui_lang=en wirkt nicht: {titles}"
    # Vorlage folgt der PROMPT-Sprache (deutsch), nicht der UI-Sprache
    assert "## Aufgabe" in d["template"], f"Vorlage nicht deutsch:\n{d['template'][:150]}"


def test_analyze_error():
    r = requests.post(BASE + "/analyze_prompt", timeout=10,
                      json={"prompt": "", "model": "claude", "ui_lang": "de"})
    assert r.status_code == 400 and not r.json()["ok"], "Leerer Prompt muss 400 liefern"


def test_convert_and_download():
    path = os.path.join(FIXTURES, "smoke_upload.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("Zeile eins mit Inhalt.\n\n\n\n\nZeile zwei nach Leerzeilen-Müll.")
    with open(path, "rb") as f:
        r = requests.post(BASE + "/convert", timeout=30,
                          files={"file": ("smoke_upload.txt", f)},
                          data={"target_model": "claude"})
    d = r.json()
    assert r.status_code == 200 and d["ok"], f"Convert fehlgeschlagen: {d}"
    assert d["target_format"] == "markdown" and d["target_model"] == "claude"
    assert "<document" in d["output_text"], "Claude-Wrapping fehlt"
    assert "Zeile zwei" in d["output_text"], "Inhalt fehlt"
    # Download-Kette
    dl = requests.get(f"{BASE}/download/{d['download_id']}",
                      params={"name": d["download_name"]}, timeout=10)
    assert dl.status_code == 200 and "Zeile eins" in dl.text, "Download defekt"


def test_convert_unsupported():
    r = requests.post(BASE + "/convert", timeout=10,
                      files={"file": ("test.xyz", b"egal")},
                      data={"target_model": "none"})
    assert r.status_code == 400 and not r.json()["ok"], \
        "Unbekannter Dateityp muss 400 liefern"


def test_stats_endpoints():
    """Statistik-Endpunkte: Roundtrip zaehlen -> lesen -> zuruecksetzen."""
    r = requests.post(BASE + "/stats/reset", timeout=10)
    assert r.status_code == 200 and r.json()["ok"]
    r = requests.post(BASE + "/stats/count_file", timeout=10,
                      json={"saved_tokens": 42, "format": "pdf"})
    assert r.status_code == 200 and r.json()["ok"]
    r = requests.post(BASE + "/stats/count_prompt", timeout=10,
                      json={"score": 90, "ampel": "gruen"})
    assert r.status_code == 200 and r.json()["ok"]
    s = requests.get(BASE + "/stats", timeout=10).json()
    assert s["files_converted"] == 1 and s["prompts_analyzed"] == 1
    assert s["tokens_saved_total"] == 42 and s["best_score"] == 90
    requests.post(BASE + "/stats/reset", timeout=10)
    assert requests.get(BASE + "/stats", timeout=10).json()["files_converted"] == 0


ALL_TESTS = [
    test_index,
    test_analyze_de,
    test_analyze_en_ui,
    test_analyze_error,
    test_convert_and_download,
    test_convert_unsupported,
    test_stats_endpoints,
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
