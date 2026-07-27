"""Card sets for NWL single-letter extension drills (scrabble-2s, scrabble-2s+)."""

import string

from cards.cardSet import CardSet
from scrabble.ExtensionCard import ExtensionCard
from scrabble.AcClozeExtensionCard import AcClozeExtensionCard, _ALPHABET_GROUPS
from scrabble.AcBatchedExtensionCard import AcBatchedExtensionCard
from scrabble.extensions import (
    load_nwl_set, load_nwl_defs, load_two_letter_playability, AcExtensionLookup,
)

_LETTERS = string.ascii_uppercase

_TILE_COUNTS = {
    'A': 9,  'B': 2,  'C': 2,  'D': 4,  'E': 12, 'F': 2,  'G': 3,
    'H': 2,  'I': 9,  'J': 1,  'K': 1,  'L': 4,  'M': 2,  'N': 6,
    'O': 8,  'P': 2,  'Q': 1,  'R': 6,  'S': 4,  'T': 6,  'U': 4,
    'V': 2,  'W': 2,  'X': 1,  'Y': 2,  'Z': 1,
}
_VOWELS = frozenset('AEIOU')

def _letter_order_key(letter: str):
    """Consonants first, then vowels; within each group, higher tile count first, then alpha."""
    return (letter in _VOWELS, -_TILE_COUNTS.get(letter, 0), letter)

def _word_tile_prob_key(word: str):
    """Higher product of tile counts sorts first (more likely to draw)."""
    prod = 1
    for c in word:
        prod *= _TILE_COUNTS.get(c, 1)
    return -prod



def _build_2s(nwl: frozenset[str], defs: dict[str, str],
              ext_lookup: AcExtensionLookup,
              top20k: frozenset[str] = frozenset(),
              top50k: frozenset[str] = frozenset()) -> list[ExtensionCard]:
    """52-card set (26 letters × 2 directions); blank answer is correct when no extension exists."""
    twos = {w for w in nwl if len(w) == 2}
    cards = []
    for letter in sorted(_LETTERS, key=_letter_order_key):
        for direction in ("right", "left"):
            if direction == "right":
                valid = frozenset(w[1] for w in twos if w[0] == letter)
                card_id = f"2s-{letter}-right"
                prompt_text = f"{letter}?"
                valid_words = [(letter + c, defs.get(letter + c, "")) for c in valid]
            else:
                valid = frozenset(w[0] for w in twos if w[1] == letter)
                card_id = f"2s-{letter}-left"
                prompt_text = f"?{letter}"
                valid_words = [(c + letter, defs.get(c + letter, "")) for c in valid]
            cards.append(ExtensionCard(card_id, prompt_text, valid, valid_words,
                                       ext_lookup, top20k, top50k))
    return cards


def _build_2s_plus(nwl: frozenset[str], defs: dict[str, str],
                   ext_lookup: AcExtensionLookup,
                   top20k: frozenset[str] = frozenset(),
                   top50k: frozenset[str] = frozenset()) -> list[ExtensionCard]:
    """Extension cards for NWL 2-letter words: which letters extend each to a 3-letter word."""
    twos   = sorted((w for w in nwl if len(w) == 2), key=_word_tile_prob_key)
    threes = {w for w in nwl if len(w) == 3}

    cards = []
    for word in twos:
        for direction in ("right", "left"):
            if direction == "right":
                valid = frozenset(c for c in _LETTERS if word + c in threes)
                card_id = f"2s+-{word}-right"
                prompt_text = f"{word}?"
                valid_words = [(word + c, defs.get(word + c, "")) for c in valid]
            else:
                valid = frozenset(c for c in _LETTERS if c + word in threes)
                card_id = f"2s+-{word}-left"
                prompt_text = f"?{word}"
                valid_words = [(c + word, defs.get(c + word, "")) for c in valid]
            cards.append(ExtensionCard(card_id, prompt_text, valid, valid_words,
                                       ext_lookup, top20k, top50k))
    return cards


# ── Atomic cloze builder (shared by scrabble-2s+ now, scrabble-2s later) ───────

def _commonness_rank(word: str, top20k: frozenset[str], top50k: frozenset[str]) -> int:
    w = word.lower()
    return 0 if w in top20k else 1 if w in top50k else 2


def _order_letters_by_commonness(valid_words, direction, top20k, top50k):
    """Extension letters ordered by how common the resulting word is."""
    from wordfreq import word_frequency
    def ext_letter(word):
        return word[-1] if direction == "right" else word[0]
    ordered = sorted(
        valid_words,
        key=lambda wd: (_commonness_rank(wd[0], top20k, top50k),
                        -word_frequency(wd[0].lower(), 'en'), wd[0]),
    )
    return [ext_letter(w) for w, _ in ordered]


def _cloze_cards_for_pattern(prefix, base_word, direction, valid_letters,
                             defs, ext_lookup, top20k, top50k):
    """Expand one (base_word, direction) pattern into atomic cloze cards.

    One card per valid extension letter (clustered, ordered by resulting-word
    commonness), or a single `-none` card when the pattern has no extension."""
    def make_word(c):
        return base_word + c if direction == "right" else c + base_word

    valid_words = [(make_word(c), defs.get(make_word(c), "")) for c in sorted(valid_letters)]

    if not valid_letters:
        cid = f"{prefix}-{base_word}-{direction}-none"
        return [AcClozeExtensionCard(cid, base_word, direction, None,
                                     frozenset(), [], ext_lookup, top20k, top50k)]

    cards = []
    for c in _order_letters_by_commonness(valid_words, direction, top20k, top50k):
        cid = f"{prefix}-{base_word}-{direction}-{c}"
        cards.append(AcClozeExtensionCard(cid, base_word, direction, c, valid_letters,
                                          valid_words, ext_lookup, top20k, top50k))
    return cards


def _build_2s_plus_cloze(nwl, defs, ext_lookup, top20k=frozenset(), top50k=frozenset()):
    """Atomic cloze cards: each valid 3-letter extension of a 2-letter word is one card.

    Cards are clustered per (base word, direction) pattern; patterns ordered by
    tile probability, extensions within a pattern by resulting-word commonness."""
    twos   = sorted((w for w in nwl if len(w) == 2), key=_word_tile_prob_key)
    threes = {w for w in nwl if len(w) == 3}
    cards = []
    for word in twos:
        for direction in ("right", "left"):
            if direction == "right":
                valid = frozenset(c for c in _LETTERS if word + c in threes)
            else:
                valid = frozenset(c for c in _LETTERS if c + word in threes)
            cards.extend(_cloze_cards_for_pattern("2s+", word, direction, valid,
                                                  defs, ext_lookup, top20k, top50k))
    return cards


def _vowel_family(word, valid_bases):
    """The base plus every valid base formed by swapping one of its vowels.

    `valid_bases` is the set of legal base "words" (bigrams for 2s+, single
    letters for 2s). A consonant-only base (e.g. "L", "TH") has no vowel to
    swap, so its family is just itself."""
    family = {word}
    for i, ch in enumerate(word):
        if ch in _VOWELS:
            for v in _VOWELS:
                cand = word[:i] + v + word[i + 1:]
                if cand in valid_bases:
                    family.add(cand)
    return family


def _segment_is_relevant(family, direction, group, results):
    """True if the base OR a vowel-cousin has a valid extension in this segment.
    `results` is the set of legal extended words (threes for 2s+, twos for 2s)."""
    for f in family:
        for c in group:
            if (f + c if direction == "right" else c + f) in results:
                return True
    return False


def _batched_pattern_cards(base_word, direction, valid, all_words, results,
                           valid_bases, eligible, prefix,
                           ext_lookup, top20k, top50k):
    """The card(s) one (base, direction) pattern contributes to a batched set.

    Not `eligible`, or ≤4 extensions → a single legacy "type them all" card. An
    eligible 5+ pattern splits into per-segment cloze-by-segment cards, one per
    alphabet segment the base OR a vowel-cousin extends into (so meaningful empty
    segments are still confirmed without showing every segment on every base)."""
    if not eligible or len(valid) <= 4:
        cid = f"{prefix}-{base_word}-{direction}"
        prompt_text = f"{base_word}?" if direction == "right" else f"?{base_word}"
        return [ExtensionCard(cid, prompt_text, valid, all_words,
                              ext_lookup, top20k, top50k)]
    family = _vowel_family(base_word, valid_bases)
    cards = []
    for group in _ALPHABET_GROUPS:
        if not _segment_is_relevant(family, direction, group, results):
            continue
        subset_valid = frozenset(c for c in valid if c in group)
        cid = f"{prefix}-{base_word}-{direction}-{group}"
        cards.append(AcBatchedExtensionCard(cid, base_word, direction, group,
                                            subset_valid, valid, all_words,
                                            ext_lookup, top20k, top50k))
    return cards


def _playability_order_key(playability):
    """Drip-feed order for a 2s+ root: most-played 2-letter word first (real
    scrabble play frequency, see load_two_letter_playability), tile probability
    as the tiebreak and as the fallback for roots absent from the play data.

    NOTE: the play-frequency data is Collins-derived (no clean NWL 2-letter table
    is published) — see cache/two_letter_playability.md before swapping it out."""
    def key(word):
        return (-playability.get(word, 0), _word_tile_prob_key(word))
    return key


def _build_2s_plus_batched(nwl, defs, ext_lookup, top20k=frozenset(), top50k=frozenset()):
    """Hybrid 3s set. Every bigram is eligible for batching: ≤4 extensions stay a
    single legacy card, 5+ split into relevant per-segment cards. Reveal order is
    clustered per root (both directions + all its segment cards together); roots
    are drip-fed most-played-first by real scrabble play frequency."""
    twos_set = frozenset(w for w in nwl if len(w) == 2)
    twos = sorted(twos_set, key=_playability_order_key(load_two_letter_playability()))
    threes = {w for w in nwl if len(w) == 3}
    cards = []
    for word in twos:
        for direction in ("right", "left"):
            if direction == "right":
                valid = frozenset(c for c in _LETTERS if word + c in threes)
                make = lambda c, w=word: w + c
            else:
                valid = frozenset(c for c in _LETTERS if c + word in threes)
                make = lambda c, w=word: c + w
            all_words = [(make(c), defs.get(make(c), "")) for c in sorted(valid)]
            cards.extend(_batched_pattern_cards(
                word, direction, valid, all_words, threes, twos_set,
                eligible=True, prefix="2s+b",
                ext_lookup=ext_lookup, top20k=top20k, top50k=top50k))
    return cards


def _build_2s_batched(nwl, defs, ext_lookup, top20k=frozenset(), top50k=frozenset()):
    """Hybrid 2s set. Only vowel bases (A/E/I/O/U) are eligible for batching: a
    consonant's 2-letter extensions cluster almost entirely in the vowel segment,
    so splitting them into segments is pure noise. Consonant bases (and any
    ≤4-extension vowel base) therefore stay a single legacy card; vowel bases
    with 5+ extensions split into relevant per-segment cards. Reveal order
    matches the legacy 2s set (consonants first, then vowels)."""
    twos = {w for w in nwl if len(w) == 2}
    valid_bases = frozenset(_LETTERS)   # every single letter is a legal base
    cards = []
    for letter in sorted(_LETTERS, key=_letter_order_key):
        for direction in ("right", "left"):
            if direction == "right":
                valid = frozenset(w[1] for w in twos if w[0] == letter)
                make = lambda c, L=letter: L + c
            else:
                valid = frozenset(w[0] for w in twos if w[1] == letter)
                make = lambda c, L=letter: c + L
            all_words = [(make(c), defs.get(make(c), "")) for c in sorted(valid)]
            cards.extend(_batched_pattern_cards(
                letter, direction, valid, all_words, twos, valid_bases,
                eligible=(letter in _VOWELS), prefix="2s",
                ext_lookup=ext_lookup, top20k=top20k, top50k=top50k))
    return cards


class AcExtensionCardSet(CardSet):
    rating_time_threshold_s = 7
    _top20k: frozenset[str] | None = None
    _top50k: frozenset[str] | None = None

    @classmethod
    def _get_top20k(cls) -> frozenset[str]:
        if cls._top20k is None:
            from wordfreq import top_n_list
            cls._top20k = frozenset(top_n_list('en', 20000))
        return cls._top20k

    @classmethod
    def _get_top50k(cls) -> frozenset[str]:
        if cls._top50k is None:
            from wordfreq import top_n_list
            cls._top50k = frozenset(top_n_list('en', 50000))
        return cls._top50k

    def __init__(self, set_id: str, name: str, cards: list[ExtensionCard]):
        super().__init__(set_id, name, cards)
        self.new_card_order = [c.id for c in cards]

    @classmethod
    def scrabble_2s(cls) -> "AcExtensionCardSet":
        nwl = load_nwl_set()
        defs = load_nwl_defs()
        ext_lookup = AcExtensionLookup(nwl, defs)
        top20k = cls._get_top20k()
        top50k = cls._get_top50k()
        return cls("scrabble-2s-legacy", "Scrabble 2-Letter Extensions — legacy",
                   _build_2s(nwl, defs, ext_lookup, top20k, top50k))

    @classmethod
    def scrabble_2s_plus(cls) -> "AcExtensionCardSet":
        nwl = load_nwl_set()
        defs = load_nwl_defs()
        ext_lookup = AcExtensionLookup(nwl, defs)
        top20k = cls._get_top20k()
        top50k = cls._get_top50k()
        return cls("scrabble-2s+legacy", "Scrabble Useful 3s (extend 2s) — legacy",
                   _build_2s_plus(nwl, defs, ext_lookup, top20k, top50k))


class AcClozeExtensionCardSet(CardSet):
    """Atomic cloze extension set (scrabble-2s+-cloze) — one card per extension."""
    rating_time_threshold_s = 5

    def __init__(self, set_id: str, name: str, cards: list):
        super().__init__(set_id, name, cards)
        self.new_card_order = [c.id for c in cards]

    @classmethod
    def scrabble_2s_plus(cls) -> "AcClozeExtensionCardSet":
        nwl = load_nwl_set()
        defs = load_nwl_defs()
        ext_lookup = AcExtensionLookup(nwl, defs)
        top20k = AcExtensionCardSet._get_top20k()
        top50k = AcExtensionCardSet._get_top50k()
        return cls("scrabble-2s+-cloze", "Scrabble Useful 3s (atomic cloze)",
                   _build_2s_plus_cloze(nwl, defs, ext_lookup, top20k, top50k))


class AcBatchedExtensionCardSet(CardSet):
    """Batched-by-segment extension sets — the canonical scrabble-2s / scrabble-2s+.

    Each pattern either stays a single legacy "type them all" card (≤4
    extensions, or an ineligible base) or splits into per-alphabet-segment
    cloze-by-segment cards. 2s+ batches every bigram; 2s batches only vowel
    bases (see _build_2s_batched)."""
    rating_time_threshold_s = 7

    def __init__(self, set_id: str, name: str, cards: list):
        super().__init__(set_id, name, cards)
        self.new_card_order = [c.id for c in cards]

    @classmethod
    def scrabble_2s_plus(cls) -> "AcBatchedExtensionCardSet":
        nwl = load_nwl_set()
        defs = load_nwl_defs()
        ext_lookup = AcExtensionLookup(nwl, defs)
        top20k = AcExtensionCardSet._get_top20k()
        top50k = AcExtensionCardSet._get_top50k()
        return cls("scrabble-2s+", "Scrabble Useful 3s",
                   _build_2s_plus_batched(nwl, defs, ext_lookup, top20k, top50k))

    @classmethod
    def scrabble_2s(cls) -> "AcBatchedExtensionCardSet":
        nwl = load_nwl_set()
        defs = load_nwl_defs()
        ext_lookup = AcExtensionLookup(nwl, defs)
        top20k = AcExtensionCardSet._get_top20k()
        top50k = AcExtensionCardSet._get_top50k()
        return cls("scrabble-2s", "Scrabble 2-Letter Extensions",
                   _build_2s_batched(nwl, defs, ext_lookup, top20k, top50k))
