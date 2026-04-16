import sys
import subprocess
import shutil
import argparse

# import fsrs_rs_python as fsrs

from cards.cardSet import CardSet
from squareCardSet import SquareCardSet
from scrabble.ScrabbleCardSet import ScrabbleCardSet

_CONTROLS_HELP = """\
CONTROLS
  <answer>      Submit
  <enter>       Unknown / reveal
  ?             This help
  ctrl-c        Quit
"""

_CARDSET_HELP = {
    "squares":   "",
    "scrabble7": "Type any valid NWL word (upper- or lower-case).\n",
    "scrabble8": "Type any valid NWL word (upper- or lower-case).\n",
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
    parser.add_argument('--top', type=int, default=500)
    parser.add_argument('--rebuild', action='store_true')
    parsed_args = parser.parse_args(args)

    if not parsed_args.cardset:
        _show_help("")
        return

    rebuild = parsed_args.rebuild

    if parsed_args.cardset == "squares":
        cardset = SquareCardSet()
    elif parsed_args.cardset == "scrabble7":
        cardset = ScrabbleCardSet(length=7, top_n=parsed_args.top, rebuild=rebuild)
    elif parsed_args.cardset == "scrabble8":
        cardset = ScrabbleCardSet(length=8, top_n=parsed_args.top, rebuild=rebuild)
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
            answer_text = "Correct!\n" + card.getAnswer().getDisplayTextWhenCorrect()
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
