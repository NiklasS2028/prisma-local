# -*- coding: utf-8 -*-
"""
test_blockI_batch.py
--------------------
Tests für Block I (Batch-Konvertierung mehrerer Dateien). Läuft ueber den
Flask-Testclient (kein Live-Server noetig); jede Testdatei wird selbst
konstruiert, keine echten Nutzerdaten.

Kern-Absicherung ist die VERTAUSCH-SICHERHEIT: jede Datei traegt eine eigene
download_id durch die ganze Kette; der Inhalt von ID X liegt in der ZIP
wirklich unter Name X.

Abgedeckt:
  - Mehrere gueltige Dateien -> alle ok, eigene eindeutige IDs, alle in der
    ZIP, KEINE Vertauschung (Inhalt-zu-Name Kreuzprobe).
  - Gemischt gueltig + kaputt -> Batch laeuft durch (partielle Fehler brechen
    nicht ab), kaputte Datei hat error-Status und KEINE download_id und ist
    NICHT in der ZIP.
  - Limit: 21 Dateien -> sauberer 400-Fehler, NICHTS verarbeitet.
  - Leerer Batch / fremder Origin -> saubere Ablehnung.
  - ZIP: serverseitiges ok-Gate (manipulierte error-/Fantasie-IDs fliegen
    raus), Namenskollision (bericht.md + bericht (2).md), reine
    Arbeitsspeicher-ZIP ohne Zwischendatei in outputs/.

Aufruf:  python tests/test_blockI_batch.py
"""

import io
import os
import sys
import zipfile
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# app.py liegt eine Ebene hoeher
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as app_module  # noqa: E402

app_module.app.testing = True
CLIENT = app_module.app.test_client()
OUTPUT_DIR = app_module.OUTPUT_DIR


# ---------------------------------------------------------------------------
# HILFEN
# ---------------------------------------------------------------------------

def _f(name, content):
    """Baut ein Datei-Tupel (Stream, Dateiname) fuer den Testclient."""
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    return (io.BytesIO(data), name)


def _post_batch(files, model="none", origin=None):
    data = {"target_model": model, "files": files}
    headers = {"Origin": origin} if origin else {}
    return CLIENT.post("/convert-batch", data=data,
                       content_type="multipart/form-data", headers=headers)


def _zip_of(ok_rows, origin=None):
    """Fordert die Sammel-ZIP fuer die uebergebenen ok-Zeilen an."""
    payload = {"files": [{"id": r["download_id"], "name": r["download_name"]}
                         for r in ok_rows]}
    headers = {"Origin": origin} if origin else {}
    return CLIENT.post("/download-batch", json=payload, headers=headers)


def _outputs_count():
    try:
        return len([n for n in os.listdir(OUTPUT_DIR)
                    if os.path.isfile(os.path.join(OUTPUT_DIR, n))])
    except OSError:
        return 0


def _cleanup(rows):
    """Entfernt NUR die in diesem Test erzeugten Ausgabedateien wieder,
    damit der outputs-Ordner des Nutzers nicht zugemuellt wird."""
    for r in rows:
        did = r.get("download_id")
        if did:
            try:
                os.remove(os.path.join(OUTPUT_DIR, os.path.basename(did)))
            except OSError:
                pass


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

def test_multiple_valid_unique_ids_no_swap():
    """Mehrere gueltige Dateien: alle ok, eigene eindeutige IDs, und der
    ZIP-Inhalt von ID X liegt wirklich unter Name X (keine Vertauschung)."""
    files = [_f("alpha.txt", "MARKER_ALPHA " * 40),
             _f("beta.txt", "MARKER_BETA " * 40),
             _f("gamma.csv", "spalte1,spalte2\nMARKER,GAMMA\n")]
    r = _post_batch(files)
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] and j["count"] == 3
    rows = j["results"]
    assert all(it["status"] == "ok" for it in rows), "nicht alle ok"
    # eigene, eindeutige IDs
    ids = [it["download_id"] for it in rows]
    assert len(set(ids)) == 3, "download_ids nicht eindeutig"
    assert len(set(it["id"] for it in rows)) == 3, "Zeilen-IDs nicht eindeutig"
    try:
        # ZIP ziehen und Inhalt-zu-Name pruefen
        zr = _zip_of(rows)
        assert zr.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(zr.get_data()))
        names = zf.namelist()
        assert set(names) == {"alpha.md", "beta.md", "gamma.csv"}, names
        assert "MARKER_ALPHA" in zf.read("alpha.md").decode()
        assert "MARKER_BETA" in zf.read("beta.md").decode()
        assert "GAMMA" in zf.read("gamma.csv").decode()
        # Kreuzprobe: alpha-Marker steckt NUR in alpha, nicht in beta/gamma
        assert "MARKER_ALPHA" not in zf.read("beta.md").decode()
        assert "MARKER_ALPHA" not in zf.read("gamma.csv").decode()
        assert "MARKER_BETA" not in zf.read("alpha.md").decode()
    finally:
        _cleanup(rows)


def test_mixed_valid_and_broken_runs_through():
    """Gemischt: gueltige + kaputte Dateien. Der Batch laeuft durch (partielle
    Fehler brechen nicht ab), kaputte haben error-Status und KEINE
    download_id und landen NICHT in der ZIP."""
    files = [_f("gut1.txt", "MARKER_GUT_EINS " * 40),
             _f("kaputt_ext.xyz", "nicht unterstuetzter Typ"),
             _f("gut2.txt", "MARKER_GUT_ZWEI " * 40),
             _f("kaputt_docx.docx", b"das ist kein echtes docx"),
             _f("gut3.txt", "MARKER_GUT_DREI " * 40)]
    r = _post_batch(files)
    assert r.status_code == 200
    j = r.get_json()
    assert j["count"] == 5, "alle 5 Dateien muessen ein Ergebnis-Objekt haben"
    by = {it["name"]: it for it in j["results"]}
    ok_rows = [it for it in j["results"] if it["status"] == "ok"]
    err_rows = [it for it in j["results"] if it["status"] == "error"]
    assert len(ok_rows) == 3 and len(err_rows) == 2, \
        f"3 ok + 2 error erwartet, got {len(ok_rows)}/{len(err_rows)}"
    # Kaputte: error-Status, KEINE download_id
    for name in ("kaputt_ext.xyz", "kaputt_docx.docx"):
        assert by[name]["status"] == "error"
        assert "download_id" not in by[name], f"{name} hat eine download_id!"
        assert by[name].get("error"), f"{name} ohne verstaendliche Meldung"
    try:
        zr = _zip_of(ok_rows)
        assert zr.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(zr.get_data()))
        names = zf.namelist()
        assert set(names) == {"gut1.md", "gut2.md", "gut3.md"}, names
        # Nichts Kaputtes in der ZIP
        assert not any("kaputt" in n for n in names), "kaputte Datei in der ZIP!"
        assert "MARKER_GUT_EINS" in zf.read("gut1.md").decode()
    finally:
        _cleanup(ok_rows)


def test_limit_21_rejected_nothing_processed():
    """21 Dateien -> sauberer 400-Fehler, und NICHTS wurde verarbeitet
    (keine neue Ausgabedatei in outputs/)."""
    before = _outputs_count()
    files = [_f(f"datei_{i}.txt", f"inhalt {i} " * 20) for i in range(21)]
    r = _post_batch(files)
    assert r.status_code == 400, f"21 Dateien muessen 400 geben, got {r.status_code}"
    j = r.get_json()
    assert not j["ok"] and "20" in j["error"], f"Meldung nennt das Limit nicht: {j}"
    after = _outputs_count()
    assert after == before, \
        f"trotz Ablehnung wurde verarbeitet (outputs {before}->{after})"


def test_exactly_20_allowed():
    """Genau 20 Dateien sind erlaubt (Grenze inklusiv)."""
    files = [_f(f"g_{i}.txt", f"MARKER_{i} " * 20) for i in range(20)]
    r = _post_batch(files)
    assert r.status_code == 200
    j = r.get_json()
    assert j["count"] == 20 and all(it["status"] == "ok" for it in j["results"])
    _cleanup(j["results"])


def test_empty_batch_rejected():
    """Kein Datei-Feld -> 400 mit klarer Meldung, nichts passiert."""
    r = CLIENT.post("/convert-batch", data={"target_model": "none"},
                    content_type="multipart/form-data")
    assert r.status_code == 400 and not r.get_json()["ok"]


def test_origin_check_batch():
    """Fremder Origin -> 403 (wie bei den anderen schreibenden Endpunkten)."""
    r = _post_batch([_f("a.txt", "x " * 20)], origin="https://angreifer.example")
    assert r.status_code == 403, f"fremder Origin nicht abgewehrt: {r.status_code}"


def test_zip_server_side_ok_gate():
    """Defense in Depth: ein manipulierter ZIP-Request mit error-ID,
    Fantasie-ID oder Pfad-Traversal darf NICHTS Falsches einschleusen -
    gezogen wird nur, was als Datei wirklich in outputs/ existiert."""
    files = [_f("echt.txt", "MARKER_ECHT " * 40), _f("kaputt.xyz", "boese")]
    j = _post_batch(files).get_json()
    ok = [it for it in j["results"] if it["status"] == "ok"][0]
    err = [it for it in j["results"] if it["status"] == "error"][0]
    try:
        payload = {"files": [
            {"id": ok["download_id"], "name": ok["download_name"]},
            {"id": err["id"], "name": "boese.md"},          # error-Zeilen-id
            {"id": "deadbeef" * 4 + ".md", "name": "fake.md"},  # erfunden
            {"id": "../app.py", "name": "traversal.md"},    # Traversal-Versuch
        ]}
        zr = CLIENT.post("/download-batch", json=payload)
        assert zr.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(zr.get_data()))
        names = zf.namelist()
        assert names == ["echt.md"], f"nur die echte Datei erlaubt, got {names}"
        assert not any(n in ("boese.md", "fake.md", "traversal.md")
                       for n in names)
        # nur-error/erfundene Liste -> 400 (nichts gezogen)
        bad = CLIENT.post("/download-batch",
                          json={"files": [{"id": err["id"], "name": "x.md"}]})
        assert bad.status_code == 400
    finally:
        _cleanup([ok])


def test_zip_name_collision():
    """Zwei gleichnamige Ergebnisse -> bericht.md und bericht (2).md,
    beide Inhalte getrennt vorhanden (keine Vertauschung)."""
    files = [_f("bericht.txt", "MARKER_ERSTER " * 40),
             _f("bericht.txt", "MARKER_ZWEITER " * 40)]
    j = _post_batch(files).get_json()
    rows = j["results"]
    assert all(it["status"] == "ok" for it in rows)
    assert rows[0]["download_id"] != rows[1]["download_id"], "IDs kollidieren"
    assert rows[0]["download_name"] == rows[1]["download_name"] == "bericht.md"
    try:
        zf = zipfile.ZipFile(io.BytesIO(_zip_of(rows).get_data()))
        names = sorted(zf.namelist())
        assert names == ["bericht (2).md", "bericht.md"], names
        contents = "".join(zf.read(n).decode() for n in names)
        assert "MARKER_ERSTER" in contents and "MARKER_ZWEITER" in contents, \
            "eine der beiden Dateien fehlt (Kollision hat ueberschrieben)"
    finally:
        _cleanup(rows)


def test_zip_in_memory_no_leftover():
    """Die ZIP wird im Arbeitsspeicher gebaut: der /download-batch-Aufruf
    darf keine zusaetzliche Datei in outputs/ hinterlassen."""
    files = [_f("m1.txt", "MARKER_M1 " * 40), _f("m2.txt", "MARKER_M2 " * 40)]
    rows = _post_batch(files).get_json()["results"]
    try:
        before = _outputs_count()
        zr = _zip_of(rows)
        assert zr.status_code == 200
        after = _outputs_count()
        assert after == before, \
            f"ZIP-Aufruf hat Datei(en) in outputs/ hinterlassen ({before}->{after})"
    finally:
        _cleanup(rows)


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

ALL_TESTS = [
    test_multiple_valid_unique_ids_no_swap,
    test_mixed_valid_and_broken_runs_through,
    test_limit_21_rejected_nothing_processed,
    test_exactly_20_allowed,
    test_empty_batch_rejected,
    test_origin_check_batch,
    test_zip_server_side_ok_gate,
    test_zip_name_collision,
    test_zip_in_memory_no_leftover,
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
