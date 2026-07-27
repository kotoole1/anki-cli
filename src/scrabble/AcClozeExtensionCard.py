"""Atomic cloze-deletion extension cards (scrabble-2s+ and future single-hook sets).

Responsibility: model a *single* extension of a base word as one card. The
hidden answer is one letter; the pattern's other valid extensions are shown as
"given" context (blue) so the task is "name the missing one", per the SuperMemo
minimum-information principle. This replaces the legacy "type every extension at
once" card in ExtensionCard.py, which still backs the *-legacy sets.

Rendering vocabulary is shared with the anagram/extension sets: the ▶▷▹
commonness indicator (_commonness_indicator) and the +#-~ extension symbols
(AcExtensionLookup.symbols). Colors: blue = a given/other valid extension,
green = the correct (hidden) answer once revealed, red = a wrong-but-plausible
guess once revealed.
"""

import string

from cards.cardPrompt import SimpleTextPrompt
from cards.cardAnswer import CardAnswer
from scrabble.ScrabbleCard import _commonness_indicator

_BLUE  = "\033[94m"
_GREEN = "\033[92m"
_RED   = "\033[91m"
_DIM   = "\033[2m"
_RESET = "\033[0m"

_LETTERS = string.ascii_uppercase

# Mnemonic letter groups for the 4+ extension alphabet hint. Order within a
# group is the memorable order (not alphabetical). Together they cover all 26
# letters: 5 + 5 + 6 + 5 + 5 = 26, so _group_for always resolves.
_ALPHABET_GROUPS = ["AEIOU", "LNSTR", "BCDGMP", "FHVWY", "KJQXZ"]


def _group_for(letter: str) -> str:
    for group in _ALPHABET_GROUPS:
        if letter in group:
            return group
    return _LETTERS  # unreachable: the groups partition the whole alphabet


class AcClozeExtensionAnswer(CardAnswer):
    """One hidden extension letter, with the pattern's other extensions as context.

    `target_letter` is None for a zero-extension card (correct answer = the empty
    string). `all_valid` is every valid extension letter for the pattern;
    `given` is everything except the hidden one. `valid_words` is the full
    `(word, definition)` list for all valid extensions of the pattern.
    """

    def __init__(self, card_id: str, base_word: str, direction: str,
                 target_letter: str | None, all_valid: frozenset[str],
                 valid_words: list[tuple[str, str]], ext_lookup=None,
                 top20k: frozenset[str] = frozenset(),
                 top50k: frozenset[str] = frozenset()):
        super().__init__(card_id)
        self.base_word = base_word
        self.direction = direction              # "right" or "left"
        self.target_letter = target_letter      # str, or None for a zero-ext card
        self.all_valid = frozenset(all_valid)
        self.given = self.all_valid - ({target_letter} if target_letter else frozenset())
        self._valid_words = list(valid_words)   # ALL valid extensions [(word, defn), ...]
        self._ext_lookup = ext_lookup
        self._top20k = top20k
        self._top50k = top50k
        self.nwl_words = list(valid_words)       # parity with ExtensionAnswer (future tab panel)
        self.prompt_text = f"{base_word}?" if direction == "right" else f"?{base_word}"

    # ── geometry ──────────────────────────────────────────────────────────────

    def _ext_letter(self, word: str) -> str:
        return word[-1] if self.direction == "right" else word[0]

    def shown_alphabet(self) -> str:
        """The alphabet letters shown on the clue line, in display order.

        0–1 valid extensions → "" (none). 2–3 → full A–Z. 4+ → only the
        mnemonic group containing the hidden answer.
        """
        n = len(self.all_valid)
        if n <= 1:
            return ""
        if n <= 3:
            return _LETTERS
        return _group_for(self.target_letter)

    # ── clue line (prompt + colored alphabet) ───────────────────────────────────

    def _color_alphabet(self, guess: str | None, revealed: bool) -> str:
        letters = self.shown_alphabet()
        if not letters:
            return ""
        g = guess.upper() if guess else ""
        out = []
        for ch in letters:
            if revealed and ch == self.target_letter:
                out.append(f"{_GREEN}{ch}{_RESET}")
            elif revealed and g and ch == g and g != self.target_letter:
                out.append(f"{_RED}{ch}{_RESET}")
            elif ch in self.given:
                out.append(f"{_BLUE}{ch}{_RESET}")
            else:
                out.append(ch)  # white (includes the hidden answer pre-reveal)
        return " ".join(out)

    def clue_text(self, guess: str | None = None, revealed: bool = False) -> str:
        alpha = self._color_alphabet(guess, revealed)
        return f"{self.prompt_text}   {alpha}" if alpha else self.prompt_text

    # ── word list ───────────────────────────────────────────────────────────────

    def _word_line(self, word: str, defn: str, color: str) -> str:
        if self._ext_lookup and len(word) < 5:
            ls, rs = self._ext_lookup.symbols(word)
            lpfx = f"{_DIM}{ls or ' '}{_RESET}"
            rsuf = f"{_DIM}{rs or ' '}{_RESET}"
        else:
            lpfx = rsuf = " "

        if color == "green":
            w_str = f"{_GREEN}{word}{_RESET}"
        elif color == "red":
            w_str = f"{_RED}{word}{_RESET}"
        elif color == "blue":  # color only the extension letter blue, rest white
            if self.direction == "right":
                w_str = f"{word[:-1]}{_BLUE}{word[-1]}{_RESET}"
            else:
                w_str = f"{_BLUE}{word[0]}{_RESET}{word[1:]}"
        else:
            w_str = word

        indicator = _commonness_indicator(word, self._top20k, self._top50k)
        d = f"  {indicator} {_DIM}{defn}{_RESET}" if defn else f"  {indicator}"
        return f"  {lpfx}{w_str}{rsuf}{d}"

    def _given_color(self, word: str) -> str:
        """A given extension's letter is blue only if it's blue in the shown
        alphabet. For a 4+ card (only one group shown) that means just the givens
        inside that group; givens in other groups stay white."""
        return "blue" if self._ext_letter(word) in self.shown_alphabet() else "white"

    def _sorted_words(self) -> list[tuple[str, str]]:
        return sorted(self._valid_words, key=lambda wd: wd[0])

    def getDisplayText(self) -> str:
        """Live context shown below the input: the GIVEN extensions only.

        The hidden answer word is omitted. Empty for zero- and one-extension
        cards (nothing to give away)."""
        lines = [
            self._word_line(word, defn, self._given_color(word))
            for word, defn in self._sorted_words()
            if not (self.target_letter and self._ext_letter(word) == self.target_letter)
        ]
        return "\n".join(lines)

    def _full_list(self, correct: bool) -> str:
        if not self._valid_words:  # zero-extension card
            msg = "  (no valid extensions)"
            return f"{_GREEN}{msg}{_RESET}" if correct else f"{_RED}{msg}{_RESET}"
        lines = []
        for word, defn in self._sorted_words():
            if self.target_letter and self._ext_letter(word) == self.target_letter:
                lines.append(self._word_line(word, defn, "green" if correct else "red"))
            else:
                lines.append(self._word_line(word, defn, self._given_color(word)))
        return "\n".join(lines)

    def getDisplayTextWhenCorrect(self) -> str:
        return self._full_list(correct=True)

    def getDisplayTextWhenIncorrect(self) -> str:
        return self._full_list(correct=False)

    # ── scoring ───────────────────────────────────────────────────────────────

    def isCorrect(self, answer: str) -> bool:
        a = answer.strip().upper()
        if self.target_letter is None:
            return a == ""
        return a == self.target_letter

    def isValid(self, answer: str) -> bool:
        """A submission is a scorable attempt only if it is a *plausible candidate*:
        the empty string, or a single letter within the shown alphabet that is not
        one of the given (shown) extensions. Implausible input (multi-char,
        non-letter, outside the alphabet, or a given letter) is rejected and
        re-prompted without scoring."""
        a = answer.strip().upper()
        if a == "":
            return True
        if len(a) != 1 or a not in _LETTERS:
            return False
        shown = self.shown_alphabet()
        if not shown:               # 0–1 ext: no narrowing, any single letter scores
            return True
        return a in shown and a not in self.given

    def getInvalidFeedback(self, submitted: str) -> str:
        a = submitted.strip().upper()
        if len(a) == 1 and a in self.given:
            return f"  {_BLUE}{a}{_RESET} is already shown — name the missing one"
        return "  not a candidate — pick a white letter from the alphabet shown"

    # cloze cards reveal everything via the clue line + list; no per-letter prefix
    def getWrongAnswerFeedback(self, submitted: str) -> str:
        return ""


class AcClozeExtensionCard:
    def __init__(self, card_id: str, base_word: str, direction: str,
                 target_letter: str | None, all_valid: frozenset[str],
                 valid_words: list[tuple[str, str]], ext_lookup=None,
                 top20k: frozenset[str] = frozenset(),
                 top50k: frozenset[str] = frozenset()):
        self.id = card_id
        self._answer = AcClozeExtensionAnswer(
            card_id, base_word, direction, target_letter, all_valid,
            valid_words, ext_lookup, top20k, top50k)
        self._prompt = SimpleTextPrompt(card_id, self._answer.prompt_text)

    def getPrompt(self):
        return self._prompt

    def getAnswer(self):
        return self._answer

    def isCorrect(self, answer: str) -> bool:
        return self._answer.isCorrect(answer)

    # ── study-loop hooks (presence signals a cloze card to the loop) ────────────

    def clue_text(self, guess: str | None = None, revealed: bool = False) -> str:
        return self._answer.clue_text(guess, revealed)

    def live_context(self) -> str:
        return self._answer.getDisplayText()

    @property
    def rating_time_threshold_s(self) -> int:
        return 5  # single-letter recall is fast; Good under ~5s, Hard over
