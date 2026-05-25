import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import json
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

_CARDSET_OPTIONS = [
    ("oscars",        "Oscar Best Picture winners"),
    ("scrabble7",     "7-letter bingos (1k, common words only)"),
    ("scrabble7-1k",  "7-letter bingos (1k, any legal word)"),
    ("scrabble8",     "8-letter bingos (1k, common words only)"),
    ("scrabble8-1k",  "8-letter bingos (1k, any legal word)"),
    ("scrabble-2s",   "2-letter word extensions"),
    ("scrabble-2s+",  "3-letter extensions of 2s"),
    ("squares",       "perfect squares"),
]

_CARDSET_HELP = {
    "squares":       "",
    "scrabble7":     "Type any valid NWL word (upper- or lower-case).\n",
    "scrabble7-1k":  "Type any valid NWL word (upper- or lower-case).\n",
    "scrabble8":     "Type any valid NWL word (upper- or lower-case).\n",
    "scrabble8-1k":  "Type any valid NWL word (upper- or lower-case).\n",
    "scrabble-2s":   "Type all valid extending letters in any order (e.g. SHL or B).\n",
    "scrabble-2s+":  "Type all valid extending letters in any order (e.g. SHL or B).\n",
    "oscars":        "Type the Best Picture title. Glob shorthand: gl* matches Gladiator.\n",
}

_ENTER_ALT = "\033[?1049h"
_EXIT_ALT  = "\033[?1049l"
_CLEAR     = "\033[2J\033[H"

_SHORTCUTS = {
    "o": "oscars",
    "s2":  "scrabble-2s",
    "s3":  "scrabble-2s+",
    "s2+":  "scrabble-2s+",
    "s7":  "scrabble7",
    "s8":  "scrabble8",
    "s7-1k": "scrabble7-1k",
    "s8-1k": "scrabble8-1k",
}

_RATINGS      = [Rating.Again, Rating.Hard, Rating.Good, Rating.Easy]
_RATING_NAMES = ["🆇 Again 🆇", "⌇ Hard ⌇ ", "✔︎ Good ✔︎ ", "⍟ Easy ⍟ "]

def _goto(row, col):
    return f"\033[{row};{col}H"

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
                sys.stdout.write(_goto(2 + i, 3) + marker + key + "   " + desc + stats_str)
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
    extra = _CARDSET_HELP.get(cardset_key, "")
    text = (extra + "\n" + _CONTROLS_HELP) if extra else _CONTROLS_HELP
    try:
        proc = subprocess.Popen(["more"], stdin=subprocess.PIPE)
        proc.communicate(input=text.encode())
    except (OSError, BrokenPipeError):
        print(text)


def _build_help_epilog() -> str:
    shortcut_for = {v: k for k, v in _SHORTCUTS.items()}
    name_w = max(len(n) for n, _ in _CARDSET_OPTIONS) + 2
    desc_w = max(len(d) for _, d in _CARDSET_OPTIONS) + 3
    lines = ["card sets (shortcuts):"]
    for name, desc in _CARDSET_OPTIONS:
        sc = shortcut_for.get(name, "")
        lines.append(f"  {name:<{name_w}}{desc:<{desc_w}}{sc}")
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

    memory_dir = parsed_args.memory_dir or os.path.expanduser("~/.local/share/anki-cli")
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
    elif parsed_args.cardset == "oscars":
        from oscars.OscarCardSet import OscarCardSet
        from memory.AcReviewStore import AcReviewStore
        from memory.AcScheduler import AcScheduler
        cardset = OscarCardSet()
        store = AcReviewStore(memory_dir)
        scheduler = AcScheduler(cardset, store)
    elif parsed_args.cardset in ("scrabble-2s", "scrabble-2s+"):
        from scrabble.ExtensionCardSet import AcExtensionCardSet
        from memory.AcReviewStore import AcReviewStore
        from memory.AcScheduler import AcScheduler
        if parsed_args.cardset == "scrabble-2s":
            cardset = AcExtensionCardSet.scrabble_2s()
        else:
            cardset = AcExtensionCardSet.scrabble_2s_plus()
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


def _study_loop(cardset: CardSet, cardset_key: str, scheduler=None):
    while True:
        card = scheduler.getNextCard() if scheduler else cardset.getNextCard()
        prompt_text = card.getPrompt().getDisplayText()

        sys.stdout.write(_CLEAR)
        _draw_hint(len(prompt_text.split('\n')[0]))
        _draw_status_bar(scheduler)
        sys.stdout.write(_goto(1, 1))
        sys.stdout.flush()

        print(prompt_text)

        try:
            t0 = time.time()
            user_input = input("> ").strip()
            elapsed = time.time() - t0
        except (KeyboardInterrupt, EOFError):
            return

        if user_input == "?":
            _show_help(cardset_key)
            continue

        used_glob = user_input.endswith("*")

        if card.isCorrect(user_input):
            is_correct = True
            answer_text = card.getAnswer().getDisplayTextWhenCorrect()
        elif user_input == "":
            is_correct = False
            answer_text = card.getAnswer().getDisplayTextWhenIncorrect()
        else:
            is_correct = False
            feedback = card.getAnswer().getWrongAnswerFeedback(user_input)
            answer_text = feedback + "\n" + card.getAnswer().getDisplayTextWhenIncorrect()

        if scheduler and is_correct:
            auto_rating = scheduler.inferRating(elapsed, used_glob, card)
        elif not is_correct:
            auto_rating = Rating.Again
        else:
            auto_rating = Rating.Good

        try:
            idx = _RATINGS.index(auto_rating)

            prob = getattr(card, 'probability', None)
            rack_stat = f"   {prob * 1e6:.1f}/M" if prob is not None else ""

            if not sys.stdin.isatty():
                input("")
                left  = "← " if idx > 0               else "  "
                right = " →" if idx < len(_RATINGS) - 1 else "  "
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
                    left  = "← " if idx > 0               else "  "
                    right = " →" if idx < len(_RATINGS) - 1 else "  "
                    sys.stdout.write(f"{left}{_RATING_NAMES[idx]}{right}{rack_stat}   \r\n")
                    sys.stdout.write(answer_text.replace("\n", "\r\n") + "\r\n")
                    sys.stdout.flush()

                    n_up   = len(answer_text.splitlines()) + 1
                    at_top = False  # True after ctrl-o clears screen (content at line 1)

                    while True:
                        ch = sys.stdin.buffer.read(1)
                        if ch in (b'\x03', b'\x04'):
                            raise KeyboardInterrupt
                        if ch in (b'\r', b'\n'):
                            break
                        if ch == b'\x0f':  # ctrl-o
                            _show_extensions_panel(card)
                            sys.stdout.write(_CLEAR + _goto(1, 1))
                            _draw_status_bar(scheduler)
                            sys.stdout.write(f"{left}{_RATING_NAMES[idx]}{right}{rack_stat}   \r\n")
                            sys.stdout.write(answer_text.replace("\n", "\r\n") + "\r\n")
                            sys.stdout.write(_goto(1, 1))  # keep cursor at top; prevents scroll
                            sys.stdout.flush()
                            at_top = True
                            continue
                        if ch == b'\x1b':
                            seq = sys.stdin.buffer.read(2)
                            if seq == b'[D':
                                idx = max(0, idx - 1)
                            elif seq == b'[C':
                                idx = min(len(_RATINGS) - 1, idx + 1)
                        left  = "← " if idx > 0               else "  "
                        right = " →" if idx < len(_RATINGS) - 1 else "  "
                        if at_top:
                            sys.stdout.write(_goto(1, 1))
                            sys.stdout.write(f"{left}{_RATING_NAMES[idx]}{right}{rack_stat}   ")
                        else:
                            sys.stdout.write(f"\033[{n_up}A\r")
                            sys.stdout.write(f"{left}{_RATING_NAMES[idx]}{right}{rack_stat}   ")
                            sys.stdout.write(f"\033[{n_up}B")
                        sys.stdout.flush()
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
