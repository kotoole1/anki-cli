"""Extension card type for single-letter NWL extension drills.

Legacy: this "type every valid extension at once" card now backs only the
*-legacy sets. The atomic per-extension replacement is AcClozeExtensionCard.
TODOCC: once all extension sets are converted to cloze cards, this multi-answer
feedback/rendering becomes dead and can be removed.

Completion colours (shared with the batched set): green = answer you gave,
purple = answer you missed, red = a letter you wrongly added.
"""

from cards.cardPrompt import SimpleTextPrompt
from cards.cardAnswer import CardAnswer
from scrabble.ScrabbleCard import _commonness_indicator

_RED    = "\033[91m"
_GREEN  = "\033[92m"
_PURPLE = "\033[95m"
_DIM    = "\033[2m"
_RESET  = "\033[0m"


class ExtensionAnswer(CardAnswer):
    diff_on_blank = True   # a blank "idk" still shows the +missing diff

    def __init__(self, card_id: str, valid_letters: frozenset[str],
                 valid_words: list[tuple[str, str]], ext_lookup=None,
                 top20k: frozenset[str] = frozenset(),
                 top50k: frozenset[str] = frozenset()):
        super().__init__(card_id)
        self._valid_letters = valid_letters
        self._valid_words = valid_words  # [(word, definition), ...]
        self._ext_lookup = ext_lookup
        self._top20k = top20k
        self._top50k = top50k
        self.nwl_words = valid_words
        self._is_right = card_id.endswith("-right")
        self._last_guess: frozenset[str] = frozenset()
        from wordfreq import word_frequency
        self._words_sorted = sorted(
            valid_words, key=lambda w: word_frequency(w[0].lower(), 'en'), reverse=True
        )

    def _ext_letter(self, word: str) -> str:
        return word[-1] if self._is_right else word[0]

    def _render(self, guess) -> str:
        """Word list. `guess` is the set of letters the user gave (green = you
        got it, purple = you missed it), or None before an answer (plain)."""
        if not self._valid_letters:
            return "  No valid extensions"
        lines = [f"  {''.join(sorted(self._valid_letters))}"]
        for word, defn in self._words_sorted:
            if self._ext_lookup and len(word) < 5:
                # Extension symbols stay dim: the recall signal is the word itself.
                ls, rs = self._ext_lookup.symbols(word)
                lpfx = f"{_DIM}{ls or ' '}{_RESET}"
                rsuf = f"{_DIM}{rs or ' '}{_RESET}"
            else:
                lpfx = rsuf = " "
            if guess is None:
                w_str = word
            elif self._ext_letter(word) in guess:
                w_str = f"{_GREEN}{word}{_RESET}"
            else:
                w_str = f"{_PURPLE}{word}{_RESET}"
            indicator = _commonness_indicator(word, self._top20k, self._top50k)
            d = f"  {indicator} {_DIM}{defn}{_RESET}" if defn else f"  {indicator}"
            lines.append(f"  {lpfx}{w_str}{rsuf}{d}")
        return "\n".join(lines)

    def getDisplayText(self) -> str:
        return self._render(None)

    def getDisplayTextWhenCorrect(self) -> str:
        return self._render(self._valid_letters)

    def getDisplayTextWhenIncorrect(self) -> str:
        return self._render(self._last_guess)

    def isCorrect(self, answer: str) -> bool:
        self._last_guess = frozenset(c for c in answer.upper() if c.isalpha())
        return self._last_guess == self._valid_letters

    def getWrongAnswerFeedback(self, submitted: str) -> str:
        given   = frozenset(c for c in submitted.upper() if c.isalpha())
        correct = given & self._valid_letters
        missing = self._valid_letters - given
        extra   = given - self._valid_letters
        # green = right, +purple = missed, -red = wrongly added. e.g. "AB +CD -X".
        parts = []
        if correct:
            parts.append(f"{_GREEN}{''.join(sorted(correct))}{_RESET}")
        if missing:
            parts.append(f"{_PURPLE}+{''.join(sorted(missing))}{_RESET}")
        if extra:
            parts.append(f"{_RED}-{''.join(sorted(extra))}{_RESET}")
        return "  " + " ".join(parts) if parts else ""


class ExtensionCard:
    def __init__(self, card_id: str, prompt_text: str, valid_letters: frozenset[str],
                 valid_words: list[tuple[str, str]], ext_lookup=None,
                 top20k: frozenset[str] = frozenset(),
                 top50k: frozenset[str] = frozenset()):
        self.id = card_id
        self._prompt = SimpleTextPrompt(card_id, prompt_text)
        self._answer = ExtensionAnswer(card_id, valid_letters, valid_words, ext_lookup,
                                       top20k, top50k)

    def getPrompt(self):
        return self._prompt

    def getAnswer(self):
        return self._answer

    def isCorrect(self, answer: str) -> bool:
        return self._answer.isCorrect(answer)

    @property
    def rating_time_threshold_s(self) -> int:
        return 5 + 1.5 * len(self._answer._valid_letters)
