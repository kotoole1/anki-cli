import csv
import os

from cards.cardSet import CardSet
from oscars.OscarCard import OscarCard

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data.csv")


class OscarCardSet(CardSet):
    def __init__(self, start_year: int = 1928, end_year: int = 2026):
        cards = []
        with open(_DATA_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                year = int(row["year"])
                if start_year <= year <= end_year:
                    actors = [a.strip() for a in row["actors"].split("|") if a.strip()]
                    cards.append(OscarCard(
                        year=year,
                        title=row["title"],
                        actors=actors,
                        description=row["description"],
                    ))
        super().__init__("oscars", "Oscar Best Pictures", cards)
