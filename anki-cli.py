import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import json
import re
import subprocess
import shutil
import argparse
import time
import tty
import termios

from fsrs import Rating

from cards.cardSet import CardSet

_CONTROLS_HELP = """\
CONTROLS
  <answer>      Submit
  <enter>       Unknown / reveal
  ?             This help
  ctrl-c        Quit
"""

# Shared by every scrabble set: all of them annotate answer words with the
# ▶/▷ commonness indicator and the +#-~ extension symbols. Most also support the
# tab/ctrl-o extension panel (the cloze set does not). Kept out of _CONTROLS_HELP
# because these mean nothing for the non-scrabble sets (oscars, squares).
_SCRABBLE_HELP = """\
SYMBOLS (beside each answer word)
  ▶ ▷ ▹    common / less common / rare word (top 20k / 50k / beyond)
  +        one 1-letter extension on that side
  #        several 1-letter extensions on that side
  -        a 2-7 letter extension on that side (5+ letter words)
  ~        2-7 letter extensions on both sides, no 1-letter ones
"""

# tab/ctrl-o panel — every scrabble set but the cloze set, which already lists
# every extension on screen.
_TAB_HELP = """\
  tab      (or ctrl-o) reveal the full extension list for the words on screen
"""

# Menu/help table is sized for an 80-column terminal. Names fit _NAME_W and
# descriptions fit _DESC_W (both ellipsized past those lengths); the stats that
# follow start at a fixed column so the percentages line up, then run free and
# are clipped at the right edge rather than wrapping. Keep descriptions <= _DESC_W.
_NAME_W = 12
_DESC_W = 30

_CARDSET_OPTIONS = [
    ("oscars",        "Oscar Best Picture winners"),
    ("scrabble7",     "7-letter bingos (1k, common)"),
    ("scrabble7-1k",  "7-letter bingos (1k, any word)"),
    ("scrabble8",     "8-letter bingos (1k, common)"),
    ("scrabble8-1k",  "8-letter bingos (1k, any word)"),
    ("scrabble-2s",   "2-letter word extensions"),
    ("scrabble-2s-legacy", "legacy: type all at once"),
    ("scrabble-2s+",  "3-letter extensions of 2s"),
    ("scrabble-2s+-cloze", "3-letter ext of 2s (atomic cloze)"),
    ("scrabble-2s+legacy", "legacy: type all at once"),
    ("scrabble-hv",   "high-value tiles (QZJXKVW)"),
    ("squares",       "perfect squares"),
]

# Every scrabble set shares the symbol legend; all but the cloze set also get
# the tab/ctrl-o extension panel.
_SCRABBLE_KEYS = frozenset(k for k, _ in _CARDSET_OPTIONS if k.startswith("scrabble"))
# The cloze and batched sets already show every extension / segment, so their
# tab/ctrl-o panel is deferred.
_TAB_KEYS = _SCRABBLE_KEYS - {"scrabble-2s", "scrabble-2s+", "scrabble-2s+-cloze"}

_CARDSET_HELP = {
    "squares":       "",
    "scrabble7":     "Type any valid NWL word (upper- or lower-case).\n",
    "scrabble7-1k":  "Type any valid NWL word (upper- or lower-case).\n",
    "scrabble8":     "Type any valid NWL word (upper- or lower-case).\n",
    "scrabble8-1k":  "Type any valid NWL word (upper- or lower-case).\n",
    "scrabble-2s":        "Type all valid extending letters within the shown group (or Enter if none).\n",
    "scrabble-2s-legacy": "Type all valid extending letters in any order (e.g. SHL or B).\n",
    "scrabble-2s+":       "Type all valid extending letters within the shown group (or Enter if none).\n",
    "scrabble-2s+-cloze": "Type the single missing extension letter (others shown), or Enter if none.\n",
    "scrabble-2s+legacy": "Type all valid extending letters in any order (e.g. SHL or B).\n",
    "scrabble-hv":   "Type ALL valid NWL words for the rack, separated by spaces or commas.\n",
    "oscars":        "Type the Best Picture title. Glob shorthand: gl* matches Gladiator.\n",
}

_ENTER_ALT = "\033[?1049h"
_EXIT_ALT  = "\033[?1049l"
_CLEAR     = "\033[2J\033[H"

_SHORTCUTS = {
    "o": "oscars",
    "s2":  "scrabble-2s",
    "s2l": "scrabble-2s-legacy",
    "s3":  "scrabble-2s+",
    "s2+":  "scrabble-2s+",
    "s2+c": "scrabble-2s+-cloze",
    "s2+l": "scrabble-2s+legacy",
    "s7":  "scrabble7",
    "s8":  "scrabble8",
    "s7-1k": "scrabble7-1k",
    "s8-1k": "scrabble8-1k",
    "shv": "scrabble-hv",
}

_RATINGS      = [Rating.Again, Rating.Hard, Rating.Good, Rating.Easy]
_RATING_NAMES = ["🆇 Again 🆇", "⌇ Hard ⌇ ", "✔︎ Good ✔︎ ", "⍟ Easy ⍟ "]

def _goto(row, col):
    return f"\033[{row};{col}H"

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

def _vis_len(text: str) -> int:
    """Visible length of the first line, ignoring SGR color escapes."""
    return len(_ANSI_RE.sub("", text.split("\n")[0]))

def _fit(text: str, width: int) -> str:
    """Left-justify text to exactly width columns, ellipsizing if it's too long."""
    if len(text) > width:
        return text[: width - 1] + "…"
    return text.ljust(width)

def _draw_hint(used_cols: int = 0) -> None:
    hint = "?=help"
    cols = shutil.get_terminal_size().columns
    if used_cols + 1 + len(hint) > cols:
        return
    sys.stdout.write("\033[s" + _goto(1, cols - len(hint) + 1) + hint + "\033[u")
    sys.stdout.flush()

def _draw_status_bar(scheduler) -> None:
    if scheduler is None:
        return
    s = scheduler.deck_stats()
    pct = int(s["expected_correct"] * 100)
    bar = (
        f"  {pct}% learned  |"
        f"  unseen {s['unseen']}"
        f"  learning {s['learning']}"
        f"  relearning {s['relearning']}"
        f"  learned {s['learned']}"
    )
    size = shutil.get_terminal_size()
    sys.stdout.write(
        "\033[s"
        + _goto(size.lines, 1)
        + bar[: size.columns].ljust(size.columns)
        + "\033[u"
    )
    sys.stdout.flush()


def _load_menu_stats(key: str, memory_dir: str) -> dict | None:
    path = os.path.join(memory_dir, f"{key}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        total = state.get("total_cards", 0)
        if not total:
            return None
        from memory.AcScheduler import compute_deck_stats
        return compute_deck_stats(state.get("cards", {}), total)
    except Exception:
        return None


def _migrate_legacy_state(memory_dir: str) -> None:
    """Idempotent id renames so review history follows a set when its id changes.

    Each move fires only when the source file exists and the destination does
    not, so re-runs (and fresh installs) are no-ops. Order matters for the 2s+
    swap: the cloze set must vacate `scrabble-2s+.json` before the batched set
    claims it.

    Timeline:
      * the original list-style 2s+  →  scrabble-2s+legacy
      * the atomic cloze set (once `scrabble-2s+`)  →  scrabble-2s+-cloze
      * the batched set (once `scrabble-2s+batched`)  →  the canonical scrabble-2s+
      * the list-style 2s  →  scrabble-2s-legacy, freeing scrabble-2s for batched
    """
    def move(src_id: str, dst_id: str) -> None:
        src = os.path.join(memory_dir, f"{src_id}.json")
        dst = os.path.join(memory_dir, f"{dst_id}.json")
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                os.replace(src, dst)
            except OSError:
                pass

    move("scrabble-2s+", "scrabble-2s+legacy")   # pre-existing (list-style → legacy)
    move("scrabble-2s+", "scrabble-2s+-cloze")   # cloze vacates the canonical id …
    move("scrabble-2s+batched", "scrabble-2s+")  # … so batched can claim it
    move("scrabble-2s", "scrabble-2s-legacy")    # list-style 2s → legacy


def _choose_cardset(stats: dict | None = None) -> str | None:
    """Arrow-key menu to pick a card set. Falls back to usage text if not a TTY."""
    if not sys.stdin.isatty():
        print("usage:   uv run anki-cli.py <cardset>")
        print("example: uv run anki-cli.py scrabble7")
        return None

    idx = 0
    sys.stdout.write(_ENTER_ALT + _CLEAR)
    sys.stdout.flush()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    result = None
    try:
        tty.setraw(fd)
        sys.stdout.write("\033[?25l")  # hide cursor
        sys.stdout.flush()
        cols = shutil.get_terminal_size().columns
        # _NAME_W is the 80-col baseline; widen if a set id (e.g. the legacy one)
        # is longer so names never ellipsize into ambiguity.
        name_w = max(_NAME_W, *(len(k) for k, _ in _CARDSET_OPTIONS))
        while True:
            sys.stdout.write(_CLEAR)
            _draw_hint()
            for i, (key, desc) in enumerate(_CARDSET_OPTIONS):
                marker = "> " if i == idx else "  "
                s = (stats or {}).get(key)
                stats_str = ""
                if s:
                    pct = int(s["expected_correct"] * 100)
                    stats_str = (
                        f"   {pct}%"
                        f"  {s['learned']}✓"
                        f"  {s['learning']}L"
                        f"  {s['relearning']}↺"
                        f"  {s['unseen']} new"
                    )
                # Fixed-width name + desc columns keep the percentages aligned;
                # clipping the whole line to the terminal width stops stats from
                # wrapping onto the next row when a deck has outsized counts.
                line = marker + _fit(key, name_w) + "  " + _fit(desc, _DESC_W) + stats_str
                sys.stdout.write(_goto(2 + i, 3) + line[: cols - 2].rstrip())
            sys.stdout.flush()

            ch = sys.stdin.buffer.read(1)
            if ch in (b'\x03', b'\x04'):
                break
            elif ch in (b'\r', b'\n'):
                result = _CARDSET_OPTIONS[idx][0]
                break
            elif ch == b'\x1b':
                seq = sys.stdin.buffer.read(2)
                if seq == b'[A':
                    idx = (idx - 1) % len(_CARDSET_OPTIONS)
                elif seq == b'[B':
                    idx = (idx + 1) % len(_CARDSET_OPTIONS)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\033[?25h")  # restore cursor
        sys.stdout.write(_EXIT_ALT)
        sys.stdout.flush()

    return result


_DIM   = "\033[2m"
_RESET = "\033[0m"


def _show_extensions_panel(card) -> None:
    answer = card.getAnswer()
    nwl_words  = getattr(answer, 'nwl_words',   None)
    ext_lookup = getattr(answer, '_ext_lookup',  None)
    if not nwl_words or not ext_lookup:
        return

    from wordfreq import word_frequency
    cols = shutil.get_terminal_size().columns
    words_by_freq = sorted(nwl_words, key=lambda w: word_frequency(w[0].lower(), 'en'), reverse=True)

    sys.stdout.write(_CLEAR + _goto(1, 1))
    first = True
    for word, _ in words_by_freq:
        lefts, rights = ext_lookup.extensions_for(word)
        if not lefts and not rights:
            continue
        if not first:
            sys.stdout.write("\r\n")
        first = False

        max_pre = max((len(e) - len(word) for e, _ in lefts), default=0)

        for ext_word, defn in lefts:
            pre = ext_word[: len(ext_word) - len(word)]
            pad = " " * (max_pre - len(pre))
            avail = cols - (2 + max_pre + len(word)) - 2
            d = f"  {_DIM}{defn[:avail]}{_RESET}" if defn and avail > 0 else ""
            sys.stdout.write(f"  {pad}{_DIM}{pre}{_RESET}{word}{d}\r\n")

        for ext_word, defn in rights:
            suf = ext_word[len(word):]
            pad = " " * max_pre
            avail = cols - (2 + max_pre + len(word) + len(suf)) - 2
            d = f"  {_DIM}{defn[:avail]}{_RESET}" if defn and avail > 0 else ""
            sys.stdout.write(f"  {pad}{word}{_DIM}{suf}{_RESET}{d}\r\n")

    sys.stdout.write(f"\r\n  {_DIM}[any key to close]{_RESET}\r\n")
    sys.stdout.flush()
    sys.stdin.buffer.read(1)


def _show_help(cardset_key: str):
    sections = []
    extra = _CARDSET_HELP.get(cardset_key, "")
    if extra:
        sections.append(extra.rstrip("\n"))
    if cardset_key in _SCRABBLE_KEYS:
        sections.append(_SCRABBLE_HELP.rstrip("\n"))
        if cardset_key in _TAB_KEYS:
            sections.append(_TAB_HELP.rstrip("\n"))
    sections.append(_CONTROLS_HELP.rstrip("\n"))
    text = "\n\n".join(sections) + "\n"
    try:
        proc = subprocess.Popen(["more"], stdin=subprocess.PIPE)
        proc.communicate(input=text.encode())
    except (OSError, BrokenPipeError):
        print(text)


def _build_help_epilog() -> str:
    shortcut_for: dict[str, list[str]] = {}
    for k, v in _SHORTCUTS.items():
        shortcut_for.setdefault(v, []).append(k)
    name_w = max(len(n) for n, _ in _CARDSET_OPTIONS) + 2
    desc_w = max(len(d) for _, d in _CARDSET_OPTIONS) + 3
    lines = [f"  {'card sets:':<{name_w}}{'':<{desc_w}}shortcut(s)"]
    for name, desc in _CARDSET_OPTIONS:
        sc = ", ".join(shortcut_for.get(name, []))
        lines.append(f"  {_DIM}{name:<{name_w}}{desc:<{desc_w}}{sc}{_RESET}")
    return "\n".join(lines) + "\n"


def run(args: list[str]):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_build_help_epilog(),
    )
    parser.add_argument('cardset', type=str, nargs='?')
    parser.add_argument('--memory-dir', type=str, default=None)
    parsed_args = parser.parse_args(args)

    if parsed_args.cardset:
        parsed_args.cardset = _SHORTCUTS.get(parsed_args.cardset, parsed_args.cardset)

    memory_dir = parsed_args.memory_dir or os.path.expanduser("~/.local/share/anki-cli") # TODOK: portable way to have this configurable once-ish per user, without hardcoded paths or an argument every call. Or move somewhere we can guarantee access to on each OS.
    _migrate_legacy_state(memory_dir)
    scheduler = None

    if not parsed_args.cardset:
        _menu_stats = {
            key: s
            for key, _ in _CARDSET_OPTIONS
            if (s := _load_menu_stats(key, memory_dir)) is not None
        }
        chosen = _choose_cardset(_menu_stats)
        if not chosen:
            return
        parsed_args.cardset = chosen

    if parsed_args.cardset == "squares":
        from squareCardSet import SquareCardSet
        cardset = SquareCardSet()
    elif parsed_args.cardset in ("scrabble7", "scrabble7-1k", "scrabble8", "scrabble8-1k"):
        from scrabble.ScrabbleCardSet import ScrabbleCardSet
        from memory.AcReviewStore import AcReviewStore
        from memory.AcScheduler import AcScheduler
        length = 7 if "7" in parsed_args.cardset else 8
        common_filter = not parsed_args.cardset.endswith("-1k")
        cardset = ScrabbleCardSet(length=length, top_n=1000, common_filter=common_filter)
        store = AcReviewStore(memory_dir)
        scheduler = AcScheduler(cardset, store)
    elif parsed_args.cardset == "scrabble-hv":
        from scrabble.HighValueCardSet import AcHighValueCardSet
        from memory.AcReviewStore import AcReviewStore
        from memory.AcScheduler import AcScheduler
        cardset = AcHighValueCardSet()
        store = AcReviewStore(memory_dir)
        scheduler = AcScheduler(cardset, store)
    elif parsed_args.cardset == "oscars":
        from oscars.OscarCardSet import OscarCardSet
        from memory.AcReviewStore import AcReviewStore
        from memory.AcScheduler import AcScheduler
        cardset = OscarCardSet()
        store = AcReviewStore(memory_dir)
        scheduler = AcScheduler(cardset, store)
    elif parsed_args.cardset in ("scrabble-2s", "scrabble-2s-legacy", "scrabble-2s+",
                                 "scrabble-2s+-cloze", "scrabble-2s+legacy"):
        from scrabble.ExtensionCardSet import (
            AcExtensionCardSet, AcClozeExtensionCardSet, AcBatchedExtensionCardSet,
        )
        from memory.AcReviewStore import AcReviewStore
        from memory.AcScheduler import AcScheduler
        if parsed_args.cardset == "scrabble-2s":
            cardset = AcBatchedExtensionCardSet.scrabble_2s()
        elif parsed_args.cardset == "scrabble-2s-legacy":
            cardset = AcExtensionCardSet.scrabble_2s()
        elif parsed_args.cardset == "scrabble-2s+-cloze":
            cardset = AcClozeExtensionCardSet.scrabble_2s_plus()
        elif parsed_args.cardset == "scrabble-2s+legacy":
            cardset = AcExtensionCardSet.scrabble_2s_plus()
        else:  # scrabble-2s+ (canonical, batched)
            cardset = AcBatchedExtensionCardSet.scrabble_2s_plus()
        store = AcReviewStore(memory_dir)
        scheduler = AcScheduler(cardset, store)
    else:
        print(f"unknown card set: '{parsed_args.cardset}'")
        return

    startStudy(cardset, parsed_args.cardset, scheduler)


def startStudy(cardset: CardSet, cardset_key: str, scheduler=None):
    sys.stdout.write(_ENTER_ALT)
    sys.stdout.flush()
    try:
        _study_loop(cardset, cardset_key, scheduler)
    finally:
        sys.stdout.write(_EXIT_ALT)
        sys.stdout.flush()


def _paint_cloze_question(card, scheduler, clue, feedback=None) -> None:
    """Repaint a cloze question: clue+alphabet on top, the input line, then the
    given-extension context below it; cursor left on the input line."""
    sys.stdout.write(_CLEAR)
    _draw_hint(_vis_len(clue))
    _draw_status_bar(scheduler)
    sys.stdout.write(_goto(1, 1))
    sys.stdout.write(clue + "\n")          # row 1: clue + alphabet
    sys.stdout.write("\n")                 # row 2: the "> " input line
    context = card.live_context()
    if context:
        sys.stdout.write(context + "\n")   # row 3+: other valid extensions (given)
    if feedback:
        sys.stdout.write("\n" + feedback + "\n")
    sys.stdout.write(_goto(2, 1))
    sys.stdout.flush()


def _paint_answer(scheduler, clue, guess, idx, rack_stat, answer_text) -> None:
    """Repaint the post-submit screen pinned to the top (no scroll, so the clue
    line never disappears): clue, the submitted guess, the rating selector, then
    the full answer list."""
    left  = "← " if idx > 0               else "  "
    right = " →" if idx < len(_RATINGS) - 1 else "  "
    sys.stdout.write(_CLEAR)
    _draw_status_bar(scheduler)
    sys.stdout.write(_goto(1, 1))
    sys.stdout.write(clue.replace("\n", "\r\n") + "\r\n")
    sys.stdout.write(f"> {guess}\r\n")
    sys.stdout.write(f"{left}{_RATING_NAMES[idx]}{right}{rack_stat}   \r\n")
    sys.stdout.write(answer_text.replace("\n", "\r\n") + "\r\n")
    sys.stdout.flush()


def _study_loop(cardset: CardSet, cardset_key: str, scheduler=None):
    while True:
        card = scheduler.getNextCard() if scheduler else cardset.getNextCard()
        answer = card.getAnswer()
        # Cloze cards expose clue_text/live_context; everything else uses the
        # plain prompt and the original single-line layout.
        is_cloze = hasattr(card, "clue_text")
        clue = card.clue_text() if is_cloze else card.getPrompt().getDisplayText()

        t0 = time.time()
        show_help = False

        if is_cloze:
            feedback = None
            while True:
                _paint_cloze_question(card, scheduler, clue, feedback)
                try:
                    user_input = input("> ").strip()
                except (KeyboardInterrupt, EOFError):
                    return
                if user_input == "?":
                    show_help = True
                    break
                if user_input == "" or answer.isValid(user_input):
                    break
                feedback = answer.getInvalidFeedback(user_input)
        else:
            sys.stdout.write(_CLEAR)
            _draw_hint(len(clue.split("\n")[0]))
            _draw_status_bar(scheduler)
            sys.stdout.write(_goto(1, 1))
            sys.stdout.flush()
            print(clue)
            while True:
                try:
                    user_input = input("> ").strip()
                except (KeyboardInterrupt, EOFError):
                    return
                if user_input == "?":
                    show_help = True
                    break
                # Empty (whitespace-only collapses to "") is always a wrong answer —
                # the simple "idk". Otherwise reject submissions the card deems
                # invalid (e.g. not an anagram of the rack): show a single feedback
                # line and re-prompt without scoring, like pre-submission typing.
                if user_input == "" or answer.isValid(user_input):
                    break
                print(answer.getInvalidFeedback(user_input))

        if show_help:
            _show_help(cardset_key)
            continue

        elapsed = time.time() - t0
        used_glob = user_input.endswith("*")

        if card.isCorrect(user_input):
            is_correct = True
            answer_text = answer.getDisplayTextWhenCorrect()
        elif user_input == "" and not getattr(answer, "diff_on_blank", False):
            is_correct = False
            answer_text = answer.getDisplayTextWhenIncorrect()
        else:
            is_correct = False
            feedback = answer.getWrongAnswerFeedback(user_input)
            body = answer.getDisplayTextWhenIncorrect()
            answer_text = f"{feedback}\n{body}" if feedback else body

        if scheduler and is_correct:
            auto_rating = scheduler.inferRating(elapsed, used_glob, card)
        elif not is_correct:
            auto_rating = Rating.Again
        else:
            auto_rating = Rating.Good

        # Post-submit the clue recolors: the answer letter goes green, a
        # wrong-but-plausible guess goes red (cloze only).
        clue_revealed = card.clue_text(user_input, revealed=True) if is_cloze else clue

        try:
            idx = _RATINGS.index(auto_rating)

            prob = getattr(card, "probability", None)
            rack_stat = f"   {prob * 1e6:.1f}/M" if prob is not None else ""

            if not sys.stdin.isatty():
                input("")
                left  = "← " if idx > 0               else "  "
                right = " →" if idx < len(_RATINGS) - 1 else "  "
                if is_cloze:
                    print(clue_revealed)
                sys.stdout.write(f"{left}{_RATING_NAMES[idx]}{right}{rack_stat}\n")
                sys.stdout.flush()
                print(answer_text)
                rating = auto_rating
            else:
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    sys.stdout.write("\033[?25l")  # hide cursor
                    _paint_answer(scheduler, clue_revealed, user_input, idx, rack_stat, answer_text)
                    while True:
                        ch = sys.stdin.buffer.read(1)
                        if ch in (b'\x03', b'\x04'):
                            raise KeyboardInterrupt
                        if ch in (b'\r', b'\n'):
                            break
                        # ctrl-o extension panel: every scrabble set but the cloze one.
                        # TODOCC: add an answer-safe (post-submit) extension panel for cloze.
                        if ch in (b'\x0f', b'\t') and not is_cloze:
                            _show_extensions_panel(card)
                            _paint_answer(scheduler, clue_revealed, user_input, idx, rack_stat, answer_text)
                            continue
                        if ch == b'\x1b':
                            seq = sys.stdin.buffer.read(2)
                            if seq == b'[D':
                                idx = max(0, idx - 1)
                            elif seq == b'[C':
                                idx = min(len(_RATINGS) - 1, idx + 1)
                            _paint_answer(scheduler, clue_revealed, user_input, idx, rack_stat, answer_text)
                finally:
                    sys.stdout.write("\033[?25h")  # restore cursor
                    sys.stdout.flush()
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)

                rating = _RATINGS[idx]

            if scheduler:
                scheduler.recordResult(card, rating, elapsed)
                _draw_status_bar(scheduler)

        except (KeyboardInterrupt, EOFError):
            return


if __name__ == "__main__":
    run(sys.argv[1:])
