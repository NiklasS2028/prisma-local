"""
app.py
------
Lokaler Webserver fuer Prisma (Datei-Konverter + Prompt-Trainer).

Startet einen kleinen Flask-Server auf http://localhost:8770
Die Weboberflaeche (index.html) laedt dort, du ziehst Dateien rein,
der Server konvertiert sie und bietet den Download an.

Alles laeuft nur auf deinem Rechner - keine Datei verlaesst deinen PC.

Start:  python app.py
"""

import io
import os
import sys
import json
import uuid
import zipfile
import tempfile
import datetime
import traceback
import threading
import webbrowser

from flask import Flask, request, jsonify, send_file, Response

from converter import convert_file, SUPPORTED_EXTENSIONS
from prompt_trainer import analyze_prompt

# ---------------------------------------------------------------------------
# FROZEN-TAUGLICHE PFADE (.exe vs. python app.py)
# ---------------------------------------------------------------------------
# PyInstaller setzt zur Laufzeit sys.frozen = True und legt den Pfad der
# laufenden .exe in sys.executable ab. Zwei Faelle sind zu trennen:
#   - Normalbetrieb (python app.py): alles __file__-basiert wie bisher.
#   - Eingefroren (.exe): NUR-LESBARE Ressourcen (index.html, static/) kommen
#     aus dem Bundle-Ort, SCHREIBBARE Daten (outputs/, stats.json) liegen
#     NEBEN der .exe, damit sie das Schliessen ueberleben.
# Wichtig: Im Normalbetrieb liefern beide Helfer denselben Pfad wie das
# fruehere BASE_DIR - also null Verhaltensaenderung ohne .exe.

_APP_FILE_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_dir():
    """Ort der gebuendelten NUR-LESBAREN Ressourcen (index.html, static/).
    Normal: der Ordner dieser Datei. Eingefroren onedir: der Ordner der .exe.
    Eingefroren onefile: der Temp-Entpackordner (sys._MEIPASS)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return _APP_FILE_DIR


def writable_dir():
    """Ort fuer SCHREIBBARE, persistente Daten (outputs/, stats.json, uploads/).
    Normal: der Ordner dieser Datei. Eingefroren: NEBEN der .exe (NICHT der
    Temp-Ordner - sonst waeren Statistik und Ausgaben nach dem Schliessen weg)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return _APP_FILE_DIR


app = Flask(__name__)

# Ordner fuer temporaere Uploads und fertige Ausgaben (schreibbar, persistent)
UPLOAD_DIR = os.path.join(writable_dir(), "uploads")
OUTPUT_DIR = os.path.join(writable_dir(), "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Max. Upload-Groesse: 500 MB.
# (Schuetzt nur vor versehentlichem Hochladen riesiger Dateien.
#  Falls du doch mal groessere Dateien brauchst, hier die Zahl erhoehen.)
MAX_MB = 500
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024

# Batch: hoechstens so viele Dateien pro Vorgang. Schuetzt vor dem
# versehentlichen Reinziehen hunderter Dateien. Die 500-MB-Grenze oben
# gilt bei Batch fuer die SUMME aller Dateien (Flask misst den gesamten
# Multipart-Request und wirft 413, bevor unser Code laeuft - abgefangen
# vom 413-Handler). Anzahl und Groesse sind damit zwei getrennte Grenzen.
MAX_BATCH_FILES = 20

# HTML-Oberflaeche liegt als separate Datei daneben (nur lesend -> resource_dir)
INDEX_PATH = os.path.join(resource_dir(), "index.html")

# ---------------------------------------------------------------------------
# LOKALE STATISTIK (stats.json)
# ---------------------------------------------------------------------------
# HARTE REGEL: Diese Datei speichert AUSSCHLIESSLICH aggregierte Zahlen.
# Niemals Dateinamen, Prompt-Texte, Dokumentinhalte oder Zeitstempel mit
# Bezug zu konkreten Aktionen. Das Versprechen "nichts verlaesst den PC,
# nichts wird inhaltlich protokolliert" haengt an dieser Regel.

STATS_PATH = os.path.join(writable_dir(), "stats.json")
_STATS_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# STATS-DIAGNOSE (Block A) - standardmaessig AUS, per Umgebungsvariable an
# ---------------------------------------------------------------------------
# Einschalten:  Umgebungsvariable PRISMA_DEBUG=1 setzen, dann Prisma starten
#   PowerShell:  $env:PRISMA_DEBUG = "1"; .\Prisma.exe
#   cmd:         set PRISMA_DEBUG=1 && Prisma.exe
# Schreibt dann Diagnose-Zeilen sowohl in die offene Konsole als auch in eine
# stats_debug.log NEBEN der .exe (writable_dir). Jede Zeile nennt die
# AUFRUFENDE Funktion (_caller), damit die Reihenfolge der read-modify-write-
# und reset-Zugriffe rekonstruierbar ist. Bleibt dauerhaft im Code: der
# urspruengliche Stats-Bug war auf dem Fremdrechner nicht reproduzierbar -
# taucht er bei einem Nutzer wieder auf, liefert PRISMA_DEBUG=1 sofort ein Log.
DEBUG_STATS = os.environ.get("PRISMA_DEBUG") == "1"
_DEBUG_LOG_PATH = os.path.join(writable_dir(), "stats_debug.log")


def _caller():
    """Name der Funktion, die die instrumentierte Funktion aufgerufen hat.
    Frame 0 = _caller, Frame 1 = die instrumentierte Funktion,
    Frame 2 = deren Aufrufer (die Route)."""
    try:
        return sys._getframe(2).f_code.co_name
    except Exception:
        return "?"


def _dbg(msg):
    if not DEBUG_STATS:
        return
    line = "[{}] {}".format(datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3], msg)
    try:
        print("DBG " + line, flush=True)
    except Exception:
        pass
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

_DEFAULT_STATS = {
    "files_converted": 0,
    "prompts_analyzed": 0,
    "tokens_saved_total": 0,
    "score_buckets": {"red": 0, "yellow": 0, "green": 0},
    "best_score": 0,
    "format_counts": {"pdf": 0, "docx": 0, "xlsx": 0, "csv": 0,
                      "txt": 0, "pptx": 0},
}


def _fresh_stats():
    """Tiefe Kopie der Null-Struktur."""
    return json.loads(json.dumps(_DEFAULT_STATS))


def _clean_int(value, lo=0, hi=None):
    """Akzeptiert nur echte Zahlen (kein bool), klemmt auf [lo, hi]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return lo
    n = int(value)
    if n < lo:
        n = lo
    if hi is not None and n > hi:
        n = hi
    return n


def _load_stats():
    """Liest stats.json defensiv: fehlende/kaputte Datei oder fremde
    Schluessel fuehren NIE zum Crash - es zaehlt nur die bekannte
    Nur-Zahlen-Struktur, alles andere wird verworfen."""
    caller = _caller()
    try:
        _exists = os.path.exists(STATS_PATH)
        _size = os.path.getsize(STATS_PATH) if _exists else -1
    except Exception:
        _exists, _size = "?", "?"
    _dbg("_load_stats <- {} | path={} exists={} size={}".format(
        caller, STATS_PATH, _exists, _size))
    try:
        with open(STATS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("stats.json ist kein Objekt")
    except Exception as e:
        _dbg("_load_stats READ-FEHLER/leer -> gibt NULLEN zurueck. Grund: {!r}".format(e))
        return _fresh_stats()

    clean = _fresh_stats()
    clean["files_converted"] = _clean_int(raw.get("files_converted"))
    clean["prompts_analyzed"] = _clean_int(raw.get("prompts_analyzed"))
    clean["tokens_saved_total"] = _clean_int(raw.get("tokens_saved_total"))
    clean["best_score"] = _clean_int(raw.get("best_score"), 0, 100)
    buckets = raw.get("score_buckets") or {}
    for key in clean["score_buckets"]:
        clean["score_buckets"][key] = _clean_int(
            buckets.get(key) if isinstance(buckets, dict) else 0)
    formats = raw.get("format_counts") or {}
    for key in clean["format_counts"]:
        clean["format_counts"][key] = _clean_int(
            formats.get(key) if isinstance(formats, dict) else 0)
    _dbg("_load_stats OK  files={} prompts={} tokens={} best={}".format(
        clean["files_converted"], clean["prompts_analyzed"],
        clean["tokens_saved_total"], clean["best_score"]))
    return clean


def _save_stats(stats):
    """Schreibt stats.json ATOMAR: erst vollstaendig in eine .tmp-Datei im
    selben Verzeichnis, dann os.replace (atomar auf NTFS). Ein Absturz
    mitten im Schreiben kann so nie die bestehende Datei zerstoeren.
    Fehler duerfen die Kernfunktion nie stoppen."""
    caller = _caller()
    _dbg("_save_stats <- {} | SCHREIBT files={} prompts={} tokens={} best={} -> {}".format(
        caller, stats.get("files_converted"), stats.get("prompts_analyzed"),
        stats.get("tokens_saved_total"), stats.get("best_score"), STATS_PATH))
    tmp_path = STATS_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
        os.replace(tmp_path, STATS_PATH)
        _dbg("_save_stats OK  ({}) geschrieben".format(caller))
    except Exception as e:
        # Original bleibt unberuehrt; .tmp-Rest best effort entfernen
        _dbg("_save_stats SCHREIBFEHLER ({}): {!r}".format(caller, e))
        _dbg(traceback.format_exc())
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _remove_files_in(dirpath):
    """Loescht alle Dateien DIREKT in dirpath (Unterordner und der Ordner
    selbst bleiben). Gibt die Anzahl geloeschter Dateien zurueck;
    Fehler stoppen nichts."""
    removed = 0
    try:
        names = os.listdir(dirpath)
    except OSError:
        return 0
    for name in names:
        path = os.path.join(dirpath, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed


# Origins, von denen zustandsaendernde POSTs akzeptiert werden (die eigene UI)
_ALLOWED_ORIGINS = {"http://127.0.0.1:8770", "http://localhost:8770"}


def _check_origin():
    """
    Wehrt Cross-Site-POSTs ab: Browser senden bei Cross-Site-Requests IMMER
    einen Origin-Header - ist er vorhanden und fremd, antworten wir 403.
    Fehlender Origin bleibt erlaubt (requests/curl/Tests senden keinen).
    Gibt None zurueck, wenn der Request passieren darf, sonst die 403-Antwort.
    """
    origin = request.headers.get("Origin")
    if origin and origin not in _ALLOWED_ORIGINS:
        return jsonify({"ok": False,
                        "error": "Anfrage von fremdem Origin abgelehnt."}), 403
    return None


@app.errorhandler(413)
def too_large(_e):
    """
    Saubere Fehlermeldung, wenn eine Datei ueber dem Limit liegt.
    Ohne diesen Handler bekaeme der Browser nur ein kryptisches '413'.
    """
    return jsonify({
        "ok": False,
        "error": f"Datei bzw. Dateien zusammen zu gross "
                 f"(Limit: {MAX_MB} MB pro Vorgang). "
                 f"Erhoehe MAX_MB in app.py, falls du groessere Dateien brauchst.",
    }), 413


@app.route("/")
def index():
    """Liefert die Weboberflaeche aus."""
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


def _process_upload(upload, target_model):
    """
    Gemeinsame Kette fuer Einzel- UND Batch-Konvertierung: validiert die
    Datei, speichert sie temporaer, schickt sie durch den BESTEHENDEN
    Konverter (convert_file - nicht dupliziert) und schreibt bei Erfolg die
    Ausgabedatei mit einer EIGENEN, eindeutigen download_id in OUTPUT_DIR.

    Genau dieses ID-Muster (download_id = Speichername in outputs/,
    download_name = Anzeigename) macht Vertauschung strukturell unmoeglich:
    der Download greift immer die Datei mit ID X, nie "das letzte Ergebnis".

    Gibt das reine Ergebnis-dict zurueck (KEINE HTTP-Antwort), damit beide
    Pfade exakt dieselbe Logik nutzen. Bei Erfolg enthaelt es zusaetzlich
    download_id + download_name; bei Fehler {"ok": False, "error": ...}.
    """
    filename = upload.filename or ""
    if not filename:
        return {"ok": False, "error": "Dateiname fehlt."}

    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {
            "ok": False,
            "error": f"Dateityp '{ext}' nicht unterstuetzt. "
                     f"Moeglich: {', '.join(SUPPORTED_EXTENSIONS)}",
        }

    # Upload temporaer speichern (eindeutiger Name, um Kollisionen zu vermeiden)
    tmp_name = f"{uuid.uuid4().hex}{ext}"
    tmp_path = os.path.join(UPLOAD_DIR, tmp_name)
    upload.save(tmp_path)

    try:
        result = convert_file(tmp_path, target_model=target_model,
                              original_name=filename)
    finally:
        # Upload sofort wieder loeschen - wir brauchen nur das Ergebnis
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    if not result.get("ok"):
        return result

    # Ausgabedatei mit eigener ID schreiben (fuer den Download)
    base_no_ext = os.path.splitext(os.path.basename(filename))[0]
    out_filename = f"{base_no_ext}{result['output_ext']}"
    out_id = f"{uuid.uuid4().hex}{result['output_ext']}"
    out_path = os.path.join(OUTPUT_DIR, out_id)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result["output_text"])

    result["download_id"] = out_id
    result["download_name"] = out_filename
    return result


@app.route("/convert", methods=["POST"])
def convert():
    """
    Nimmt eine hochgeladene Datei + die XML-Option entgegen,
    konvertiert sie und gibt das Ergebnis als JSON zurueck.
    Die fertige Datei wird in OUTPUT_DIR abgelegt und ueber /download geholt.
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Keine Datei empfangen."}), 400

    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"ok": False, "error": "Dateiname fehlt."}), 400

    # Ziel-Modell aus dem Formular lesen (claude/gpt/gemini/none)
    target_model = request.form.get("target_model", "none").lower()

    result = _process_upload(upload, target_model)
    if not result.get("ok"):
        return jsonify(result), 400

    # Vorschau kuerzen, damit das JSON nicht riesig wird
    preview = result["output_text"]
    if len(preview) > 4000:
        preview = preview[:4000] + "\n\n... (gekuerzt - vollstaendig in der Download-Datei)"
    result["preview"] = preview

    return jsonify(result)


@app.route("/convert-batch", methods=["POST"])
def convert_batch():
    """
    Nimmt MEHRERE Dateien (FormData-Feld 'files') entgegen und schickt sie
    NACHEINANDER (nicht parallel - OCR ist CPU-intensiv) durch dieselbe
    Kette wie /convert. Jede Datei behaelt ihre eigene download_id, also ist
    Vertauschung strukturell ausgeschlossen.

    Zwei getrennte Grenzen:
      - GROESSE: 500 MB fuer den GESAMTEN Request (Summe aller Dateien).
        Das prueft Flask via MAX_CONTENT_LENGTH und wirft 413, bevor diese
        Funktion ueberhaupt laeuft - der 413-Handler liefert die
        verstaendliche Meldung.
      - ANZAHL: max. MAX_BATCH_FILES. Das pruefen wir hier, BEVOR
        irgendeine Datei verarbeitet wird.

    Partielle Fehler brechen den Batch NICHT ab: schlaegt Datei 3 fehl,
    laufen 4 und 5 trotzdem. Zurueck kommt pro Datei ein Ergebnis-Objekt
    (Status 'ok' oder 'error'), jedes mit eigener ID.
    """
    denied = _check_origin()
    if denied:
        return denied

    # leere Eintraege (Feld ohne Dateiname) rauswerfen
    uploads = [u for u in request.files.getlist("files") if u and u.filename]
    if not uploads:
        return jsonify({"ok": False, "error": "Keine Dateien empfangen."}), 400
    if len(uploads) > MAX_BATCH_FILES:
        return jsonify({
            "ok": False,
            "error": f"Maximal {MAX_BATCH_FILES} Dateien gleichzeitig - "
                     f"bitte in kleineren Gruppen konvertieren.",
        }), 400

    target_model = request.form.get("target_model", "none").lower()

    results = []
    for upload in uploads:
        original_name = os.path.basename(upload.filename)
        # id = Zeilen-ID fuer die Frontend-Liste; die eigentliche
        # Vertausch-Sicherheit haengt an download_id (s.u.).
        item = {
            "id": uuid.uuid4().hex,
            "name": original_name,
            "format": os.path.splitext(original_name)[1].lower().lstrip("."),
        }
        try:
            res = _process_upload(upload, target_model)
        except Exception as e:
            # Eine einzelne kaputte Datei darf den Batch NIE mitreissen.
            item["status"] = "error"
            item["error"] = f"Fehler beim Verarbeiten der Datei: {e}"
            results.append(item)
            continue

        if res.get("ok"):
            item["status"] = "ok"
            item["download_id"] = res["download_id"]
            item["download_name"] = res["download_name"]
            item["target_format"] = res["target_format"]
            item["tokens_before"] = res["tokens_before"]
            item["tokens_after"] = res["tokens_after"]
            item["tokens_saved"] = res["tokens_saved"]
            item["percent_saved"] = res["percent_saved"]
            item["token_method"] = res["token_method"]
            item["was_ocr"] = res["was_ocr"]
            item["target_model"] = res["target_model"]
            item["note"] = res["note"]
        else:
            item["status"] = "error"
            item["error"] = res.get("error", "Unbekannter Fehler.")
            if res.get("error_detail"):
                item["error_detail"] = res["error_detail"]
        results.append(item)

    return jsonify({"ok": True, "count": len(results), "results": results})


def _unique_zip_name(name, used):
    """Verhindert Namenskollisionen INNERHALB der ZIP: liegt 'bericht.md'
    schon drin, wird die zweite Datei zu 'bericht (2).md', die dritte zu
    'bericht (3).md' usw. Vergleich case-insensitiv, weil ZIPs unter Windows
    sonst als Duplikat kollidieren. 'used' ist das Set der schon vergebenen
    Namen (lowercase)."""
    base, ext = os.path.splitext(name)
    candidate = name
    n = 2
    while candidate.lower() in used:
        candidate = f"{base} ({n}){ext}"
        n += 1
    used.add(candidate.lower())
    return candidate


@app.route("/download-batch", methods=["POST"])
def download_batch():
    """
    Schnuert aus MEHREREN Ergebnis-Dateien EINE ZIP - komplett im
    Arbeitsspeicher (io.BytesIO + zipfile), es bleibt KEINE Zwischendatei in
    outputs/ liegen.

    Der Client schickt die Liste der IDs (+ Anzeigenamen), die in die ZIP
    sollen:  {"files": [{"id": "<download_id>", "name": "bericht.md"}, ...]}

    VERTAUSCH- UND MANIPULATIONS-SCHUTZ (Defense in Depth):
      - Gezogen wird ausschliesslich PER ID, nie per Reihenfolge.
      - Der Server prueft JEDE ID serverseitig: nur eine ID, zu der WIRKLICH
        eine Datei in OUTPUT_DIR existiert, kommt in die ZIP. Fehlgeschlagene
        Konvertierungen schreiben NIE eine Ausgabedatei - ihre ID kann also
        gar nicht existieren. Ein manipulierter Request mit einer error-ID
        oder erfundenen ID laeuft damit ins Leere (Datei nicht vorhanden).
      - os.path.basename gegen Pfad-Traversal, nur unsere .md/.csv-Endungen.
    """
    denied = _check_origin()
    if denied:
        return denied

    data = request.get_json(silent=True) or {}
    entries = data.get("files")
    if not isinstance(entries, list) or not entries:
        return jsonify({
            "ok": False,
            "error": "Keine Dateien zum Herunterladen angegeben.",
        }), 400

    buf = io.BytesIO()
    used_names = set()
    added = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            safe_id = os.path.basename(str(entry.get("id", "")))
            if not safe_id:
                continue
            # Nur unsere Ausgabe-Endungen zulassen
            if os.path.splitext(safe_id)[1].lower() not in (".md", ".csv"):
                continue
            path = os.path.join(OUTPUT_DIR, safe_id)
            # DER serverseitige ok-Status-Check: existiert die Datei wirklich?
            # (Nur erfolgreiche Konvertierungen haben hier eine Datei liegen.)
            if not os.path.isfile(path):
                continue
            display = os.path.basename(str(entry.get("name") or safe_id))
            arcname = _unique_zip_name(display, used_names)
            with open(path, "rb") as f:
                zf.writestr(arcname, f.read())
            added += 1

    if added == 0:
        return jsonify({
            "ok": False,
            "error": "Keine gueltigen Dateien fuer den Download gefunden "
                     "(evtl. Server neu gestartet).",
        }), 400

    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name="prisma_export.zip")


@app.route("/analyze_prompt", methods=["POST"])
def analyze():
    """
    Prompt-Trainer: Nimmt einen Prompt + Ziel-Modell entgegen und gibt die
    Analyse (Score, Ampel, Checks, Vorlage) als JSON zurueck.
    Laeuft komplett lokal - der Prompt verlaesst den Rechner nicht.
    """
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "")
    model = data.get("model", "claude")
    ui_lang = data.get("ui_lang", "de")
    result = analyze_prompt(prompt, model, ui_lang=ui_lang)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@app.route("/stats")
def stats_get():
    """Liefert die lokale Statistik (nur aggregierte Zahlen)."""
    with _STATS_LOCK:
        return jsonify(_load_stats())


@app.route("/stats/count_file", methods=["POST"])
def stats_count_file():
    """
    Zaehl-Event des Clients: Der Nutzer hat ein Konvertierungs-Ergebnis
    wirklich GENUTZT (Download oder Zwischenablage). Der Client schickt
    das Event pro Ergebnis nur einmal. Payload: nur Zahlen + Format-Kategorie.
    Cross-Site-POSTs fremder Webseiten werden per Origin-Check abgewiesen.
    """
    denied = _check_origin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    saved = _clean_int(data.get("saved_tokens"))
    fmt = str(data.get("format", "")).lower()
    fmt = {"xlsm": "xlsx", "md": "txt"}.get(fmt, fmt)
    with _STATS_LOCK:
        stats = _load_stats()
        stats["files_converted"] += 1
        stats["tokens_saved_total"] += saved
        if fmt in stats["format_counts"]:
            stats["format_counts"][fmt] += 1
        _save_stats(stats)
        return jsonify({"ok": True, "stats": stats})


@app.route("/stats/count_prompt", methods=["POST"])
def stats_count_prompt():
    """
    Zaehl-Event des Clients: eine Prompt-Analyse (pro Prompt-Inhalt nur
    einmal - die Dopplungs-Entscheidung trifft der Client).
    Payload: nur Score-Zahl + Ampel-Kategorie, NIE der Prompt selbst.
    Cross-Site-POSTs fremder Webseiten werden per Origin-Check abgewiesen.
    """
    denied = _check_origin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    score = _clean_int(data.get("score"), 0, 100)
    bucket = {"rot": "red", "gelb": "yellow", "gruen": "green"}.get(data.get("ampel"))
    if bucket is None:
        return jsonify({"ok": False, "error": "Unbekannte Ampel-Farbe."}), 400
    with _STATS_LOCK:
        stats = _load_stats()
        stats["prompts_analyzed"] += 1
        stats["score_buckets"][bucket] += 1
        stats["best_score"] = max(stats["best_score"], score)
        _save_stats(stats)
        return jsonify({"ok": True, "stats": stats})


@app.route("/stats/reset", methods=["POST"])
def stats_reset():
    """Setzt die Statistik auf Null. Die zweistufige Bestaetigung passiert
    im Client; serverseitig schuetzt der Origin-Check vor Cross-Site-POSTs
    fremder Webseiten (mehr ist bei einem localhost-Tool nicht noetig)."""
    denied = _check_origin()
    if denied:
        return denied
    with _STATS_LOCK:
        stats = _fresh_stats()
        _save_stats(stats)
        return jsonify({"ok": True, "stats": stats})


@app.route("/outputs/info")
def outputs_info():
    """Anzahl + Gesamtgroesse der gespeicherten Ausgabedateien.
    NUR Zahlen, keine Dateinamen - die Datenschutz-Regel der Statistik
    gilt auch hier."""
    count = 0
    total = 0
    try:
        for name in os.listdir(OUTPUT_DIR):
            path = os.path.join(OUTPUT_DIR, name)
            if os.path.isfile(path):
                count += 1
                total += os.path.getsize(path)
    except OSError:
        pass
    return jsonify({"count": count, "total_bytes": total})


@app.route("/outputs/clear", methods=["POST"])
def outputs_clear():
    """Loescht alle gespeicherten Ausgabedateien. Die zweistufige
    Bestaetigung passiert im Client; serverseitig schuetzt der Origin-Check
    vor Cross-Site-POSTs. Alte Download-Links laufen danach in den
    bestehenden 404-Pfad von /download."""
    denied = _check_origin()
    if denied:
        return denied
    removed = _remove_files_in(OUTPUT_DIR)
    return jsonify({"ok": True, "removed": removed})


@app.route("/outputs/open", methods=["POST"])
def outputs_open():
    """Oeffnet den outputs-Ordner im Datei-Explorer. Das ist ein
    OS-Seiteneffekt, den ein Cross-Site-POST sonst spammen koennte -
    deshalb origin-geprueft (F.4-Helper). Auf Systemen ohne os.startfile
    (Nicht-Windows) kommt eine ehrliche JSON-Fehlermeldung statt Absturz."""
    denied = _check_origin()
    if denied:
        return denied
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        if not hasattr(os, "startfile"):
            return jsonify({
                "ok": False,
                "error": "Ordner-Oeffnen wird nur unter Windows unterstuetzt.",
            }), 501
        os.startfile(OUTPUT_DIR)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Ordner konnte nicht geoeffnet werden: {e}",
        }), 500


@app.route("/download/<out_id>")
def download(out_id):
    """Liefert eine fertige Ausgabedatei zum Herunterladen."""
    # Sicherheit: nur Dateinamen ohne Pfad-Anteile zulassen
    safe_id = os.path.basename(out_id)
    path = os.path.join(OUTPUT_DIR, safe_id)
    if not os.path.exists(path):
        return "Datei nicht gefunden (evtl. Server neu gestartet).", 404

    # gewuenschten Download-Namen aus Query holen
    download_name = request.args.get("name", safe_id)
    return send_file(path, as_attachment=True, download_name=download_name)


if __name__ == "__main__":
    port = 8770
    # Verwaiste Upload-Reste entfernen (bleiben nur nach hartem Abbruch
    # mitten in einer Konvertierung liegen - normal wird sofort geloescht).
    purged = _remove_files_in(UPLOAD_DIR)
    print("=" * 60)
    print("  PRISMA laeuft!")
    print(f"  Upload-Reste geloescht: {purged}")
    print(f"  Oeffne im Browser:  http://localhost:{port}")
    print(f"  Max. Dateigroesse:  {MAX_MB} MB")
    print("  Beenden mit:        Strg + C")
    print("=" * 60)

    # --- Instrumentierung Block A/2: Laufzeit-Pfade + Ist-Zustand stats.json ---
    _dbg("=== PRISMA START (Instrumentierung Block A/2) ===")
    _dbg("START frozen={} executable={}".format(
        getattr(sys, "frozen", False), sys.executable))
    _dbg("START writable_dir={}".format(writable_dir()))
    _dbg("START resource_dir={}".format(resource_dir()))
    _dbg("START STATS_PATH={}".format(STATS_PATH))
    _dbg("START DEBUG_LOG={}".format(_DEBUG_LOG_PATH))
    try:
        _st_exists = os.path.exists(STATS_PATH)
        _st_head = ""
        if _st_exists:
            with open(STATS_PATH, "r", encoding="utf-8") as _f:
                _st_head = _f.read(300)
        _dbg("START stats.json exists={} head={!r}".format(_st_exists, _st_head))
    except Exception as _e:
        _dbg("START stats.json Check-Fehler: {!r}".format(_e))

    # Browser-Autostart NUR im eingefrorenen (.exe-)Zustand: dort gibt es
    # keine start.bat mehr. Im normalen "python app.py"-Betrieb bleibt der
    # Autostart bei start.bat, sonst ginge der Browser doppelt auf.
    if getattr(sys, "frozen", False):
        def _open_browser():
            try:
                webbrowser.open(f"http://localhost:{port}")
            except Exception:
                pass  # kein Browser gesetzt o.ae. - Server laeuft trotzdem
        # app.run blockiert, daher zeitversetzt in einem Daemon-Thread starten
        threading.Timer(1.5, _open_browser).start()

    # host=127.0.0.1 -> nur lokal erreichbar, nichts geht ins Netz
    app.run(host="127.0.0.1", port=port, debug=False)
