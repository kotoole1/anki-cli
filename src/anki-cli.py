import os
import sys
import argparse

import fsrs_rs_python as fsrs

from cards.cardSet import CardSet

def run(args: list[str]):
    parser = argparse.ArgumentParser(description='A command-line tool for memorizing text-based content.')
    parser.add_argument('cardset', type=str, help='Path to the file containing content to memorize')
    parsed_args = parser.parse_args(args)

    if parsed_args.cardset == "squares":
        cardset = CardSet.squares()
    # elif os.path.exists(parsed_args.cardset):
    #     cardset = CardSet.from_file(parsed_args.cardset)
    else:
        print(f"Error: The file '{parsed_args.cardset}' does not exist.")
        return

    start_study(cardset)

def start_study(cardset: CardSet):


if __name__ == "__main__":
    run(sys.argv[1:])
