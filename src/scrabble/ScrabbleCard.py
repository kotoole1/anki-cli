from collections import Counter

from cards.cardPrompt import SimpleTextPrompt
from cards.cardAnswer import CardAnswer

_RED    = "\033[91m"
_ORANGE = "\033[38;5;208m"
_PURPLE = "\033[95m"
_DIM    = "\033[2m"
_RESET  = "\033[0m"


class ScrabbleAnswer(CardAnswer):
    def __init__(self, alphagram: str, nwl_words: list, top20k: frozenset[str] = frozenset(),
                 ext_lookup=None):
        super().__init__(alphagram)
        self.nwl_words = nwl_words
        self._valid = {w.upper() for w, _ in nwl_words}
        self._alpha_counter = Counter(alphagram)
        self._top20k = top20k
        self._ext_lookup = ext_lookup

    def getDisplayText(self):
        return self._format_words()

    def getDisplayTextWhenCorrect(self):
        return self._format_words()

    def getDisplayTextWhenIncorrect(self):
        return self._format_words()

    def isCorrect(self, answer: str) -> bool:
        return answer.upper() in self._valid

    def getWrongAnswerFeedback(self, submitted: str) -> str:
        up = submitted.upper()
        sub_counter = Counter(up)

        if sub_counter == self._alpha_counter:
            return up  # valid anagram, just not a word

        excess  = sub_counter - self._alpha_counter
        missing = self._alpha_counter - sub_counter

        remaining = Counter(excess)
        colored = ""
        for letter in up:
            if remaining.get(letter, 0) > 0:
                if self._alpha_counter.get(letter, 0) > 0:
                    colored += f"{_ORANGE}{letter}{_RESET}"
                else:
                    colored += f"{_RED}{letter}{_RESET}"
                remaining[letter] -= 1
            else:
                colored += letter

        if missing:
            colored += f"  {_PURPLE}+{''.join(sorted(missing.elements()))}{_RESET}"

        return colored

    def _format_words(self) -> str:
        from wordfreq import word_frequency
        lines = []
        for word, defn in sorted(self.nwl_words, key=lambda w: word_frequency(w[0].lower(), 'en'), reverse=True):
            indicator = "▶" if word.lower() in self._top20k else "▷"
            defn_str = f"  {indicator} {_DIM}{defn}{_RESET}" if defn else f"  {indicator}"
            if self._ext_lookup is not None:
                left_sym, right_sym = self._ext_lookup.symbols(word)
                left_sym  = left_sym  or " "
                right_sym = right_sym or " "
            else:
                left_sym = right_sym = " "
            dim_l = "" if left_sym  == "+" else _DIM
            dim_r = "" if right_sym == "+" else _DIM
            lines.append(
                f"  {dim_l}{left_sym}{_RESET}{word}{dim_r}{right_sym}{_RESET}{defn_str}"
            )
        return "\n".join(lines) if lines else "  (no valid words)"


class ScrabbleCard:
    def __init__(self, id: str, alphagram: str, probability: float, nwl_words: list,
                 top20k: frozenset[str] = frozenset(), ext_lookup=None):
        self.id = id
        self.probability = probability
        self._prompt = SimpleTextPrompt(id, alphagram)
        self._answer = ScrabbleAnswer(alphagram, nwl_words, top20k, ext_lookup)

    def getPrompt(self):
        return self._prompt

    def getAnswer(self):
        return self._answer

    def isCorrect(self, answer: str) -> bool:
        return self._answer.isCorrect(answer)
