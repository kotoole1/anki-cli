

"""
A collection of cards which are learned as a group. Users chose which card set to study when,
while an algorithm (anki or ours) decides which cards to show when within that card set.
"""
class CardSet:
    def __init__(self, id: str, name: str, cards: list[Card]):
        self.id = id
        self.name = name
        self.cards = cards

