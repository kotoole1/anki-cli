"""Unit tests for the batched (cloze-by-segment) extension sets, scrabble-2s+ and scrabble-2s."""

import re
import string

import pytest

from scrabble.AcBatchedExtensionCard import AcBatchedExtensionCard, _segment_index
from scrabble.ExtensionCard import ExtensionCard
from scrabble.ExtensionCardSet import AcBatchedExtensionCardSet, _vowel_family
from scrabble.extensions import load_two_letter_playability

_BLUE   = "\033[94m"
_GREEN  = "\033[92m"
_PURPLE = "\033[95m"
_RESET  = "\033[0m"
_ANSI = re.compile(r"\033\[[0-9;]*m")


def _strip(text: str) -> str:
    return _ANSI.sub("", text)


@pytest.fixture(scope="module")
def batched():
    return AcBatchedExtensionCardSet.scrabble_2s_plus()


@pytest.fixture(scope="module")
def batched_2s():
    return AcBatchedExtensionCardSet.scrabble_2s()


def _some_batched(batched, pred):
    return next(c for c in batched.cards if isinstance(c, AcBatchedExtensionCard) and pred(c.getAnswer()))


# ── set shape ─────────────────────────────────────────────────────────────────

def test_set_id(batched):
    assert batched.id == "scrabble-2s+"


def test_mixes_legacy_and_batched(batched):
    assert any(isinstance(c, ExtensionCard) for c in batched.cards)
    assert any(isinstance(c, AcBatchedExtensionCard) for c in batched.cards)


def test_legacy_cards_have_at_most_four_valid(batched):
    for c in batched.cards:
        if isinstance(c, ExtensionCard):
            assert len(c.getAnswer()._valid_letters) <= 4


def test_reveal_order_unchanged(batched):
    assert batched.new_card_order == [c.id for c in batched.cards]


# ── drip-feed ordered by real scrabble play frequency (2s+ only) ──────────────

def _root(card_id):
    return card_id.split("-")[1]


def test_playability_data_loads_with_qi_most_played():
    play = load_two_letter_playability()
    assert play, "playability cache should be present"
    assert max(play, key=play.get) == "QI"     # QI is the most-played 2 (matches 538)
    assert play["QI"] > play["XI"] > play["OX"]


def test_2s_plus_drip_starts_with_most_played_roots(batched):
    roots = []
    for cid in batched.new_card_order:
        r = _root(cid)
        if not roots or roots[-1] != r:
            roots.append(r)
    # the real O'Laughlin play-frequency ordering of the top roots
    assert roots[:6] == ["QI", "XI", "OX", "ZA", "EX", "AX"]


def test_2s_plus_more_played_root_drips_before_less_played(batched):
    order = batched.new_card_order
    first = {}
    for i, cid in enumerate(order):
        first.setdefault(_root(cid), i)
    # QI (most played) introduced before SO (least played of the covered roots)
    assert first["QI"] < first["SO"]
    assert first["EX"] < first["AS"]


def test_2s_plus_roots_stay_clustered_in_drip_order(batched):
    """Ordering by root must not interleave a root's cards with another's."""
    from itertools import groupby
    blocks = [k for k, _ in groupby(_root(cid) for cid in batched.new_card_order)]
    assert len(blocks) == len(set(blocks))      # each root is one contiguous run


# ── segment display (all 5, active hidden, context blue) ──────────────────────

def test_card_shows_all_five_segments(batched):
    c = _some_batched(batched, lambda a: True)
    clue = _strip(c.clue_text())
    # The active segment is spaced out for readability; the rest stay compact.
    for seg in ("AEIOU", "LNRST", "BCDGMP", "FHVWY", "JKQXZ"):
        assert seg in clue or " ".join(seg) in clue


def test_active_segment_is_spaced_out(batched):
    """The active batch (the one you answer) renders spaced ('L N R S T'); the
    non-active context segments stay compact."""
    c = _some_batched(batched, lambda a: a._valid_letters)
    a = c.getAnswer()
    clue = _strip(a.clue_text())
    assert " ".join(a._active_display) in clue          # active spaced
    assert a._active_display not in clue                # …and not also compact


def test_active_hidden_pre_submit_colored_by_guess():
    # active segment LNSTR (S valid); a vowel A valid in a non-active segment
    from scrabble.AcBatchedExtensionCard import AcBatchedExtensionAnswer
    a = AcBatchedExtensionAnswer("id", "BA", "right", "LNSTR",
                                 frozenset("S"), frozenset("SA"),
                                 [("BAS", ""), ("BAA", "")])
    pre = a.clue_text()
    assert f"{_BLUE}S{_RESET}" not in pre       # active answer hidden pre-submit (white)
    assert f"{_BLUE}A{_RESET}" in pre           # non-active valid shown blue as context
    a.isCorrect("S")                            # correct → S green in the active segment
    assert f"{_GREEN}S{_RESET}" in a.clue_text(revealed=True)
    a.isCorrect("")                             # blank → S purple (missed), never blue/white
    blank = a.clue_text(revealed=True)
    assert f"{_PURPLE}S{_RESET}" in blank
    assert f"{_BLUE}S{_RESET}" not in blank


def test_blank_answer_marks_every_missed_letter_and_word_purple():
    """Regression (the REX/REZ bug): a blank answer on a segment with *two* valid
    letters must show BOTH as missed — purple in the segment display, purple in
    the word list, and both in the +diff. The earlier stateful coloring recorded
    only one, leaving the other uncolored and dropping it from the diff."""
    from scrabble.AcBatchedExtensionCard import _PURPLE, _RESET, _RED, _DIM
    from scrabble.AcBatchedExtensionCard import AcBatchedExtensionAnswer
    # RE? extends with X and Z (KJQXZ segment); RES/REV live in other segments.
    a = AcBatchedExtensionAnswer(
        "2s+b-RE-right-KJQXZ", "RE", "right", "KJQXZ",
        frozenset("XZ"), frozenset("XZSV"),
        [("REX", ""), ("REZ", ""), ("RES", ""), ("REV", "")])
    a.isCorrect("")   # blank → both X and Z missed

    seg = a.clue_text(revealed=True)
    assert f"{_PURPLE}X{_RESET}" in seg and f"{_PURPLE}Z{_RESET}" in seg   # both purple
    assert f"{_DIM}J{_RESET}" in seg                                       # skipped → grey

    words = a.getDisplayTextWhenIncorrect()
    assert f"{_PURPLE}REX{_RESET}" in words and f"{_PURPLE}REZ{_RESET}" in words

    diff = _strip(a.getWrongAnswerFeedback(""))
    assert "+XZ" in diff and "+X " not in diff    # both letters in one +group, not just one


def test_partial_answer_greens_given_reds_wrong_purples_missed():
    """A partial/mixed guess exercises all four completion colors at once."""
    from scrabble.AcBatchedExtensionCard import _PURPLE, _GREEN, _RED, _DIM, _RESET
    from scrabble.AcBatchedExtensionCard import AcBatchedExtensionAnswer
    a = AcBatchedExtensionAnswer(
        "2s+b-RE-right-KJQXZ", "RE", "right", "KJQXZ",
        frozenset("XZ"), frozenset("XZSV"),
        [("REX", ""), ("REZ", ""), ("RES", ""), ("REV", "")])
    a.isCorrect("XK")   # X correct, Z missed, K wrong, J/Q skipped
    seg = a.clue_text(revealed=True)
    assert f"{_GREEN}X{_RESET}" in seg     # given & valid → green
    assert f"{_PURPLE}Z{_RESET}" in seg    # valid, not given → purple
    assert f"{_RED}K{_RESET}" in seg       # given, not valid → red
    assert f"{_DIM}J{_RESET}" in seg       # correctly skipped → grey
    fb = _strip(a.getWrongAnswerFeedback("XK"))
    assert "X" in fb and "+Z" in fb and "-K" in fb


def test_subset_valid_within_active_group(batched):
    for c in batched.cards:
        if isinstance(c, AcBatchedExtensionCard):
            a = c.getAnswer()
            assert a._valid_letters <= set(a.subset)


# ── vowel-swap selection ──────────────────────────────────────────────────────

def test_vowel_family_swaps_one_vowel():
    fam = _vowel_family("BA", frozenset({"BA", "BE", "BO", "ZZ"}))
    assert {"BA", "BE", "BO"} <= fam
    assert "ZZ" not in fam         # unreachable by a vowel swap
    assert "BI" not in fam         # BI not in the supplied valid-bigram set


def test_confirm_empty_segment_cards_exist(batched):
    # vowel-swap creates cards for segments the bigram itself doesn't extend into
    empties = [c for c in batched.cards
               if isinstance(c, AcBatchedExtensionCard) and not c.getAnswer()._valid_letters]
    assert empties
    assert empties[0].isCorrect("")


# ── scoring & feedback ────────────────────────────────────────────────────────

def test_iscorrect_active_segment_letters(batched):
    c = _some_batched(batched, lambda a: a._valid_letters)
    valid_str = "".join(sorted(c.getAnswer()._valid_letters))
    assert c.isCorrect(valid_str)
    assert not c.isCorrect("")


def test_batched_rejects_letters_outside_active_segment():
    """Regression: `?O` with FHVWY active — typing 'jwy' must be rejected (J is
    outside the shown segment), not scored as a wrong answer."""
    from scrabble.AcBatchedExtensionCard import AcBatchedExtensionAnswer
    a = AcBatchedExtensionAnswer("2s+b-O-left-FHVWY", "O", "left", "FHVWY",
                                 frozenset("FW"), frozenset("FWX"),
                                 [("FO", ""), ("WO", ""), ("XO", "")])
    assert a.isValid("")            # idk
    assert a.isValid("FW")          # letters within the active segment
    assert a.isValid("f h v")       # case- and space-tolerant, all in FHVWY
    assert not a.isValid("jwy")     # J is outside FHVWY → rejected (the bug)
    assert not a.isValid("F1")      # non-letter → rejected
    fb = _strip(a.getInvalidFeedback("jwy"))
    assert "Which of these letters complete ?O" in fb
    assert "F H V W Y" in fb         # the active segment, spaced


def test_feedback_plus_missing_minus_extra(batched):
    c = _some_batched(batched, lambda a: a._valid_letters)
    a = c.getAnswer()
    wrong = next(ch for ch in string.ascii_uppercase if ch not in a._all_valid)
    fb = _strip(a.getWrongAnswerFeedback(wrong))
    assert "+" in fb               # you missed the real answers
    assert f"-{wrong}" in fb       # and wrongly included `wrong`


# ── completion display ────────────────────────────────────────────────────────

def test_completion_word_list_sorted_by_segment(batched):
    c = _some_batched(batched, lambda a: len(a._all_words) >= 3)
    a = c.getAnswer()
    seg_seq = [_segment_index(a._ext_letter(w)) for w, _ in a._words_sorted]
    assert seg_seq == sorted(seg_seq)


def test_completion_colors_outside_blue_missed_purple(batched):
    c = _some_batched(batched, lambda a: 0 < len(a._valid_letters) < len(a._all_words))
    c.getAnswer().isCorrect("")     # blank → every active answer missed
    incorrect = c.getAnswer().getDisplayTextWhenIncorrect()
    assert _PURPLE in incorrect     # in-segment answers you missed
    assert _BLUE in incorrect       # other segments' words shown blue


def test_correct_answers_green_in_word_list(batched):
    c = _some_batched(batched, lambda a: a._valid_letters)
    a = c.getAnswer()
    a.isCorrect("".join(sorted(a._valid_letters)))   # give them all
    assert _GREEN in a.getDisplayTextWhenCorrect()


def test_blank_feedback_lists_all_missing(batched):
    c = _some_batched(batched, lambda a: a._valid_letters)
    fb = _strip(c.getAnswer().getWrongAnswerFeedback(""))
    assert fb.strip().startswith("+")          # +<all valid>, nothing correct/extra


def test_empty_subset_shows_no_extensions_message(batched):
    c = next(c for c in batched.cards
             if isinstance(c, AcBatchedExtensionCard) and not c.getAnswer()._valid_letters)
    a = c.getAnswer()
    a.isCorrect("")
    assert "No valid extensions with" in _strip(a.getDisplayTextWhenCorrect())


# ── scrabble-2s batched set (only vowel bases batch) ──────────────────────────

_VOWELS = set("AEIOU")


def test_2s_set_id(batched_2s):
    assert batched_2s.id == "scrabble-2s"


def test_2s_only_vowel_bases_are_batched(batched_2s):
    """Every cloze-by-segment card in the 2s set is a vowel base; consonant bases
    (even with 5+ extensions) stay a single legacy card."""
    for c in batched_2s.cards:
        base = c.getAnswer().base_word if isinstance(c, AcBatchedExtensionCard) \
            else c.id.split("-")[1]
        if isinstance(c, AcBatchedExtensionCard):
            assert base in _VOWELS, f"{c.id} batched a non-vowel base"


def test_2s_consonant_with_five_plus_stays_legacy(batched_2s):
    """B? extends to BA BE BI BO BY (5 letters) but B is a consonant → one legacy
    card, not segment-split."""
    b_right = [c for c in batched_2s.cards if c.id.startswith("2s-B-right")]
    assert len(b_right) == 1
    assert isinstance(b_right[0], ExtensionCard)


def test_2s_vowel_base_splits_into_segments(batched_2s):
    """A vowel base with many extensions produces multiple per-segment cards."""
    a_right = [c for c in batched_2s.cards
               if c.id.startswith("2s-A-right") and isinstance(c, AcBatchedExtensionCard)]
    assert len(a_right) >= 2


def test_2s_split_is_total_vowels_batched_consonants_legacy(batched_2s):
    """Every vowel base is batched and every consonant base is legacy — no
    exceptions (the vowel/consonant split is total, not count-gated)."""
    for c in batched_2s.cards:
        base = c.getAnswer().base_word if isinstance(c, AcBatchedExtensionCard) \
            else c.id.split("-")[1]
        if base in _VOWELS:
            assert isinstance(c, AcBatchedExtensionCard), f"{c.id}: vowel not batched"
        else:
            assert isinstance(c, ExtensionCard), f"{c.id}: consonant not legacy"


def test_2s_sparse_vowel_still_batched(batched_2s):
    """Regression: ?U has only a few extensions but must still be batched (it was
    falling under a 5+ count threshold and staying legacy)."""
    u_left = [c for c in batched_2s.cards if c.id.startswith("2s-U-left")]
    assert u_left
    assert all(isinstance(c, AcBatchedExtensionCard) for c in u_left)
