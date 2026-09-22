from cards.cardPrompt import SimpleTextPrompt
from cards.cardAnswer import CardAnswer
from cards.textMatch import fuzzy_title_match

_RED   = "\033[91m"
_RESET = "\033[0m"


class OscarAnswer(CardAnswer):
    def __init__(self, year: int, title: str, actors: list[str], description: str, adjacent_line: str = ""):
        super().__init__(str(year))
        self.title = title
        self.actors = actors
        self.description = description
        self.adjacent_line = adjacent_line

    def getDisplayText(self):
        return self._format()

    def getDisplayTextWhenCorrect(self):
        return self._format()

    def getDisplayTextWhenIncorrect(self):
        return self._format()

    def isCorrect(self, answer: str) -> bool:
        return fuzzy_title_match(answer, self.title)

    def getWrongAnswerFeedback(self, submitted: str) -> str:
        return f"{_RED}{submitted}{_RESET}"

    def _format(self) -> str:
        lines = [self.title]
        if self.actors:
            lines.append(f"  {', '.join(self.actors)}")
        lines.append(f"  {self.description}")
        if self.adjacent_line:
            lines.append(f"  {self.adjacent_line}")
        return "\n".join(lines)


class OscarCard:
    def __init__(self, year: int, title: str, actors: list[str], description: str, variant: str, adjacent_line: str = ""):
        self.id = f"{year}-{variant}"
        self.year = year
        self.variant = variant
        self._actors = actors
        self._description = description
        self._adjacent_line = adjacent_line
        self._answer = OscarAnswer(year, title, actors, description, adjacent_line)

    def getPrompt(self):
        if self.variant == "desc":
            clue = self._description
        elif self.variant == "actors":
            clue = ", ".join(self._actors)
        else:  # "year"
            clue = "?? " + self._adjacent_line
        return SimpleTextPrompt(self.id, f"{self.year}: {clue}")

    def getAnswer(self):
        return self._answer

    def isCorrect(self, answer: str) -> bool:
        return self._answer.isCorrect(answer)
