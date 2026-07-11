"""
prompt_trainer.py
-----------------
Kern-Logik des Prompt-Trainers (Lern-Werkzeug fuer Anfaenger).

WICHTIG - Ehrliche Einordnung:
Dieses Modul nutzt KEINE KI. Es prueft Prompts mit nachvollziehbaren
Regeln (Heuristiken) auf strukturelle Qualitaet und erklaert, WARUM
etwas fehlt - mit Beispielen. Es kann den Inhalt eines Prompts nicht
"verstehen" und erfindet nichts dazu. Fehlende Teile werden als
Platzhalter-Fragen in die Vorlage eingebaut, die der Nutzer selbst
beantwortet. Genau dieses Selbst-Ausfuellen ist der Lerneffekt.

Alle Regeln arbeiten zweisprachig (Deutsch + Englisch).
"""

import re

# ---------------------------------------------------------------------------
# SIGNALWORT-LISTEN (Deutsch + Englisch)
# ---------------------------------------------------------------------------
# Kleinschreibung; Pruefung erfolgt auf dem kleingeschriebenen Prompt.

# Aufgaben-Verben: erkennen, ob eine klare Anweisung existiert
_TASK_VERBS = [
    # Deutsch (Stamm-Formen, damit "schreibe"/"schreib" beide treffen)
    "schreib", "erstell", "erklaer", "erklär", "fass", "analysier",
    "uebersetze", "übersetze", "übersetz", "generier", "mach", "hilf",
    "gib ", "liste", "vergleich", "bewerte", "korrigier", "verbesser",
    "formulier", "entwirf", "plane ", "berechne", "zeig", "nenn",
    "beschreib", "definier", "pruef", "prüf", "optimier", "kuerz", "kürz",
    # Englisch
    "write", "create", "explain", "summar", "analyz", "analys",
    "translate", "generate", "make ", "help", "give ", "list ",
    "compare", "evaluate", "review", "fix ", "improve", "draft",
    "design", "plan ", "calculate", "show ", "describe", "define",
    "check", "optimize", "shorten", "rewrite", "build",
]

# Kontext-Signale: Hintergrund, Zweck, Zielgruppe
_CONTEXT_SIGNALS = [
    # Deutsch
    "weil", "da ich", "da wir", "hintergrund", "kontext", "ziel ist",
    "es geht um", "ich bin", "wir sind", "ich arbeite", "fuer mein",
    "für mein", "fuer die", "für die", "fuer einen", "für einen",
    "fuer eine", "für eine", "zielgruppe", "an mein", "an unser",
    "im rahmen", "situation", "ich moechte", "ich möchte", "ich will",
    "wir wollen", "damit ich", "damit wir", "zweck",
    # Englisch
    "because", "since i", "background", "context", "the goal",
    "my goal", "i am ", "i'm ", "we are", "i work", "for my",
    "for a ", "for the", "audience", "purpose", "in order to",
    "so that", "i want", "we want", "i need", "we need",
]

# Rollen-Signale
_ROLE_SIGNALS = [
    # Deutsch
    "du bist", "sie sind ein", "als erfahren", "als expert", "als profi",
    "verhalte dich", "agiere als", "nimm die rolle", "in der rolle",
    "du agierst", "stell dir vor, du",
    # Englisch
    "you are", "you're a", "act as", "acting as", "as an expert",
    "as a senior", "as a professional", "take the role", "roleplay as",
    "imagine you are", "pretend you are",
]

# Format-Signale: gewuenschte Ausgabeform
_FORMAT_SIGNALS = [
    # Deutsch
    "als liste", "als tabelle", "stichpunkt", "aufzaehlung", "aufzählung",
    "absatz", "abschnitt", "woerter", "wörter", "zeichen", "saetze",
    "sätze", "maximal", "hoechstens", "höchstens", "mindestens", "kurz ",
    "ausfuehrlich", "ausführlich", "als json", "als e-mail", "als email",
    "als mail", "als tweet", "als post", "ueberschrift", "überschrift",
    "nummerier", "gliederung", "format", "auf deutsch", "auf englisch",
    "in einem satz", "in drei", "in 3", "schritt fuer schritt",
    "schritt für schritt", "als markdown", "als code",
    # Englisch
    "as a list", "as a table", "bullet point", "paragraph", "section",
    "words", "characters", "sentences", "maximum", "at most", "at least",
    "brief", "detailed", "as json", "as an email", "as a tweet",
    "headline", "numbered", "outline", "step by step", "in one sentence",
    "in three", "in 3", "markdown", "as code", "in german", "in english",
]

# Beispiel-Signale
_EXAMPLE_SIGNALS = [
    "z.b.", "z. b.", "zum beispiel", "beispiel:", "beispiele:",
    "beispiel fuer", "beispiel für", "beispiel waere", "beispiel wäre",
    "ein beispiel", "als beispiel", "etwa so", "wie etwa", "so wie",
    "beispielsweise",
    "e.g.", "for example", "example:", "examples:", "for instance",
    "an example", "such as", "like this",
]

# Vage Woerter: verwaessern die Spezifitaet
_VAGUE_WORDS = [
    # Deutsch
    "irgendwas", "irgendwie", "irgendein", "etwas gutes", "was gutes",
    "was schoenes", "was schönes", "ein bisschen", "bisschen was",
    "das ding", "dings", "zeug", "halt ", "einfach mal", "mal was",
    "usw", "und so weiter", "oder so",
    # Englisch
    "something good", "something nice", "some stuff", "stuff about",
    "kind of", "sort of", "whatever", "anything", "etc", "and so on",
    "or something",
]


# ---------------------------------------------------------------------------
# HILFSFUNKTIONEN
# ---------------------------------------------------------------------------

def _contains_any(text: str, signals) -> bool:
    return any(s in text for s in signals)


def _count_matches(text: str, signals) -> int:
    return sum(1 for s in signals if s in text)


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


# ---------------------------------------------------------------------------
# DIE 6 CHECKS
# ---------------------------------------------------------------------------
# Jeder Check gibt zurueck: status (1.0 erfuellt / 0.5 teilweise / 0.0 fehlt)
# plus die Texte fuer die Anzeige. Erklaertexte sind fuer ANFAENGER
# geschrieben: kurz, konkret, immer mit Schlecht->Gut-Beispiel.

def _check_task(text: str, words: int) -> dict:
    has_verb = _contains_any(text, _TASK_VERBS)
    has_question = "?" in text
    if has_verb:
        status = 1.0
    elif has_question:
        status = 0.5  # Frage ist ok, aber Anweisung ist meist staerker
    else:
        status = 0.0
    return {
        "id": "task",
        "titel": "Klare Aufgabe",
        "gewicht": 3.0,
        "optional": False,
        "status": status,
        "frage": "Sagt der Prompt eindeutig, WAS die KI tun soll?",
        "warum": ("Die KI raet sonst, was du willst - und raet oft falsch. "
                  "Eine klare Anweisung ist der wichtigste Teil jedes Prompts."),
        "beispiel_schlecht": "Hunde.",
        "beispiel_gut": "Erklaere mir die 3 wichtigsten Dinge bei der Hundeerziehung.",
        "feedback": {
            1.0: "Klare Anweisung erkannt - gut!",
            0.5: "Eine Frage ist da, aber eine direkte Anweisung (z.B. 'Erklaere...', 'Schreibe...') macht das Ziel oft noch klarer.",
            0.0: "Es ist keine klare Aufgabe erkennbar. Beginne mit einem Verb: 'Schreibe...', 'Erklaere...', 'Erstelle...'",
        },
    }


def _check_context(text: str, words: int) -> dict:
    signal_hits = _count_matches(text, _CONTEXT_SIGNALS)
    if signal_hits >= 2 or (signal_hits >= 1 and words >= 15):
        status = 1.0
    elif signal_hits >= 1 or words >= 25:
        status = 0.5
    else:
        status = 0.0
    return {
        "id": "context",
        "titel": "Kontext & Zweck",
        "gewicht": 2.0,
        "optional": False,
        "status": status,
        "frage": "Weiss die KI, WOFUER und FUER WEN du das brauchst?",
        "warum": ("Derselbe Text sieht voellig anders aus, je nachdem ob er fuer "
                  "deinen Chef, deine Oma oder ein Fachpublikum ist. Ohne Kontext "
                  "bekommst du Durchschnitt."),
        "beispiel_schlecht": "Schreib eine E-Mail wegen dem Termin.",
        "beispiel_gut": "Schreib eine E-Mail an meinen Professor, weil ich den Abgabetermin um 3 Tage verschieben muss (Grund: Krankheit).",
        "feedback": {
            1.0: "Kontext ist erkennbar - die KI weiss, worum es geht.",
            0.5: "Etwas Kontext ist da, aber mehr Hintergrund (Fuer wen? Warum? Worum genau?) wuerde das Ergebnis deutlich verbessern.",
            0.0: "Es fehlt Hintergrund: Wofuer brauchst du das? Fuer wen ist es? Was ist die Situation?",
        },
    }


def _check_specificity(text: str, words: int) -> dict:
    vague_hits = _count_matches(text, _VAGUE_WORDS)
    if words < 4:
        status = 0.0
    elif vague_hits >= 2:
        status = 0.0
    elif vague_hits == 1 or words < 8:
        status = 0.5
    else:
        status = 1.0
    return {
        "id": "specificity",
        "titel": "Konkretheit",
        "gewicht": 2.0,
        "optional": False,
        "status": status,
        "frage": "Ist der Prompt konkret genug - oder schwammig?",
        "warum": ("Vage Woerter wie 'irgendwas', 'was Gutes' oder 'oder so' zwingen "
                  "die KI zum Raten. Je konkreter du bist, desto besser das Ergebnis."),
        "beispiel_schlecht": "Mach mal was Schoenes fuer Social Media oder so.",
        "beispiel_gut": "Erstelle 3 Instagram-Caption-Varianten (je max. 100 Zeichen) fuer den Launch unserer Kaffee-Marke.",
        "feedback": {
            1.0: "Der Prompt ist konkret formuliert.",
            0.5: "Geht in die richtige Richtung, aber ein paar Stellen sind noch schwammig. Ersetze vage Woerter durch konkrete Angaben.",
            0.0: "Zu vage. Ersetze Woerter wie 'irgendwas' oder 'was Gutes' durch genaue Angaben: Was genau? Wie viel? Woruber?",
        },
    }


def _check_role(text: str, words: int) -> dict:
    status = 1.0 if _contains_any(text, _ROLE_SIGNALS) else 0.0
    return {
        "id": "role",
        "titel": "Rolle (optional)",
        "gewicht": 1.0,
        "optional": True,
        "status": status,
        "frage": "Hat die KI eine Rolle bekommen (z.B. 'Du bist ein erfahrener Lektor')?",
        "warum": ("Eine Rolle gibt der Antwort Perspektive und Tiefe. Bei einfachen "
                  "Fragen unnoetig - bei Fachthemen oder Texten oft ein grosser Hebel."),
        "beispiel_schlecht": "Verbessere diesen Text.",
        "beispiel_gut": "Du bist ein strenger Lektor einer Tageszeitung. Verbessere diesen Text.",
        "feedback": {
            1.0: "Rolle definiert - das gibt der Antwort Richtung.",
            0.0: "Keine Rolle definiert. Das ist ok - bei Fachthemen kann 'Du bist ein erfahrener ...' die Qualitaet aber spuerbar heben.",
        },
    }


def _check_format(text: str, words: int) -> dict:
    hits = _count_matches(text, _FORMAT_SIGNALS)
    if hits >= 2:
        status = 1.0
    elif hits == 1:
        status = 1.0  # ein klares Formatsignal reicht
    else:
        status = 0.0
    return {
        "id": "format",
        "titel": "Gewuenschtes Format",
        "gewicht": 1.5,
        "optional": False,
        "status": status,
        "frage": "Steht im Prompt, WIE die Antwort aussehen soll?",
        "warum": ("Ohne Format-Angabe entscheidet die KI selbst ueber Laenge und "
                  "Aufbau - und liefert oft zu viel oder zu wenig. Laenge, Form und "
                  "Sprache anzugeben kostet dich 5 Sekunden."),
        "beispiel_schlecht": "Erklaere mir Photosynthese.",
        "beispiel_gut": "Erklaere mir Photosynthese in maximal 5 Saetzen, so dass es ein 12-Jaehriger versteht.",
        "feedback": {
            1.0: "Format-Wunsch erkannt - die Antwort wird passen.",
            0.0: "Kein Format angegeben. Sag der KI: Wie lang? Liste oder Fliesstext? Fuer welches Publikum?",
        },
    }


def _check_examples(text: str, words: int) -> dict:
    status = 1.0 if _contains_any(text, _EXAMPLE_SIGNALS) else 0.0
    return {
        "id": "examples",
        "titel": "Beispiele (optional)",
        "gewicht": 1.0,
        "optional": True,
        "status": status,
        "frage": "Zeigt der Prompt ein Beispiel, wie das Ergebnis aussehen soll?",
        "warum": ("Ein Beispiel sagt mehr als drei Saetze Beschreibung. Besonders "
                  "wertvoll bei Stil-Fragen ('schreib im Stil von...') und "
                  "wiederkehrenden Formaten."),
        "beispiel_schlecht": "Schreib Produktbeschreibungen fuer meine Kerzen.",
        "beispiel_gut": "Schreib Produktbeschreibungen fuer meine Kerzen. Beispiel fuer den Stil: 'Warmes Licht, ehrlicher Duft - handgegossen in Koeln.'",
        "feedback": {
            1.0: "Beispiel vorhanden - das ist die staerkste Form der Anleitung.",
            0.0: "Kein Beispiel. Optional - aber bei Stil- und Formatfragen ist ein kurzes Beispiel oft der groesste Qualitaets-Hebel.",
        },
    }


_ALL_CHECKS = [_check_task, _check_context, _check_specificity,
               _check_format, _check_role, _check_examples]


# ---------------------------------------------------------------------------
# MODELLSPEZIFISCHE VORLAGEN
# ---------------------------------------------------------------------------
# Kuratiertes Wissen: Welches Modell mag welche Struktur.
#   Claude  -> XML-Tags (von Anthropic offiziell empfohlen)
#   GPT     -> Markdown-Ueberschriften / Delimiter (OpenAI-Stil)
#   Gemini  -> klare Markdown-Struktur (kommt mit beidem klar)
# Fehlende Teile werden als [Platzhalter-Fragen] eingefuegt, die der
# Nutzer selbst beantwortet - das ist der Lerneffekt.

_PLACEHOLDERS = {
    "role": {
        "de_frage": "Optional: Welche Rolle soll die KI einnehmen? "
                    "z.B. 'Du bist ein erfahrener Hundetrainer.'",
    },
    "context": {
        "de_frage": "Ergaenze: Wofuer brauchst du das? Fuer wen? Was ist die Situation? "
                    "z.B. 'Ich schreibe einen Blogartikel fuer Erstbesitzer.'",
    },
    "task_add": {
        "de_frage": "Mach die Aufgabe konkreter: Was genau soll entstehen? "
                    "z.B. 'Schreibe einen 300-Woerter-Ueberblick ueber die 5 wichtigsten Punkte.'",
    },
    "format": {
        "de_frage": "Ergaenze: Wie soll die Antwort aussehen? Laenge, Form, Sprache? "
                    "z.B. 'Als nummerierte Liste mit je 2-3 Saetzen pro Punkt.'",
    },
    "examples": {
        "de_frage": "Optional: Zeig ein kurzes Beispiel fuer Stil oder Aufbau des Ergebnisses.",
    },
}


def _build_template(prompt: str, checks: dict, model: str) -> str:
    """
    Baut die modellspezifische Vorlage. Der Original-Prompt wandert in den
    Aufgaben-Block; fuer schwache/fehlende Dimensionen kommen Platzhalter-
    Fragen dazu. Vorhandene optionale Bloecke ohne Befund werden weggelassen,
    damit die Vorlage nicht aufgeblaeht wird.
    """
    p = _PLACEHOLDERS
    sections = []  # Liste von (schluessel, ueberschrift, inhalt)

    # Rolle: nur aufnehmen, wenn sie fehlt UND der Prompt komplex genug ist,
    # dass sie sich lohnen koennte - sonst weglassen (kein Zwang zu Optionalem).
    if checks["role"]["status"] == 0.0 and _word_count(prompt) >= 6:
        sections.append(("role", "Rolle", f"[{p['role']['de_frage']}]"))

    if checks["context"]["status"] < 1.0:
        sections.append(("context", "Kontext", f"[{p['context']['de_frage']}]"))

    # Aufgabe: immer drin - Original-Prompt + ggf. Konkretisierungs-Hinweis
    task_content = prompt.strip()
    if checks["task"]["status"] < 1.0 or checks["specificity"]["status"] < 1.0:
        task_content += f"\n[{p['task_add']['de_frage']}]"
    sections.append(("task", "Aufgabe", task_content))

    if checks["format"]["status"] < 1.0:
        sections.append(("format", "Format", f"[{p['format']['de_frage']}]"))

    if checks["examples"]["status"] == 0.0 and _word_count(prompt) >= 10:
        sections.append(("examples", "Beispiel", f"[{p['examples']['de_frage']}]"))

    # --- Modellspezifisch rendern ---
    if model == "claude":
        # Anthropic-Empfehlung: XML-Tags
        tag_map = {"role": "role", "context": "context", "task": "task",
                   "format": "format", "examples": "examples"}
        parts = [f"<{tag_map[key]}>\n{content}\n</{tag_map[key]}>"
                 for key, _titel, content in sections]
        return "\n\n".join(parts)

    if model == "gpt":
        # OpenAI-Stil: Markdown-Ueberschriften als klare Abschnitte
        parts = [f"## {titel}\n{content}" for _key, titel, content in sections]
        return "\n\n".join(parts)

    if model == "gemini":
        # Gemini: klare, schlichte Struktur mit Labels
        parts = [f"**{titel}:**\n{content}" for _key, titel, content in sections]
        return "\n\n".join(parts)

    # "universal": schlichte Absaetze mit Labels (funktioniert ueberall)
    parts = [f"{titel}:\n{content}" for _key, titel, content in sections]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# HAUPTFUNKTION
# ---------------------------------------------------------------------------

def analyze_prompt(prompt: str, model: str = "claude") -> dict:
    """
    Analysiert einen Prompt und gibt zurueck:
      ok, score (0-100), ampel ('gruen'/'gelb'/'rot'), ampel_text,
      checks (Liste mit Status + Erklaerungen), template (Vorlage),
      model (fuer das die Vorlage gebaut wurde)
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return {"ok": False, "error": "Bitte gib zuerst einen Prompt ein."}

    if len(prompt) > 20000:
        return {"ok": False, "error": "Der Prompt ist sehr lang (>20.000 Zeichen). "
                                      "Bitte kuerze ihn fuer die Analyse."}

    model = model if model in ("claude", "gpt", "gemini", "universal") else "universal"
    text = prompt.lower()
    words = _word_count(prompt)

    # Sonderfall: praktisch leerer Prompt
    if words < 2:
        return {
            "ok": True,
            "score": 0,
            "ampel": "rot",
            "ampel_text": "Das ist noch kein vollstaendiger Prompt.",
            "checks": [],
            "template": "",
            "model": model,
            "hinweis": ("Ein Prompt braucht mindestens eine klare Aufgabe. "
                        "Starte mit einem Verb: 'Erklaere...', 'Schreibe...', 'Erstelle...'"),
        }

    # Alle Checks ausfuehren
    results = [check(text, words) for check in _ALL_CHECKS]
    by_id = {r["id"]: r for r in results}

    # Score: gewichteter Anteil
    total_weight = sum(r["gewicht"] for r in results)
    achieved = sum(r["gewicht"] * r["status"] for r in results)
    score = round(achieved / total_weight * 100)

    if score >= 75:
        ampel, ampel_text = "gruen", "Starker Prompt - gut strukturiert!"
    elif score >= 45:
        ampel, ampel_text = "gelb", "Solide Basis - mit wenigen Ergaenzungen wird er stark."
    else:
        ampel, ampel_text = "rot", "Braucht Arbeit - die Vorlage unten zeigt dir, was fehlt."

    # Fuer die Anzeige: pro Check den passenden Feedback-Text mitgeben
    checks_out = []
    for r in results:
        fb = r["feedback"].get(r["status"])
        if fb is None:  # 0.5 nicht ueberall definiert -> auf 0.0-Text zurueckfallen
            fb = r["feedback"].get(0.5) or r["feedback"][0.0]
        checks_out.append({
            "id": r["id"],
            "titel": r["titel"],
            "optional": r["optional"],
            "status": r["status"],
            "frage": r["frage"],
            "warum": r["warum"],
            "feedback": fb,
            "beispiel_schlecht": r["beispiel_schlecht"],
            "beispiel_gut": r["beispiel_gut"],
        })

    template = _build_template(prompt, by_id, model)

    return {
        "ok": True,
        "score": score,
        "ampel": ampel,
        "ampel_text": ampel_text,
        "checks": checks_out,
        "template": template,
        "model": model,
    }
