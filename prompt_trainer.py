# -*- coding: utf-8 -*-
"""
prompt_trainer.py (v2)
----------------------
Kern-Logik des Prompt-Trainers (Lern-Werkzeug für Anfänger).

WICHTIG - Ehrliche Einordnung:
Dieses Modul nutzt KEINE KI. Es prüft Prompts mit nachvollziehbaren
Regeln (Heuristiken) auf strukturelle Qualität und erklärt, WARUM
etwas fehlt - mit Beispielen. Es kann den Inhalt eines Prompts nicht
"verstehen" und erfindet nichts dazu. Fehlende Teile werden als
Platzhalter-Fragen in die Vorlage eingebaut, die der Nutzer selbst
beantwortet. Genau dieses Selbst-Ausfüllen ist der Lerneffekt.

Neu in v2:
  - Wortgrenzen-Matching (_rx_prefix/_rx_exact) statt Substring-Suche:
    "Informationen" triggert nicht mehr das Format-Signal "format",
    "in 30 Minuten" nicht mehr "in 3", "ebenso wie" nicht mehr "so wie".
  - Fragen zählen als vollwertige Aufgabe (Variante "question").
  - Situativer Input-Check: Bei Transformationsverben ("fasse zusammen",
    "verbessere") wird geprüft, ob das Material überhaupt da ist.
  - Format-Zahlerkennung ("3 Varianten", "200 Wörter").
  - Zweisprachig: TEXTS (Feedback in ui_lang), EXAMPLES (domänenpassend).
    Die VORLAGEN-Sprache folgt der erkannten Prompt-Sprache (prompt_lang),
    nicht der UI-Sprache.
  - Anti-Dopplungs-Tipp (move_tip) gegen Rolle/Kontext doppelt in der Vorlage.

Signatur: analyze_prompt(prompt, model, ui_lang='de') -> dict (inkl. prompt_lang)
"""

import re


# ---------------------------------------------------------------------------
# REGEX-HELFER: WORTGRENZEN STATT SUBSTRING
# ---------------------------------------------------------------------------
# Der v1-Bug: einfaches "signal in text" fand 'format' mitten in
# 'Informationen'. Deshalb bauen wir jetzt kompilierte Regexe:
#   _rx_exact:  Phrase muss an BEIDEN Enden an einer Wortgrenze stehen.
#   _rx_prefix: Wortanfang reicht ('schreib' trifft 'schreibe'/'schreibst'),
#               aber davor muss eine Wortgrenze sein ('be-schreib' zählt nicht,
#               dafür gibt es den eigenen Stamm 'beschreib').
# (?<!\w)/(?!\w) statt \b, weil \b bei Phrasen mit Satzzeichen ('z.b.')
# am Ende nicht zuverlässig funktioniert.

def _rx_exact(phrases):
    alts = "|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:" + alts + r")(?!\w)")


def _rx_prefix(stems):
    alts = "|".join(re.escape(p) for p in sorted(stems, key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:" + alts + r")")


def _count_distinct(rx, text):
    """Wie viele VERSCHIEDENE Signale matchen (nicht: wie oft insgesamt)."""
    return len(set(rx.findall(text)))


def _word_count(text):
    return len(re.findall(r"\S+", text))


# ---------------------------------------------------------------------------
# SIGNALLISTEN (Deutsch + Englisch, geprüft auf kleingeschriebenem Prompt)
# ---------------------------------------------------------------------------

# Aufgaben-Verben (Stämme: 'schreib' trifft 'schreibe'/'schreibst')
_TASK_VERB_RX = _rx_prefix([
    # Deutsch
    "schreib", "erstell", "erklär", "erklaer", "fass", "analysier",
    "übersetz", "uebersetz", "generier", "mach", "hilf", "gib", "liste",
    "vergleich", "bewert", "korrigier", "verbesser", "formulier", "entwirf",
    "plane", "berechn", "zeig", "nenn", "beschreib", "definier", "prüf",
    "pruef", "optimier", "kürz", "kuerz", "überarbeit", "ueberarbeit",
    "empfiehl", "empfehl",
    # Englisch
    "write", "creat", "explain", "summar", "analyz", "analys", "translat",
    "generat", "make", "help", "give", "list", "compar", "evaluat",
    "review", "fix", "improv", "draft", "design", "plan", "calculat",
    "show", "describ", "defin", "check", "optimiz", "optimis", "shorten",
    "rewrit", "build", "suggest", "recommend",
])

# Frage-Anfangswörter: eine präzise Frage ist eine VOLLWERTIGE Aufgabe
_QUESTION_STARTS = {
    # Deutsch
    "was", "wie", "warum", "wieso", "weshalb", "welche", "welcher",
    "welches", "wann", "wo", "wer", "wem", "wen", "womit", "wofür",
    "wofuer", "kann", "kannst", "ist", "sind", "gibt", "hat", "haben",
    "darf", "muss", "soll", "sollte", "wäre", "waere",
    # Englisch
    "what", "how", "why", "which", "when", "where", "who", "whom",
    "can", "could", "is", "are", "does", "do", "should", "would",
    "will", "did", "has", "have", "am",
}

# Transformationsverben: der Prompt will vorhandenes Material BEARBEITEN.
# Nur dann erscheint der situative Input-Check.
_TRANSFORM_RX = _rx_prefix([
    # Deutsch
    "fass", "übersetz", "uebersetz", "verbesser", "korrigier", "kürz",
    "kuerz", "überarbeit", "ueberarbeit", "umformulier", "redigier",
    # Englisch
    "summar", "translat", "improv", "correct", "rewrit", "rephras",
    "paraphras", "proofread", "shorten", "condense", "fix",
])

# Echte Material-Indikatoren. WICHTIG: bewusst KEINE Zeiger wie
# "diesen Text" oder "folgenden" - die zeigen bei Anfängern oft ins Leere
# (der Text wurde nie eingefügt). Nur Formulierungen, die praktisch immer
# direkt vor dem eingefügten Material stehen.
_INPUT_REF_RX = _rx_exact([
    "hier ist", "hier sind", "anbei", "im anhang",
    "here is", "here's", "here are", "attached", "as follows",
])

# Kontext-Signale: Hintergrund, Zweck, Zielgruppe
_CONTEXT_EXACT_RX = _rx_exact([
    # Deutsch
    "weil", "da ich", "da wir", "hintergrund", "kontext", "ziel ist",
    "es geht um", "ich bin", "wir sind", "ich arbeite", "ich betreibe",
    "für die", "fuer die", "für einen", "fuer einen", "für eine",
    "fuer eine", "zielgruppe", "im rahmen", "situation", "ich möchte",
    "ich moechte", "ich will", "wir wollen", "damit ich", "damit wir",
    "zweck",
    # Englisch
    "because", "since i", "background", "context", "the goal", "my goal",
    "i am", "i'm", "we are", "i work", "i run", "for a", "for the",
    "for our", "audience", "purpose", "in order to", "so that", "i want",
    "we want", "i need", "we need",
])
# Präfix-Varianten, damit auch 'für meinen'/'an meinem' matchen
_CONTEXT_PREFIX_RX = _rx_prefix([
    "für mein", "fuer mein", "für unser", "fuer unser",
    "an mein", "an unser", "for my",
])

# Rollen-Signale
_ROLE_EXACT_RX = _rx_exact([
    "du bist", "sie sind ein", "verhalte dich", "agiere als",
    "nimm die rolle", "in der rolle", "du agierst", "stell dir vor, du",
    "you are", "you're a", "you're an", "act as", "acting as",
    "take the role", "roleplay as", "imagine you are", "pretend you are",
])
_ROLE_PREFIX_RX = _rx_prefix([
    "als erfahren", "als expert", "als profi",
    "as an expert", "as a senior", "as a professional",
])

# Format-Signale: gewünschte Ausgabeform
_FORMAT_EXACT_RX = _rx_exact([
    # Deutsch
    "als liste", "als tabelle", "aufzählung", "aufzaehlung", "absatz",
    "absätze", "absaetze", "abschnitt", "wörter", "woerter", "worte",
    "wörtern", "woertern", "zeichen", "sätze", "saetze", "sätzen",
    "saetzen", "maximal", "höchstens", "hoechstens", "mindestens",
    "ausführlich", "ausfuehrlich", "als json", "als e-mail", "als email",
    "als mail", "als tweet", "als post", "überschrift", "ueberschrift",
    "überschriften", "ueberschriften", "zwischenüberschriften",
    "zwischenueberschriften", "gliederung", "format", "auf deutsch",
    "auf englisch", "in einem satz", "schritt für schritt",
    "schritt fuer schritt", "als markdown", "als code",
    # Englisch
    "as a list", "as a table", "bullet point", "bullet points",
    "paragraph", "paragraphs", "section", "sections", "words",
    "characters", "sentences", "maximum", "at most", "at least", "brief",
    "detailed", "as json", "as an email", "as a tweet", "headline",
    "numbered", "outline", "step by step", "in one sentence", "markdown",
    "as code", "in german", "in english", "subheadings",
])
_FORMAT_PREFIX_RX = _rx_prefix([
    "stichpunkt", "nummerier", "kurz", "knapp",
])
# Format-Zahlerkennung: '3 Varianten', '200 Wörter', '5 bullet points' ...
# Bewusst OHNE Zeiteinheiten (Minuten/Stunden) - "in 30 Minuten" ist eine
# Deadline, kein Ausgabeformat.
_FORMAT_NUM_RX = re.compile(
    r"(?<!\w)\d+\s*(?:"
    r"sätzen?|saetzen?|sätze|saetze|wörtern?|woertern?|worten?|zeichen|"
    r"varianten?|beispielen?|stichpunkten?|punkten?|absätzen?|absaetzen?|"
    r"zeilen|überschriften|ueberschriften|zwischenüberschriften|"
    r"zwischenueberschriften|"
    r"words?|sentences?|characters?|variants?|options?|examples?|"
    r"bullet points?|paragraphs?|lines?|headings?|subheadings?"
    r")(?!\w)"
)

# Beispiel-Signale
_EXAMPLE_RX = _rx_exact([
    "z.b.", "z. b.", "zum beispiel", "beispiel:", "beispiele:",
    "beispiel für", "beispiel fuer", "beispiel wäre", "beispiel waere",
    "ein beispiel", "als beispiel", "etwa so", "wie etwa", "so wie",
    "beispielsweise", "im stil von",
    "e.g.", "for example", "example:", "examples:", "for instance",
    "an example", "such as", "like this", "in the style of",
])

# Vage Wörter: verwässern die Spezifität
_VAGUE_RX = _rx_exact([
    # Deutsch
    "irgendwas", "irgendwie", "irgendein", "irgendwelche", "etwas gutes",
    "was gutes", "was schönes", "was schoenes", "ein bisschen",
    "bisschen was", "das ding", "dings", "zeug", "halt", "einfach mal",
    "mal was", "mal irgendwas", "usw", "und so weiter", "oder so",
    # Englisch
    "something good", "something nice", "some stuff", "stuff about",
    "kind of", "sort of", "whatever", "anything", "etc", "and so on",
    "or something",
])


# ---------------------------------------------------------------------------
# SPRACH- UND DOMÄNEN-ERKENNUNG
# ---------------------------------------------------------------------------

_DE_HINT_RX = _rx_exact([
    "und", "der", "die", "das", "ein", "eine", "einen", "einem", "ich",
    "du", "nicht", "mit", "für", "fuer", "über", "ueber", "bitte", "mir",
    "mich", "mein", "meine", "meinen", "dein", "deine", "ist", "sind",
    "auf", "zu", "als", "wie", "was", "oder", "wegen", "beim", "vom",
])
_EN_HINT_RX = _rx_exact([
    "the", "and", "is", "are", "to", "of", "for", "with", "please",
    "my", "your", "me", "about", "that", "this", "it", "you", "at",
    "from", "on", "what", "or",
])


def _detect_lang(text, default="de"):
    """Erkennt die Prompt-Sprache (de/en) über Stoppwörter und Umlaute.
    Bei Gleichstand gewinnt der Default (= UI-Sprache)."""
    low = text.lower()
    de = _count_distinct(_DE_HINT_RX, low)
    en = _count_distinct(_EN_HINT_RX, low)
    if re.search(r"[äöüß]", low):
        de += 3
    if de > en:
        return "de"
    if en > de:
        return "en"
    return default if default in ("de", "en") else "de"


_DOMAIN_EMAIL_RX = _rx_prefix([
    "mail", "e-mail", "email", "brief", "anschreiben", "betreff",
    "professor", "kunde", "kunden", "chef", "bewerbung", "absage",
    "letter", "boss", "client", "subject line", "application",
])
_DOMAIN_EXPLAIN_RX = _rx_prefix([
    "erklär", "erklaer", "versteh", "was ist", "wie funktioniert",
    "warum", "definier", "unterschied zwischen",
    "explain", "understand", "what is", "how does", "why", "difference between",
])


def _detect_domain(text):
    """Wählt das passendste Beispiel-Set: email / explain / content."""
    if _DOMAIN_EMAIL_RX.search(text):
        return "email"
    if _DOMAIN_EXPLAIN_RX.search(text):
        return "explain"
    return "content"


# ---------------------------------------------------------------------------
# TEXTS: ALLE FEEDBACK-TEXTE ZWEISPRACHIG (Anzeige-Sprache = ui_lang)
# ---------------------------------------------------------------------------

TEXTS = {
    "de": {
        "err_empty": "Bitte gib zuerst einen Prompt ein.",
        "err_too_long": "Der Prompt ist sehr lang (>20.000 Zeichen). Bitte kürze ihn für die Analyse.",
        "empty_ampel_text": "Das ist noch kein vollständiger Prompt.",
        "empty_hinweis": ("Ein Prompt braucht mindestens eine klare Aufgabe. "
                          "Starte mit einem Verb: 'Erkläre…', 'Schreibe…', 'Erstelle…'"),
        "ampel": {
            "gruen": "Starker Prompt — gut strukturiert!",
            "gelb": "Solide Basis — mit wenigen Ergänzungen wird er stark.",
            "rot": "Braucht Arbeit — die Vorlage unten zeigt dir, was fehlt.",
        },
        "checks": {
            "task": {
                "titel": "Klare Aufgabe",
                "frage": "Sagt der Prompt eindeutig, WAS die KI tun soll?",
                "warum": ("Die KI rät sonst, was du willst — und rät oft falsch. "
                          "Eine klare Anweisung oder präzise Frage ist der wichtigste "
                          "Teil jedes Prompts."),
                "feedback": {
                    "verb": "Klare Anweisung erkannt — gut!",
                    "question": ("Präzise Frage erkannt — eine gute Frage ist eine "
                                 "vollwertige Aufgabe."),
                    "none": ("Es ist keine klare Aufgabe erkennbar. Beginne mit einem "
                             "Verb ('Schreibe…', 'Erkläre…') oder stelle eine konkrete Frage."),
                },
            },
            "input": {
                "titel": "Eingabe-Material",
                "frage": "Der Prompt will Text bearbeiten — ist das Material auch da?",
                "warum": ("'Verbessere diesen Text' ohne den Text ist der häufigste "
                          "Anfängerfehler: Die KI hat nichts zum Bearbeiten und muss "
                          "raten oder nachfragen."),
                "feedback": {
                    1.0: "Material erkannt — die KI hat etwas zum Bearbeiten.",
                    0.0: ("Dein Prompt will Text bearbeiten (zusammenfassen, verbessern, "
                          "übersetzen…), aber es ist kein Material erkennbar. Füge den "
                          "Text direkt ein — am besten nach einem Doppelpunkt."),
                },
            },
            "context": {
                "titel": "Kontext & Zweck",
                "frage": "Weiß die KI, WOFÜR und FÜR WEN du das brauchst?",
                "warum": ("Derselbe Text sieht völlig anders aus, je nachdem ob er für "
                          "deinen Chef, deine Oma oder ein Fachpublikum ist. Ohne Kontext "
                          "bekommst du Durchschnitt."),
                "feedback": {
                    1.0: "Kontext ist erkennbar — die KI weiß, worum es geht.",
                    0.5: ("Etwas Kontext ist da, aber mehr Hintergrund (Für wen? Warum? "
                          "Worum genau?) würde das Ergebnis deutlich verbessern."),
                    0.0: ("Es fehlt Hintergrund: Wofür brauchst du das? Für wen ist es? "
                          "Was ist die Situation?"),
                },
            },
            "specificity": {
                "titel": "Konkretheit",
                "frage": "Ist der Prompt konkret genug — oder schwammig?",
                "warum": ("Vage Wörter wie 'irgendwas', 'was Gutes' oder 'oder so' zwingen "
                          "die KI zum Raten. Je konkreter du bist, desto besser das Ergebnis."),
                "feedback": {
                    1.0: "Der Prompt ist konkret formuliert.",
                    0.5: ("Geht in die richtige Richtung, aber ein paar Stellen sind noch "
                          "schwammig. Ersetze vage Wörter durch konkrete Angaben."),
                    0.0: ("Zu vage. Ersetze Wörter wie 'irgendwas' oder 'was Gutes' durch "
                          "genaue Angaben: Was genau? Wie viel? Worüber?"),
                },
            },
            "format": {
                "titel": "Gewünschtes Format",
                "frage": "Steht im Prompt, WIE die Antwort aussehen soll?",
                "warum": ("Ohne Format-Angabe entscheidet die KI selbst über Länge und "
                          "Aufbau — und liefert oft zu viel oder zu wenig. Länge, Form und "
                          "Sprache anzugeben kostet dich 5 Sekunden."),
                "feedback": {
                    1.0: "Format-Wunsch erkannt — die Antwort wird passen.",
                    0.0: ("Kein Format angegeben. Sag der KI: Wie lang? Liste oder "
                          "Fließtext? Für welches Publikum?"),
                },
            },
            "role": {
                "titel": "Rolle (optional)",
                "frage": "Hat die KI eine Rolle bekommen (z.B. 'Du bist ein erfahrener Lektor')?",
                "warum": ("Eine Rolle gibt der Antwort Perspektive und Tiefe. Bei einfachen "
                          "Fragen unnötig — bei Fachthemen oder Texten oft ein großer Hebel."),
                "feedback": {
                    1.0: "Rolle definiert — das gibt der Antwort Richtung.",
                    0.0: ("Keine Rolle definiert. Das ist ok — bei Fachthemen kann "
                          "'Du bist ein erfahrener …' die Qualität aber spürbar heben."),
                },
            },
            "examples": {
                "titel": "Beispiele (optional)",
                "frage": "Zeigt der Prompt ein Beispiel, wie das Ergebnis aussehen soll?",
                "warum": ("Ein Beispiel sagt mehr als drei Sätze Beschreibung. Besonders "
                          "wertvoll bei Stil-Fragen ('schreib im Stil von…') und "
                          "wiederkehrenden Formaten."),
                "feedback": {
                    1.0: "Beispiel vorhanden — das ist die stärkste Form der Anleitung.",
                    0.0: ("Kein Beispiel. Optional — aber bei Stil- und Formatfragen ist "
                          "ein kurzes Beispiel oft der größte Qualitäts-Hebel."),
                },
            },
        },
        "sections": {"role": "Rolle", "context": "Kontext", "task": "Aufgabe",
                     "format": "Format", "examples": "Beispiel"},
        "placeholders": {
            "role": ("Optional: Welche Rolle soll die KI einnehmen? "
                     "z.B. 'Du bist ein erfahrener Hundetrainer.'"),
            "context": ("Ergänze: Wofür brauchst du das? Für wen? Was ist die Situation? "
                        "z.B. 'Ich schreibe einen Blogartikel für Erstbesitzer.'"),
            "task_add": ("Mach die Aufgabe konkreter: Was genau soll entstehen? "
                         "z.B. 'Schreibe einen 300-Wörter-Überblick über die 5 wichtigsten Punkte.'"),
            "format": ("Ergänze: Wie soll die Antwort aussehen? Länge, Form, Sprache? "
                       "z.B. 'Als nummerierte Liste mit je 2-3 Sätzen pro Punkt.'"),
            "examples": "Optional: Zeig ein kurzes Beispiel für Stil oder Aufbau des Ergebnisses.",
            "input": "Füge hier den Text / das Material ein, das die KI bearbeiten soll.",
        },
        "move_tip": ("Tipp: Dein Prompt enthält schon Rolle oder Kontext — verschiebe "
                     "diese Teile in die passenden Abschnitte, damit die Aufgabe hier "
                     "sauber getrennt bleibt."),
    },
    "en": {
        "err_empty": "Please enter a prompt first.",
        "err_too_long": "The prompt is very long (>20,000 characters). Please shorten it for analysis.",
        "empty_ampel_text": "This isn't a complete prompt yet.",
        "empty_hinweis": ("A prompt needs at least one clear task. "
                          "Start with a verb: 'Explain…', 'Write…', 'Create…'"),
        "ampel": {
            "gruen": "Strong prompt — well structured!",
            "gelb": "Solid base — a few additions will make it strong.",
            "rot": "Needs work — the template below shows you what's missing.",
        },
        "checks": {
            "task": {
                "titel": "Clear task",
                "frage": "Does the prompt clearly say WHAT the AI should do?",
                "warum": ("Otherwise the AI guesses what you want — and often guesses "
                          "wrong. A clear instruction or a precise question is the most "
                          "important part of any prompt."),
                "feedback": {
                    "verb": "Clear instruction detected — good!",
                    "question": ("Precise question detected — a good question is a "
                                 "fully valid task."),
                    "none": ("No clear task detected. Start with a verb ('Write…', "
                             "'Explain…') or ask a concrete question."),
                },
            },
            "input": {
                "titel": "Input material",
                "frage": "The prompt wants to edit text — is the material actually there?",
                "warum": ("'Improve this text' without the text is the most common "
                          "beginner mistake: the AI has nothing to work on and has to "
                          "guess or ask back."),
                "feedback": {
                    1.0: "Material detected — the AI has something to work on.",
                    0.0: ("Your prompt wants to edit text (summarize, improve, "
                          "translate…), but no material is detectable. Paste the text "
                          "directly — ideally after a colon."),
                },
            },
            "context": {
                "titel": "Context & purpose",
                "frage": "Does the AI know WHAT FOR and FOR WHOM you need this?",
                "warum": ("The same text looks completely different depending on whether "
                          "it's for your boss, your grandma or an expert audience. "
                          "Without context you get average output."),
                "feedback": {
                    1.0: "Context detected — the AI knows what this is about.",
                    0.5: ("Some context is there, but more background (For whom? Why? "
                          "About what exactly?) would clearly improve the result."),
                    0.0: ("Background is missing: What do you need this for? Who is it "
                          "for? What's the situation?"),
                },
            },
            "specificity": {
                "titel": "Specificity",
                "frage": "Is the prompt concrete enough — or vague?",
                "warum": ("Vague words like 'something', 'anything good' or 'or whatever' "
                          "force the AI to guess. The more concrete you are, the better "
                          "the result."),
                "feedback": {
                    1.0: "The prompt is concretely worded.",
                    0.5: ("Going in the right direction, but some parts are still vague. "
                          "Replace vague words with concrete details."),
                    0.0: ("Too vague. Replace words like 'something' or 'whatever' with "
                          "exact details: What exactly? How much? About what?"),
                },
            },
            "format": {
                "titel": "Desired format",
                "frage": "Does the prompt say WHAT the answer should look like?",
                "warum": ("Without a format request the AI decides length and structure "
                          "itself — and often delivers too much or too little. Stating "
                          "length, form and language costs you 5 seconds."),
                "feedback": {
                    1.0: "Format request detected — the answer will fit.",
                    0.0: ("No format specified. Tell the AI: How long? List or prose? "
                          "For which audience?"),
                },
            },
            "role": {
                "titel": "Role (optional)",
                "frage": "Did the AI get a role (e.g. 'You are an experienced editor')?",
                "warum": ("A role gives the answer perspective and depth. Unnecessary for "
                          "simple questions — often a big lever for expert topics or texts."),
                "feedback": {
                    1.0: "Role defined — that gives the answer direction.",
                    0.0: ("No role defined. That's fine — but for expert topics, "
                          "'You are an experienced …' can noticeably raise quality."),
                },
            },
            "examples": {
                "titel": "Examples (optional)",
                "frage": "Does the prompt show an example of what the result should look like?",
                "warum": ("An example says more than three sentences of description. "
                          "Especially valuable for style questions ('write in the style "
                          "of…') and recurring formats."),
                "feedback": {
                    1.0: "Example present — that's the strongest form of guidance.",
                    0.0: ("No example. Optional — but for style and format questions a "
                          "short example is often the biggest quality lever."),
                },
            },
        },
        "sections": {"role": "Role", "context": "Context", "task": "Task",
                     "format": "Format", "examples": "Example"},
        "placeholders": {
            "role": ("Optional: Which role should the AI take? "
                     "e.g. 'You are an experienced dog trainer.'"),
            "context": ("Add: What do you need this for? For whom? What's the situation? "
                        "e.g. 'I'm writing a blog article for first-time owners.'"),
            "task_add": ("Make the task more concrete: What exactly should be created? "
                         "e.g. 'Write a 300-word overview of the 5 most important points.'"),
            "format": ("Add: What should the answer look like? Length, form, language? "
                       "e.g. 'As a numbered list with 2-3 sentences per point.'"),
            "examples": "Optional: Show a short example of the style or structure you want.",
            "input": "Paste the text / material the AI should work on here.",
        },
        "move_tip": ("Tip: Your prompt already contains a role or context — move those "
                     "parts into the matching sections so the task stays cleanly "
                     "separated here."),
    },
}


# ---------------------------------------------------------------------------
# EXAMPLES: DOMÄNENPASSENDE SCHLECHT/GUT-BEISPIELE (Anzeige-Sprache = ui_lang)
# ---------------------------------------------------------------------------
# Struktur: EXAMPLES[lang][domain][check_id] = (schlecht, gut)
# Domänen: email (Mails/Briefe), explain (Erklärungen), content (Texte/Marketing)

EXAMPLES = {
    "de": {
        "email": {
            "task": ("Der Termin morgen.",
                     "Schreib eine kurze Absage für den Termin morgen."),
            "input": ("Verbessere meine E-Mail.",
                      "Verbessere meine E-Mail. Hier ist sie: [deine E-Mail]"),
            "context": ("Schreib eine E-Mail wegen dem Termin.",
                        "Schreib eine E-Mail an meinen Professor, weil ich den "
                        "Abgabetermin um 3 Tage verschieben muss (Grund: Krankheit)."),
            "specificity": ("Schreib irgendwas Nettes an den Kunden.",
                            "Schreib eine Dankes-E-Mail an den Kunden für die "
                            "Vertragsverlängerung am Montag."),
            "format": ("Schreib die E-Mail.",
                       "Schreib die E-Mail in maximal 5 Sätzen, freundlich aber bestimmt."),
            "role": ("Verbessere diese E-Mail: [deine E-Mail]",
                     "Du bist ein erfahrener Kommunikationsprofi. Verbessere diese "
                     "E-Mail: [deine E-Mail]"),
            "examples": ("Schreib die Betreffzeile.",
                         "Schreib die Betreffzeile. Beispiel für den Ton: "
                         "'Kurze Frage zum Projektstart'."),
        },
        "explain": {
            "task": ("Photosynthese.",
                     "Erkläre mir Photosynthese in einfachen Worten."),
            "input": ("Fasse den Artikel zusammen.",
                      "Fasse diesen Artikel zusammen: [Artikeltext einfügen]"),
            "context": ("Erkläre Inflation.",
                        "Erkläre Inflation für mein BWL-Studium — ich schreibe "
                        "nächste Woche eine Klausur darüber."),
            "specificity": ("Erklär mir das mit der Wirtschaft oder so.",
                            "Erkläre mir, wie die EZB mit dem Leitzins die "
                            "Inflation steuert."),
            "format": ("Erkläre mir Photosynthese.",
                       "Erkläre mir Photosynthese in maximal 5 Sätzen, so dass es "
                       "ein 12-Jähriger versteht."),
            "role": ("Erkläre mir Vertragsrecht.",
                     "Du bist Jura-Professor mit Talent für einfache Sprache. "
                     "Erkläre mir Vertragsrecht."),
            "examples": ("Erkläre Metaphern.",
                         "Erkläre Metaphern. Beispiel für das Niveau: "
                         "'Die Zeit rennt' = die Zeit vergeht schnell."),
        },
        "content": {
            "task": ("Hunde.",
                     "Schreibe einen kurzen Blogabsatz über Hundeerziehung."),
            "input": ("Korrigiere meinen Text.",
                      "Korrigiere diesen Text: [dein Text]"),
            "context": ("Schreib was über unser Produkt.",
                        "Schreib einen Text über unsere Kaffeemarke — Zielgruppe "
                        "sind Studierende, es geht um den Launch nächste Woche."),
            "specificity": ("Mach mal was Schönes für Social Media oder so.",
                            "Erstelle 3 Instagram-Caption-Varianten (je max. 100 "
                            "Zeichen) für den Launch unserer Kaffee-Marke."),
            "format": ("Schreib einen Produkttext.",
                       "Schreib einen Produkttext mit 3 Stichpunkten und maximal "
                       "200 Wörtern."),
            "role": ("Verbessere diesen Text: [dein Text]",
                     "Du bist ein strenger Lektor einer Tageszeitung. Verbessere "
                     "diesen Text: [dein Text]"),
            "examples": ("Schreib Produktbeschreibungen für meine Kerzen.",
                         "Schreib Produktbeschreibungen für meine Kerzen. Beispiel "
                         "für den Stil: 'Warmes Licht, ehrlicher Duft — "
                         "handgegossen in Köln.'"),
        },
    },
    "en": {
        "email": {
            "task": ("The meeting tomorrow.",
                     "Write a short email to cancel tomorrow's meeting."),
            "input": ("Improve my email.",
                      "Improve my email. Here it is: [your email]"),
            "context": ("Write an email about the appointment.",
                        "Write an email to my professor because I need to move the "
                        "deadline by 3 days (reason: illness)."),
            "specificity": ("Write something nice to the client.",
                            "Write a thank-you email to the client for Monday's "
                            "contract renewal."),
            "format": ("Write the email.",
                       "Write the email in at most 5 sentences, friendly but firm."),
            "role": ("Improve this email: [your email]",
                     "You are an experienced communications professional. Improve "
                     "this email: [your email]"),
            "examples": ("Write the subject line.",
                         "Write the subject line. Example of the tone: "
                         "'Quick question about the project start'."),
        },
        "explain": {
            "task": ("Photosynthesis.",
                     "Explain photosynthesis to me in simple terms."),
            "input": ("Summarize the article.",
                      "Summarize this article: [paste article text]"),
            "context": ("Explain inflation.",
                        "Explain inflation for my business studies — I have an "
                        "exam about it next week."),
            "specificity": ("Explain that economy thing or something.",
                            "Explain how the ECB uses the key interest rate to "
                            "control inflation."),
            "format": ("Explain photosynthesis.",
                       "Explain photosynthesis in at most 5 sentences, so that a "
                       "12-year-old understands it."),
            "role": ("Explain contract law to me.",
                     "You are a law professor with a talent for plain language. "
                     "Explain contract law to me."),
            "examples": ("Explain metaphors.",
                         "Explain metaphors. Example of the level: "
                         "'Time flies' = time passes quickly."),
        },
        "content": {
            "task": ("Dogs.",
                     "Write a short blog paragraph about dog training."),
            "input": ("Fix my text.",
                      "Fix this text: [your text]"),
            "context": ("Write something about our product.",
                        "Write a text about our coffee brand — the audience is "
                        "students, it's about next week's launch."),
            "specificity": ("Make something nice for social media or whatever.",
                            "Create 3 Instagram caption options (max. 100 "
                            "characters each) for our coffee brand's launch."),
            "format": ("Write a product description.",
                       "Write a product description with 3 bullet points and at "
                       "most 200 words."),
            "role": ("Improve this text: [your text]",
                     "You are a strict newspaper editor. Improve this text: "
                     "[your text]"),
            "examples": ("Write product descriptions for my candles.",
                         "Write product descriptions for my candles. Style "
                         "example: 'Warm light, honest scent — hand-poured in "
                         "Cologne.'"),
        },
    },
}


# ---------------------------------------------------------------------------
# DIE CHECKS (reine Logik - Texte kommen aus TEXTS/EXAMPLES)
# ---------------------------------------------------------------------------
# Jeder Check liefert: status (1.0 / 0.5 / 0.0) + feedback_key
# (Schlüssel in TEXTS[lang]["checks"][id]["feedback"]).

def _check_task(text, words):
    if _TASK_VERB_RX.search(text):
        return 1.0, "verb"
    first_word = re.sub(r"[^\wäöüß']", "", text.split()[0]) if text.split() else ""
    if "?" in text or first_word in _QUESTION_STARTS:
        # Eine präzise Frage ist eine VOLLWERTIGE Aufgabe (v1 gab nur 0.5)
        return 1.0, "question"
    return 0.0, "none"


def _has_input_material(text, words):
    """Ist Material zum Bearbeiten erkennbar?
      - echter Indikator ('hier ist', 'anbei'), ODER
      - Doppelpunkt mit >=10 Wörtern danach, ODER
      - >=60 Wörter insgesamt (der Text steckt vermutlich schon drin)."""
    if _INPUT_REF_RX.search(text):
        return True
    colon = text.find(":")
    if colon != -1 and _word_count(text[colon + 1:]) >= 10:
        return True
    return words >= 60


def _check_input(text, words):
    status = 1.0 if _has_input_material(text, words) else 0.0
    return status, status


def _check_context(text, words):
    hits = (_count_distinct(_CONTEXT_EXACT_RX, text)
            + _count_distinct(_CONTEXT_PREFIX_RX, text))
    if hits >= 2 or (hits >= 1 and words >= 15):
        status = 1.0
    elif hits >= 1 or words >= 25:
        status = 0.5
    else:
        status = 0.0
    return status, status


def _check_specificity(text, words):
    vague = _count_distinct(_VAGUE_RX, text)
    if words < 4 or vague >= 2:
        status = 0.0
    elif vague == 1 or words < 8:
        status = 0.5
    else:
        status = 1.0
    return status, status


def _check_format(text, words):
    hits = (_count_distinct(_FORMAT_EXACT_RX, text)
            + _count_distinct(_FORMAT_PREFIX_RX, text)
            + (1 if _FORMAT_NUM_RX.search(text) else 0))
    status = 1.0 if hits >= 1 else 0.0
    return status, status


def _check_role(text, words):
    has = _ROLE_EXACT_RX.search(text) or _ROLE_PREFIX_RX.search(text)
    status = 1.0 if has else 0.0
    return status, status


def _check_examples(text, words):
    status = 1.0 if _EXAMPLE_RX.search(text) else 0.0
    return status, status


# (id, gewicht, optional, funktion) - 'input' ist SITUATIV: erscheint nur,
# wenn der Prompt ein Transformationsverb enthält.
_CHECK_DEFS = [
    ("task", 3.0, False, _check_task),
    ("input", 2.0, False, _check_input),
    ("context", 2.0, False, _check_context),
    ("specificity", 2.0, False, _check_specificity),
    ("format", 1.5, False, _check_format),
    ("role", 1.0, True, _check_role),
    ("examples", 1.0, True, _check_examples),
]


# ---------------------------------------------------------------------------
# MODELLSPEZIFISCHE VORLAGEN
# ---------------------------------------------------------------------------
# Kuratiertes Wissen: Welches Modell mag welche Struktur.
#   Claude  -> XML-Tags (von Anthropic offiziell empfohlen)
#   GPT     -> Markdown-Überschriften (klar getrennte Abschnitte)
#   Gemini  -> klare Markdown-Struktur mit Labels
# Fehlende Teile werden als [Platzhalter-Fragen] eingefügt, die der
# Nutzer selbst beantwortet - das ist der Lerneffekt.
# WICHTIG: Die Vorlagen-Sprache folgt der PROMPT-Sprache (prompt_lang),
# nicht der UI-Sprache - ein englischer Prompt bekommt englische Platzhalter.

def _build_template(prompt, by_id, model, tpl_lang):
    t = TEXTS[tpl_lang]
    p = t["placeholders"]
    titles = t["sections"]
    sections = []  # Liste von (schluessel, ueberschrift, inhalt)

    words = _word_count(prompt)

    # Rolle: nur aufnehmen, wenn sie fehlt UND der Prompt komplex genug ist,
    # dass sie sich lohnen könnte - sonst weglassen (kein Zwang zu Optionalem).
    if by_id["role"]["status"] == 0.0 and words >= 6:
        sections.append(("role", titles["role"], f"[{p['role']}]"))

    if by_id["context"]["status"] < 1.0:
        sections.append(("context", titles["context"], f"[{p['context']}]"))

    # Aufgabe: immer drin - Original-Prompt + ggf. Ergänzungen
    task_content = prompt.strip()
    if "input" in by_id and by_id["input"]["status"] < 1.0:
        # Transformationsprompt ohne Material -> Platzhalter fürs Material
        task_content += f"\n[{p['input']}]"
    if by_id["task"]["status"] < 1.0 or by_id["specificity"]["status"] < 1.0:
        task_content += f"\n[{p['task_add']}]"
    sections.append(("task", titles["task"], task_content))

    if by_id["format"]["status"] < 1.0:
        sections.append(("format", titles["format"], f"[{p['format']}]"))

    if by_id["examples"]["status"] == 0.0 and words >= 10:
        sections.append(("examples", titles["examples"], f"[{p['examples']}]"))

    # Anti-Dopplungs-Tipp (move_tip): Wenn der Prompt schon Rolle oder
    # Kontext ENTHÄLT, steht dieser Teil jetzt im Aufgaben-Block - der Tipp
    # sagt ehrlich, dass man ihn in die passenden Abschnitte verschieben soll.
    has_inline_parts = (by_id["role"]["status"] == 1.0
                        or by_id["context"]["status"] >= 0.5)
    if has_inline_parts and len(sections) > 1:
        for i, (key, titel, content) in enumerate(sections):
            if key == "task":
                sections[i] = (key, titel, content + f"\n[{t['move_tip']}]")
                break

    # --- Modellspezifisch rendern ---
    if model == "claude":
        # Anthropic-Empfehlung: XML-Tags (Tags bleiben englisch = Konvention)
        parts = [f"<{key}>\n{content}\n</{key}>"
                 for key, _titel, content in sections]
        return "\n\n".join(parts)

    if model == "gpt":
        # OpenAI-Stil: Markdown-Überschriften als klare Abschnitte
        parts = [f"## {titel}\n{content}" for _key, titel, content in sections]
        return "\n\n".join(parts)

    if model == "gemini":
        # Gemini: klare, schlichte Struktur mit Labels
        parts = [f"**{titel}:**\n{content}" for _key, titel, content in sections]
        return "\n\n".join(parts)

    # "universal": schlichte Absätze mit Labels (funktioniert überall)
    parts = [f"{titel}:\n{content}" for _key, titel, content in sections]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# HAUPTFUNKTION
# ---------------------------------------------------------------------------

def analyze_prompt(prompt: str, model: str = "claude", ui_lang: str = "de") -> dict:
    """
    Analysiert einen Prompt und gibt zurück:
      ok, score (0-100), ampel ('gruen'/'gelb'/'rot'), ampel_text,
      checks (Liste mit Status + Erklärungen in ui_lang),
      template (Vorlage in der ERKANNTEN Prompt-Sprache),
      model, prompt_lang ('de'/'en'), ggf. hinweis (bei fast-leerem Prompt)
    """
    ui_lang = ui_lang if ui_lang in ("de", "en") else "de"
    t = TEXTS[ui_lang]

    prompt = (prompt or "").strip()
    if not prompt:
        return {"ok": False, "error": t["err_empty"]}
    if len(prompt) > 20000:
        return {"ok": False, "error": t["err_too_long"]}

    model = model if model in ("claude", "gpt", "gemini", "universal") else "universal"
    text = prompt.lower()
    words = _word_count(prompt)
    prompt_lang = _detect_lang(prompt, default=ui_lang)
    domain = _detect_domain(text)

    # Sonderfall: praktisch leerer Prompt
    if words < 2:
        return {
            "ok": True,
            "score": 0,
            "ampel": "rot",
            "ampel_text": t["empty_ampel_text"],
            "checks": [],
            "template": "",
            "model": model,
            "prompt_lang": prompt_lang,
            "hinweis": t["empty_hinweis"],
        }

    # Situativ: Input-Check nur bei Transformationsverben
    is_transform = bool(_TRANSFORM_RX.search(text))

    results = []
    for check_id, gewicht, optional, fn in _CHECK_DEFS:
        if check_id == "input" and not is_transform:
            continue
        status, fb_key = fn(text, words)
        results.append({
            "id": check_id,
            "gewicht": gewicht,
            "optional": optional,
            "status": status,
            "fb_key": fb_key,
        })
    by_id = {r["id"]: r for r in results}

    # Score: gewichteter Anteil
    total_weight = sum(r["gewicht"] for r in results)
    achieved = sum(r["gewicht"] * r["status"] for r in results)
    score = round(achieved / total_weight * 100)

    if score >= 75:
        ampel = "gruen"
    elif score >= 45:
        ampel = "gelb"
    else:
        ampel = "rot"

    # Für die Anzeige: Texte in ui_lang, Beispiele domänenpassend
    checks_out = []
    for r in results:
        ct = t["checks"][r["id"]]
        fb = ct["feedback"].get(r["fb_key"])
        if fb is None:  # 0.5 nicht überall definiert -> auf 0.0-Text zurückfallen
            fb = ct["feedback"].get(0.5) or ct["feedback"][0.0]
        ex_bad, ex_good = EXAMPLES[ui_lang][domain][r["id"]]
        checks_out.append({
            "id": r["id"],
            "titel": ct["titel"],
            "optional": r["optional"],
            "status": r["status"],
            "frage": ct["frage"],
            "warum": ct["warum"],
            "feedback": fb,
            "beispiel_schlecht": ex_bad,
            "beispiel_gut": ex_good,
        })

    # Vorlage in der Sprache des Prompts (nicht der UI!)
    template = _build_template(prompt, by_id, model, prompt_lang)

    return {
        "ok": True,
        "score": score,
        "ampel": ampel,
        "ampel_text": t["ampel"][ampel],
        "checks": checks_out,
        "template": template,
        "model": model,
        "prompt_lang": prompt_lang,
    }
