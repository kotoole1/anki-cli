import csv
import os
import urllib.request
from collections import Counter
from math import comb

from cards.cardSet import CardSet
from scrabble.ScrabbleCard import ScrabbleCard

TILE_COUNTS = {
    'A': 9, 'B': 2, 'C': 2, 'D': 4, 'E': 12, 'F': 2, 'G': 3, 'H': 2,
    'I': 9, 'J': 1, 'K': 1, 'L': 4, 'M': 2, 'N': 6, 'O': 8, 'P': 2,
    'Q': 1, 'R': 6, 'S': 4, 'T': 6, 'U': 4, 'V': 2, 'W': 2, 'X': 1,
    'Y': 2, 'Z': 1, '?': 2,
}
TOTAL_TILES = 100

NWL_URL = "https://raw.githubusercontent.com/scrabblewords/scrabblewords/main/words/North-American/NWL2023.txt"

_CACHE_DIR   = os.path.join(os.path.dirname(__file__), "cache")
_WORDS_CACHE = os.path.join(_CACHE_DIR, "nwl_words.txt")


def _alphagram(word: str) -> str:
    return "".join(sorted(word.upper()))


def _prob(alpha: str) -> float:
    n = len(alpha)
    counts = Counter(alpha)
    numerator = 1
    for letter, k in counts.items():
        bag_n = TILE_COUNTS.get(letter, 0)
        if k > bag_n:
            return 0.0
        numerator *= comb(bag_n, k)
    return numerator / comb(TOTAL_TILES, n)


def _fetch_word_list() -> dict:
    print("  Downloading NWL2023...")
    with urllib.request.urlopen(NWL_URL, timeout=30) as resp:
        text = resp.read().decode("utf-8")
    words = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        word = parts[0].upper()
        defn = parts[1].strip() if len(parts) > 1 else ""
        words[word] = defn
    return words


def _cache_path(length: int) -> str:
    return os.path.join(_CACHE_DIR, f"nwl_{length}.csv")


def _write_words_cache(nwl: dict) -> None:
    from scrabble.extensions import _DEFS_CACHE
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_WORDS_CACHE, "w") as f:
        for word in nwl:
            f.write(word + "\n")
    with open(_DEFS_CACHE, "w") as f:
        for word, defn in nwl.items():
            f.write(f"{word}\t{defn}\n")


def _build_cache(length: int) -> None:
    from collections import defaultdict
    from wordfreq import word_frequency

    nwl = _fetch_word_list()

    if not os.path.exists(_WORDS_CACHE):
        _write_words_cache(nwl)

    nwl_map: dict[str, list] = defaultdict(list)
    for word, defn in nwl.items():
        if len(word) == length:
            nwl_map[_alphagram(word)].append([word, defn])

    print(f"  Computing scores for {len(nwl_map)} alphagrams...")
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_cache_path(length), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["alphagram", "prob", "commonness", "word", "definition"])
        for alpha, words in nwl_map.items():
            p = _prob(alpha)
            c = max((word_frequency(w.lower(), 'en') for w, _ in words), default=0.0)
            for word, defn in sorted(words):
                writer.writerow([alpha, p, c, word, defn])


def _read_entries(length: int) -> list:
    seen: dict[str, dict] = {}
    with open(_cache_path(length), newline="") as f:
        for row in csv.DictReader(f):
            alpha = row["alphagram"]
            if alpha not in seen:
                seen[alpha] = {
                    "alphagram": alpha,
                    "prob":       float(row["prob"]),
                    "commonness": float(row["commonness"]),
                    "nwl":        [],
                }
            seen[alpha]["nwl"].append([row["word"], row["definition"]])
    return list(seen.values())


def _load_top(length: int, top_n: int = 2000) -> list:
    entries = _read_entries(length)
    top = sorted(entries, key=lambda e: e["commonness"], reverse=True)[:top_n]
    top.sort(key=lambda e: e["prob"], reverse=True)
    return top


def _load_prob(length: int, top_n: int) -> list:
    """Top top_n alphagrams sorted by tile probability (no commonness filter)."""
    entries = _read_entries(length)
    entries.sort(key=lambda e: e["prob"], reverse=True)
    return entries[:top_n]


def _load_common(length: int, top20k: frozenset[str], top_n: int) -> list:
    """Top top_n alphagrams (by probability) that have at least one word in top20k."""
    entries = _read_entries(length)
    entries = [e for e in entries if any(w.lower() in top20k for w, _ in e["nwl"])]
    entries.sort(key=lambda e: e["prob"], reverse=True)
    return entries[:top_n]


class ScrabbleCardSet(CardSet):
    rating_time_threshold_s = 7
    _top20k: frozenset[str] | None = None
    _top50k: frozenset[str] | None = None
    _ext_lookup = None

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

    @classmethod
    def _get_ext_lookup(cls):
        if cls._ext_lookup is None:
            from scrabble.extensions import load_nwl_set, load_nwl_defs, AcExtensionLookup
            nwl = load_nwl_set()
            if nwl:
                defs = load_nwl_defs()
                cls._ext_lookup = AcExtensionLookup(nwl, defs)
        return cls._ext_lookup

    def __init__(self, length: int = 7, top_n: int = 2000, common_filter: bool = False):
        path = _cache_path(length)
        if not os.path.exists(path):
            print(f"Building {length}-letter NWL cache (all alphagrams)...")
            _build_cache(length)
        elif not os.path.exists(_WORDS_CACHE):
            print("Building NWL words cache for extension lookup...")
            nwl = _fetch_word_list()
            _write_words_cache(nwl)

        top20k = self._get_top20k()
        top50k = self._get_top50k()
        ext_lookup = self._get_ext_lookup()

        if common_filter:
            entries = _load_common(length, top20k, top_n)
            card_id = f"scrabble{length}"
            title = f"Scrabble {length}-Letter Bingos ({top_n // 1000}k common)"
        elif top_n < 2000:
            entries = _load_prob(length, top_n)
            card_id = f"scrabble{length}-{top_n // 1000}k"
            title = f"Scrabble {length}-Letter Bingos ({top_n // 1000}k)"
        else:
            entries = _load_top(length, top_n)
            card_id = f"scrabble{length}-2k"
            title = f"Scrabble {length}-Letter Bingos (2k)"

        cards = [
            ScrabbleCard(
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
        super().__init__(card_id, title, cards)
        self.new_card_order = [e["alphagram"] for e in entries]
