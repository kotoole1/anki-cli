import difflib
import random

from cards.cardPrompt import SimpleTextPrompt
from cards.cardAnswer import CardAnswer


class OscarCard:
    def __init__(self, year: int, title: str, actors: list[str], description: str, variant: str):
        self.id = f"{year}-{variant}"
        self.year = year
        self.variant = variant
        self._actors = actors
        self._description = description
        self._answer = OscarAnswer(year, title, actors, description)

    def getPrompt(self):
        clue = self._description if self.variant == "desc" else ", ".join(self._actors)
        return SimpleTextPrompt(self.id, f"{self.year}: {clue}")

    def getAnswer(self):
        return self._answer

    def isCorrect(self, answer: str) -> bool:
        return difflib.SequenceMatcher(None, answer.lower(), self._answer.title.lower()).ratio() > 0.8


class OscarAnswer(CardAnswer):
    def __init__(self, year: int, title: str, actors: list[str], description: str):
        self.year = year
        self.title = title
        self.actors = actors
        self.description = description
