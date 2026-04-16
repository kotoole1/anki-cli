import csv
import os
import urllib.request
from collections import Counter, defaultdict
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

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")


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


def _cache_path(length: int, top_n: int) -> str:
    return os.path.join(_CACHE_DIR, f"nwl_{length}_{top_n}.csv")


def _build_cache(length: int, top_n: int) -> None:
    nwl = _fetch_word_list()

    nwl_map: dict[str, list] = defaultdict(list)
    for word, defn in nwl.items():
        if len(word) == length:
            nwl_map[_alphagram(word)].append([word, defn])

    sorted_alphas = sorted(nwl_map.keys(), key=_prob, reverse=True)[:top_n]

    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_cache_path(length, top_n), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["alphagram", "prob", "word", "definition"])
        for alpha in sorted_alphas:
            p = _prob(alpha)
            for word, defn in sorted(nwl_map[alpha]):
                writer.writerow([alpha, p, word, defn])


def _load_cache(length: int, top_n: int) -> list:
    entries: dict[str, dict] = {}
    with open(_cache_path(length, top_n), newline="") as f:
        for row in csv.DictReader(f):
            alpha = row["alphagram"]
            if alpha not in entries:
                entries[alpha] = {"alphagram": alpha, "prob": float(row["prob"]), "nwl": []}
            entries[alpha]["nwl"].append([row["word"], row["definition"]])
    return list(entries.values())


class ScrabbleCardSet(CardSet):
    def __init__(self, length: int = 7, top_n: int = 500, rebuild: bool = False):
        path = _cache_path(length, top_n)

        if rebuild and os.path.exists(path):
            os.remove(path)

        if not os.path.exists(path):
            print(f"Building {length}-letter NWL bingo list (top {top_n})...")
            _build_cache(length, top_n)
            entries = _load_cache(length, top_n)
            print(f"  Cached {len(entries)} alphagrams.")
        else:
            entries = _load_cache(length, top_n)

        cards = [
            ScrabbleCard(
                id=e["alphagram"],
                alphagram=e["alphagram"],
                probability=e["prob"],
                nwl_words=e["nwl"],
            )
            for e in entries
        ]
        super().__init__(f"scrabble-{length}s", f"Scrabble {length}-Letter Bingos", cards)
