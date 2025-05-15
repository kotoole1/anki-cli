from abc import ABC, abstractmethod

class CardAnswer(ABC):
    def __init__(self, id: str):
        self.id = id

    def getDisplayText(self):
        return self.answer_text
    
class SimpleTextAnswer(CardAnswer):
    def __init__(self, id: str, text: str):
        super().__init__(id)
        self.text = text

    def getDisplayTextWhenCorrect(self):
        return self.text

    def getDisplayTextWhenIncorrect(self):
        return self.text

    def isCorrect(self, answer: str):
        return self.text == answer
