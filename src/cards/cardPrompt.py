from abc import ABC, abstractmethod

class CardPrompt(ABC):
    def __init__(self, id: str):
        self.id = id

    @abstractmethod
    def getDisplayText(self):
        pass

class SimpleTextPrompt(CardPrompt):
    def __init__(self, id: str, text: str):
        super().__init__(id)
        self.text = text

    def getDisplayText(self):
        return self.text

