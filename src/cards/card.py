from cards.cardPrompt import SimpleTextPrompt
from cards.cardAnswer import SimpleTextAnswer

class Card:
    def __init__(self, id: str, simple_prompt_text: str, simple_answer_text: str):
        self.id = id
        self.prompt = SimpleTextPrompt(id, simple_prompt_text)
        self.answer = SimpleTextAnswer(id, simple_answer_text)


