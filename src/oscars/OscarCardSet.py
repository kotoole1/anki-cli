import csv
import os


def _build_new_card_order(rows: list[dict]) -> list[str]:
    years = sorted({int(r["year"]) for r in rows}, reverse=True)
    max_year = years[0]
    block_map: dict[int, list[int]] = {}
    for year in years:
        block_idx = (max_year - year) // 5
        block_map.setdefault(block_idx, []).append(year)

    order = []
    for block_idx in sorted(block_map):
        block_years = sorted(block_map[block_idx], reverse=True)
        for year in block_years:
            order.append(f"{year}-desc")
        for year in block_years:
            order.append(f"{year}-actors")
    return order


class OscarCardSet(CardSet):
    rating_time_threshold_s = 7

    def __init__(self, start_year: int = 1928, end_year: int = 2026):
        cards = []
        rows = []
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
                    rows.append(row)

        cards = []
        for row in rows:
            year = int(row["year"])
            actors = [a.strip() for a in row["actors"].split("|") if a.strip()]
            kwargs = dict(year=year, title=row["title"], actors=actors, description=row["description"])
            cards.append(OscarCard(**kwargs, variant="desc"))
            cards.append(OscarCard(**kwargs, variant="actors"))

        super().__init__("oscars", "Oscar Best Pictures", cards)
        self.new_card_order = _build_new_card_order(rows)
