from cards.card import Card

class SubstituteQuestionMarkCard(Card):
    def getDisplayTextWhenCorrect(self) -> str:
        return self.answer.text.replace("?", self.answer.text)

    def getDisplayTextWhenIncorrect(self, answer: str) -> str:
        return self.answer.text.replace("?", f"\x1b[9m{answer}\x1b[0m {self.answer.text}")
