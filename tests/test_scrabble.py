"""Unit tests for ScrabbleCardSet card selection, ordering, and structure."""

import os
import re

import pytest

_ANSI = re.compile(r"\033(?:\[[^\x40-\x7e]*[\x40-\x7e]|\?[0-9]+[hl])")

def _strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)

_CACHE_7 = os.path.join(os.path.dirname(__file__), "..", "src", "scrabble", "cache", "nwl_7.csv")
_CACHE_8 = os.path.join(os.path.dirname(__file__), "..", "src", "scrabble", "cache", "nwl_8.csv")


def _skip7():
    if not os.path.exists(_CACHE_7):
        pytest.skip("scrabble7 cache missing — run: uv run anki-cli.py scrabble7")


def _skip8():
    if not os.path.exists(_CACHE_8):
        pytest.skip("scrabble8 cache missing — run: uv run anki-cli.py scrabble8")


@pytest.fixture(scope="module")
def cs7():
    """Default scrabble7: 1k-common (filtered to alphagrams with a common word)."""
    _skip7()
    from scrabble.ScrabbleCardSet import ScrabbleCardSet
    return ScrabbleCardSet(7, top_n=1000, common_filter=True)


@pytest.fixture(scope="module")
def cs7_1k():
    """scrabble7-1k: top 1000 by probability, no common-word filter."""
    _skip7()
    from scrabble.ScrabbleCardSet import ScrabbleCardSet
    return ScrabbleCardSet(7, top_n=1000, common_filter=False)


@pytest.fixture(scope="module")
def cs7_2k():
    """Legacy 2k set (top 2000 by commonness, sorted by prob)."""
    _skip7()
    from scrabble.ScrabbleCardSet import ScrabbleCardSet
    return ScrabbleCardSet(7, top_n=2000, common_filter=False)


@pytest.fixture(scope="module")
def cs8():
    """Default scrabble8: 1k-common."""
    _skip8()
    from scrabble.ScrabbleCardSet import ScrabbleCardSet
    return ScrabbleCardSet(8, top_n=1000, common_filter=True)


# ── scrabble7 (1k-common) — basic properties ─────────────────────────────────

def test_scrabble7_has_1000_cards(cs7):
    assert len(cs7.cards) == 1000


def test_scrabble7_id_is_scrabble7(cs7):
    assert cs7.id == "scrabble7"


def test_scrabble7_rating_threshold_is_seven(cs7):
    assert cs7.rating_time_threshold_s == 7


def test_scrabble7_all_cards_have_common_word(cs7):
    """Every card in the 1k-common set has at least one word in the top-20k."""
    from scrabble.ScrabbleCardSet import ScrabbleCardSet
    top20k = ScrabbleCardSet._get_top20k()
    for card in cs7.cards:
        words = [w for w, _ in card.getAnswer().nwl_words]
        assert any(w.lower() in top20k for w in words), \
            f"{card.id} has no common word: {words}"


def test_scrabble7_new_card_order_length_equals_card_count(cs7):
    assert len(cs7.new_card_order) == len(cs7.cards)


def test_scrabble7_new_card_order_contains_all_ids(cs7):
    assert set(cs7.new_card_order) == {c.id for c in cs7.cards}


def test_scrabble7_new_card_order_sorted_by_prob_descending(cs7):
    prob_by_id = {c.id: c.probability for c in cs7.cards}
    probs = [prob_by_id[cid] for cid in cs7.new_card_order]
    assert probs == sorted(probs, reverse=True)


def test_scrabble7_first_card_has_highest_probability(cs7):
    prob_by_id = {c.id: c.probability for c in cs7.cards}
    first_prob = prob_by_id[cs7.new_card_order[0]]
    assert first_prob == max(prob_by_id.values())


def test_scrabble7_all_alphagrams_have_seven_letters(cs7):
    assert all(len(c.id) == 7 for c in cs7.cards)


def test_scrabble7_alphagrams_are_uppercase_sorted(cs7):
    for card in cs7.cards:
        assert card.id == "".join(sorted(card.id))


def test_scrabble7_all_cards_have_at_least_one_valid_word(cs7):
    for card in cs7.cards:
        assert card.getAnswer().nwl_words, f"{card.id} has no valid words"


# ── scrabble7-1k (prob-only) ──────────────────────────────────────────────────

def test_scrabble7_1k_has_1000_cards(cs7_1k):
    assert len(cs7_1k.cards) == 1000


def test_scrabble7_1k_id_is_scrabble7_1k(cs7_1k):
    assert cs7_1k.id == "scrabble7-1k"


def test_scrabble7_1k_new_card_order_sorted_by_prob_descending(cs7_1k):
    prob_by_id = {c.id: c.probability for c in cs7_1k.cards}
    probs = [prob_by_id[cid] for cid in cs7_1k.new_card_order]
    assert probs == sorted(probs, reverse=True)


def test_scrabble7_1k_first_card_has_highest_probability(cs7_1k):
    prob_by_id = {c.id: c.probability for c in cs7_1k.cards}
    assert prob_by_id[cs7_1k.new_card_order[0]] == max(prob_by_id.values())


def test_scrabble7_1k_has_highest_prob_alphagrams(cs7_1k, cs7_2k):
    """1k-prob has higher or equal min-probability than 2k-commonness set."""
    min_1k = min(c.probability for c in cs7_1k.cards)
    max_2k_outside = max(
        (c.probability for c in cs7_2k.cards if c.id not in {x.id for x in cs7_1k.cards}),
        default=0.0,
    )
    assert min_1k >= max_2k_outside


# ── Legacy 2k set — commonness selection ─────────────────────────────────────

def test_scrabble7_2k_has_2000_cards(cs7_2k):
    assert len(cs7_2k.cards) == 2000


def test_scrabble7_2k_id(cs7_2k):
    assert cs7_2k.id == "scrabble7-2k"


def test_scrabble7_top_2000_are_more_common_than_the_rest(cs7_2k):
    """The top-2000 selection by commonness: every included card >= every excluded card."""
    import csv
    from scrabble.ScrabbleCardSet import _load_top

    all_entries: dict[str, float] = {}
    with open(_CACHE_7, newline="") as f:
        for row in csv.DictReader(f):
            alpha = row["alphagram"]
            if alpha not in all_entries:
                all_entries[alpha] = float(row["commonness"])

    top = _load_top(7, 2000)
    top_alphas = {e["alphagram"] for e in top}
    min_top = min(e["commonness"] for e in top)
    tail = [c for a, c in all_entries.items() if a not in top_alphas]
    if tail:
        assert max(tail) <= min_top


# ── ScrabbleCardSet(8) — basic properties ─────────────────────────────────────

def test_scrabble8_has_1000_cards(cs8):
    assert len(cs8.cards) == 1000


def test_scrabble8_id_is_scrabble8(cs8):
    assert cs8.id == "scrabble8"


def test_scrabble8_all_cards_have_common_word(cs8):
    from scrabble.ScrabbleCardSet import ScrabbleCardSet
    top20k = ScrabbleCardSet._get_top20k()
    for card in cs8.cards:
        words = [w for w, _ in card.getAnswer().nwl_words]
        assert any(w.lower() in top20k for w in words), \
            f"{card.id} has no common word: {words}"


def test_scrabble8_all_alphagrams_have_eight_letters(cs8):
    assert all(len(c.id) == 8 for c in cs8.cards)


def test_scrabble8_new_card_order_length_equals_card_count(cs8):
    assert len(cs8.new_card_order) == len(cs8.cards)


def test_scrabble8_new_card_order_contains_all_ids(cs8):
    assert set(cs8.new_card_order) == {c.id for c in cs8.cards}


def test_scrabble8_new_card_order_sorted_by_prob_descending(cs8):
    prob_by_id = {c.id: c.probability for c in cs8.cards}
    probs = [prob_by_id[cid] for cid in cs8.new_card_order]
    assert probs == sorted(probs, reverse=True)


# ── Frequency indicator ───────────────────────────────────────────────────────

def test_frequency_indicator_common_word_gets_filled_triangle(cs7_2k):
    """ANOTHER is a common English word and should get the ▶ indicator."""
    card = next(c for c in cs7_2k.cards if c.id == "AEHNORT")
    assert "▶" in card.getAnswer().getDisplayText()


def test_frequency_indicator_uncommon_word_gets_outline_triangle(cs7_2k):
    """ANTSIER has zero wordfreq and should get ▷."""
    card = next(c for c in cs7_2k.cards if c.id == "AEINRST")
    assert "▷" in card.getAnswer().getDisplayText()


def test_frequency_indicator_every_word_has_one(cs7):
    """Every word line in every answer should have exactly one frequency indicator."""
    for card in cs7.cards[:50]:
        text = _strip_ansi(card.getAnswer().getDisplayText())
        for line in text.splitlines():
            if not line.strip():
                continue
            assert line.count("▶") + line.count("▷") == 1, \
                f"Expected exactly one indicator in: {line!r}"


# ── Extension annotations ─────────────────────────────────────────────────────

_WORDS_CACHE = os.path.join(os.path.dirname(__file__), "..", "src", "scrabble", "cache", "nwl_words.txt")
requires_words_cache = pytest.mark.skipif(
    not os.path.exists(_WORDS_CACHE),
    reason="nwl_words.txt cache missing — run: uv run anki-cli.py scrabble7",
)


@requires_words_cache
def test_extension_symbols_detrain_has_right_plus(cs7_2k):
    """DETRAIN → DETRAINS, so DETRAIN should show '+' on the right (ADEINRT card)."""
    card = next(c for c in cs7_2k.cards if c.id == "ADEINRT")
    text = _strip_ansi(card.getAnswer().getDisplayText())
    detrain_line = next(l for l in text.splitlines() if re.match(r"\s+[+~-]?DETRAIN[+~-]?\s", l))
    idx = detrain_line.index("DETRAIN")
    assert detrain_line[idx + len("DETRAIN")] == "+", f"Expected DETRAIN+ in: {detrain_line!r}"


@requires_words_cache
def test_extension_no_spurious_symbols_without_cache(cs7):
    """Words show no extension symbols when ext_lookup is None."""
    from scrabble.ScrabbleCard import ScrabbleCard
    card = ScrabbleCard(id="TEST", alphagram="TEST", probability=0.0,
                        nwl_words=[("TEST", "a test")], top20k=frozenset(), ext_lookup=None)
    text = card.getAnswer().getDisplayText()
    assert "+" not in text
    assert "-" not in text
    assert "~" not in text


@requires_words_cache
def test_extension_symbols_present_for_spot_check(cs7):
    """At least some cards in the first 50 should have extension symbols."""
    symbols_found = set()
    for card in cs7.cards[:50]:
        text = card.getAnswer().getDisplayText()
        for sym in ("+", "-", "~"):
            if sym in text:
                symbols_found.add(sym)
    assert "+" in symbols_found, "Expected at least one '+' extension in first 50 cards"


@requires_words_cache
def test_extension_lookup_extensions_for_single_letter(cs7_2k):
    """extensions_for returns known single-letter extensions."""
    card = next(c for c in cs7_2k.cards if c.id == "ADEINRT")
    lookup = card.getAnswer()._ext_lookup
    lefts, rights = lookup.extensions_for("DETRAIN")
    right_words = [w for w, _ in rights]
    assert "DETRAINS" in right_words


@requires_words_cache
def test_extension_lookup_extensions_for_multi_letter(cs7_2k):
    """extensions_for returns multi-letter extensions for 5+ letter words."""
    card = next(c for c in cs7_2k.cards if c.id == "ADEINRT")
    lookup = card.getAnswer()._ext_lookup
    lefts, rights = lookup.extensions_for("TRAINED")
    left_words = [w for w, _ in lefts]
    assert "STRAINED" in left_words
    assert "CONSTRAINED" in left_words


@requires_words_cache
def test_extension_lookup_sorted_by_length(cs7_2k):
    """extensions_for results are sorted shortest first."""
    card = next(c for c in cs7_2k.cards if c.id == "ADEINRT")
    lookup = card.getAnswer()._ext_lookup
    lefts, rights = lookup.extensions_for("TRAINED")
    assert [len(w) for w, _ in lefts] == sorted(len(w) for w, _ in lefts)


@requires_words_cache
def test_extension_lookup_includes_definitions(cs7_2k):
    """Extension words include definitions from the defs cache."""
    card = next(c for c in cs7_2k.cards if c.id == "ADEINRT")
    lookup = card.getAnswer()._ext_lookup
    _, rights = lookup.extensions_for("DETRAIN")
    detrains = next((d for w, d in rights if w == "DETRAINS"), None)
    assert detrains is not None and len(detrains) > 0


# ── Word ordering ─────────────────────────────────────────────────────────────

def test_words_ordered_by_frequency_descending(cs7_2k):
    """Words in the display output are ordered most-common-first."""
    from wordfreq import word_frequency
    card = next(c for c in cs7_2k.cards if c.id == "AEINRST")
    text = _strip_ansi(card.getAnswer().getDisplayText())
    # Extract the word from each non-empty line (2nd token after leading spaces/symbols)
    words = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            # strip extension symbols: leading +/-/~ and trailing +/-/~
            word = stripped.lstrip("+-~ ").split()[0].rstrip("+-~ ")
            if word.isalpha():
                words.append(word)
    freqs = [word_frequency(w.lower(), 'en') for w in words]
    assert freqs == sorted(freqs, reverse=True), \
        f"Words not sorted by frequency: {list(zip(words, freqs))}"


# ── Wrong answer feedback: red vs orange ──────────────────────────────────────

_RED    = "\033[91m"
_ORANGE = "\033[38;5;208m"
_PURPLE = "\033[95m"


def _make_answer(alphagram: str) -> "ScrabbleAnswer":
    from scrabble.ScrabbleCard import ScrabbleAnswer
    return ScrabbleAnswer(alphagram, [(alphagram, "")], frozenset(), None)


def test_wrong_answer_non_alphagram_letter_is_red():
    """A letter not in the alphagram at all should be colored red."""
    ans = _make_answer("AEINRST")
    feedback = ans.getWrongAnswerFeedback("XEINRST")  # X not in alphagram
    assert _RED in feedback
    assert _ORANGE not in feedback


def test_wrong_answer_overused_alphagram_letter_is_orange():
    """A letter that IS in the alphagram but used one too many times → orange."""
    ans = _make_answer("AEINRST")
    # SSEINRST has two S's; alphagram has one S
    feedback = ans.getWrongAnswerFeedback("SSEINRST")
    assert _ORANGE in feedback
    assert _RED not in feedback


def test_wrong_answer_mix_orange_and_red():
    """X (not in alphagram) → red; extra S (in alphagram) → orange; both present."""
    ans = _make_answer("AEINRST")
    # SXEINRST: extra S (in alphagram) → orange, X (not in alphagram) → red
    feedback = ans.getWrongAnswerFeedback("SXEINRST")
    assert _ORANGE in feedback
    assert _RED in feedback


def test_wrong_answer_valid_anagram_not_colored():
    """A valid anagram (right tiles, wrong word) gets no coloring."""
    ans = _make_answer("AEINRST")
    # TSAREIN is an anagram of AEINRST (same letters)
    feedback = ans.getWrongAnswerFeedback("NASTIER")
    assert _RED not in feedback
    assert _ORANGE not in feedback


def test_wrong_answer_missing_shown_in_purple():
    """Missing tiles are shown as +LETTERS in purple."""
    ans = _make_answer("AEINRST")
    feedback = ans.getWrongAnswerFeedback("XEINRST")  # missing A, extra X
    assert _PURPLE in feedback
    assert "A" in feedback  # the missing letter is shown
