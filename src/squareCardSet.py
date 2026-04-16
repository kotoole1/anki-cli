from cards.cardSet import CardSet
from QuestionMarkCard import SubstituteQuestionMarkCard

class SquareCardSet(CardSet):
    def __init__(self, max_number: int = 30):
        cards = [
            SubstituteQuestionMarkCard(id=str(x), simple_prompt_text=f"{x}² = ?", simple_answer_text=f"{x**2}")
            for x in range(1, max_number)
        ] + [
            SubstituteQuestionMarkCard(id=f"sqrt-{x}", simple_prompt_text=f"√{x**2} = ?", simple_answer_text=f"{x}")
            for x in range(1, max_number)
        ]
        super().__init__("squares-v1", "Squares", cards)
