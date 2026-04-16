"""Unit tests for card answer logic."""

from cards.cardAnswer import SimpleTextAnswer
from scrabble.ScrabbleCard import ScrabbleAnswer

_ALPHAGRAM = "AEILNST"
_WORDS = [["ENTAILS", "third-person singular of entail"], ["NAILSET", "a tool"], ["TENAILS", ""]]


def _ans():
    return ScrabbleAnswer(_ALPHAGRAM, _WORDS)


# ── SimpleTextAnswer ──────────────────────────────────────────────────────────

def test_simple_correct():
    a = SimpleTextAnswer("id", "16")
    assert a.isCorrect("16")


def test_simple_wrong():
    a = SimpleTextAnswer("id", "16")
    assert not a.isCorrect("15")
    assert not a.isCorrect("")


def test_simple_feedback_uppercases():
    a = SimpleTextAnswer("id", "16")
    assert a.getWrongAnswerFeedback("hello") == "HELLO"


# ── ScrabbleAnswer — isCorrect ────────────────────────────────────────────────

def test_scrabble_correct_uppercase():
    assert _ans().isCorrect("ENTAILS")


def test_scrabble_correct_lowercase():
    assert _ans().isCorrect("entails")


def test_scrabble_correct_mixed_case():
    assert _ans().isCorrect("Entails")


def test_scrabble_wrong_word():
    assert not _ans().isCorrect("ZOEAE")


def test_scrabble_empty_answer():
    assert not _ans().isCorrect("")


# ── ScrabbleAnswer — getWrongAnswerFeedback ───────────────────────────────────

def test_feedback_excess_letters_are_red():
    # ENTAILX has X which is not in AEILNST → X should be red
    feedback = _ans().getWrongAnswerFeedback("ENTAILX")
    assert "\033[91m" in feedback
    assert "X" in feedback


def test_feedback_missing_letters_are_purple():
    # ENTAIL is missing S compared to AEILNST
    feedback = _ans().getWrongAnswerFeedback("ENTAIL")
    assert "\033[95m" in feedback
    assert "+S" in feedback


def test_feedback_no_excess_no_red():
    # ENTAIL has no excess letters (just missing S)
    feedback = _ans().getWrongAnswerFeedback("ENTAIL")
    assert "\033[91m" not in feedback


def test_feedback_valid_anagram_no_color():
    # TSNAILE is a valid anagram of AEILNST (same letter counts)
    feedback = _ans().getWrongAnswerFeedback("TSNAILE")
    assert "\033[91m" not in feedback
    assert "\033[95m" not in feedback
    assert feedback == "TSNAILE"


def test_feedback_all_wrong_letters():
    # ZZZZZZZ — all excess, all alphagram letters missing
    feedback = _ans().getWrongAnswerFeedback("ZZZZZZZ")
    assert feedback.count("\033[91m") == 7  # each Z is red
    assert "\033[95m" in feedback           # missing AEILNST shown in purple


def test_feedback_uppercases_input():
    feedback = _ans().getWrongAnswerFeedback("entailx")
    assert "X" in feedback  # uppercased before processing
    assert "x" not in feedback


def test_feedback_multiple_excess_same_letter():
    # EENTAIL has two E's; AEILNST only has one → second E is excess (red)
    feedback = _ans().getWrongAnswerFeedback("EENTAIL")
    assert "\033[91m" in feedback
