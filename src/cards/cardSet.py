import random
from cards.card import Card


class CardSet:
    """
    A collection of cards learned as a group. An algorithm decides which cards
    to show within the set.
    """
    # Anki deck option hints for a future export script.
    # These reflect Anki's defaults and have NOT been tuned for any specific card set.
    rating_time_threshold_s: int = 7
    new_card_order: list = []
    desired_retention: float = 0.9
    new_cards_per_day: int = 5
    learning_steps: list = ["1m", "10m"]
    relearning_steps: list = ["10m"]

    def __init__(self, id: str, name: str, cards: list[Card]):
        self.id = id
        self.name = name
        self.cards = cards

    def getNextCard(self) -> Card:
        return random.choice(self.cards)

    def anki_tags(self) -> list[str]:
        return [f"anki-cli::threshold={self.rating_time_threshold_s}"]
