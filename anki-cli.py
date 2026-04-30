import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import subprocess
import shutil
import argparse
import tty
import termios

# import fsrs_rs_python as fsrs

from cards.cardSet import CardSet
from squareCardSet import SquareCardSet
from scrabble.ScrabbleCardSet import ScrabbleCardSet
from oscars.OscarCardSet import OscarCardSet

_CONTROLS_HELP = """\
CONTROLS
  <answer>      Submit
  <enter>       Unknown / reveal
  ?             This help
  ctrl-c        Quit
"""

_CARDSET_OPTIONS = [
    ("oscars",   "Oscar Best Picture winners by year"),
    ("scrabble7", "7-letter bingo alphagrams"),
    ("scrabble8", "8-letter bingo alphagrams"),
    ("squares",   "perfect squares"),
]

_CARDSET_HELP = {
    "squares":   "",
    "scrabble7": "Type any valid NWL word (upper- or lower-case).\n",
    "scrabble8": "Type any valid NWL word (upper- or lower-case).\n",
    "oscars":    "Type the Best Picture title (fuzzy match accepted).\n",
}

_ENTER_ALT = "\033[?1049h"
_EXIT_ALT  = "\033[?1049l"
_CLEAR     = "\033[2J\033[H"


def _goto(row, col):
    return f"\033[{row};{col}H"


def _draw_hint():
    hint = "?=help"
    cols = shutil.get_terminal_size().columns
    sys.stdout.write("\033[s" + _goto(1, cols - len(hint) + 1) + hint + "\033[u")
    sys.stdout.flush()


def _choose_cardset() -> str | None:
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
        while True:
            sys.stdout.write(_CLEAR)
            _draw_hint()
            for i, (key, desc) in enumerate(_CARDSET_OPTIONS):
                marker = "> " if i == idx else "  "
                sys.stdout.write(_goto(2 + i, 3) + marker + key + "   " + desc)
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
        sys.stdout.write(_EXIT_ALT)
        sys.stdout.flush()

    return result


def _show_help(cardset_key: str):
    extra = _CARDSET_HELP.get(cardset_key, "")
    text = (extra + "\n" + _CONTROLS_HELP) if extra else _CONTROLS_HELP
    try:
        proc = subprocess.Popen(["more"], stdin=subprocess.PIPE)
        proc.communicate(input=text.encode())
    except (OSError, BrokenPipeError):
        print(text)


def run(args: list[str]):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('cardset', type=str, nargs='?')
    parser.add_argument('--top', type=int, default=100)
    parser.add_argument('--rebuild', action='store_true')
    parsed_args = parser.parse_args(args)

    if not parsed_args.cardset:
        chosen = _choose_cardset()
        if not chosen:
            return
        parsed_args.cardset = chosen

    rebuild = parsed_args.rebuild

    if parsed_args.cardset == "oscars":
        cardset = OscarCardSet()
    elif parsed_args.cardset == "squares":
        cardset = SquareCardSet()
    elif parsed_args.cardset == "scrabble7":
        cardset = ScrabbleCardSet(length=7, study_n=parsed_args.top, rebuild=rebuild)
    elif parsed_args.cardset == "scrabble8":
        cardset = ScrabbleCardSet(length=8, study_n=parsed_args.top, rebuild=rebuild)
    else:
        print(f"unknown card set: '{parsed_args.cardset}'")
        return

    startStudy(cardset, parsed_args.cardset)


def startStudy(cardset: CardSet, cardset_key: str):
    sys.stdout.write(_ENTER_ALT)
    sys.stdout.flush()
    try:
        _study_loop(cardset, cardset_key)
    finally:
        sys.stdout.write(_EXIT_ALT)
        sys.stdout.flush()


def _study_loop(cardset: CardSet, cardset_key: str):
    while True:
        card = cardset.getNextCard()

        sys.stdout.write(_CLEAR)
        _draw_hint()
        sys.stdout.write(_goto(1, 1))
        sys.stdout.flush()

        print(card.getPrompt().getDisplayText())

        try:
            user_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            return

        if user_input == "?":
            _show_help(cardset_key)
            continue
        elif user_input == "":
            answer_text = card.getAnswer().getDisplayTextWhenIncorrect()
        elif card.isCorrect(user_input):
            answer_text = " ✔︎\n" + card.getAnswer().getDisplayTextWhenCorrect()
        else:
            feedback = card.getAnswer().getWrongAnswerFeedback(user_input)
            answer_text = feedback + "\n" + card.getAnswer().getDisplayTextWhenIncorrect()

        print(answer_text)

        try:
            input("")
        except (KeyboardInterrupt, EOFError):
            return


if __name__ == "__main__":
    run(sys.argv[1:])
