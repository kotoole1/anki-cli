"""Extension card type for single-letter NWL extension drills."""

from cards.cardPrompt import SimpleTextPrompt
from cards.cardAnswer import CardAnswer

_RED    = "\033[91m"
_PURPLE = "\033[95m"
_DIM    = "\033[2m"
_RESET  = "\033[0m"


class ExtensionAnswer(CardAnswer):
    def __init__(self, card_id: str, valid_letters: frozenset[str],
                 valid_words: list[tuple[str, str]], ext_lookup=None):
        super().__init__(card_id)
        self._valid_letters = valid_letters
        self._valid_words = valid_words  # [(word, definition), ...]
        self._ext_lookup = ext_lookup
        self.nwl_words = valid_words
        self._is_right = card_id.endswith("-right")
        self._missed_words: frozenset[str] = frozenset(w for w, _ in valid_words)
        from wordfreq import word_frequency
        self._words_sorted = sorted(
            valid_words, key=lambda w: word_frequency(w[0].lower(), 'en'), reverse=True
        )

    def _ext_letter(self, word: str) -> str:
        return word[-1] if self._is_right else word[0]

    def _render(self, missed_words: frozenset[str]) -> str:
        if not self._valid_letters:
            return "  No valid extensions"
        letters_str = "".join(sorted(self._valid_letters))
        lines = [f"  {letters_str}"]
        for word, defn in self._words_sorted:
            if self._ext_lookup and len(word) < 5:
                ls, rs = self._ext_lookup.symbols(word)
                lpfx = f"{_DIM}{ls or ' '}{_RESET}"
                rsuf = f"{_DIM}{rs or ' '}{_RESET}"
            else:
                lpfx = " "
                rsuf = " "
            w_str = f"{_PURPLE}{word}{_RESET}" if word in missed_words else word
            d = f"  {_DIM}{defn}{_RESET}" if defn else ""
            lines.append(f"  {lpfx}{w_str}{rsuf}{d}")
        return "\n".join(lines)

    def getDisplayText(self) -> str:
        return self._render(frozenset())

    def getDisplayTextWhenCorrect(self) -> str:
        return self._render(frozenset())

    def getDisplayTextWhenIncorrect(self) -> str:
        return self._render(self._missed_words)

    def isCorrect(self, answer: str) -> bool:
        return set(answer.upper()) == self._valid_letters

    def getWrongAnswerFeedback(self, submitted: str) -> str:
        up = submitted.upper()
        given   = set(up)
        extra   = given - self._valid_letters
        missing = self._valid_letters - given
        self._missed_words = frozenset(
            w for w, _ in self._valid_words if self._ext_letter(w) in missing
        )

        colored = ""
        for letter in up:
            colored += f"{_RED}{letter}{_RESET}" if letter in extra else letter

        if missing:
            colored += f"  {_PURPLE}+{''.join(sorted(missing))}{_RESET}"

        return colored


class ExtensionCard:
    def __init__(self, card_id: str, prompt_text: str, valid_letters: frozenset[str],
                 valid_words: list[tuple[str, str]], ext_lookup=None):
        self.id = card_id
        self._prompt = SimpleTextPrompt(card_id, prompt_text)
        self._answer = ExtensionAnswer(card_id, valid_letters, valid_words, ext_lookup)

    def getPrompt(self):
        return self._prompt

    def getAnswer(self):
        return self._answer

    def isCorrect(self, answer: str) -> bool:
        return self._answer.isCorrect(answer)

    @property
    def rating_time_threshold_s(self) -> int:
        return 5 + 1.5 * len(self._answer._valid_letters)
