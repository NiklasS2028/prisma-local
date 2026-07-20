# -*- coding: utf-8 -*-
"""
test_block2.py
--------------
Tests für Block 2 (prompt_trainer.py v2). Bildet die Testfälle aus dem
Prompt-Trainer-Audit ab:

  - Wortgrenzen: "Informationen" triggert nicht Format, "in 30 Minuten"
    nicht "in 3", "ebenso wie" nicht "so wie"
  - Fragen sind eine vollwertige Aufgabe (Status 1.0)
  - Situativer Input-Check bei Transformationsverben
  - Format-Zahlerkennung ("3 Varianten", "200 Wörter")
  - Zweisprachigkeit: Feedback folgt ui_lang, Vorlage folgt prompt_lang
  - move_tip gegen Rolle/Kontext-Dopplung
  - Korrigiertes Rollen-Beispiel mit "[dein Text]"
  - hinweis-Feld bei fast-leerem Prompt
  - Kriterienzahl (Block E): criteria_met/criteria_total statt 0-100-Score,
    Nenner 6 ohne / 7 mit Transformationsverb, relative Farbregel
  - Kalibrierung: schwach 1/6 rot, mittel 3/6 gelb, stark 5/6 grün

Aufruf:  python tests/test_block2.py
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompt_trainer import analyze_prompt  # noqa: E402


def get_check(result, check_id):
    return next((c for c in result["checks"] if c["id"] == check_id), None)


# --- Referenz-Prompts für die Kalibrierung (= Demo-Buttons in Block 3) ---
DEMO_DE = {
    "weak": "schreib mal irgendwas über hunde oder so",
    "medium": "Erklär mir Photosynthese für mein Studium in maximal 5 Sätzen",
    "strong": ("Du bist ein erfahrener Texter. Es geht um meinen Blog für "
               "Ersthundebesitzer. Schreibe einen Blogartikel über "
               "Leinentraining: maximal 600 Wörter, mit 3 Zwischenüberschriften "
               "und einer kurzen Checkliste am Ende."),
}
DEMO_EN = {
    "weak": "write some stuff about dogs or whatever",
    "medium": "Explain photosynthesis for my biology class in at most 5 sentences",
    "strong": ("You are an experienced copywriter. My goal is to help "
               "first-time dog owners with my blog. Write a blog post about "
               "leash training: maximum 600 words, with 3 subheadings and a "
               "short checklist at the end."),
}


# ---------------------------------------------------------------------------
# WORTGRENZEN-BUGS (Kategorie 1 des Audits)
# ---------------------------------------------------------------------------

def test_informationen_not_format():
    """'format' steckt in 'Informationen' - darf NICHT mehr matchen."""
    r = analyze_prompt("Gib mir Informationen zu Photosynthese", "claude")
    c = get_check(r, "format")
    assert c["status"] == 0.0, \
        f"Format-Check besteht fälschlich (Status {c['status']}) - Substring-Bug zurück?"


def test_in_30_minuten_not_format():
    """'in 3' (für 'in 3 Sätzen') darf nicht in 'in 30 Minuten' matchen."""
    r = analyze_prompt("Schreib das bitte, ich brauche das in 30 Minuten", "claude")
    c = get_check(r, "format")
    assert c["status"] == 0.0, \
        f"Format-Check besteht fälschlich bei 'in 30 Minuten' (Status {c['status']})"


def test_ebenso_wie_not_example():
    """'so wie' darf nicht in 'ebenso wie' matchen."""
    r = analyze_prompt("Mach das ebenso wie letztes Mal bitte", "claude")
    c = get_check(r, "examples")
    assert c["status"] == 0.0, \
        f"Beispiel-Check besteht fälschlich bei 'ebenso wie' (Status {c['status']})"


def test_real_format_signals_still_work():
    """Echte Format-Signale müssen weiterhin erkannt werden."""
    r = analyze_prompt("Erkläre mir Photosynthese in maximal 5 Sätzen", "claude")
    assert get_check(r, "format")["status"] == 1.0, "Echtes Format-Signal nicht erkannt"


# ---------------------------------------------------------------------------
# FRAGEN ALS VOLLWERTIGE AUFGABE
# ---------------------------------------------------------------------------

def test_question_is_full_task():
    """Eine präzise Frage bekommt volle Punktzahl (v1: nur 0.5)."""
    r = analyze_prompt("Was kostet ein Tesla Model 3 in Deutschland?", "claude")
    c = get_check(r, "task")
    assert c["status"] == 1.0, f"Frage nur mit Status {c['status']} bewertet"
    assert "Frage" in c["feedback"], f"Feedback nennt die Frage-Variante nicht: {c['feedback']}"


def test_question_without_questionmark():
    """Auch ohne '?' zählt ein Frage-Anfangswort."""
    r = analyze_prompt("Wann endet die Abgabefrist an der THI dieses Semester", "claude")
    assert get_check(r, "task")["status"] == 1.0, "Frage ohne '?' nicht erkannt"


# ---------------------------------------------------------------------------
# SITUATIVER INPUT-CHECK
# ---------------------------------------------------------------------------

def test_transform_without_material():
    """'Verbessere diesen Text.' ohne Text -> Input-Check schlägt an."""
    r = analyze_prompt("Verbessere diesen Text.", "claude")
    c = get_check(r, "input")
    assert c is not None, "Input-Check fehlt bei Transformationsverb"
    assert c["status"] == 0.0, f"Fehlendes Material nicht erkannt (Status {c['status']})"
    # Vorlage muss den Material-Platzhalter enthalten
    assert "Material" in r["template"] or "material" in r["template"], \
        "Vorlage enthält keinen Material-Platzhalter"


def test_transform_with_colon_material():
    """Doppelpunkt + >=10 Wörter danach = Material vorhanden."""
    r = analyze_prompt(
        "Fasse diesen Text zusammen: Die Sitzung begann um neun Uhr und "
        "behandelte zunächst die offenen Budgetfragen des laufenden Quartals.",
        "claude")
    c = get_check(r, "input")
    assert c is not None and c["status"] == 1.0, \
        "Material nach Doppelpunkt nicht erkannt"


def test_transform_with_hier_ist():
    """Echter Indikator 'hier ist' = Material vorhanden."""
    r = analyze_prompt("Übersetze das bitte. Hier ist der Text: Guten Morgen.", "claude")
    c = get_check(r, "input")
    assert c is not None and c["status"] == 1.0, "'hier ist' nicht als Indikator erkannt"


def test_pointer_words_are_not_material():
    """Zeiger wie 'den folgenden Text' zählen NICHT als Material (zeigen oft ins Leere)."""
    r = analyze_prompt("Fasse den folgenden Text bitte zusammen.", "claude")
    c = get_check(r, "input")
    assert c is not None and c["status"] == 0.0, \
        "'den folgenden Text' wurde fälschlich als Material gewertet"


def test_no_input_check_for_creation():
    """Erstellungs-Prompts ('Schreibe ein Gedicht') bekommen KEINEN Input-Check."""
    r = analyze_prompt("Schreibe ein Gedicht über den Herbst.", "claude")
    assert get_check(r, "input") is None, \
        "Input-Check erscheint fälschlich bei einem Erstellungsauftrag"


# ---------------------------------------------------------------------------
# FORMAT-ZAHLERKENNUNG
# ---------------------------------------------------------------------------

def test_format_number_varianten():
    r = analyze_prompt("Gib mir 3 Varianten für den Slogan unserer Kaffeemarke.", "claude")
    assert get_check(r, "format")["status"] == 1.0, "'3 Varianten' nicht als Format erkannt"


def test_format_number_woerter():
    r = analyze_prompt("Schreibe einen Text über Berlin mit 200 Wörtern.", "claude")
    assert get_check(r, "format")["status"] == 1.0, "'200 Wörtern' nicht als Format erkannt"


# ---------------------------------------------------------------------------
# ZWEISPRACHIGKEIT
# ---------------------------------------------------------------------------

def test_prompt_lang_detection():
    r_de = analyze_prompt(DEMO_DE["weak"], "claude")
    r_en = analyze_prompt(DEMO_EN["weak"], "claude")
    assert r_de["prompt_lang"] == "de", f"Deutsch nicht erkannt: {r_de['prompt_lang']}"
    assert r_en["prompt_lang"] == "en", f"Englisch nicht erkannt: {r_en['prompt_lang']}"


def test_template_follows_prompt_lang():
    """Englischer Prompt + deutsche UI -> ENGLISCHE Vorlage (prompt_lang gewinnt)."""
    r = analyze_prompt(DEMO_EN["medium"], "gpt", ui_lang="de")
    assert r["prompt_lang"] == "en"
    assert "## Task" in r["template"], \
        f"Vorlage nicht englisch trotz englischem Prompt:\n{r['template'][:200]}"
    # Feedback dagegen bleibt Deutsch (ui_lang)
    assert get_check(r, "task")["titel"] == "Klare Aufgabe", \
        "Check-Titel folgt nicht der UI-Sprache"


def test_ui_lang_english_feedback():
    """ui_lang='en' -> englische Check-Titel und Feedback."""
    r = analyze_prompt(DEMO_DE["weak"], "claude", ui_lang="en")
    assert get_check(r, "task")["titel"] == "Clear task", \
        f"Englischer Titel fehlt: {get_check(r, 'task')['titel']}"
    assert r["ampel"] == "rot"  # Ampel-Codes bleiben stabil (API-Konstante)


def test_real_umlauts():
    """Echte Umlaute statt 'Gewuenschtes'."""
    r = analyze_prompt(DEMO_DE["weak"], "claude", ui_lang="de")
    fmt = get_check(r, "format")
    assert "ü" in fmt["titel"], f"Titel ohne echten Umlaut: {fmt['titel']}"
    task = get_check(r, "task")
    assert "rät" in task["warum"], "Umlaute im warum-Text fehlen"


# ---------------------------------------------------------------------------
# VORLAGE: move_tip UND KORRIGIERTES ROLLEN-BEISPIEL
# ---------------------------------------------------------------------------

def test_move_tip_when_role_inline():
    """Prompt enthält schon eine Rolle -> Tipp zum Auslagern in der Vorlage."""
    r = analyze_prompt(DEMO_DE["strong"], "claude")
    assert "Tipp:" in r["template"], \
        f"move_tip fehlt in der Vorlage:\n{r['template'][:300]}"


def test_no_move_tip_without_inline_parts():
    """Prompt ohne Rolle/Kontext -> kein (unnötiger) Tipp."""
    r = analyze_prompt("Schreibe ein Gedicht über den Herbst.", "claude")
    assert "Tipp:" not in r["template"], "move_tip erscheint ohne Anlass"


def test_role_example_has_material():
    """Das Rollen-Gut-Beispiel enthält jetzt '[dein Text]' (v1 lehrte den
    Fehler, den der Input-Check woanders anprangert)."""
    r = analyze_prompt("Schreibe einen Text über Katzen für meinen Blog.", "claude")
    role = get_check(r, "role")
    assert "[dein Text]" in role["beispiel_gut"], \
        f"Rollen-Beispiel ohne Material-Platzhalter: {role['beispiel_gut']}"


def test_no_good_example_teaches_input_mistake():
    """KEIN Gut-Beispiel (egal welcher Check, Sprache oder Domäne) darf den
    Fehler vormachen, den der Input-Check anmahnt: Transformationsverb ohne
    Material. Ein Gut-Beispiel mit 'Verbessere...' braucht einen
    [Platzhalter] oder echtes Material."""
    from prompt_trainer import EXAMPLES, _TRANSFORM_RX, _has_input_material, _word_count
    violations = []
    for lang, domains in EXAMPLES.items():
        for domain, checks in domains.items():
            for check_id, (_bad, good) in checks.items():
                low = good.lower()
                if _TRANSFORM_RX.search(low):
                    has_placeholder = "[" in good
                    has_material = _has_input_material(low, _word_count(low))
                    if not (has_placeholder or has_material):
                        violations.append(f"{lang}/{domain}/{check_id}: {good}")
    assert not violations, \
        "Gut-Beispiele mit Transformationsverb ohne Material:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# HINWEIS-FELD UND FEHLERFÄLLE
# ---------------------------------------------------------------------------

def test_hinweis_on_near_empty_prompt():
    r = analyze_prompt("Hunde", "claude")
    assert r["ok"] is True
    assert r["criteria_met"] == 0 and r["ampel"] == "rot"
    assert r.get("hinweis"), "hinweis-Feld fehlt bei fast-leerem Prompt"
    assert r["template"] == "", "Vorlage muss bei fast-leerem Prompt leer sein"


def test_empty_prompt_error():
    r = analyze_prompt("", "claude")
    assert r["ok"] is False and r.get("error"), "Leerer Prompt muss Fehler liefern"


def test_signature_defaults():
    """analyze_prompt(prompt, model) ohne ui_lang bleibt aufrufbar (Default 'de')."""
    r = analyze_prompt("Erkläre mir Photosynthese in 5 Sätzen", "claude")
    assert r["ok"] and "prompt_lang" in r, "prompt_lang fehlt im Ergebnis"


# ---------------------------------------------------------------------------
# KRITERIENZAHL UND FARBREGEL (Block E)
# ---------------------------------------------------------------------------

def test_no_score_field():
    """Der 0-100-Score ist ersatzlos entfallen (Design-Entscheidung 1)."""
    r = analyze_prompt(DEMO_DE["strong"], "claude")
    assert "score" not in r, "Alter score-Schlüssel taucht wieder auf"
    assert "criteria_met" in r and "criteria_total" in r


def test_denominator_without_transform():
    """Ohne Transformationsverb: 6 geprüfte Kriterien (kein input-Check)."""
    r = analyze_prompt("Schreibe ein Gedicht über den Herbst.", "claude")
    assert r["criteria_total"] == 6, f"Nenner: {r['criteria_total']}"
    assert get_check(r, "input") is None


def test_denominator_with_transform():
    """Mit Transformationsverb: 7 geprüfte Kriterien (input-Check dabei)."""
    r = analyze_prompt("Verbessere diesen Text.", "claude")
    assert r["criteria_total"] == 7, f"Nenner: {r['criteria_total']}"
    assert get_check(r, "input") is not None


def test_color_rule_boundaries():
    """Relative Farbregel: GRÜN wenn höchstens 1 nicht erfüllt, ROT wenn
    weniger als die Hälfte erfüllt, sonst GELB - für beide Nenner."""
    from prompt_trainer import _ampel_for
    assert _ampel_for(5, 6) == "gruen"
    assert _ampel_for(6, 6) == "gruen"
    assert _ampel_for(6, 7) == "gruen"
    assert _ampel_for(7, 7) == "gruen"
    assert _ampel_for(2, 6) == "rot"
    assert _ampel_for(3, 7) == "rot"
    assert _ampel_for(0, 6) == "rot"
    assert _ampel_for(4, 6) == "gelb"
    assert _ampel_for(3, 6) == "gelb"
    assert _ampel_for(5, 7) == "gelb"
    assert _ampel_for(4, 7) == "gelb"


def _assert_calibration(demos, lang):
    """Demo-Prompts unter der Kriterien-Regel: schwach 1/6 rot,
    mittel 3/6 gelb (task/specificity/format erfüllt, context 0.5),
    stark 5/6 grün (nur examples fehlt; alle ohne Transformationsverb
    -> Nenner 6)."""
    r_weak = analyze_prompt(demos["weak"], "claude")
    r_med = analyze_prompt(demos["medium"], "claude")
    r_strong = analyze_prompt(demos["strong"], "claude")
    for name, r, met, ampel in (("schwach", r_weak, 1, "rot"),
                                ("mittel", r_med, 3, "gelb"),
                                ("stark", r_strong, 5, "gruen")):
        assert r["criteria_total"] == 6, \
            f"[{lang}] {name}: Nenner {r['criteria_total']}, erwartet 6"
        assert r["criteria_met"] == met, \
            f"[{lang}] {name}: {r['criteria_met']} erfüllt, erwartet {met}"
        assert r["ampel"] == ampel, \
            f"[{lang}] {name}: erwartet {ampel}, bekam {r['ampel']}"
    print(f"        [{lang}] Kriterien: schwach={r_weak['criteria_met']}/6, "
          f"mittel={r_med['criteria_met']}/6, stark={r_strong['criteria_met']}/6")


def test_calibration_de():
    _assert_calibration(DEMO_DE, "de")


def test_calibration_en():
    _assert_calibration(DEMO_EN, "en")


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

ALL_TESTS = [
    test_informationen_not_format,
    test_in_30_minuten_not_format,
    test_ebenso_wie_not_example,
    test_real_format_signals_still_work,
    test_question_is_full_task,
    test_question_without_questionmark,
    test_transform_without_material,
    test_transform_with_colon_material,
    test_transform_with_hier_ist,
    test_pointer_words_are_not_material,
    test_no_input_check_for_creation,
    test_format_number_varianten,
    test_format_number_woerter,
    test_prompt_lang_detection,
    test_template_follows_prompt_lang,
    test_ui_lang_english_feedback,
    test_real_umlauts,
    test_move_tip_when_role_inline,
    test_no_move_tip_without_inline_parts,
    test_role_example_has_material,
    test_no_good_example_teaches_input_mistake,
    test_hinweis_on_near_empty_prompt,
    test_empty_prompt_error,
    test_signature_defaults,
    test_no_score_field,
    test_denominator_without_transform,
    test_denominator_with_transform,
    test_color_rule_boundaries,
    test_calibration_de,
    test_calibration_en,
]

if __name__ == "__main__":
    passed, failed = 0, 0
    for test in ALL_TESTS:
        name = test.__name__
        try:
            test()
            print(f"  PASS  {name}")
            passed += 1
        except Exception:
            print(f"  FAIL  {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} bestanden, {failed} fehlgeschlagen.")
    sys.exit(1 if failed else 0)
