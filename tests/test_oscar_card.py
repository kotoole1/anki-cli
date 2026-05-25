"""Unit tests for OscarCard variant system and OscarCardSet."""

import csv
import os

import pytest

from oscars.OscarCard import OscarCard
from oscars.OscarCardSet import OscarCardSet

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "oscars", "data.csv")

_YEAR = 2025
_TITLE = "The Brutalist"
_ACTORS = ["Adrien Brody", "Felicity Jones"]
_DESC = "Hungarian Jewish architect rebuilds his life in postwar America"
_ADJ = "[2024: Anora, 2026: Unknown]"


def _card(variant):
    return OscarCard(year=_YEAR, title=_TITLE, actors=_ACTORS, description=_DESC,
                     variant=variant, adjacent_line=_ADJ)


# ── OscarCard ─────────────────────────────────────────────────────────────────

def test_desc_card_id_ends_with_desc():
    assert _card("desc").id == f"{_YEAR}-desc"


def test_actors_card_id_ends_with_actors():
    assert _card("actors").id == f"{_YEAR}-actors"


def test_year_card_id_ends_with_year():
    assert _card("year").id == f"{_YEAR}-year"


def test_desc_prompt_contains_description():
    text = _card("desc").getPrompt().getDisplayText()
    assert _DESC in text


def test_desc_prompt_does_not_contain_actors():
    text = _card("desc").getPrompt().getDisplayText()
    assert _ACTORS[0] not in text


def test_actors_prompt_contains_actor_name():
    text = _card("actors").getPrompt().getDisplayText()
    assert _ACTORS[0] in text


def test_actors_prompt_does_not_contain_description():
    text = _card("actors").getPrompt().getDisplayText()
    assert _DESC not in text


def test_year_prompt_contains_adjacent_line():
    """The year variant's only clue is the adjacent year context string."""
    text = _card("year").getPrompt().getDisplayText()
    assert _ADJ in text


def test_year_prompt_does_not_contain_description():
    text = _card("year").getPrompt().getDisplayText()
    assert _DESC not in text


def test_year_prompt_does_not_contain_actors():
    text = _card("year").getPrompt().getDisplayText()
    assert _ACTORS[0] not in text


def test_prompt_includes_year():
    for variant in ("desc", "actors", "year"):
        text = _card(variant).getPrompt().getDisplayText()
        assert str(_YEAR) in text


def test_answer_includes_adjacent_line_for_all_variants():
    """Adjacent year context appears in the answer for every variant."""
    for variant in ("desc", "actors", "year"):
        text = _card(variant).getAnswer().getDisplayText()
        assert _ADJ in text, f"adjacent_line missing from {variant} answer"


def test_is_correct_matches_title():
    card = _card("desc")
    assert card.isCorrect("The Brutalist")
    assert card.isCorrect("brutalist")  # fuzzy
    assert not card.isCorrect("Oppenheimer")


def test_glob_initials_include_article():
    # "tks*" should match "The King's Speech": initials of the full title are t,k,s
    # before this fix, _normalize stripped "the" so initials were only "ks"
    from oscars.OscarCard import OscarCard as OC
    card = OC(year=2010, title="The King's Speech",
              actors=["Colin Firth"], description="...", variant="desc")
    assert card.isCorrect("tks*")
    assert card.isCorrect("ks*")   # normalized initials still work too


# ── OscarCardSet ──────────────────────────────────────────────────────────────

def _csv_row_count():
    with open(_DATA_PATH, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def test_cardset_has_exactly_three_variants_per_year():
    cardset = OscarCardSet()
    assert len(cardset.cards) == _csv_row_count() * 3


def test_cardset_cards_cycle_desc_actors_year():
    """Cards are stored in (desc, actors, year) triples."""
    cardset = OscarCardSet()
    variants = [c.variant for c in cardset.cards]
    for i in range(0, len(variants), 3):
        assert variants[i]     == "desc"
        assert variants[i + 1] == "actors"
        assert variants[i + 2] == "year"


def test_cardset_adjacent_line_present_on_all_cards():
    """Every card should have a non-empty adjacent_line (all years have at least one neighbour)."""
    cardset = OscarCardSet()
    for card in cardset.cards:
        assert card._adjacent_line, f"empty adjacent_line on {card.id}"


def test_cardset_adjacent_line_format():
    """Adjacent line should be bracketed and contain at least one 'prev/next: Title (Year)' entry."""
    import re
    cardset = OscarCardSet()
    pattern = re.compile(r"\[(?:prev|next): .+ \(\d{4}\).*\]")
    for card in cardset.cards:
        assert pattern.match(card._adjacent_line), f"bad format on {card.id}: {card._adjacent_line!r}"


def test_new_card_order_starts_with_most_recent_year_desc():
    cardset = OscarCardSet()
    max_year = max(int(c.id.split("-")[0]) for c in cardset.cards)
    assert cardset.new_card_order[0] == f"{max_year}-desc"


def test_new_card_order_has_desc_block_before_actors_block():
    cardset = OscarCardSet()
    order = cardset.new_card_order
    first_block_variants = [cid.split("-")[1] for cid in order[:5]]
    assert all(v == "desc" for v in first_block_variants)
    second_block_variants = [cid.split("-")[1] for cid in order[5:10]]
    assert all(v == "actors" for v in second_block_variants)


def test_new_card_order_has_year_block_after_actors_block():
    """The year-variant sub-block follows actors within each 5-year period."""
    cardset = OscarCardSet()
    order = cardset.new_card_order
    third_block_variants = [cid.split("-")[1] for cid in order[10:15]]
    assert all(v == "year" for v in third_block_variants)


def test_new_card_order_length_equals_card_count():
    cardset = OscarCardSet()
    assert len(cardset.new_card_order) == len(cardset.cards)


def test_new_card_order_contains_all_card_ids():
    cardset = OscarCardSet()
    card_ids = {c.id for c in cardset.cards}
    order_ids = set(cardset.new_card_order)
    assert card_ids == order_ids


def test_cardset_rating_threshold_is_ten():
    assert OscarCardSet.rating_time_threshold_s == 10
