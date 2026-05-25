"""Extension lookup for NWL words.

Provides per-word extension symbols for display in scrabble card answers:
  +  at least one valid 1-letter NWL extension on that side
  -  at least one valid 2-7 letter extension on that side (5+ letter words only)
  ~  2-7 letter extensions on both sides, neither has a 1-letter extension

Symbol priority: + overrides -, ~ replaces -- when both sides qualify for -.
"""

import os
import string

_WORDS_CACHE = os.path.join(os.path.dirname(__file__), "cache", "nwl_words.txt")
_DEFS_CACHE  = os.path.join(os.path.dirname(__file__), "cache", "nwl_defs.txt")
_LETTERS = string.ascii_uppercase


def load_nwl_set() -> frozenset[str]:
    """Load all NWL words from the words cache. Returns empty set if cache missing."""
    if not os.path.exists(_WORDS_CACHE):
        return frozenset()
    with open(_WORDS_CACHE) as f:
        return frozenset(line.strip() for line in f if line.strip())


def load_nwl_defs() -> dict[str, str]:
    """Load word→definition from the defs cache. Returns empty dict if cache missing."""
    if not os.path.exists(_DEFS_CACHE):
        return {}
    defs: dict[str, str] = {}
    with open(_DEFS_CACHE) as f:
        for line in f:
            line = line.rstrip("\n")
            tab = line.find("\t")
            if tab >= 0:
                defs[line[:tab]] = line[tab + 1:]
    return defs


class AcExtensionLookup:
    """Precomputed single-letter and multi-letter extension data for all NWL words."""

    def __init__(self, nwl: frozenset[str], defs: dict[str, str] | None = None):
        self._nwl  = nwl
        self._defs = defs or {}
        left_multi: set[str] = set()
        right_multi: set[str] = set()

        for word in nwl:
            n = len(word)
            # suffix s of `word` where extension_len = n - len(s) ∈ [2, 7]
            # → suffix_len ∈ [max(1, n-7), n-2]
            for suffix_len in range(max(1, n - 7), n - 1):
                left_multi.add(word[n - suffix_len:])
            # prefix p of `word` where extension_len = n - len(p) ∈ [2, 7]
            for prefix_len in range(max(1, n - 7), n - 1):
                right_multi.add(word[:prefix_len])

        self._left_multi = frozenset(left_multi)
        self._right_multi = frozenset(right_multi)

    def symbols(self, word: str) -> tuple[str, str]:
        """Return (left_sym, right_sym) for the extension annotation of `word`.

        left_sym/right_sym each ∈ {"", "+", "-", "~"}.
        """
        left_single = any(c + word in self._nwl for c in _LETTERS)
        right_single = any(word + c in self._nwl for c in _LETTERS)
        left_sym = "+" if left_single else ""
        right_sym = "+" if right_single else ""

        if len(word) >= 5:
            if not left_sym and word in self._left_multi:
                left_sym = "-"
            if not right_sym and word in self._right_multi:
                right_sym = "-"
            if left_sym == "-" and right_sym == "-":
                left_sym = right_sym = "~"

        return left_sym, right_sym

    def extensions_for(self, word: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """Return (left_exts, right_exts) as [(ext_word, definition), ...] sorted by length."""
        lefts: list[tuple[str, str]] = []
        rights: list[tuple[str, str]] = []

        for c in _LETTERS:
            ext = c + word
            if ext in self._nwl:
                lefts.append((ext, self._defs.get(ext, "")))
            ext = word + c
            if ext in self._nwl:
                rights.append((ext, self._defs.get(ext, "")))

        if len(word) >= 5:
            n = len(word)
            left_seen  = {w for w, _ in lefts}
            right_seen = {w for w, _ in rights}
            for nwl_word in self._nwl:
                m = len(nwl_word)
                if not (2 <= m - n <= 7):
                    continue
                if nwl_word.endswith(word) and nwl_word not in left_seen:
                    lefts.append((nwl_word, self._defs.get(nwl_word, "")))
                    left_seen.add(nwl_word)
                if nwl_word.startswith(word) and nwl_word not in right_seen:
                    rights.append((nwl_word, self._defs.get(nwl_word, "")))
                    right_seen.add(nwl_word)

        lefts.sort(key=lambda x: len(x[0]))
        rights.sort(key=lambda x: len(x[0]))
        return lefts, rights
