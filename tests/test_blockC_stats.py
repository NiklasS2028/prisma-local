# -*- coding: utf-8 -*-
"""
test_blockC_stats.py
--------------------
Backend-Tests für Block C (Statistik) gegen den laufenden Server.

Geprüft wird:
  - GET /stats liefert die Null-Struktur (criteria_missed über die 7
    Kriterien-Schlüssel, kein score_buckets/best_score mehr)
  - count_file / count_prompt zählen korrekt (inkl. Klemmen negativer Werte,
    Format-Mapping xlsm->xlsx / md->txt)
  - count_prompt-Randfälle: unbekannte Schlüssel ignoriert, Duplikate
    dedupliziert, leere Liste zählt nur den Prompt, kaputter Payload crasht nicht
  - alte stats.json mit score_buckets/best_score lädt crashfrei und normalisiert
  - stats.json enthält AUSSCHLIESSLICH Zahlen (rekursiv geprüft)
  - kaputte/fehlende stats.json crasht nicht (Neustart bei Null)
  - /stats/reset setzt alles auf Null

Die Tests setzen die Statistik am Anfang und am Ende zurück.

Aufruf:  python tests/test_blockC_stats.py
"""

import json
import os
import sys
import traceback

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8770"
STATS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stats.json")


def reset():
    r = requests.post(BASE + "/stats/reset", timeout=10)
    assert r.status_code == 200 and r.json()["ok"]


def get_stats():
    r = requests.get(BASE + "/stats", timeout=10)
    assert r.status_code == 200
    return r.json()


def count_file(saved, fmt):
    return requests.post(BASE + "/stats/count_file", timeout=10,
                         json={"saved_tokens": saved, "format": fmt})


CRITERIA = ["task", "input", "context", "specificity", "format", "role",
            "examples"]


def count_prompt(missed):
    return requests.post(BASE + "/stats/count_prompt", timeout=10,
                         json={"missed": missed})


def assert_numbers_only(obj, path="stats"):
    """Harte Datenschutz-Regel: rekursiv nur Zahlen (keine Strings/Inhalte)."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            assert isinstance(key, str), f"{path}: Schlüssel {key!r} kein String"
            assert_numbers_only(val, f"{path}.{key}")
    else:
        assert isinstance(obj, int) and not isinstance(obj, bool), \
            f"{path}: Wert {obj!r} ist keine ganze Zahl - VERBOTEN (nur Zahlen!)"


def test_default_structure():
    reset()
    s = get_stats()
    assert s == {
        "files_converted": 0,
        "prompts_analyzed": 0,
        "tokens_saved_total": 0,
        "criteria_missed": {key: 0 for key in CRITERIA},
        "format_counts": {"pdf": 0, "docx": 0, "xlsx": 0, "csv": 0,
                          "txt": 0, "pptx": 0},
    }, f"Null-Struktur weicht ab: {s}"


def test_count_file():
    reset()
    assert count_file(120, "pdf").json()["ok"]
    assert count_file(80, "docx").json()["ok"]
    s = get_stats()
    assert s["files_converted"] == 2
    assert s["tokens_saved_total"] == 200
    assert s["format_counts"]["pdf"] == 1 and s["format_counts"]["docx"] == 1


def test_count_file_clamps_negative():
    reset()
    assert count_file(-500, "txt").json()["ok"]
    s = get_stats()
    assert s["files_converted"] == 1, "Datei muss trotzdem zählen"
    assert s["tokens_saved_total"] == 0, "Negative Ersparnis muss auf 0 geklemmt werden"


def test_format_mapping():
    reset()
    count_file(10, "xlsm")
    count_file(10, "md")
    count_file(10, "exotisch")
    s = get_stats()
    assert s["format_counts"]["xlsx"] == 1, "xlsm nicht auf xlsx gemappt"
    assert s["format_counts"]["txt"] == 1, "md nicht auf txt gemappt"
    assert s["files_converted"] == 3, "Unbekanntes Format: Datei zählt, Format nicht"
    assert sum(s["format_counts"].values()) == 2


def test_count_prompt_criteria():
    """3 rote Kriterien -> genau diese 3 Zähler +1, prompts_analyzed +1."""
    reset()
    assert count_prompt(["context", "format", "examples"]).json()["ok"]
    s = get_stats()
    assert s["prompts_analyzed"] == 1
    expected = {key: 0 for key in CRITERIA}
    expected.update({"context": 1, "format": 1, "examples": 1})
    assert s["criteria_missed"] == expected, f"Zähler falsch: {s['criteria_missed']}"


def test_count_prompt_unknown_key_ignored():
    reset()
    r = count_prompt(["task", "quatsch", 42, None, {"x": 1}])
    assert r.status_code == 200 and r.json()["ok"], \
        "Unbekannte/kaputte Einträge dürfen nicht crashen"
    s = get_stats()
    assert s["prompts_analyzed"] == 1
    assert s["criteria_missed"]["task"] == 1
    assert sum(s["criteria_missed"].values()) == 1, "Nur 'task' darf zählen"


def test_count_prompt_duplicates_deduplicated():
    reset()
    assert count_prompt(["role", "role", "role"]).json()["ok"]
    s = get_stats()
    assert s["criteria_missed"]["role"] == 1, \
        "Duplikate in der Liste: max. +1 pro Kriterium pro Prompt"


def test_count_prompt_empty_list():
    reset()
    assert count_prompt([]).json()["ok"]
    s = get_stats()
    assert s["prompts_analyzed"] == 1
    assert sum(s["criteria_missed"].values()) == 0


def test_count_prompt_broken_payload():
    """Kein/kaputtes 'missed'-Feld -> zählt nur den Prompt, kein Crash."""
    reset()
    r = requests.post(BASE + "/stats/count_prompt", timeout=10,
                      json={"missed": "keine-liste"})
    assert r.status_code == 200 and r.json()["ok"]
    r = requests.post(BASE + "/stats/count_prompt", timeout=10,
                      json={"score": 90, "ampel": "gruen"})  # altes Format
    assert r.status_code == 200 and r.json()["ok"]
    s = get_stats()
    assert s["prompts_analyzed"] == 2
    assert sum(s["criteria_missed"].values()) == 0


def test_old_schema_file_normalizes():
    """Alte stats.json mit score_buckets/best_score lädt crashfrei;
    Whitelist verwirft die alten Felder, criteria_missed startet bei 0."""
    reset()
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump({"files_converted": 7, "prompts_analyzed": 3,
                   "tokens_saved_total": 500,
                   "score_buckets": {"red": 1, "yellow": 1, "green": 1},
                   "best_score": 90}, f)
    s = get_stats()
    assert "score_buckets" not in s and "best_score" not in s, \
        "Alte Felder überleben das Laden"
    assert s["files_converted"] == 7 and s["prompts_analyzed"] == 3
    assert s["criteria_missed"] == {key: 0 for key in CRITERIA}
    # Zählen schreibt die Datei im neuen Schema neu
    assert count_prompt(["format"]).json()["ok"]
    with open(STATS_PATH, "r", encoding="utf-8") as f:
        on_disk = json.load(f)
    assert "score_buckets" not in on_disk and "best_score" not in on_disk
    assert on_disk["criteria_missed"]["format"] == 1


def test_stats_file_numbers_only():
    reset()
    count_file(120, "pdf")
    count_prompt(["context"])
    with open(STATS_PATH, "r", encoding="utf-8") as f:
        on_disk = json.load(f)
    assert_numbers_only(on_disk)
    # Und explizit: exakt die erlaubte Schlüssel-Struktur, nichts darüber hinaus
    assert set(on_disk.keys()) == {"files_converted", "prompts_analyzed",
                                   "tokens_saved_total", "criteria_missed",
                                   "format_counts"}
    assert set(on_disk["criteria_missed"].keys()) == set(CRITERIA)
    assert set(on_disk["format_counts"].keys()) == {"pdf", "docx", "xlsx",
                                                    "csv", "txt", "pptx"}


def test_corrupt_stats_file_survives():
    reset()
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        f.write("kaputt{{{nicht-json")
    s = get_stats()
    assert s["files_converted"] == 0, "Kaputte Datei muss zu Null-Werten führen"
    # Zählen repariert die Datei
    assert count_file(50, "csv").json()["ok"]
    s = get_stats()
    assert s["files_converted"] == 1 and s["tokens_saved_total"] == 50


def test_bom_stats_file_loads():
    """Block J: stats.json mit UTF-8-BOM (EF BB BF) muss beim Lesen korrekt
    geladen werden - nicht still auf Nullen zurueckfallen. Realer Ausloeser:
    Endnutzer oeffnet und speichert die Datei in Notepad, das schreibt die BOM.
    Rot-vor-Fix: mit encoding="utf-8" scheitert json.load an der BOM und die
    Werte gehen verloren; mit "utf-8-sig" bleiben sie erhalten."""
    reset()
    payload = {"files_converted": 42, "prompts_analyzed": 7,
               "tokens_saved_total": 1234,
               "criteria_missed": {"task": 3},
               "format_counts": {"pdf": 5}}
    json_bytes = json.dumps(payload).encode("utf-8")
    # BOM-Bytes explizit voranstellen (kein encoding-Automatismus)
    with open(STATS_PATH, "wb") as f:
        f.write(b"\xef\xbb\xbf" + json_bytes)

    s = get_stats()
    assert s["files_converted"] == 42, \
        "BOM-Datei: files_converted verloren (Fallback auf Null?)"
    assert s["prompts_analyzed"] == 7, "BOM-Datei: prompts_analyzed verloren"
    assert s["tokens_saved_total"] == 1234, "BOM-Datei: tokens_saved_total verloren"
    assert s["criteria_missed"]["task"] == 3, "BOM-Datei: criteria_missed verloren"
    assert s["format_counts"]["pdf"] == 5, "BOM-Datei: format_counts verloren"

    # Gegenprobe: dieselbe Datei OHNE BOM laedt weiterhin korrekt (unveraendert).
    with open(STATS_PATH, "wb") as f:
        f.write(json_bytes)
    s = get_stats()
    assert s["files_converted"] == 42 and s["tokens_saved_total"] == 1234, \
        "Datei ohne BOM darf sich nicht anders verhalten"


def test_foreign_keys_are_dropped():
    """Fremde/injizierte Schlüssel in stats.json werden beim Laden verworfen."""
    reset()
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump({"files_converted": 5, "geheimer_text": "darf nicht bleiben",
                   "criteria_missed": {"task": -3, "fremd": 9}}, f)
    s = get_stats()
    assert "geheimer_text" not in s, "Fremder Schlüssel überlebt das Laden"
    assert s["files_converted"] == 5
    assert "fremd" not in s["criteria_missed"], \
        "Fremder Kriterien-Schlüssel überlebt das Laden"
    assert s["criteria_missed"]["task"] == 0, \
        "Negativer Zähler muss auf 0 geklemmt werden"


def test_origin_check_reset():
    """Block F.4: Reset mit fremdem Origin -> 403, erlaubt/ohne -> 200."""
    reset()
    count_file(10, "pdf")
    r = requests.post(BASE + "/stats/reset", timeout=10,
                      headers={"Origin": "http://boese-seite.example"})
    assert r.status_code == 403 and not r.json()["ok"], \
        f"Fremder Origin nicht abgewehrt: {r.status_code}"
    assert get_stats()["files_converted"] == 1, "403 darf nicht resetten"
    r = requests.post(BASE + "/stats/reset", timeout=10,
                      headers={"Origin": "http://localhost:8770"})
    assert r.status_code == 200, "Eigener Origin muss erlaubt sein"
    r = requests.post(BASE + "/stats/reset", timeout=10)  # ohne Origin
    assert r.status_code == 200, "Fehlender Origin (curl/Tests) muss erlaubt sein"


def test_origin_check_count_endpoints():
    """Block F.4: je ein 403-Fall fuer beide Zaehl-Endpunkte."""
    reset()
    evil = {"Origin": "https://angreifer.example"}
    r = requests.post(BASE + "/stats/count_file", timeout=10,
                      json={"saved_tokens": 9999, "format": "pdf"}, headers=evil)
    assert r.status_code == 403, f"count_file: {r.status_code}"
    r = requests.post(BASE + "/stats/count_prompt", timeout=10,
                      json={"missed": ["task"]}, headers=evil)
    assert r.status_code == 403, f"count_prompt: {r.status_code}"
    s = get_stats()
    assert s["files_converted"] == 0 and s["prompts_analyzed"] == 0, \
        "Abgewehrte Events haben trotzdem gezählt"


def test_atomic_save_survives_write_failure():
    """Block F.3: Schreibfehler mitten im json.dump darf die bestehende
    stats.json NIE zerstoeren (tmp + os.replace). Direkt-Import von app,
    json.dump wird per Monkeypatch zum Scheitern gebracht."""
    reset()
    assert count_file(77, "pdf").json()["ok"]  # bekannter Zustand auf Platte
    with open(STATS_PATH, "r", encoding="utf-8") as f:
        before = f.read()

    root = os.path.dirname(STATS_PATH)
    if root not in sys.path:
        sys.path.insert(0, root)
    import app as app_module

    def boom(*_a, **_k):
        raise OSError("simulierter Schreibfehler")

    orig_dump = app_module.json.dump
    app_module.json.dump = boom
    try:
        app_module._save_stats({"files_converted": 999})
    finally:
        app_module.json.dump = orig_dump

    with open(STATS_PATH, "r", encoding="utf-8") as f:
        after = f.read()
    assert after == before, "stats.json wurde trotz Schreibfehler verändert"
    assert json.loads(after)["files_converted"] == 1, "Inhalt nicht mehr lesbar"
    assert not os.path.exists(STATS_PATH + ".tmp"), ".tmp-Rest blieb liegen"


def test_atomic_save_leaves_no_tmp():
    """Erfolgsfall: nach jedem Zaehl-Event existiert keine .tmp-Datei."""
    reset()
    assert count_file(5, "txt").json()["ok"]
    assert count_prompt(["context"]).json()["ok"]
    assert not os.path.exists(STATS_PATH + ".tmp"), ".tmp nach Erfolg übrig"
    s = get_stats()
    assert s["files_converted"] == 1 and s["prompts_analyzed"] == 1


def _make_output_file():
    """Erzeugt ueber /convert eine echte Ausgabedatei in outputs/."""
    import io
    r = requests.post(BASE + "/convert", timeout=30,
                      files={"file": ("f5_probe.txt",
                                      io.BytesIO(b"Inhalt fuer Block-F5-Test."))},
                      data={"target_model": "none"})
    assert r.status_code == 200 and r.json()["ok"]
    return r.json()["download_id"]


def test_outputs_info_and_clear():
    """Block F.5: /outputs/info liefert NUR Zahlen, /outputs/clear loescht
    alles und alte Download-Links laufen in den bestehenden 404-Pfad."""
    r = requests.post(BASE + "/outputs/clear", timeout=10)
    assert r.status_code == 200 and r.json()["ok"]
    info = requests.get(BASE + "/outputs/info", timeout=10).json()
    assert info == {"count": 0, "total_bytes": 0}, f"Leerzustand: {info}"

    dl_id = _make_output_file()
    _make_output_file()
    info = requests.get(BASE + "/outputs/info", timeout=10).json()
    assert set(info.keys()) == {"count", "total_bytes"}, "Fremde Schlüssel im Payload"
    assert all(isinstance(v, int) and not isinstance(v, bool)
               for v in info.values()), f"Nicht nur Zahlen: {info}"
    assert info["count"] == 2 and info["total_bytes"] > 0

    r = requests.post(BASE + "/outputs/clear", timeout=10)
    assert r.json()["removed"] == 2, f"removed: {r.json()}"
    info = requests.get(BASE + "/outputs/info", timeout=10).json()
    assert info["count"] == 0 and info["total_bytes"] == 0
    r = requests.get(f"{BASE}/download/{dl_id}", timeout=10)
    assert r.status_code == 404, "Geloeschte Ausgabe muss im 404-Pfad landen"


def test_outputs_clear_origin_check():
    """Block F.5: auch /outputs/clear wehrt Cross-Site-POSTs ab."""
    _make_output_file()
    r = requests.post(BASE + "/outputs/clear", timeout=10,
                      headers={"Origin": "https://angreifer.example"})
    assert r.status_code == 403, f"Fremder Origin nicht abgewehrt: {r.status_code}"
    info = requests.get(BASE + "/outputs/info", timeout=10).json()
    assert info["count"] >= 1, "403 darf nicht loeschen"
    requests.post(BASE + "/outputs/clear", timeout=10)  # aufraeumen


def test_outputs_open_calls_startfile():
    """Block G.2: /outputs/open legt den Ordner an und oeffnet ihn per
    os.startfile - per Monkeypatch, damit im Testlauf KEIN echtes
    Explorer-Fenster aufgeht (Flask test_client, nicht der Live-Server)."""
    root = os.path.dirname(STATS_PATH)
    if root not in sys.path:
        sys.path.insert(0, root)
    import app as app_module

    calls = []
    orig_makedirs = os.makedirs
    orig_startfile = getattr(os, "startfile", None)
    os.makedirs = lambda p, exist_ok=False: calls.append(("makedirs", p))
    os.startfile = lambda p: calls.append(("startfile", p))
    try:
        client = app_module.app.test_client()
        r = client.post("/outputs/open")
        assert r.status_code == 200 and r.get_json()["ok"], \
            f"Endpoint fehlgeschlagen: {r.status_code} {r.get_json()}"
    finally:
        os.makedirs = orig_makedirs
        if orig_startfile is not None:
            os.startfile = orig_startfile
        else:
            del os.startfile
    assert calls == [("makedirs", app_module.OUTPUT_DIR),
                     ("startfile", app_module.OUTPUT_DIR)], \
        f"Falsche Aufruf-Reihenfolge/Pfade: {calls}"


def test_outputs_open_origin_check():
    """Block G.2: fremder Origin -> 403 (gegen den Live-Server, gefahrlos,
    weil der Check VOR dem Oeffnen greift); erlaubter/kein Origin -> 200
    (per test_client mit gepatchtem startfile, kein Explorer-Fenster)."""
    r = requests.post(BASE + "/outputs/open", timeout=10,
                      headers={"Origin": "https://angreifer.example"})
    assert r.status_code == 403, f"Fremder Origin nicht abgewehrt: {r.status_code}"

    import app as app_module
    orig_startfile = getattr(os, "startfile", None)
    os.startfile = lambda p: None
    try:
        client = app_module.app.test_client()
        r = client.post("/outputs/open",
                        headers={"Origin": "http://localhost:8770"})
        assert r.status_code == 200, "Eigener Origin muss erlaubt sein"
        r = client.post("/outputs/open")
        assert r.status_code == 200, "Fehlender Origin muss erlaubt sein"
    finally:
        if orig_startfile is not None:
            os.startfile = orig_startfile
        else:
            del os.startfile


def test_reset():
    reset()
    count_file(100, "pdf")
    count_prompt(["format", "role"])
    reset()
    s = get_stats()
    assert s["files_converted"] == 0 and s["prompts_analyzed"] == 0
    assert s["tokens_saved_total"] == 0
    assert sum(s["criteria_missed"].values()) == 0
    assert sum(s["format_counts"].values()) == 0


ALL_TESTS = [
    test_default_structure,
    test_count_file,
    test_count_file_clamps_negative,
    test_format_mapping,
    test_count_prompt_criteria,
    test_count_prompt_unknown_key_ignored,
    test_count_prompt_duplicates_deduplicated,
    test_count_prompt_empty_list,
    test_count_prompt_broken_payload,
    test_old_schema_file_normalizes,
    test_stats_file_numbers_only,
    test_corrupt_stats_file_survives,
    test_bom_stats_file_loads,
    test_foreign_keys_are_dropped,
    test_origin_check_reset,
    test_origin_check_count_endpoints,
    test_atomic_save_survives_write_failure,
    test_atomic_save_leaves_no_tmp,
    test_outputs_info_and_clear,
    test_outputs_clear_origin_check,
    test_outputs_open_calls_startfile,
    test_outputs_open_origin_check,
    test_reset,
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
    reset()  # Entwickler-Statistik sauber bei Null hinterlassen
    print(f"\n{passed} bestanden, {failed} fehlgeschlagen.")
    sys.exit(1 if failed else 0)
