"""Card sets for NWL single-letter extension drills (scrabble-2s, scrabble-2s+)."""

import string

from cards.cardSet import CardSet
from scrabble.ExtensionCard import ExtensionCard
from scrabble.extensions import load_nwl_set, load_nwl_defs, AcExtensionLookup

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
              ext_lookup: AcExtensionLookup) -> list[ExtensionCard]:
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
            cards.append(ExtensionCard(card_id, prompt_text, valid, valid_words, ext_lookup))
    return cards


def _build_2s_plus(nwl: frozenset[str], defs: dict[str, str],
                   ext_lookup: AcExtensionLookup) -> list[ExtensionCard]:
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
            cards.append(ExtensionCard(card_id, prompt_text, valid, valid_words, ext_lookup))
    return cards


class AcExtensionCardSet(CardSet):
    rating_time_threshold_s = 7

    def __init__(self, set_id: str, name: str, cards: list[ExtensionCard]):
        super().__init__(set_id, name, cards)
        self.new_card_order = [c.id for c in cards]

    @classmethod
    def scrabble_2s(cls) -> "AcExtensionCardSet":
        nwl = load_nwl_set()
        defs = load_nwl_defs()
        ext_lookup = AcExtensionLookup(nwl, defs)
        return cls("scrabble-2s", "Scrabble 2-Letter Extensions", _build_2s(nwl, defs, ext_lookup))

    @classmethod
    def scrabble_2s_plus(cls) -> "AcExtensionCardSet":
        nwl = load_nwl_set()
        defs = load_nwl_defs()
        ext_lookup = AcExtensionLookup(nwl, defs)
        return cls("scrabble-2s+", "Scrabble Useful 3s (extend 2s)", _build_2s_plus(nwl, defs, ext_lookup))
