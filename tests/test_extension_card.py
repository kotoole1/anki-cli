"""Unit and integration tests for extension card types (scrabble-2s, scrabble-2s+)."""

import re
import pytest

from scrabble.ExtensionCard import ExtensionCard, ExtensionAnswer
from scrabble.ExtensionCardSet import AcExtensionCardSet

_RED    = "\033[91m"
_PURPLE = "\033[95m"

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cs_2s():
    return AcExtensionCardSet.scrabble_2s()


@pytest.fixture(scope="module")
def cs_2s_plus():
    return AcExtensionCardSet.scrabble_2s_plus()


def _make_ext_answer(word: str, direction: str) -> ExtensionAnswer:
    """Build a minimal ExtensionAnswer for a prompt of WORD? or ?WORD."""
    from scrabble.extensions import load_nwl_set, load_nwl_defs
    nwl  = load_nwl_set()
    defs = load_nwl_defs()
    target_len = len(word) + 1
    import string
    if direction == "right":
        valid = frozenset(c for c in string.ascii_uppercase if word + c in nwl)
        valid_words = [(word + c, defs.get(word + c, "")) for c in valid]
        card_id = f"test-{word}-right"
    else:
        valid = frozenset(c for c in string.ascii_uppercase if c + word in nwl)
        valid_words = [(c + word, defs.get(c + word, "")) for c in valid]
        card_id = f"test-{word}-left"
    return ExtensionAnswer(card_id, valid, valid_words)


# ── ExtensionAnswer.isCorrect ─────────────────────────────────────────────────

def test_is_correct_exact_set():
    ans = ExtensionAnswer("id", frozenset("SHL"), [("AAS", ""), ("AAH", ""), ("AAL", "")])
    assert ans.isCorrect("SHL")


def test_is_correct_any_order():
    ans = ExtensionAnswer("id", frozenset("SHL"), [])
    assert ans.isCorrect("LHS")
    assert ans.isCorrect("HLS")


def test_is_correct_lowercase():
    ans = ExtensionAnswer("id", frozenset("SH"), [])
    assert ans.isCorrect("sh")
    assert ans.isCorrect("Sh")


def test_is_correct_wrong():
    ans = ExtensionAnswer("id", frozenset("SHL"), [])
    assert not ans.isCorrect("SH")   # missing L
    assert not ans.isCorrect("SHLA") # extra A


def test_is_correct_empty_when_no_valid_letters():
    ans = ExtensionAnswer("id", frozenset(), [])
    assert ans.isCorrect("")  # blank is correct when no extensions exist


def test_is_correct_empty_wrong_when_letters_exist():
    ans = ExtensionAnswer("id", frozenset("S"), [])
    assert not ans.isCorrect("")


# ── ExtensionAnswer.getWrongAnswerFeedback ────────────────────────────────────

def test_feedback_extra_letter_is_red():
    ans = ExtensionAnswer("id", frozenset("S"), [])
    fb = ans.getWrongAnswerFeedback("SX")
    assert _RED in fb
    assert "X" in fb


def test_feedback_missing_letter_is_purple():
    ans = ExtensionAnswer("id", frozenset("SH"), [])
    fb = ans.getWrongAnswerFeedback("S")
    assert _PURPLE in fb
    assert "+H" in fb


def test_feedback_correct_letters_no_color():
    ans = ExtensionAnswer("id", frozenset("SH"), [])
    fb = ans.getWrongAnswerFeedback("SH")
    # Valid anagram — both letters present, no excess — no color codes
    assert _RED not in fb
    assert _PURPLE not in fb


def test_feedback_uppercases_input():
    ans = ExtensionAnswer("id", frozenset("S"), [])
    fb = ans.getWrongAnswerFeedback("sx")
    assert "X" in fb
    assert "x" not in fb


# ── ExtensionCard prompt format ───────────────────────────────────────────────

def test_right_card_prompt_has_question_mark_suffix():
    card = ExtensionCard("2s-A-right", "A?", frozenset("H"), [("AH", "")])
    assert card.getPrompt().getDisplayText() == "A?"


def test_left_card_prompt_has_question_mark_prefix():
    card = ExtensionCard("2s-A-left", "?A", frozenset("B"), [("BA", "")])
    assert card.getPrompt().getDisplayText() == "?A"


# ── scrabble-2s card set ──────────────────────────────────────────────────────

def test_2s_has_cards(cs_2s):
    assert len(cs_2s.cards) > 0


def test_2s_card_count_is_52(cs_2s):
    assert len(cs_2s.cards) == 52  # 26 letters × 2 directions, blank answer where no extensions


def test_2s_all_prompts_have_question_mark(cs_2s):
    for card in cs_2s.cards:
        prompt = card.getPrompt().getDisplayText()
        assert "?" in prompt, f"Card {card.id} prompt missing '?': {prompt!r}"


def test_2s_right_cards_format(cs_2s):
    right = [c for c in cs_2s.cards if c.id.endswith("-right")]
    for card in right:
        assert card.getPrompt().getDisplayText().endswith("?")


def test_2s_left_cards_format(cs_2s):
    left = [c for c in cs_2s.cards if c.id.endswith("-left")]
    for card in left:
        assert card.getPrompt().getDisplayText().startswith("?")


def test_2s_blank_answer_correct_for_empty_set(cs_2s):
    # "C?" — C has no valid right-side 2-letter word; blank answer is correct
    card = next(c for c in cs_2s.cards if c.id == "2s-C-right")
    assert card.isCorrect("")


def test_2s_correct_answer_for_A_right(cs_2s):
    # "A?" — letters that follow A to make a 2-letter NWL word
    card = next(c for c in cs_2s.cards if c.id == "2s-A-right")
    # AH is definitely a NWL 2-letter word
    assert "H" in card.getAnswer()._valid_letters


def test_2s_aa_in_A_right(cs_2s):
    # AA is a valid NWL 2-letter word → A is a valid right extension of A
    card = next(c for c in cs_2s.cards if c.id == "2s-A-right")
    assert "A" in card.getAnswer()._valid_letters


def test_2s_isCorrect_all_letters(cs_2s):
    card = next(c for c in cs_2s.cards if c.id == "2s-A-right")
    valid_str = "".join(sorted(card.getAnswer()._valid_letters))
    assert card.isCorrect(valid_str)


def test_2s_set_id(cs_2s):
    assert cs_2s.id == "scrabble-2s"


def test_2s_display_shows_letters_and_words(cs_2s):
    card = next(c for c in cs_2s.cards if c.id == "2s-A-right")
    text = card.getAnswer().getDisplayText()
    assert "H" in text  # AH extends A on the right
    assert "AH" in text  # full word shown


# ── scrabble-2s+ card set ─────────────────────────────────────────────────────

def test_2s_plus_has_cards(cs_2s_plus):
    assert len(cs_2s_plus.cards) > 0


def test_2s_plus_card_count(cs_2s_plus):
    # 107 NWL 2-letter words × 2 directions = 214 cards (blank answer where no extension)
    assert len(cs_2s_plus.cards) == 214


def test_2s_plus_all_prompts_have_question_mark(cs_2s_plus):
    for card in cs_2s_plus.cards:
        prompt = card.getPrompt().getDisplayText()
        assert "?" in prompt


def test_2s_plus_prompts_are_2letter_words(cs_2s_plus):
    from scrabble.extensions import load_nwl_set
    nwl  = load_nwl_set()
    twos = {w for w in nwl if len(w) == 2}
    for card in cs_2s_plus.cards:
        prompt = card.getPrompt().getDisplayText()
        word = prompt.strip("?")
        assert len(word) == 2, f"Card {card.id} base word has wrong length: {word!r}"
        assert word in twos, f"{word} is not a NWL 2-letter word"


def test_2s_plus_valid_extensions_are_3letter_nwl_words(cs_2s_plus):
    from scrabble.extensions import load_nwl_set
    nwl = load_nwl_set()
    for card in cs_2s_plus.cards[:30]:  # spot-check first 30
        ans = card.getAnswer()
        for word, _ in ans._valid_words:
            assert word in nwl, f"Extension word {word!r} not in NWL"
            assert len(word) == 3, f"Extension word {word!r} is not 3 letters"


def test_2s_plus_blank_answer_when_no_extensions(cs_2s_plus):
    # Some 2-letter words have no valid extension in one direction
    blank_cards = [c for c in cs_2s_plus.cards if not c.getAnswer()._valid_letters]
    assert len(blank_cards) > 0  # there should be some
    for card in blank_cards:
        assert card.isCorrect("")


def test_2s_plus_aa_right_extensions(cs_2s_plus):
    # AA? — AAH, AAL, AAS are valid 3-letter extensions
    card = next(c for c in cs_2s_plus.cards if c.id == "2s+-AA-right")
    valid = card.getAnswer()._valid_letters
    assert "H" in valid  # AAH
    assert "L" in valid  # AAL
    assert "S" in valid  # AAS


def test_2s_plus_set_id(cs_2s_plus):
    assert cs_2s_plus.id == "scrabble-2s+"
