"""Anagram card set for short (<=4 letter) NWL words built around high-value tiles.

High-value tiles are Q, Z, J, X, K, V, W — the rarest, highest-scoring letters,
so the short words that use them are the highest-leverage plays to memorize.

Cards are anagram-style (reusing ScrabbleCard): the prompt is an alphagram and
any valid NWL word that anagrams those letters is a correct answer. Learning
order surfaces the rarest-tile words (Q/J/Z/X) first, then shorter words before
longer, then more common words before rare ones.
"""

import os
from collections import defaultdict

from cards.cardSet import CardSet
from scrabble.ScrabbleCard import ScrabbleCard, ScrabbleAnswer, _tokens, _RED, _PURPLE, _RESET
from scrabble.ScrabbleCardSet import (
    _alphagram,
    _prob,
    _fetch_word_list,
    _write_words_cache,
    _WORDS_CACHE,
)
from scrabble.extensions import load_nwl_set, load_nwl_defs, AcExtensionLookup

# Words containing any of these tiles qualify for the set.
_HIGH_VALUE = frozenset("QZJXKVW")
# The rarest high-value tiles; words using these are learned before the rest.
_RAREST = frozenset("QJZX")
_MIN_LEN = 2
_MAX_LEN = 4

_GREEN = "\033[92m"


def _has(letters: str, pool: frozenset[str]) -> bool:
    return any(c in pool for c in letters)


class AcAllAnagramAnswer(ScrabbleAnswer):
    """Anagram answer that requires *every* valid word for the rack.

    Words may be separated by any combination of spaces and commas. Submission
    validity and the reject feedback for bad anagrams are inherited from
    ScrabbleAnswer (shared by all anagram sets); this subclass only changes
    correctness (all words required) and the wrong-answer feedback.
    """

    def isCorrect(self, answer: str) -> bool:
        return set(_tokens(answer)) == self._valid

    def getWrongAnswerFeedback(self, submitted: str) -> str:
        """Per-token feedback: each word you gave green if it's a valid word for
        the rack, red if it's a rack anagram that isn't a word, then the words
        you missed in purple.

        This runs only after ScrabbleAnswer.isValid has passed, so every token is
        already a rack anagram — coloring is purely word-vs-not-a-word. It applies
        even when the rack has a single valid word: submitting "SEX XES" for ESX
        must green SEX and red XES, not fall back to the single-word tile diff
        (which would treat the whole "SEX XES" string as one mis-tiled word)."""
        seen: set[str] = set()
        parts: list[str] = []
        for tok in _tokens(submitted):
            if tok in seen:
                continue
            seen.add(tok)
            color = _GREEN if tok in self._valid else _RED
            parts.append(f"{color}{tok}{_RESET}")

        line = "  ".join(parts)
        missing = self._valid - seen
        if missing:
            line += f"  {_PURPLE}+{' '.join(sorted(missing))}{_RESET}"
        return line


class AcAllAnagramCard(ScrabbleCard):
    """ScrabbleCard whose answer demands all valid anagrams of the rack."""

    def __init__(self, id, alphagram, probability, nwl_words,
                 top20k=frozenset(), ext_lookup=None, top50k=frozenset()):
        super().__init__(id, alphagram, probability, nwl_words, top20k, ext_lookup, top50k)
        self._answer = AcAllAnagramAnswer(alphagram, nwl_words, top20k, ext_lookup, top50k)


class AcHighValueCardSet(CardSet):
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

    def __init__(self):
        if not os.path.exists(_WORDS_CACHE):
            print("Building NWL words cache...")
            _write_words_cache(_fetch_word_list())

        from wordfreq import word_frequency

        nwl = load_nwl_set()
        defs = load_nwl_defs()
        top20k = self._get_top20k()
        top50k = self._get_top50k()
        ext_lookup = AcExtensionLookup(nwl, defs)

        # Group qualifying words by alphagram so anagrams share a single card.
        # The entire NWL universe is considered: every legal word of the right
        # length and tiles is included — there is no commonness filter (top20k/
        # top50k below only drive the ▶/▷/▹ display indicator, not inclusion).
        by_alpha: dict[str, list] = defaultdict(list)
        for word in nwl:
            if _MIN_LEN <= len(word) <= _MAX_LEN and _has(word, _HIGH_VALUE):
                by_alpha[_alphagram(word)].append([word, defs.get(word, "")])

        entries = []
        for alpha, words in by_alpha.items():
            commonness = max(
                (word_frequency(w.lower(), 'en') for w, _ in words), default=0.0
            )
            entries.append({
                "alphagram":  alpha,
                "prob":       _prob(alpha),
                "commonness": commonness,
                "nwl":        sorted(words),
            })

        # Learning order: rarest-tile (Q/J/Z/X) words first, then by length
        # (short before long), then most common first.
        entries.sort(key=lambda e: (
            0 if _has(e["alphagram"], _RAREST) else 1,
            len(e["alphagram"]),
            -e["commonness"],
        ))

        cards = [
            AcAllAnagramCard(
                id=e["alphagram"],
                alphagram=e["alphagram"],
                probability=e["prob"],
                nwl_words=e["nwl"],
                top20k=top20k,
                ext_lookup=ext_lookup,
                top50k=top50k,
            )
            for e in entries
        ]
        super().__init__("scrabble-hv", "Scrabble High-Value Short Words", cards)
        self.new_card_order = [e["alphagram"] for e in entries]
