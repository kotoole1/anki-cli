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


def _card(variant):
    return OscarCard(year=_YEAR, title=_TITLE, actors=_ACTORS, description=_DESC, variant=variant)


# ── OscarCard ─────────────────────────────────────────────────────────────────

def test_desc_card_id_ends_with_desc():
    assert _card("desc").id == f"{_YEAR}-desc"


def test_actors_card_id_ends_with_actors():
    assert _card("actors").id == f"{_YEAR}-actors"


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


def test_prompt_includes_year():
    for variant in ("desc", "actors"):
        text = _card(variant).getPrompt().getDisplayText()
        assert str(_YEAR) in text


def test_is_correct_matches_title():
    card = _card("desc")
    assert card.isCorrect("The Brutalist")
    assert card.isCorrect("brutalist")  # fuzzy
    assert not card.isCorrect("Oppenheimer")


# ── OscarCardSet ──────────────────────────────────────────────────────────────

def _csv_row_count():
    with open(_DATA_PATH, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def test_cardset_has_exactly_two_variants_per_year():
    cardset = OscarCardSet()
    assert len(cardset.cards) == _csv_row_count() * 2


def test_cardset_cards_alternate_desc_and_actors():
    cardset = OscarCardSet()
    variants = [c.variant for c in cardset.cards]
    # Each consecutive pair should be desc then actors for the same year
    for i in range(0, len(variants), 2):
        assert variants[i] == "desc"
        assert variants[i + 1] == "actors"


def test_new_card_order_starts_with_most_recent_year_desc():
    cardset = OscarCardSet()
    max_year = max(int(c.id.split("-")[0]) for c in cardset.cards)
    assert cardset.new_card_order[0] == f"{max_year}-desc"


def test_new_card_order_has_desc_block_before_actors_block():
    cardset = OscarCardSet()
    order = cardset.new_card_order
    # First 5 entries should all be desc (2025-2021 block)
    first_block_variants = [cid.split("-")[1] for cid in order[:5]]
    assert all(v == "desc" for v in first_block_variants)
    # Next 5 should all be actors
    second_block_variants = [cid.split("-")[1] for cid in order[5:10]]
    assert all(v == "actors" for cid in order[5:10]]


def test_new_card_order_length_equals_card_count():
    cardset = OscarCardSet()
    assert len(cardset.new_card_order) == len(cardset.cards)


def test_new_card_order_contains_all_card_ids():
    cardset = OscarCardSet()
    card_ids = {c.id for c in cardset.cards}
    order_ids = set(cardset.new_card_order)
    assert card_ids == order_ids


def test_cardset_rating_threshold_is_seven():
    assert OscarCardSet.rating_time_threshold_s == 7
