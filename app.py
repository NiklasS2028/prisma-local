"""
app.py
------
Lokaler Webserver fuer den Token-Konverter.

Startet einen kleinen Flask-Server auf http://localhost:8770
Die Weboberflaeche (index.html) laedt dort, du ziehst Dateien rein,
der Server konvertiert sie und bietet den Download an.

Alles laeuft nur auf deinem Rechner - keine Datei verlaesst deinen PC.

Start:  python app.py
"""

import os
import uuid
import tempfile

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
    result = analyze_prompt(prompt, model)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


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
    print("  TOKEN-KONVERTER laeuft!")
    print(f"  Oeffne im Browser:  http://localhost:{port}")
    print(f"  Max. Dateigroesse:  {MAX_MB} MB")
    print("  Beenden mit:        Strg + C")
    print("=" * 60)
    # host=127.0.0.1 -> nur lokal erreichbar, nichts geht ins Netz
    app.run(host="127.0.0.1", port=port, debug=False)
