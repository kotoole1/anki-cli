"""
End-to-end tests: launch the CLI as a subprocess, feed stdin, assert on stdout.

Scrabble tests require pre-built caches. If a cache is missing, the test is
skipped with a message showing the rebuild command.

Key design choices:
  - All inputs are sent upfront via communicate(); sessions end on EOFError.
  - `reveal_n(n)` sends n blank answers + n blank "next" inputs.
  - Scrabble tests that need a deterministic card use --top 1 (always AEHNORT).
"""

import os
import re
import subprocess

import pytest

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(ROOT, "anki-env", "bin", "python")
CLI    = os.path.join(ROOT, "src", "anki-cli.py")
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
        cwd=SRC,
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
    reason="scrabble7 cache missing — build with: anki-env/bin/python src/anki-cli.py scrabble7 --rebuild",
)
requires_cache_8 = pytest.mark.skipif(
    not os.path.exists(CACHE_8),
    reason="scrabble8 cache missing — build with: anki-env/bin/python src/anki-cli.py scrabble8 --rebuild",
)


# ── CLI invocation ────────────────────────────────────────────────────────────

def test_no_args_shows_controls():
    clean, _, _, rc = run_cli([], [])
    assert rc == 0
    assert "CONTROLS" in clean


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
def test_scrabble7_reveals_alphagrams():
    clean, _, err, rc = run_cli(["scrabble7"], reveal_n(3))
    assert rc == 0
    assert err == ""
    assert find_alphagram(clean, 7) is not None


@requires_cache_7
def test_scrabble7_help_during_session():
    clean, _, err, rc = run_cli(["scrabble7"], ["?", "", ""])
    assert rc == 0
    assert "CONTROLS" in clean
    assert "NWL" in clean


@requires_cache_7
def test_scrabble7_wrong_anagram_shows_red():
    # XXXXXXX can never be a valid anagram; every excess X must be red.
    _, raw, err, rc = run_cli(["scrabble7"], ["XXXXXXX", ""])
    assert rc == 0
    assert err == ""
    assert "\033[91m" in raw


@requires_cache_7
def test_scrabble7_wrong_anagram_shows_purple_for_missing():
    _, raw, err, rc = run_cli(["scrabble7"], ["XXXXXXX", ""])
    assert "\033[95m" in raw


@requires_cache_7
def test_scrabble7_correct_word():
    # --top 1 always surfaces AEHNORT (ANOTHER); first reveal discovers the word.
    clean, _, _, _ = run_cli(["scrabble7", "--top", "1"], reveal_n(1))
    word = find_revealed_word(clean)
    assert word is not None, f"No word found in output:\n{clean}"

    clean2, _, err, rc = run_cli(["scrabble7", "--top", "1"], [word, ""])
    assert rc == 0
    assert err == ""
    assert "Correct!" in clean2


@requires_cache_7
def test_scrabble7_wrong_word_no_correct():
    clean, _, err, rc = run_cli(["scrabble7", "--top", "1"], ["XXXXXXX", ""])
    assert rc == 0
    assert "Correct!" not in clean


@requires_cache_7
def test_scrabble7_blank_reveals_answer():
    clean, _, err, rc = run_cli(["scrabble7", "--top", "1"], reveal_n(1))
    assert rc == 0
    word = find_revealed_word(clean)
    assert word is not None


# ── Scrabble 7 — long session ─────────────────────────────────────────────────

@requires_cache_7
def test_scrabble7_long_session():
    clean, _, err, rc = run_cli(["scrabble7"], reveal_n(20))
    assert rc == 0
    assert err == ""
    assert len(find_all_alphagrams(clean, 7)) >= 2


@requires_cache_7
def test_scrabble7_long_session_with_answers():
    # Mix of correct word, wrong anagram, and reveals over 15 cards.
    inputs = ["ANOTHER", "", "XXXXXXX", "", "", ""] * 5
    clean, _, err, rc = run_cli(["scrabble7"], inputs)
    assert rc == 0
    assert err == ""


# ── Scrabble 8 — sessions ────────────────────────────────────────────────────

@requires_cache_8
def test_scrabble8_reveals_alphagrams():
    clean, _, err, rc = run_cli(["scrabble8"], reveal_n(3))
    assert rc == 0
    assert err == ""
    assert find_alphagram(clean, 8) is not None


@requires_cache_8
def test_scrabble8_correct_word():
    clean, _, _, _ = run_cli(["scrabble8", "--top", "1"], reveal_n(1))
    word = find_revealed_word(clean)
    assert word is not None, f"No word found in output:\n{clean}"

    clean2, _, err, rc = run_cli(["scrabble8", "--top", "1"], [word, ""])
    assert rc == 0
    assert err == ""
    assert "Correct!" in clean2


@requires_cache_8
def test_scrabble8_wrong_anagram_shows_red():
    _, raw, err, rc = run_cli(["scrabble8"], ["XXXXXXXX", ""])
    assert rc == 0
    assert "\033[91m" in raw


@requires_cache_8
def test_scrabble8_long_session():
    clean, _, err, rc = run_cli(["scrabble8"], reveal_n(20))
    assert rc == 0
    assert err == ""
    assert len(find_all_alphagrams(clean, 8)) >= 2
