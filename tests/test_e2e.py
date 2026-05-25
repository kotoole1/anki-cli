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
    run_cli(["scrabble7", "--memory-dir", str(tmp_path)], ["ZZZZZZZ", ""])
    d = json.loads((tmp_path / "scrabble7.json").read_text())
    card = next(iter(d["cards"].values()))
    assert card["reviews"][0]["rating"] == 1  # Again


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


# ── scrabble-2s ───────────────────────────────────────────────────────────────

def test_2s_shows_prompt(tmp_path):
    clean, _, err, rc = run_cli(["scrabble-2s", "--memory-dir", str(tmp_path)], reveal_n(1))
    assert rc == 0
    assert err == ""
    assert "?" in clean


def test_2s_creates_memory_file(tmp_path):
    run_cli(["scrabble-2s", "--memory-dir", str(tmp_path)], reveal_n(1))
    mem = tmp_path / "scrabble-2s.json"
    assert mem.exists()
    d = json.loads(mem.read_text())
    assert len(d["cards"]) >= 1


def test_2s_wrong_answer_records_again(tmp_path):
    run_cli(["scrabble-2s", "--memory-dir", str(tmp_path)], ["ZZZZZZ", ""])
    d = json.loads((tmp_path / "scrabble-2s.json").read_text())
    card = next(iter(d["cards"].values()))
    assert card["reviews"][0]["rating"] == 1  # Again


def test_2s_correct_answer_for_first_card(tmp_path):
    # "A?" card — H is always a valid extending letter (AH is NWL)
    # Find first card shown and answer with its full valid set
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
    from scrabble.ExtensionCardSet import AcExtensionCardSet
    cs = AcExtensionCardSet.scrabble_2s()
    first = cs.cards[0]
    valid_str = "".join(sorted(first.getAnswer()._valid_letters))
    clean, _, err, rc = run_cli(
        ["scrabble-2s", "--memory-dir", str(tmp_path)],
        [valid_str, ""],
    )
    assert rc == 0
    assert err == ""
    assert "✔︎" in clean


def test_2s_long_session(tmp_path):
    clean, _, err, rc = run_cli(["scrabble-2s", "--memory-dir", str(tmp_path)], reveal_n(5))
    assert rc == 0
    assert err == ""
