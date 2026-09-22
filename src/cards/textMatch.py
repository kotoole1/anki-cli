"""Answer matchers for typed free-text answers, shared across card sets.

Two deliberately different leniency levels live here so a set picks one rather
than re-deriving thresholds:

  * fuzzy_title_match — generous (substring, `gl*` glob, initials). For long
    titles where recalling *which* one is the whole task (oscars).
  * person_name_match — a person's full name or surname, typos forgiven:
    "even engram" and "engram" both pass for "Evan Engram", "evan" does not
    (broncos). No substring or glob shortcuts.
"""

import difflib
import re
import unicodedata

_NAME_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})
_MAX_SLIPS = 2        # typos forgiven across a whole answer …
_LONG_NAME = 8        # … against a name of at least this many letters; shorter ones get one


def _normalize_title(s: str) -> str:
    s = s.lower().strip()
    for prefix in ("the ", "a ", "an "):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s


def _initials(title: str) -> str:
    return "".join(w[0] for w in title.split() if w)


def fuzzy_title_match(answer: str, title: str) -> bool:
    a, t = _normalize_title(answer), _normalize_title(title)
    if not a:
        return False
    if a.endswith("*"):
        prefix = a[:-1]
        if len(prefix) < 2:
            return False
        return (t.startswith(prefix)
                or _initials(t).startswith(prefix)
                or _initials(title.lower()).startswith(prefix))
    if a in t or t in a:
        return True
    return difflib.SequenceMatcher(None, a, t).ratio() >= 0.75


def name_tokens(name: str) -> list[str]:
    """Lowercase words of a person's name with accents, punctuation and
    generational suffixes removed: "Marvin Mims Jr." → ["marvin", "mims"],
    "D.J. Jones" → ["dj", "jones"], "Kris Abrams-Draine" → ["kris", "abrams", "draine"]."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[-/]", " ", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return [w for w in s.split() if w not in _NAME_SUFFIXES]


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance, with an adjacent swap ("rliey") counted as one edit."""
    prev2, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            d = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if prev2 and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                d = min(d, prev2[j - 2] + 1)
            cur.append(d)
        prev2, prev = prev, cur
    return prev[-1]


def _typo_budget(name_letters: int) -> int:
    return _MAX_SLIPS if name_letters >= _LONG_NAME else 1


def person_name_match(answer: str, name: str) -> bool:
    """True when `answer` is `name` or just its surname, give or take a few slips.

    The surname is everything after the first word ("Abrams-Draine", "Surtain"
    — suffixes are already gone), which is how players are actually referred
    to. The slip budget is for the answer as a whole and is sized by what it
    is being compared with, so a bare surname gets a surname's budget. Word
    boundaries are free ("abramsdraine", "lil jordan humphrey")."""
    a, t = "".join(name_tokens(answer)), name_tokens(name)
    if not a or not t:
        return False
    targets = {"".join(t), "".join(t[1:]) or "".join(t)}
    return any(_edit_distance(a, target) <= _typo_budget(len(target)) for target in targets)
