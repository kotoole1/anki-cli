"""Batched extension cards (scrabble-2s+batched) — a cloze *by alphabet segment*.

For a pattern with 5+ valid extensions, the drill is split into per-segment
cards. Every card shows all five segments (AEIOU / LNSTR / BCDGMP / FHVWY /
KJQXZ): the card's own *active* segment is left white for you to recall, while
the other four are greyed with their valid extensions revealed in blue as
context.

Completion colours are stateless (derived from the actual guess, never cached):
  green  = a valid answer you gave            (dictionary, diff, alphabet)
  purple = a valid answer you missed          (dictionary, diff, alphabet)
  red    = a letter you wrongly gave          (diff, alphabet)
  grey   = a non-answer you correctly skipped (alphabet)
The active segment is thus never blue/white after an answer. Non-active
segments keep blue = a valid extension there (context), grey = not.

Which segment cards exist for a bigram is decided in the builder by a vowel-swap
heuristic (see ExtensionCardSet._build_2s_plus_batched).

Display order: letters alphabetised within each segment, segments vowels-first
by tile points (the _ALPHABET_GROUPS order).
"""

from cards.cardPrompt import SimpleTextPrompt
from cards.cardAnswer import CardAnswer
from scrabble.ScrabbleCard import _commonness_indicator
from scrabble.AcClozeExtensionCard import _ALPHABET_GROUPS

_BLUE   = "\033[94m"
_GREEN  = "\033[92m"
_PURPLE = "\033[95m"
_RED    = "\033[91m"
_DIM    = "\033[2m"
_RESET  = "\033[0m"

_DISPLAY_SEGMENTS = ["".join(sorted(g)) for g in _ALPHABET_GROUPS]


def _segment_index(letter: str) -> int:
    for i, group in enumerate(_ALPHABET_GROUPS):
        if letter in group:
            return i
    return len(_ALPHABET_GROUPS)


class AcBatchedExtensionAnswer(CardAnswer):
    diff_on_blank = True   # a blank "idk" still shows the +missing diff

    def __init__(self, card_id: str, base_word: str, direction: str, subset: str,
                 subset_valid: frozenset[str], all_valid: frozenset[str],
                 all_words: list[tuple[str, str]], ext_lookup=None,
                 top20k: frozenset[str] = frozenset(),
                 top50k: frozenset[str] = frozenset()):
        super().__init__(card_id)
        self.base_word = base_word
        self.subset = subset                          # canonical active group, e.g. "LNSTR"
        self._active = frozenset(subset)
        self._active_display = "".join(sorted(subset))
        self._is_right = direction == "right"
        self._valid_letters = frozenset(subset_valid)   # the answer (active segment only)
        self._all_valid = frozenset(all_valid)          # every valid letter (for blue context)
        self._all_words = list(all_words)
        self._ext_lookup = ext_lookup
        self._top20k = top20k
        self._top50k = top50k
        self.nwl_words = list(all_words)
        self.prompt_text = f"{base_word}?" if direction == "right" else f"?{base_word}"
        self._last_guess: frozenset[str] = frozenset()
        # Completion "dictionary order" for this set sorts by alphabet segment.
        self._words_sorted = sorted(
            all_words, key=lambda wd: (_segment_index(self._ext_letter(wd[0])), wd[0])
        )

    def _ext_letter(self, word: str) -> str:
        return word[-1] if self._is_right else word[0]

    # ── clue line: prompt + all five segments ───────────────────────────────────

    def _segment_display(self, revealed: bool) -> str:
        parts = []
        for disp in _DISPLAY_SEGMENTS:
            active = frozenset(disp) == self._active
            chunk = ""
            for ch in disp:
                if active:
                    if not revealed:
                        chunk += ch                                  # hidden (white)
                    else:
                        valid = ch in self._valid_letters
                        given = ch in self._last_guess
                        if valid and given:   chunk += f"{_GREEN}{ch}{_RESET}"   # got it
                        elif valid:           chunk += f"{_PURPLE}{ch}{_RESET}"  # missed
                        elif given:           chunk += f"{_RED}{ch}{_RESET}"     # wrong
                        else:                 chunk += f"{_DIM}{ch}{_RESET}"     # correctly skipped
                else:
                    chunk += (f"{_BLUE}{ch}{_RESET}" if ch in self._all_valid
                              else f"{_DIM}{ch}{_RESET}")
            parts.append(chunk)
        return "  ".join(parts)

    def clue_text(self, guess: str | None = None, revealed: bool = False) -> str:
        return f"{self.prompt_text}   {self._segment_display(revealed)}"

    # ── loop hooks ──────────────────────────────────────────────────────────────

    def getDisplayText(self) -> str:
        return ""   # no words/definitions are shown during the prompt

    def _render(self) -> str:
        lines = []
        if not self._valid_letters:
            lines.append(f"  No valid extensions with {self._active_display}")
        for word, defn in self._words_sorted:
            if self._ext_lookup and len(word) < 5:
                ls, rs = self._ext_lookup.symbols(word)
                lpfx = f"{_DIM}{ls or ' '}{_RESET}"
                rsuf = f"{_DIM}{rs or ' '}{_RESET}"
            else:
                lpfx = rsuf = " "

            ext = self._ext_letter(word)
            if ext not in self._active:                 # other segments' words → blue context
                w_str = f"{_BLUE}{word}{_RESET}"
            elif ext in self._last_guess:               # active answer you gave → green
                w_str = f"{_GREEN}{word}{_RESET}"
            else:                                        # active answer you missed → purple
                w_str = f"{_PURPLE}{word}{_RESET}"

            indicator = _commonness_indicator(word, self._top20k, self._top50k)
            d = f"  {indicator} {_DIM}{defn}{_RESET}" if defn else f"  {indicator}"
            lines.append(f"  {lpfx}{w_str}{rsuf}{d}")
        return "\n".join(lines)

    def getDisplayTextWhenCorrect(self) -> str:
        return self._render()

    def getDisplayTextWhenIncorrect(self) -> str:
        return self._render()

    # ── scoring ───────────────────────────────────────────────────────────────

    def isCorrect(self, answer: str) -> bool:
        self._last_guess = frozenset(c for c in answer.upper() if c.isalpha())
        return self._last_guess == self._valid_letters

    def getWrongAnswerFeedback(self, submitted: str) -> str:
        given   = frozenset(c for c in submitted.upper() if c.isalpha())
        correct = given & self._valid_letters
        missing = self._valid_letters - given
        extra   = given - self._valid_letters
        # green = right, +purple = missed, -red = wrongly added. e.g. "LN +RST -X".
        parts = []
        if correct:
            parts.append(f"{_GREEN}{''.join(sorted(correct))}{_RESET}")
        if missing:
            parts.append(f"{_PURPLE}+{''.join(sorted(missing))}{_RESET}")
        if extra:
            parts.append(f"{_RED}-{''.join(sorted(extra))}{_RESET}")
        return "  " + " ".join(parts) if parts else ""


class AcBatchedExtensionCard:
    def __init__(self, card_id: str, base_word: str, direction: str, subset: str,
                 subset_valid: frozenset[str], all_valid: frozenset[str],
                 all_words: list[tuple[str, str]], ext_lookup=None,
                 top20k: frozenset[str] = frozenset(),
                 top50k: frozenset[str] = frozenset()):
        self.id = card_id
        self._answer = AcBatchedExtensionAnswer(
            card_id, base_word, direction, subset, subset_valid, all_valid,
            all_words, ext_lookup, top20k, top50k)
        self._prompt = SimpleTextPrompt(card_id, self._answer.prompt_text)

    def getPrompt(self):
        return self._prompt

    def getAnswer(self):
        return self._answer

    def isCorrect(self, answer: str) -> bool:
        return self._answer.isCorrect(answer)

    # cloze-style hooks: stateful clue + no context words during the prompt
    def clue_text(self, guess: str | None = None, revealed: bool = False) -> str:
        return self._answer.clue_text(guess, revealed)

    def live_context(self) -> str:
        return ""

    @property
    def rating_time_threshold_s(self) -> int:
        return 5 + 1.5 * len(self._answer._valid_letters)
