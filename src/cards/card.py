from cards.cardPrompt import CardPrompt, SimpleTextPrompt
from cards.cardAnswer import CardAnswer, SimpleTextAnswer

class Card:
    def __init__(self, id: str, simple_prompt_text: str, simple_answer_text: str):
        self.id = id
        self.prompt = SimpleTextPrompt(id, simple_prompt_text)
        self.answer = SimpleTextAnswer(id, simple_answer_text)

    def getPrompt(self) -> CardPrompt:
        return self.prompt
    
    def getAnswer(self) -> CardAnswer:
        return self.answer
    
    def isCorrect(self, answer: str) -> bool:
        return self.answer.isCorrect(answer)
