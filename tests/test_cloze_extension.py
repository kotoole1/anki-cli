"""Unit tests for the atomic cloze extension cards (new scrabble-2s+)."""

import re
import string

import pytest

from scrabble.AcClozeExtensionCard import (
    AcClozeExtensionAnswer, _group_for, _ALPHABET_GROUPS,
)
from scrabble.ExtensionCardSet import AcClozeExtensionCardSet

_BLUE  = "\033[94m"
_GREEN = "\033[92m"
_RED   = "\033[91m"
_RESET = "\033[0m"

_ANSI = re.compile(r"\033\[[0-9;]*m")


def _strip(text: str) -> str:
    return _ANSI.sub("", text)


def _ans(target, all_valid, direction="right", base="AE"):
    """Minimal cloze answer; valid words are base+letter (right) / letter+base (left)."""
    all_valid = frozenset(all_valid)
    words = [
        ((base + c) if direction == "right" else (c + base), "")
        for c in sorted(all_valid)
    ]
    return AcClozeExtensionAnswer("id", base, direction, target, all_valid, words)


# ── letter groups ─────────────────────────────────────────────────────────────

def test_alphabet_groups_partition_all_26():
    joined = "".join(_ALPHABET_GROUPS)
    assert sorted(joined) == list(string.ascii_uppercase)


@pytest.mark.parametrize("letter,group", [
    ("A", "AEIOU"), ("S", "LNSTR"), ("B", "BCDGMP"),
    ("F", "FHVWY"), ("Y", "FHVWY"), ("Z", "KJQXZ"),
])
def test_group_for(letter, group):
    assert _group_for(letter) == group


# ── shown_alphabet ──────────────────────────────────────────────────────────--

def test_alphabet_none_for_zero_or_one():
    assert _ans(None, "").shown_alphabet() == ""
    assert _ans("S", "S").shown_alphabet() == ""


def test_alphabet_full_for_two_or_three():
    assert _ans("D", "DN").shown_alphabet() == string.ascii_uppercase
    assert _ans("D", "DNS").shown_alphabet() == string.ascii_uppercase


def test_alphabet_group_for_four_plus():
    assert _ans("S", "DNST").shown_alphabet() == "LNSTR"      # target S → LNSTR
    assert _ans("F", "FHVW").shown_alphabet() == "FHVWY"      # the leftover group


# ── isCorrect ─────────────────────────────────────────────────────────────────

def test_correct_only_hidden_letter():
    a = _ans("D", "DNS")
    assert a.isCorrect("D")
    assert a.isCorrect("d")          # case-insensitive
    assert not a.isCorrect("N")      # a given/shown extension is not correct
    assert not a.isCorrect("X")
    assert not a.isCorrect("")


def test_correct_empty_for_zero_ext():
    a = _ans(None, "")
    assert a.isCorrect("")
    assert not a.isCorrect("S")


# ── isValid (plausible-candidate scoring) ─────────────────────────────────────

def test_valid_full_alphabet():
    a = _ans("D", "DNS")             # given = {N, S}
    assert a.isValid("")             # empty always scorable (idk)
    assert a.isValid("D")            # the hidden answer (white, in alphabet)
    assert a.isValid("X")            # white non-extension → scorable wrong
    assert not a.isValid("N")        # a given letter → invalid (already shown)
    assert not a.isValid("DN")       # multi-char → invalid
    assert not a.isValid("1")        # non-letter → invalid


def test_valid_group_alphabet():
    a = _ans("S", "DNST")            # shown = LNSTR, given = {D, N, T}
    assert a.isValid("S")            # answer, in group, not given
    assert a.isValid("L")            # white in group → scorable wrong
    assert not a.isValid("N")        # given letter in group → invalid
    assert not a.isValid("D")        # given but OUTSIDE the shown group → invalid
    assert not a.isValid("A")        # outside the shown group → invalid


def test_valid_no_alphabet_accepts_any_single_letter():
    a = _ans("S", "S")               # 1-ext, no alphabet shown
    assert a.isValid("S")
    assert a.isValid("X")            # scorable wrong
    assert a.isValid("")
    assert not a.isValid("XX")


def test_invalid_feedback_mentions_given_letter():
    a = _ans("D", "DNS")
    fb = a.getInvalidFeedback("N")
    assert "N" in _strip(fb)


# ── rendering: live context (pre-submit) ──────────────────────────────────────

def test_live_context_hides_answer_shows_given_blue():
    a = _ans("D", "DNS")             # words AED, AEN, AES; answer AED hidden
    ctx = a.getDisplayText()
    plain = _strip(ctx)
    assert "AED" not in plain        # hidden
    assert "AEN" in plain and "AES" in plain
    assert _BLUE in ctx              # the given extension letters are blue


def test_live_context_empty_for_one_ext():
    assert _ans("S", "S").getDisplayText() == ""


def test_live_context_blue_only_within_shown_group():
    # 4 valid → only the target's group (LNSTR) is shown; givens outside it (D in
    # BCDGMP) stay white, only in-group givens (N, T) are blue.
    a = _ans("S", "DNST")            # words AED/AEN/AES/AET; answer AES hidden
    ctx = a.getDisplayText()
    assert f"{_BLUE}N{_RESET}" in ctx
    assert f"{_BLUE}T{_RESET}" in ctx
    assert f"{_BLUE}D{_RESET}" not in ctx


# ── rendering: post-submit list ───────────────────────────────────────────────

def test_full_list_answer_green_when_correct():
    a = _ans("D", "DNS")
    out = a.getDisplayTextWhenCorrect()
    assert "AED" in _strip(out)      # answer now revealed
    assert _GREEN in out


def test_full_list_answer_red_when_incorrect():
    a = _ans("D", "DNS")
    assert _RED in a.getDisplayTextWhenIncorrect()


def test_full_list_is_alphabetical():
    a = _ans("D", "DNS")
    plain = _strip(a.getDisplayTextWhenCorrect())
    words = re.findall(r"\bAE[A-Z]\b", plain)
    assert words == sorted(words)
    assert words == ["AED", "AEN", "AES"]


def test_zero_ext_full_list_message():
    a = _ans(None, "")
    assert "no valid extensions" in _strip(a.getDisplayTextWhenCorrect())
    assert _GREEN in a.getDisplayTextWhenCorrect()
    assert _RED in a.getDisplayTextWhenIncorrect()


# ── rendering: clue line ──────────────────────────────────────────────────────

def test_clue_hides_target_pre_submit():
    a = _ans("D", "DNS")
    clue = a.clue_text()
    assert _GREEN not in clue        # target not revealed yet
    assert _BLUE in clue             # given letters are blue


def test_clue_reveals_green_when_correct():
    a = _ans("D", "DNS")
    assert _GREEN in a.clue_text("D", revealed=True)


def test_clue_reds_wrong_guess():
    a = _ans("D", "DNS")
    revealed = a.clue_text("X", revealed=True)
    assert _RED in revealed and _GREEN in revealed


def test_clue_no_alphabet_for_one_ext():
    assert _ans("S", "S").clue_text() == "AE?"
    assert _ans("S", "S", direction="left").clue_text() == "?AE"


# ── the built scrabble-2s+ cloze set ──────────────────────────────────────────

@pytest.fixture(scope="module")
def cloze():
    return AcClozeExtensionCardSet.scrabble_2s_plus()


def test_cloze_set_id(cloze):
    assert cloze.id == "scrabble-2s+-cloze"


def test_cloze_is_atomic_explosion(cloze):
    # One card per valid extension explodes well past the legacy 214 cards.
    assert len(cloze.cards) > 214


def test_cloze_new_card_order(cloze):
    assert cloze.new_card_order == [c.id for c in cloze.cards]


def test_cloze_clustered_by_pattern(cloze):
    # All cards for a (word, direction) pattern must be contiguous.
    pattern = lambda cid: cid.rsplit("-", 1)[0]   # 2s+-AE-right-D -> 2s+-AE-right
    runs = []
    for c in cloze.cards:
        p = pattern(c.id)
        if not runs or runs[-1] != p:
            runs.append(p)
    assert len(runs) == len(set(runs))            # each pattern appears in one run


def test_cloze_has_zero_ext_none_card(cloze):
    nones = [c for c in cloze.cards if c.id.endswith("-none")]
    assert nones
    assert nones[0].isCorrect("")


def test_cloze_aa_right_has_one_card_per_extension(cloze):
    ids = {c.id for c in cloze.cards}
    assert {"2s+-AA-right-H", "2s+-AA-right-L", "2s+-AA-right-S"} <= ids


def test_cloze_render_keeps_commonness_indicator(cloze):
    card = next(c for c in cloze.cards if c.id == "2s+-AA-right-S")
    text = _strip(card.getAnswer().getDisplayTextWhenCorrect())
    assert any(sym in text for sym in "▶▷▹")
