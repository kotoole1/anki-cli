import random
from cards.card import Card

class CardSet:
    """
    A collection of cards which are learned as a group. Users chose which set to study when,
    while an algorithm (anki or local) decides which cards to show when within that card set.
    """
    def __init__(self, id: str, name: str, cards: list[Card]):
        self.id = id
        self.name = name
        self.cards = cards

    def getNextCard(self) -> Card:
        return random.choice(self.cards) # TODO: source this from anki
