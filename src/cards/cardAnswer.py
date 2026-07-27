from abc import ABC, abstractmethod

class CardAnswer(ABC):
    def __init__(self, id: str):
        self.id = id

    @abstractmethod
    def getDisplayText(self):
        pass

    def getWrongAnswerFeedback(self, submitted: str) -> str:
        return submitted.upper()

    def isValid(self, answer: str) -> bool:
        """Whether `answer` is a submittable attempt worth scoring at all.

        Submissions that are not valid are *rejected* by the study loop before
        scoring: it shows getInvalidFeedback() and re-prompts on the same card
        without recording an FSRS result, treating the keystrokes like
        pre-submission typing. Empty input is never invalid — the caller always
        scores it as a wrong answer (the simple "I don't know").

        Default: every submission is valid. Override to add a notion of
        well-formed-but-possibly-wrong input (e.g. an anagram of a rack).
        """
        return True

    def getInvalidFeedback(self, submitted: str) -> str:
        """Single line shown when a submission is rejected by isValid()."""
        return self.getWrongAnswerFeedback(submitted)

class SimpleTextAnswer(CardAnswer):
    def __init__(self, id: str, text: str):
        super().__init__(id)
        self.text = text

    def getDisplayText(self):
        return self.text

    def getDisplayTextWhenCorrect(self):
        return self.text

    def getDisplayTextWhenIncorrect(self):
        return self.text

    def isCorrect(self, answer: str):
        return self.text == answer
