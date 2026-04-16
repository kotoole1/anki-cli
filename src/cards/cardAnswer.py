from abc import ABC, abstractmethod

class CardAnswer(ABC):
    def __init__(self, id: str):
        self.id = id

    @abstractmethod
    def getDisplayText(self):
        pass

    def getWrongAnswerFeedback(self, submitted: str) -> str:
        return submitted.upper()
    
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
