from cards.cardPrompt import SimpleTextPrompt
from cards.cardAnswer import CardAnswer


class ScrabbleAnswer(CardAnswer):
    def __init__(self, alphagram: str, nwl_words: list):
        super().__init__(alphagram)
        self.nwl_words = nwl_words
        self._valid = {w.upper() for w, _ in nwl_words}

    def getDisplayText(self):
        return self._format_words()

    def getDisplayTextWhenCorrect(self):
        return self._format_words()

    def getDisplayTextWhenIncorrect(self):
        return self._format_words()

    def isCorrect(self, answer: str) -> bool:
        return answer.upper() in self._valid

    def _format_words(self) -> str:
        lines = []
        for word, defn in sorted(self.nwl_words):
            defn_str = f"  {defn}" if defn else ""
            lines.append(f"  {word}{defn_str}")
        return "\n".join(lines) if lines else "  (no valid words)"


class ScrabbleCard:
    def __init__(self, id: str, alphagram: str, probability: float, nwl_words: list):
        self.id = id
        self.probability = probability
        self._prompt = SimpleTextPrompt(id, alphagram)
        self._answer = ScrabbleAnswer(alphagram, nwl_words)

    def getPrompt(self):
        return self._prompt

    def getAnswer(self):
        return self._answer

    def isCorrect(self, answer: str) -> bool:
        return self._answer.isCorrect(answer)
