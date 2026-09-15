"""
End-to-end tests: launch the CLI as a subprocess, feed stdin, assert on stdout.

Scrabble tests require pre-built caches. If a cache is missing, the test is
skipped with a message showing the rebuild command.

Key design choices:
  - All inputs are sent upfront via communicate(); sessions end on EOFError.
  - `reveal_n(n)` sends n blank answers + n blank "next" inputs.
  - All scrabble tests pass --memory-dir tmp_path to avoid writing to user state.
  - Scrabble correct-word tests use _first_scrabble_word() to find the first card
    deterministically (top-2000 by commonness, sorted by prob).
"""

import csv
import json
import os
import re
import string
import subprocess

import pytest

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(ROOT, ".venv", "bin", "python")
CLI    = os.path.join(ROOT, "anki-cli.py")
SRC    = os.path.join(ROOT, "src")

CACHE_7 = os.path.join(SRC, "scrabble", "cache", "nwl_7.csv")
CACHE_8 = os.path.join(SRC, "scrabble", "cache", "nwl_8.csv")

_ANSI = re.compile(r"\033(?:\[[^\x40-\x7e]*[\x40-\x7e]|\?[0-9]+[hl])")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def run_cli(args: list, inputs: list, timeout: int = 30):
    proc = subprocess.Popen(
        [PYTHON, CLI] + args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
    )
    stdin_bytes = ("\n".join(inputs) + "\n").encode()
    try:
        raw_out, raw_err = proc.communicate(input=stdin_bytes, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        pytest.fail(f"CLI timed out (args={args})")
    return strip_ansi(raw_out.decode()), raw_out.decode(), raw_err.decode(), proc.returncode


def reveal_n(n: int) -> list:
    """Blank answer + blank next, n times."""
    return ["", ""] * n


def find_alphagram(text: str, length: int) -> str | None:
    # Stripped output glues ?=help to the alphagram; match N uppercase letters
    # not immediately surrounded by other uppercase letters.
    m = re.search(rf"(?<![A-Z])([A-Z]{{{length}}})(?![A-Z])", text)
    return m.group(1) if m else None


def find_all_alphagrams(text: str, length: int) -> set:
    return set(re.findall(rf"(?<![A-Z])([A-Z]{{{length}}})(?![A-Z])", text))


def find_revealed_word(text: str) -> str | None:
    # After stripping ANSI, the answer line is ">   WORD  definition" because
    # input("> ") leaves no newline before print(answer_text).
    m = re.search(r"(?:^|>)\s+([A-Z]{2,})\s", text, re.MULTILINE)
    return m.group(1) if m else None


requires_cache_7 = pytest.mark.skipif(
    not os.path.exists(CACHE_7),
    reason="scrabble7 cache missing — run: uv run anki-cli.py scrabble7",
)
requires_cache_8 = pytest.mark.skipif(
    not os.path.exists(CACHE_8),
    reason="scrabble8 cache missing — run: uv run anki-cli.py scrabble8",
)


def _first_scrabble_word(cache_path: str, top_n: int = 1000, common_filter: bool = True) -> str:
    """Return the first word (alphabetically) from the highest-prob card in the set.

    common_filter=True: filter to alphagrams with at least one top-20k word, sort by prob.
    common_filter=False: all alphagrams sorted by prob (no commonness filter).
    """
    entries: dict[str, dict] = {}
    with open(cache_path, newline="") as f:
        for row in csv.DictReader(f):
            alpha = row["alphagram"]
            if alpha not in entries:
                entries[alpha] = {"prob": float(row["prob"]), "commonness": float(row["commonness"]), "words": []}
            entries[alpha]["words"].append(row["word"])

    if common_filter:
        from wordfreq import top_n_list
        top20k = set(top_n_list('en', 20000))
        pool = [e for e in entries.values() if any(w.lower() in top20k for w in e["words"])]
    else:
        pool = list(entries.values())

    pool.sort(key=lambda e: e["prob"], reverse=True)
    return sorted(pool[:top_n][0]["words"])[0]


def _first_scrabble_nonword(cache_path: str, top_n: int = 1000, common_filter: bool = True) -> str:
    """An anagram of the highest-prob card's rack that is NOT a valid word.

    This is a *valid* submission (right tiles) that should still score as a wrong
    answer — distinct from a non-anagram, which is rejected without scoring.
    """
    import itertools

    entries: dict[str, dict] = {}
    with open(cache_path, newline="") as f:
        for row in csv.DictReader(f):
            alpha = row["alphagram"]
            if alpha not in entries:
                entries[alpha] = {"alpha": alpha, "prob": float(row["prob"]),
                                  "commonness": float(row["commonness"]), "words": []}
            entries[alpha]["words"].append(row["word"])

    if common_filter:
        from wordfreq import top_n_list
        top20k = set(top_n_list('en', 20000))
        pool = [e for e in entries.values() if any(w.lower() in top20k for w in e["words"])]
    else:
        pool = list(entries.values())

    pool.sort(key=lambda e: e["prob"], reverse=True)
    first = pool[:top_n][0]
    valid = {w.upper() for w in first["words"]}
    for perm in itertools.permutations(first["alpha"]):
        cand = "".join(perm)
        if cand not in valid:
            return cand
    return first["alpha"]  # unreachable: a rack has far fewer words than permutations


# ── CLI invocation ────────────────────────────────────────────────────────────

def test_no_args_shows_usage_with_example():
    # stdin is a pipe (not a TTY), so the picker falls back to usage text.
    clean, _, _, rc = run_cli([], [])
    assert rc == 0
    assert "uv run anki-cli.py scrabble7" in clean


def test_unknown_cardset_exits_cleanly():
    clean, _, _, rc = run_cli(["foobar"], [])
    assert rc == 0
    assert "unknown card set" in clean


# ── Squares — short sessions ──────────────────────────────────────────────────

def test_squares_reveals_cards():
    clean, _, err, rc = run_cli(["squares"], reveal_n(3))
    assert rc == 0
    assert err == ""
    assert "²" in clean or "√" in clean


def test_squares_wrong_answer_no_crash():
    clean, _, err, rc = run_cli(["squares"], ["notanumber", ""])
    assert rc == 0
    assert err == ""


def test_squares_help_during_session():
    clean, _, err, rc = run_cli(["squares"], ["?", "", ""])
    assert rc == 0
    assert "CONTROLS" in clean
    # The scrabble symbol/tab legend is scrabble-only — squares must not show it.
    assert "▶" not in clean
    assert "tab" not in clean


# ── Squares — long session ────────────────────────────────────────────────────

def test_squares_long_session():
    clean, _, err, rc = run_cli(["squares"], reveal_n(20))
    assert rc == 0
    assert err == ""
    assert len(re.findall(r"[²√]", clean)) >= 20


# ── Scrabble 7 — short sessions ──────────────────────────────────────────────

@requires_cache_7
def test_scrabble7_reveals_alphagrams(tmp_path):
    clean, _, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], reveal_n(3))
    assert rc == 0
    assert err == ""
    assert find_alphagram(clean, 7) is not None


@requires_cache_7
def test_scrabble7_help_during_session(tmp_path):
    clean, _, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], ["?", "", ""])
    assert rc == 0
    assert "CONTROLS" in clean
    assert "NWL" in clean
    # Every scrabble set documents the shared symbol legend and tab shortcut.
    assert "SYMBOLS" in clean
    assert "▶" in clean
    assert "▹" in clean  # three-tier commonness legend
    assert "tab" in clean


@requires_cache_7
def test_scrabble7_wrong_anagram_shows_red(tmp_path):
    # XXXXXXX can never be a valid anagram; every excess X must be red.
    _, raw, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], ["XXXXXXX", ""])
    assert rc == 0
    assert err == ""
    assert "\033[91m" in raw


@requires_cache_7
def test_scrabble7_wrong_anagram_shows_purple_for_missing(tmp_path):
    _, raw, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], ["XXXXXXX", ""])
    assert "\033[95m" in raw


@requires_cache_7
def test_scrabble7_correct_word(tmp_path):
    word = _first_scrabble_word(CACHE_7, top_n=1000, common_filter=True)
    clean, _, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], [word, ""])
    assert rc == 0
    assert err == ""
    assert "✔︎" in clean


@requires_cache_7
def test_scrabble7_wrong_word_shows_again(tmp_path):
    clean, _, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], ["XXXXXXX", ""])
    assert rc == 0
    assert "✔︎" not in clean


@requires_cache_7
def test_scrabble7_blank_reveals_answer(tmp_path):
    clean, _, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], reveal_n(1))
    assert rc == 0
    word = find_revealed_word(clean)
    assert word is not None


@requires_cache_7
def test_scrabble7_creates_memory_file(tmp_path):
    run_cli(["scrabble7", "--memory-dir", str(tmp_path)], reveal_n(1))
    mem = tmp_path / "scrabble7.json"
    assert mem.exists()
    d = json.loads(mem.read_text())
    assert len(d["cards"]) >= 1


@requires_cache_7
def test_scrabble7_second_run_loads_state(tmp_path):
    run_cli(["scrabble7", "--memory-dir", str(tmp_path)], reveal_n(2))
    run_cli(["scrabble7", "--memory-dir", str(tmp_path)], reveal_n(2))
    d = json.loads((tmp_path / "scrabble7.json").read_text())
    assert len(d["cards"]) >= 2


@requires_cache_7
def test_scrabble7_wrong_answer_records_again(tmp_path):
    # A valid anagram of the rack that isn't a word is a real wrong answer → Again.
    wrong = _first_scrabble_nonword(CACHE_7, top_n=1000, common_filter=True)
    run_cli(["scrabble7", "--memory-dir", str(tmp_path)], [wrong, ""])
    d = json.loads((tmp_path / "scrabble7.json").read_text())
    card = next(iter(d["cards"].values()))
    assert card["reviews"][0]["rating"] == 1  # Again


@requires_cache_7
def test_scrabble7_non_anagram_is_rejected_not_recorded(tmp_path):
    # A non-anagram (wrong tiles) is rejected like pre-submission typing: it shows
    # feedback and re-prompts but records no review. The following blank (idk) is
    # what actually scores the card, so exactly one review should be recorded.
    run_cli(["scrabble7", "--memory-dir", str(tmp_path)], ["XXXXXXX", "", ""])
    d = json.loads((tmp_path / "scrabble7.json").read_text())
    card = next(iter(d["cards"].values()))
    assert len(card["reviews"]) == 1
    assert card["reviews"][0]["rating"] == 1  # Again (the blank idk, not the rejection)


@requires_cache_7
def test_scrabble7_1k_creates_separate_memory_file(tmp_path):
    run_cli(["scrabble7-1k", "--memory-dir", str(tmp_path)], reveal_n(1))
    assert (tmp_path / "scrabble7-1k.json").exists()
    assert not (tmp_path / "scrabble7.json").exists()  # 1k-prob and 1k-common use separate files


# ── Scrabble 7 — long session ─────────────────────────────────────────────────

@requires_cache_7
def test_scrabble7_long_session(tmp_path):
    clean, _, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], reveal_n(20))
    assert rc == 0
    assert err == ""
    assert len(find_all_alphagrams(clean, 7)) >= 2


@requires_cache_7
def test_scrabble7_long_session_with_answers(tmp_path):
    # Mix of correct word, wrong anagram, and reveals over 15 cards.
    inputs = ["ANOTHER", "", "XXXXXXX", "", "", ""] * 5
    clean, _, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], inputs)
    assert rc == 0
    assert err == ""


# ── Scrabble 8 — sessions ────────────────────────────────────────────────────

@requires_cache_8
def test_scrabble8_reveals_alphagrams(tmp_path):
    clean, _, err, rc = run_cli(["scrabble8", "--memory-dir", str(tmp_path)], reveal_n(3))
    assert rc == 0
    assert err == ""
    assert find_alphagram(clean, 8) is not None


@requires_cache_8
def test_scrabble8_correct_word(tmp_path):
    word = _first_scrabble_word(CACHE_8, top_n=1000, common_filter=True)
    clean, _, err, rc = run_cli(["scrabble8", "--memory-dir", str(tmp_path)], [word, ""])
    assert rc == 0
    assert err == ""
    assert "✔︎" in clean


@requires_cache_8
def test_scrabble8_wrong_anagram_shows_red(tmp_path):
    _, raw, err, rc = run_cli(["scrabble8", "--memory-dir", str(tmp_path)], ["XXXXXXXX", ""])
    assert rc == 0
    assert "\033[91m" in raw


@requires_cache_8
def test_scrabble8_long_session(tmp_path):
    clean, _, err, rc = run_cli(["scrabble8", "--memory-dir", str(tmp_path)], reveal_n(20))
    assert rc == 0
    assert err == ""
    assert len(find_all_alphagrams(clean, 8)) >= 2


# ── Scrabble — rack probability display ──────────────────────────────────────

@requires_cache_7
def test_scrabble7_shows_rack_probability(tmp_path):
    # The rating bar should show a per-million rack probability (e.g. "12.3/M")
    clean, _, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], reveal_n(1))
    assert rc == 0
    assert re.search(r"\d+\.\d+/M", clean), "Expected rack probability like '12.3/M' in output"


@requires_cache_7
def test_scrabble7_1k_uses_separate_memory_and_any_word(tmp_path):
    # scrabble7-1k is the prob-only set; memory file is scrabble7-1k.json
    run_cli(["scrabble7-1k", "--memory-dir", str(tmp_path)], reveal_n(1))
    assert (tmp_path / "scrabble7-1k.json").exists()
    assert not (tmp_path / "scrabble7.json").exists()


@requires_cache_7
def test_scrabble7_common_only_all_words_in_top20k(tmp_path):
    # Every word revealed in the 1k-common set should be recognized (no unknown word error)
    clean, _, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], reveal_n(5))
    assert rc == 0
    assert err == ""


# ── Scrabble — wrong answer orange/red coloring ───────────────────────────────

@requires_cache_7
def test_scrabble7_overused_alphagram_letter_shows_orange(tmp_path):
    # Take the first word of the first card and double its first letter.
    # That letter IS in the alphagram → excess should be orange.
    word = _first_scrabble_word(CACHE_7, top_n=1000, common_filter=True)
    wrong = word[0] + word  # e.g. AARENITE — extra first letter, definitely in alphagram
    _, raw, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], [wrong, ""])
    assert rc == 0
    assert "\033[38;5;208m" in raw


@requires_cache_7
def test_scrabble7_non_alphagram_letter_shows_red(tmp_path):
    # XXXXXXX has no letters in any 7-alphagram → all should be red
    _, raw, err, rc = run_cli(["scrabble7", "--memory-dir", str(tmp_path)], ["XXXXXXX", ""])
    assert rc == 0
    assert "\033[91m" in raw
    assert "\033[38;5;208m" not in raw


# ── Oscars ────────────────────────────────────────────────────────────────────

def test_oscars_reveals_year(tmp_path):
    clean, _, err, rc = run_cli(["oscars", "--memory-dir", str(tmp_path)], reveal_n(3))
    assert rc == 0
    assert err == ""
    assert re.search(r'(?<!\d)(19|20)\d{2}(?!\d)', clean)


def test_oscars_creates_memory_file(tmp_path):
    run_cli(["oscars", "--memory-dir", str(tmp_path)], reveal_n(1))
    mem = tmp_path / "oscars.json"
    assert mem.exists()
    d = json.loads(mem.read_text())
    assert len(d["cards"]) >= 1
    card = next(iter(d["cards"].values()))
    assert "reviews" in card


def test_oscars_second_run_loads_state(tmp_path):
    run_cli(["oscars", "--memory-dir", str(tmp_path)], reveal_n(2))
    run_cli(["oscars", "--memory-dir", str(tmp_path)], reveal_n(2))
    d = json.loads((tmp_path / "oscars.json").read_text())
    assert len(d["cards"]) >= 2


def test_oscars_wrong_answer_records_again(tmp_path):
    run_cli(["oscars", "--memory-dir", str(tmp_path)], ["zzzzzzz", ""])
    d = json.loads((tmp_path / "oscars.json").read_text())
    card = next(iter(d["cards"].values()))
    assert card["reviews"][0]["rating"] == 1  # Again


# ── scrabble-2s-legacy (list-style, type-all) ─────────────────────────────────

def test_2s_legacy_shows_prompt(tmp_path):
    clean, _, err, rc = run_cli(["scrabble-2s-legacy", "--memory-dir", str(tmp_path)], reveal_n(1))
    assert rc == 0
    assert err == ""
    assert "?" in clean


def test_2s_legacy_help_shows_shared_scrabble_legend(tmp_path):
    """The legacy list-style set keeps the same symbol/tab help as the anagram sets."""
    clean, _, err, rc = run_cli(["scrabble-2s-legacy", "--memory-dir", str(tmp_path)], ["?", "", ""])
    assert rc == 0
    assert "CONTROLS" in clean
    assert "SYMBOLS" in clean
    assert "▶" in clean
    assert "▹" in clean  # three-tier commonness legend
    assert "tab" in clean


def test_2s_legacy_creates_memory_file(tmp_path):
    run_cli(["scrabble-2s-legacy", "--memory-dir", str(tmp_path)], reveal_n(1))
    mem = tmp_path / "scrabble-2s-legacy.json"
    assert mem.exists()
    d = json.loads(mem.read_text())
    assert len(d["cards"]) >= 1


def test_2s_legacy_wrong_answer_records_again(tmp_path):
    run_cli(["scrabble-2s-legacy", "--memory-dir", str(tmp_path)], ["ZZZZZZ", ""])
    d = json.loads((tmp_path / "scrabble-2s-legacy.json").read_text())
    card = next(iter(d["cards"].values()))
    assert card["reviews"][0]["rating"] == 1  # Again


def test_2s_legacy_correct_answer_for_first_card(tmp_path):
    # Find first card shown and answer with its full valid set.
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
    from scrabble.ExtensionCardSet import AcExtensionCardSet
    cs = AcExtensionCardSet.scrabble_2s()
    first = cs.cards[0]
    valid_str = "".join(sorted(first.getAnswer()._valid_letters))
    clean, _, err, rc = run_cli(
        ["scrabble-2s-legacy", "--memory-dir", str(tmp_path)],
        [valid_str, ""],
    )
    assert rc == 0
    assert err == ""
    assert "✔︎" in clean


def test_2s_legacy_long_session(tmp_path):
    clean, _, err, rc = run_cli(["scrabble-2s-legacy", "--memory-dir", str(tmp_path)], reveal_n(5))
    assert rc == 0
    assert err == ""


# ── scrabble-2s (batched: only vowel bases split into segments) ────────────────

def test_2s_batched_shows_prompt(tmp_path):
    clean, _, err, rc = run_cli(["scrabble-2s", "--memory-dir", str(tmp_path)], reveal_n(1))
    assert rc == 0
    assert err == ""
    assert "?" in clean


def test_2s_batched_help_omits_tab(tmp_path):
    clean, _, err, rc = run_cli(["scrabble-2s", "--memory-dir", str(tmp_path)], ["?", "", ""])
    assert rc == 0
    assert "SYMBOLS" in clean
    assert "within the shown group" in clean
    assert "tab" not in clean               # batched sets defer the tab panel


def test_2s_batched_creates_memory_file(tmp_path):
    run_cli(["scrabble-2s", "--memory-dir", str(tmp_path)], reveal_n(1))
    assert (tmp_path / "scrabble-2s.json").exists()


def test_2s_batched_correct_first_card(tmp_path):
    import sys
    sys.path.insert(0, SRC)
    from scrabble.ExtensionCardSet import AcBatchedExtensionCardSet
    first = AcBatchedExtensionCardSet.scrabble_2s().cards[0]
    answer = "".join(sorted(first.getAnswer()._valid_letters))
    clean, _, err, rc = run_cli(["scrabble-2s", "--memory-dir", str(tmp_path)], [answer, ""])
    assert rc == 0
    assert err == ""
    assert "✔︎" in clean


# ── scrabble-2s+-cloze (atomic cloze) ─────────────────────────────────────────

def _first_cloze_card():
    import sys
    sys.path.insert(0, SRC)
    from scrabble.ExtensionCardSet import AcClozeExtensionCardSet
    return AcClozeExtensionCardSet.scrabble_2s_plus().cards[0]


def test_2s_plus_cloze_shows_prompt(tmp_path):
    clean, _, err, rc = run_cli(["scrabble-2s+-cloze", "--memory-dir", str(tmp_path)], reveal_n(1))
    assert rc == 0
    assert err == ""
    assert "?" in clean


def test_2s_plus_cloze_help_omits_tab(tmp_path):
    clean, _, err, rc = run_cli(["scrabble-2s+-cloze", "--memory-dir", str(tmp_path)], ["?", "", ""])
    assert rc == 0
    assert "SYMBOLS" in clean              # shares the commonness/extension legend
    assert "single missing extension" in clean
    assert "tab" not in clean              # the cloze set defers the tab panel


def test_2s_plus_cloze_correct_answer(tmp_path):
    card = _first_cloze_card()
    target = card.getAnswer().target_letter
    answer = "" if target is None else target
    clean, _, err, rc = run_cli(["scrabble-2s+-cloze", "--memory-dir", str(tmp_path)], [answer, ""])
    assert rc == 0
    assert err == ""
    assert "✔︎" in clean


def test_2s_plus_cloze_wrong_records_again(tmp_path):
    ans = _first_cloze_card().getAnswer()
    wrong = next(c for c in string.ascii_uppercase
                 if ans.isValid(c) and c != ans.target_letter)
    run_cli(["scrabble-2s+-cloze", "--memory-dir", str(tmp_path)], [wrong, ""])
    d = json.loads((tmp_path / "scrabble-2s+-cloze.json").read_text())
    card = next(iter(d["cards"].values()))
    assert card["reviews"][0]["rating"] == 1  # Again


def test_2s_plus_cloze_invalid_not_recorded(tmp_path):
    # A non-candidate keystroke (digits) is rejected and re-prompted, not scored;
    # the following blank idk is the only review recorded.
    run_cli(["scrabble-2s+-cloze", "--memory-dir", str(tmp_path)], ["123", "", ""])
    d = json.loads((tmp_path / "scrabble-2s+-cloze.json").read_text())
    card = next(iter(d["cards"].values()))
    assert len(card["reviews"]) == 1


# ── scrabble-2s+ (canonical, batched) ─────────────────────────────────────────

def _first_batched_card():
    import sys
    sys.path.insert(0, SRC)
    from scrabble.ExtensionCardSet import AcBatchedExtensionCardSet
    return AcBatchedExtensionCardSet.scrabble_2s_plus().cards[0]


def test_2s_plus_help_omits_tab(tmp_path):
    clean, _, err, rc = run_cli(["scrabble-2s+", "--memory-dir", str(tmp_path)], ["?", "", ""])
    assert rc == 0
    assert "SYMBOLS" in clean
    assert "within the shown group" in clean
    assert "tab" not in clean               # batched is cloze-style; tab is deferred


def test_2s_plus_prompt_shows_all_segments(tmp_path):
    # Roots drip-feed by play frequency, so the first several (QI/XI/OX…) are
    # small legacy cards; reveal through to the first batched (5+) card.
    import sys
    sys.path.insert(0, SRC)
    from scrabble.ExtensionCardSet import AcBatchedExtensionCardSet
    from scrabble.AcBatchedExtensionCard import AcBatchedExtensionCard
    cards = AcBatchedExtensionCardSet.scrabble_2s_plus().cards
    first_batched = next(i for i, c in enumerate(cards) if isinstance(c, AcBatchedExtensionCard))
    clean, _, err, rc = run_cli(["scrabble-2s+", "--memory-dir", str(tmp_path)],
                                reveal_n(first_batched + 1))
    assert rc == 0
    assert err == ""
    # Each segment shows; the active one is spaced out, so accept either form.
    assert "AEIOU" in clean or "A E I O U" in clean
    assert "JKQXZ" in clean or "J K Q X Z" in clean


def test_2s_plus_correct(tmp_path):
    card = _first_batched_card()
    answer = "".join(sorted(card.getAnswer()._valid_letters))   # "" if the subset is empty
    clean, _, err, rc = run_cli(["scrabble-2s+", "--memory-dir", str(tmp_path)], [answer, ""])
    assert rc == 0
    assert err == ""
    assert "✔︎" in clean


def test_2s_plus_creates_memory(tmp_path):
    run_cli(["scrabble-2s+", "--memory-dir", str(tmp_path)], reveal_n(1))
    assert (tmp_path / "scrabble-2s+.json").exists()


def test_2s_plus_batched_out_of_segment_rejected_not_scored(tmp_path):
    """A letter outside the shown active segment is re-prompted (custom help),
    not scored — so only the following blank is recorded."""
    import sys
    import string as _string
    sys.path.insert(0, SRC)
    from scrabble.ExtensionCardSet import AcBatchedExtensionCardSet
    from scrabble.AcBatchedExtensionCard import AcBatchedExtensionCard
    cards = AcBatchedExtensionCardSet.scrabble_2s_plus().cards
    i = next(i for i, c in enumerate(cards) if isinstance(c, AcBatchedExtensionCard))
    active = cards[i].getAnswer()._active
    outside = next(ch for ch in _string.ascii_uppercase if ch not in active)
    clean, _, err, rc = run_cli(["scrabble-2s+", "--memory-dir", str(tmp_path)],
                                reveal_n(i) + [outside, "", ""])
    assert rc == 0
    assert "Which of these letters complete" in clean       # custom help shown
    d = json.loads((tmp_path / "scrabble-2s+.json").read_text())
    assert len(d["cards"][cards[i].id]["reviews"]) == 1      # the slip wasn't scored


# ── id-rename migrations ──────────────────────────────────────────────────────

def test_migration_cloze_and_batched_swap_ids(tmp_path):
    """The cloze set vacates scrabble-2s+ for its -cloze id, and the batched set
    (formerly scrabble-2s+batched) claims the canonical scrabble-2s+ id — with
    each set's prior review history following it."""
    # legacy already present so the list-style→legacy move is a no-op
    (tmp_path / "scrabble-2s+legacy.json").write_text(
        json.dumps({"cardset_id": "scrabble-2s+legacy", "cards": {}, "total_cards": 214}))
    (tmp_path / "scrabble-2s+.json").write_text(
        json.dumps({"cardset_id": "scrabble-2s+", "cards": {"cloze-hist": {}}, "total_cards": 1224}))
    (tmp_path / "scrabble-2s+batched.json").write_text(
        json.dumps({"cardset_id": "scrabble-2s+batched", "cards": {"batched-hist": {}}, "total_cards": 900}))

    run_cli(["scrabble-2s+", "--memory-dir", str(tmp_path)], reveal_n(1))

    cloze = json.loads((tmp_path / "scrabble-2s+-cloze.json").read_text())
    assert "cloze-hist" in cloze["cards"]        # cloze history moved to its new id
    batched = json.loads((tmp_path / "scrabble-2s+.json").read_text())
    assert "batched-hist" in batched["cards"]    # batched history now under canonical id


def test_migration_2s_list_style_to_legacy(tmp_path):
    """The list-style 2s set moves aside to scrabble-2s-legacy, freeing
    scrabble-2s for the batched build."""
    (tmp_path / "scrabble-2s.json").write_text(
        json.dumps({"cardset_id": "scrabble-2s", "cards": {"old2s": {}}, "total_cards": 52}))
    run_cli(["scrabble-2s-legacy", "--memory-dir", str(tmp_path)], reveal_n(1))
    legacy = json.loads((tmp_path / "scrabble-2s-legacy.json").read_text())
    assert "old2s" in legacy["cards"]


# ── failed-card Enter lockout (needs a real tty) ──────────────────────────────

def _pty_squares():
    """Launch the squares set under a pty and return (pid, fd, read_fn).

    The lockout only exists on the raw-tty answer screen, so the pipe-based
    run_cli() harness above can't reach it. Squares has no scheduler, so these
    runs write no review state.
    """
    import pty
    import select
    import time

    pid, fd = pty.fork()
    if pid == 0:                       # child: exec'd, never returns
        os.chdir(ROOT)
        os.execv(PYTHON, [PYTHON, CLI, "squares"])

    def read_for(seconds: float) -> str:
        out, end = b"", time.time() + seconds
        while time.time() < end:
            if select.select([fd], [], [], 0.05)[0]:
                try:
                    out += os.read(fd, 65536)
                except OSError:
                    break
        return strip_ansi(out.decode(errors="replace"))

    return pid, fd, read_for


def test_failed_card_blocks_enter_then_allows_it():
    import signal
    import time

    pid, fd, read_for = _pty_squares()
    try:
        assert "= ?" in read_for(4.0)          # first question is up
        os.write(fd, b"999999\r")              # certainly wrong -> Again screen
        read_for(0.3)                          # well inside the 1s lockout

        os.write(fd, b"\r")                    # too soon: swallowed, warns in red
        assert "Enter prevented" in read_for(0.4)

        time.sleep(1.2)                        # past the 1s lockout, with margin
        os.write(fd, b"\r")                    # lockout expired: next card
        assert "= ?" in read_for(2.0)
    finally:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        os.close(fd)


def test_correct_card_does_not_block_enter():
    import signal

    pid, fd, read_for = _pty_squares()
    try:
        prompt = read_for(4.0)
        n = int(re.findall(r"(\d+)", prompt)[-1])
        answer = round(n ** 0.5) if "√" in prompt else n * n
        os.write(fd, f"{answer}\r".encode())
        read_for(0.5)

        os.write(fd, b"\r")                    # correct card: advances immediately
        out = read_for(1.0)
        assert "Enter prevented" not in out
        assert "= ?" in out
    finally:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        os.close(fd)
