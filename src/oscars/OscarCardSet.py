import csv
import os

from cards.cardSet import CardSet
from oscars.OscarCard import OscarCard


_DATA_PATH = os.path.join(os.path.dirname(__file__), "data.csv")


def _build_adjacent_lines(rows: list[dict]) -> dict[int, str]:
    """Build '[prev: prev_title (prev_year), next: next_title (next_year)]' for each year in rows."""
    year_title = {int(r["year"]): r["title"] for r in rows}
    years = sorted(year_title)
    result = {}
    for i, year in enumerate(years):
        parts = []
        if i > 0:
            py = years[i - 1]
            parts.append(f"prev: {year_title[py]} ({py})")
        if i < len(years) - 1:
            ny = years[i + 1]
            parts.append(f"next: {year_title[ny]} ({ny})")
        result[year] = f"[{', '.join(parts)}]"
    return result


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
        for year in block_years:
            order.append(f"{year}-year")
    return order


class OscarCardSet(CardSet):
    rating_time_threshold_s = 10

    def __init__(self, start_year: int = 1928, end_year: int = 2026):
        rows = []
        with open(_DATA_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                year = int(row["year"])
                if start_year <= year <= end_year:
                    rows.append(row)

        adjacent = _build_adjacent_lines(rows)
        cards = []
        for row in rows:
            year = int(row["year"])
            actors = [a.strip() for a in row["actors"].split("|") if a.strip()]
            adj = adjacent[year]
            kwargs = dict(year=year, title=row["title"], actors=actors,
                          description=row["description"], adjacent_line=adj)
            cards.append(OscarCard(**kwargs, variant="desc"))
            cards.append(OscarCard(**kwargs, variant="actors"))
            cards.append(OscarCard(**kwargs, variant="year"))

        super().__init__("oscars", "Oscar Best Pictures", cards)
        self.new_card_order = _build_new_card_order(rows)
