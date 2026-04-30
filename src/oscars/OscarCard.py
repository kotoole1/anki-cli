import difflib
import random

from cards.cardPrompt import SimpleTextPrompt
from cards.cardAnswer import CardAnswer

_RED   = "\033[91m"
_RESET = "\033[0m"


def _normalize(s: str) -> str:
    s = s.lower().strip()
    for prefix in ("the ", "a ", "an "):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s


def _initials(title: str) -> str:
    return "".join(w[0] for w in title.split() if w)


def _is_fuzzy_match(answer: str, title: str) -> bool:
    a, t = _normalize(answer), _normalize(title)
    if not a:
        return False
    if a.endswith("*"):
        prefix = a[:-1]
        if len(prefix) < 2:
            return False
        return t.startswith(prefix) or _initials(t).startswith(prefix)
    if a in t or t in a:
        return True
    return difflib.SequenceMatcher(None, a, t).ratio() >= 0.75


class OscarAnswer(CardAnswer):
    def __init__(self, year: int, title: str, actors: list[str], description: str):
        super().__init__(str(year))
        self.title = title
        self.actors = actors
        self.description = description

    def getDisplayText(self):
        return self._format()

    def getDisplayTextWhenCorrect(self):
        return self._format()

    def getDisplayTextWhenIncorrect(self):
        return self._format()

    def isCorrect(self, answer: str) -> bool:
        return _is_fuzzy_match(answer, self.title)

    def getWrongAnswerFeedback(self, submitted: str) -> str:
        return f"{_RED}{submitted}{_RESET}"

    def _format(self) -> str:
        lines = [f"{self.title}"]
        if self.actors:
            lines.append(f"  {', '.join(self.actors)}")
        lines.append(f"  {self.description}")
        return "\n".join(lines)


class OscarCard:
    def __init__(self, year: int, title: str, actors: list[str], description: str):
        self.id = str(year)
        self.year = year
        self._actors = actors
        self._description = description
        self._answer = OscarAnswer(year, title, actors, description)

    def getPrompt(self):
        clues = []
        if self._actors:
            clues.append(", ".join(self._actors))
        if self._description:
            clues.append(self._description)
        clue = random.choice(clues) if clues else ""
        return SimpleTextPrompt(self.id, f"{self.year}: {clue}")

    def getAnswer(self):
        return self._answer

    def isCorrect(self, answer: str) -> bool:
        return self._answer.isCorrect(answer)
