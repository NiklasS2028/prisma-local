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

import os
import json
import uuid
import tempfile
import threading

from flask import Flask, request, jsonify, send_file, Response

from converter import convert_file, SUPPORTED_EXTENSIONS
from prompt_trainer import analyze_prompt

app = Flask(__name__)

# Ordner fuer temporaere Uploads und fertige Ausgaben
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Max. Upload-Groesse: 500 MB.
# (Schuetzt nur vor versehentlichem Hochladen riesiger Dateien.
#  Falls du doch mal groessere Dateien brauchst, hier die Zahl erhoehen.)
MAX_MB = 500
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024

# HTML-Oberflaeche liegt als separate Datei daneben
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

# ---------------------------------------------------------------------------
# LOKALE STATISTIK (stats.json)
# ---------------------------------------------------------------------------
# HARTE REGEL: Diese Datei speichert AUSSCHLIESSLICH aggregierte Zahlen.
# Niemals Dateinamen, Prompt-Texte, Dokumentinhalte oder Zeitstempel mit
# Bezug zu konkreten Aktionen. Das Versprechen "nichts verlaesst den PC,
# nichts wird inhaltlich protokolliert" haengt an dieser Regel.

STATS_PATH = os.path.join(BASE_DIR, "stats.json")
_STATS_LOCK = threading.Lock()

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
    try:
        with open(STATS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("stats.json ist kein Objekt")
    except Exception:
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
    return clean


def _save_stats(stats):
    """Schreibt stats.json ATOMAR: erst vollstaendig in eine .tmp-Datei im
    selben Verzeichnis, dann os.replace (atomar auf NTFS). Ein Absturz
    mitten im Schreiben kann so nie die bestehende Datei zerstoeren.
    Fehler duerfen die Kernfunktion nie stoppen."""
    tmp_path = STATS_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
        os.replace(tmp_path, STATS_PATH)
    except Exception:
        # Original bleibt unberuehrt; .tmp-Rest best effort entfernen
        try:
            os.remove(tmp_path)
        except OSError:
            pass


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
        "error": f"Datei ist zu gross (Limit: {MAX_MB} MB). "
                 f"Erhoehe MAX_MB in app.py, falls du groessere Dateien brauchst.",
    }), 413


@app.route("/")
def index():
    """Liefert die Weboberflaeche aus."""
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


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

    ext = os.path.splitext(upload.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return jsonify({
            "ok": False,
            "error": f"Dateityp '{ext}' nicht unterstuetzt. "
                     f"Moeglich: {', '.join(SUPPORTED_EXTENSIONS)}",
        }), 400

    # Ziel-Modell aus dem Formular lesen (claude/gpt/gemini/none)
    target_model = request.form.get("target_model", "none").lower()

    # Upload temporaer speichern (eindeutiger Name, um Kollisionen zu vermeiden)
    tmp_name = f"{uuid.uuid4().hex}{ext}"
    tmp_path = os.path.join(UPLOAD_DIR, tmp_name)
    upload.save(tmp_path)

    try:
        result = convert_file(tmp_path, target_model=target_model,
                              original_name=upload.filename)
    finally:
        # Upload sofort wieder loeschen - wir brauchen nur das Ergebnis
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    if not result.get("ok"):
        return jsonify(result), 400

    # Ausgabedatei schreiben (fuer den Download)
    base_no_ext = os.path.splitext(upload.filename)[0]
    out_filename = f"{base_no_ext}{result['output_ext']}"
    out_id = f"{uuid.uuid4().hex}{result['output_ext']}"
    out_path = os.path.join(OUTPUT_DIR, out_id)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result["output_text"])

    # Download-Info ins Ergebnis packen
    result["download_id"] = out_id
    result["download_name"] = out_filename

    # Vorschau kuerzen, damit das JSON nicht riesig wird
    preview = result["output_text"]
    if len(preview) > 4000:
        preview = preview[:4000] + "\n\n... (gekuerzt - vollstaendig in der Download-Datei)"
    result["preview"] = preview

    return jsonify(result)


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
    print("=" * 60)
    print("  PRISMA laeuft!")
    print(f"  Oeffne im Browser:  http://localhost:{port}")
    print(f"  Max. Dateigroesse:  {MAX_MB} MB")
    print("  Beenden mit:        Strg + C")
    print("=" * 60)
    # host=127.0.0.1 -> nur lokal erreichbar, nichts geht ins Netz
    app.run(host="127.0.0.1", port=port, debug=False)
