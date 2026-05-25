"""
Tests for AcReviewStore and AcScheduler.

Key design note on state values (py-fsrs 6.3.1):
  state=1  Learning   — new card still being drilled (Again/Hard/Good keep it here)
  state=2  Review     — graduated card with long-interval FSRS scheduling
  state=3  Relearning — Review card that lapsed (Again from Review state)

First-review stabilities (py-fsrs defaults used as calibration anchors):
  Again → 0.212 d   Hard → 1.293 d   Good → 2.307 d   Easy → 8.296 d (→ state=2)
"""

import json
import math
from datetime import datetime, timezone, timedelta

import pytest

from memory.AcReviewStore import AcReviewStore
from memory.AcScheduler import (
    AcScheduler,
    compute_deck_stats,
    NEW_CARD_WEIGHT,
    _DRIP_WEIGHT,
    _LEARNING_SCALE,
    _AGAIN_STABILITY_DAYS,
)
from fsrs import Rating

_UTC = timezone.utc

# First-review stabilities as measured from py-fsrs 6.3.1.
# Used in tests that verify the FSRS shape is preserved across ratings.
_HARD_STABILITY_DAYS = 1.2931
_GOOD_STABILITY_DAYS = 2.3065


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeCard:
    def __init__(self, card_id):
        self.id = card_id


class _FakeCardSet:
    def __init__(self, card_ids, new_card_order=None, threshold=7):
        self.id = "test"
        self.cards = [_FakeCard(cid) for cid in card_ids]
        self.new_card_order = new_card_order if new_card_order is not None else card_ids
        self.rating_time_threshold_s = threshold


def _store_with_review(tmp_path, card_id, stability, days_ago, state=2):
    """Save a minimal FSRS card state. state=2 (Review) by default."""
    last_review = (datetime.now(_UTC) - timedelta(days=days_ago)).isoformat()
    data = {
        "cardset_id": "test",
        "cards": {
            card_id: {
                "card_id": 0,
                "state": state,
                "step": 0,
                "stability": stability,
                "difficulty": 5.0,
                "due": last_review,
                "last_review": last_review,
                "reviews": [],
            }
        },
    }
    store = AcReviewStore(str(tmp_path))
    store.save("test", data)
    return store


def _minutes_to_days(minutes: float) -> float:
    return minutes / 1440.0


# ── AcReviewStore ─────────────────────────────────────────────────────────────

def test_load_missing_file_returns_empty(tmp_path):
    """A missing JSON file should return an empty-cards structure, not raise."""
    store = AcReviewStore(str(tmp_path))
    assert store.load("missing") == {"cardset_id": "missing", "cards": {}}


def test_save_then_load_roundtrips(tmp_path):
    """Saving a state dict and reloading it should return the exact same structure."""
    store = AcReviewStore(str(tmp_path))
    state = {"cardset_id": "abc", "cards": {"x-desc": {"stability": 3.5}}}
    store.save("abc", state)
    assert store.load("abc") == state


def test_save_is_atomic_no_tmp_file_remains(tmp_path):
    """save() uses a tmp-then-rename pattern; no .tmp file should be left after a successful write."""
    store = AcReviewStore(str(tmp_path))
    store.save("abc", {"cardset_id": "abc", "cards": {}})
    assert not list(tmp_path.glob("*.tmp"))


def test_save_produces_valid_json(tmp_path):
    """The written file must be valid JSON that round-trips correctly."""
    store = AcReviewStore(str(tmp_path))
    store.save("abc", {"cardset_id": "abc", "cards": {"k": {"v": 1}}})
    parsed = json.loads((tmp_path / "abc.json").read_text())
    assert parsed["cards"]["k"]["v"] == 1


# ── AcScheduler — new-card drip ───────────────────────────────────────────────

def test_first_new_card_gets_full_weight(tmp_path):
    """The first card in new_card_order gets NEW_CARD_WEIGHT; it should dominate unseen cards."""
    store = AcReviewStore(str(tmp_path))
    sched = AcScheduler(_FakeCardSet(["a", "b"], new_card_order=["a", "b"]), store)
    assert sched._urgency("a") == pytest.approx(NEW_CARD_WEIGHT)


def test_non_first_new_card_gets_drip_weight(tmp_path):
    """Out-of-order unseen cards get _DRIP_WEIGHT so the scheduler respects introduction order."""
    store = AcReviewStore(str(tmp_path))
    sched = AcScheduler(_FakeCardSet(["a", "b"], new_card_order=["a", "b"]), store)
    assert sched._urgency("b") == pytest.approx(_DRIP_WEIGHT)


def test_no_new_card_order_all_unseen_get_full_weight(tmp_path):
    """When no ordering is defined, all unseen cards are equal candidates."""
    store = AcReviewStore(str(tmp_path))
    sched = AcScheduler(_FakeCardSet(["a", "b"], new_card_order=[]), store)
    assert sched._urgency("a") == pytest.approx(NEW_CARD_WEIGHT)
    assert sched._urgency("b") == pytest.approx(NEW_CARD_WEIGHT)


# ── AcScheduler — fallbacks ───────────────────────────────────────────────────

def test_card_with_missing_stability_gets_fallback_weight(tmp_path):
    """Incomplete FSRS state (stability=None) should return NEW_CARD_WEIGHT, not crash."""
    store = AcReviewStore(str(tmp_path))
    store.save("test", {"cardset_id": "test", "cards": {
        "a": {"last_review": datetime.now(_UTC).isoformat(), "stability": None}
    }})
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    assert sched._urgency("a") == pytest.approx(NEW_CARD_WEIGHT)


def test_card_with_missing_last_review_gets_fallback_weight(tmp_path):
    """Incomplete FSRS state (last_review=None) should return NEW_CARD_WEIGHT, not crash."""
    store = AcReviewStore(str(tmp_path))
    store.save("test", {"cardset_id": "test", "cards": {
        "a": {"last_review": None, "stability": 4.0}
    }})
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    assert sched._urgency("a") == pytest.approx(NEW_CARD_WEIGHT)


# ── AcScheduler — Review-state urgency (standard FSRS formula) ────────────────

def test_review_card_just_reviewed_has_near_zero_urgency(tmp_path):
    """Right after any review, retention ≈ 1 so urgency ≈ 0. Card should not immediately recur."""
    store = _store_with_review(tmp_path, "a", stability=4.0,
                               days_ago=_minutes_to_days(5), state=2)
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    assert sched._urgency("a") < 0.001


def test_review_urgency_3_days_stability_2(tmp_path):
    """Concrete expected value: 3 days elapsed with stability=2 should give specific urgency."""
    store = _store_with_review(tmp_path, "a", stability=2.0, days_ago=3, state=2)
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    expected = 1.0 - math.exp(math.log(0.9) * 3 / 2)
    assert sched._urgency("a") == pytest.approx(expected, rel=1e-3)


def test_review_urgency_3_days_stability_20(tmp_path):
    """High-stability Review card should have very low urgency even after 3 days."""
    store = _store_with_review(tmp_path, "a", stability=20.0, days_ago=3, state=2)
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    expected = 1.0 - math.exp(math.log(0.9) * 3 / 20)
    assert sched._urgency("a") == pytest.approx(expected, rel=1e-3)
    assert sched._urgency("a") < 0.02


# ── AcScheduler — Learning-state urgency (compressed time axis) ───────────────

def test_learning_card_urgency_near_zero_immediately_after_review(tmp_path):
    """
    A Learning-state card reviewed 0 seconds ago has urgency ≈ 0.
    Even a failed card shouldn't be immediately re-shown — there's a brief
    retention window (the card was just seen).
    """
    store = _store_with_review(tmp_path, "a", stability=_AGAIN_STABILITY_DAYS,
                               days_ago=0.0, state=1)
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    assert sched._urgency("a") < 0.001


def test_learning_again_urgency_equals_new_card_weight_at_one_minute(tmp_path):
    """
    _LEARNING_SCALE is calibrated so that an Again card (stability = _AGAIN_STABILITY_DAYS)
    reaches exactly NEW_CARD_WEIGHT at t = 1 minute. This is the design reference point:
    a recently-failed card competes with new cards after 1 minute, not before.
    """
    store = _store_with_review(tmp_path, "a", stability=_AGAIN_STABILITY_DAYS,
                               days_ago=_minutes_to_days(1), state=1)
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    assert sched._urgency("a") == pytest.approx(NEW_CARD_WEIGHT, abs=1e-4)


def test_learning_again_urgency_below_threshold_before_one_minute(tmp_path):
    """
    An Again card reviewed 30 seconds ago should NOT yet beat new cards.
    The 1-minute threshold ensures we don't immediately re-show a just-failed card.
    """
    store = _store_with_review(tmp_path, "a", stability=_AGAIN_STABILITY_DAYS,
                               days_ago=_minutes_to_days(0.5), state=1)
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    assert sched._urgency("a") < NEW_CARD_WEIGHT


def test_learning_again_urgency_above_threshold_after_one_minute(tmp_path):
    """
    An Again card reviewed 2 minutes ago should beat new cards.
    The scheduler should prioritize re-drilling a recently-failed card.
    """
    store = _store_with_review(tmp_path, "a", stability=_AGAIN_STABILITY_DAYS,
                               days_ago=_minutes_to_days(2), state=1)
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    assert sched._urgency("a") > NEW_CARD_WEIGHT


def test_learning_hard_urgency_lower_than_again_at_same_time(tmp_path):
    """
    FSRS shape preserved: Hard stability > Again stability, so Hard urgency < Again urgency
    at the same elapsed time. Answering Hard means you know it better than Again.
    """
    store_again = _store_with_review(tmp_path / "again", "a", stability=_AGAIN_STABILITY_DAYS,
                                     days_ago=_minutes_to_days(1), state=1)
    store_hard = _store_with_review(tmp_path / "hard", "a", stability=_HARD_STABILITY_DAYS,
                                    days_ago=_minutes_to_days(1), state=1)
    sched_again = AcScheduler(_FakeCardSet(["a"]), store_again)
    sched_hard  = AcScheduler(_FakeCardSet(["a"]), store_hard)
    assert sched_again._urgency("a") > sched_hard._urgency("a")


def test_learning_good_urgency_lower_than_hard_at_same_time(tmp_path):
    """
    FSRS shape preserved: Good stability > Hard stability, so Good urgency < Hard urgency.
    A correct answer raises stability and reduces same-session urgency.
    """
    store_hard = _store_with_review(tmp_path / "hard", "a", stability=_HARD_STABILITY_DAYS,
                                    days_ago=_minutes_to_days(2), state=1)
    store_good = _store_with_review(tmp_path / "good", "a", stability=_GOOD_STABILITY_DAYS,
                                    days_ago=_minutes_to_days(2), state=1)
    sched_hard = AcScheduler(_FakeCardSet(["a"]), store_hard)
    sched_good = AcScheduler(_FakeCardSet(["a"]), store_good)
    assert sched_hard._urgency("a") > sched_good._urgency("a")


def test_learning_urgency_higher_than_review_for_same_stability_and_elapsed(tmp_path):
    """
    A Learning-state card has strictly higher urgency than a Review-state card with
    identical stability and elapsed time, because _LEARNING_SCALE compresses the time axis.
    This is the mechanism that causes recently-drilled cards to resurface faster.
    """
    stability = 2.0
    days_ago = _minutes_to_days(2)
    store_learning = _store_with_review(tmp_path / "l", "a", stability=stability,
                                        days_ago=days_ago, state=1)
    store_review   = _store_with_review(tmp_path / "r", "a", stability=stability,
                                        days_ago=days_ago, state=2)
    sched_l = AcScheduler(_FakeCardSet(["a"]), store_learning)
    sched_r = AcScheduler(_FakeCardSet(["a"]), store_review)
    assert sched_l._urgency("a") > sched_r._urgency("a")


def test_relearning_state_uses_same_fast_decay_as_learning(tmp_path):
    """
    Relearning cards (state=3, a lapsed Review card) should decay at the same
    compressed rate as Learning cards, not at the slow Review rate. A lapsed card
    needs to be re-drilled on a minutes timescale just like a new card.
    """
    stability = _AGAIN_STABILITY_DAYS
    days_ago = _minutes_to_days(1)
    store_learning    = _store_with_review(tmp_path / "l", "a", stability=stability,
                                           days_ago=days_ago, state=1)
    store_relearning  = _store_with_review(tmp_path / "rl", "a", stability=stability,
                                           days_ago=days_ago, state=3)
    sched_l  = AcScheduler(_FakeCardSet(["a"]), store_learning)
    sched_rl = AcScheduler(_FakeCardSet(["a"]), store_relearning)
    assert sched_l._urgency("a") == pytest.approx(sched_rl._urgency("a"), abs=1e-3)


def test_learning_urgency_rises_monotonically(tmp_path):
    """Urgency must increase strictly over time for a Learning card."""
    times_minutes = [0.1, 0.5, 1.0, 2.0, 5.0]
    urgencies = []
    for t in times_minutes:
        store = _store_with_review(tmp_path / f"t{t}", "a", stability=_AGAIN_STABILITY_DAYS,
                                   days_ago=_minutes_to_days(t), state=1)
        sched = AcScheduler(_FakeCardSet(["a"]), store)
        urgencies.append(sched._urgency("a"))
    assert urgencies == sorted(urgencies), f"urgency not monotone: {urgencies}"


# ── AcScheduler — inferRating ─────────────────────────────────────────────────

def test_infer_easy_when_glob_and_fast(tmp_path):
    """Glob shorthand + fast response = Easy: user clearly knew the answer."""
    sched = AcScheduler(_FakeCardSet(["a"]), AcReviewStore(str(tmp_path)))
    assert sched.inferRating(elapsed_s=4, used_glob=True) == Rating.Easy


def test_infer_hard_when_slow(tmp_path):
    """Slow response (> threshold) = Hard even without glob shorthand."""
    sched = AcScheduler(_FakeCardSet(["a"]), AcReviewStore(str(tmp_path)))
    assert sched.inferRating(elapsed_s=10, used_glob=False) == Rating.Hard


def test_infer_good_when_normal(tmp_path):
    """Fast correct response without glob = Good."""
    sched = AcScheduler(_FakeCardSet(["a"]), AcReviewStore(str(tmp_path)))
    assert sched.inferRating(elapsed_s=3, used_glob=False) == Rating.Good


def test_infer_hard_when_glob_but_slow(tmp_path):
    """Glob shorthand + slow = Hard, not Easy. Speed matters even with shorthand."""
    sched = AcScheduler(_FakeCardSet(["a"]), AcReviewStore(str(tmp_path)))
    assert sched.inferRating(elapsed_s=10, used_glob=True) == Rating.Hard


def test_infer_uses_cardset_threshold(tmp_path):
    """The threshold is per-cardset; a lower threshold makes more answers Hard."""
    sched = AcScheduler(_FakeCardSet(["a"], threshold=3), AcReviewStore(str(tmp_path)))
    assert sched.inferRating(elapsed_s=4, used_glob=False) == Rating.Hard
    assert sched.inferRating(elapsed_s=2, used_glob=False) == Rating.Good


def test_infer_easy_requires_glob(tmp_path):
    """Easy is never auto-inferred without glob — a fast answer without shorthand is Good.
    Scrabble words never end with *, so Easy is never auto-rated there."""
    sched = AcScheduler(_FakeCardSet(["a"]), AcReviewStore(str(tmp_path)))
    assert sched.inferRating(elapsed_s=0.5, used_glob=False) == Rating.Good


# ── AcScheduler — recordResult ────────────────────────────────────────────────

def test_record_result_populates_stability(tmp_path):
    """After recordResult, the stored card must have a non-None stability from FSRS."""
    store = AcReviewStore(str(tmp_path))
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    sched.recordResult(_FakeCard("a"), Rating.Good, elapsed_s=3.0)
    assert store.load("test")["cards"]["a"]["stability"] is not None


def test_record_result_appends_review_entry(tmp_path):
    """Each recordResult call appends one entry to the reviews list with rating and elapsed."""
    store = AcReviewStore(str(tmp_path))
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    sched.recordResult(_FakeCard("a"), Rating.Good, elapsed_s=3.5)
    card_data = store.load("test")["cards"]["a"]
    assert len(card_data["reviews"]) == 1
    assert card_data["reviews"][0]["rating"] == Rating.Good.value
    assert card_data["reviews"][0]["response_time_s"] == pytest.approx(3.5)


def test_record_result_twice_appends_two_entries(tmp_path):
    """Two calls to recordResult should accumulate two review entries, not overwrite."""
    store = AcReviewStore(str(tmp_path))
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    sched.recordResult(_FakeCard("a"), Rating.Good, elapsed_s=2.0)
    sched.recordResult(_FakeCard("a"), Rating.Hard, elapsed_s=9.0)
    reviews = store.load("test")["cards"]["a"]["reviews"]
    assert len(reviews) == 2
    assert reviews[1]["rating"] == Rating.Hard.value


def test_record_result_no_reviews_key_leak_into_fsrs(tmp_path):
    """
    The 'reviews' list we store is NOT a FSRS field. It must be stripped before
    passing to FsrsCard.from_dict(), otherwise py-fsrs raises or silently misuses it.
    """
    store = _store_with_review(tmp_path, "a", stability=4.0, days_ago=1, state=2)
    state = store.load("test")
    state["cards"]["a"]["reviews"] = [{"ts": "x", "rating": 3, "response_time_s": 1.0}]
    store.save("test", state)
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    sched.recordResult(_FakeCard("a"), Rating.Good, elapsed_s=3.0)  # must not raise
    assert len(store.load("test")["cards"]["a"]["reviews"]) == 2


def test_record_result_persists_to_disk(tmp_path):
    """recordResult must flush to disk; a fresh AcReviewStore should see the change."""
    store = AcReviewStore(str(tmp_path))
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    sched.recordResult(_FakeCard("a"), Rating.Again, elapsed_s=1.0)
    assert "a" in AcReviewStore(str(tmp_path)).load("test")["cards"]


def test_record_again_sets_learning_state(tmp_path):
    """
    After recordResult(Again) on a new card, the stored state should be state=1 (Learning).
    This is what enables _urgency to apply the fast-decay formula on the next selection.
    """
    store = AcReviewStore(str(tmp_path))
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    sched.recordResult(_FakeCard("a"), Rating.Again, elapsed_s=1.0)
    stored = store.load("test")["cards"]["a"]
    assert stored["state"] == 1  # Learning


def test_record_good_twice_sets_review_state(tmp_path):
    """
    Two consecutive Good answers should graduate a card to state=2 (Review).
    Once in Review, standard long-term FSRS decay applies instead of fast decay.
    """
    store = AcReviewStore(str(tmp_path))
    sched = AcScheduler(_FakeCardSet(["a"]), store)
    sched.recordResult(_FakeCard("a"), Rating.Good, elapsed_s=3.0)
    sched.recordResult(_FakeCard("a"), Rating.Good, elapsed_s=3.0)
    stored = store.load("test")["cards"]["a"]
    assert stored["state"] == 2  # Review


# ── AcScheduler — get_next_card ───────────────────────────────────────────────

def test_get_next_card_returns_a_card(tmp_path):
    """getNextCard should return one of the cardset's cards."""
    store = AcReviewStore(str(tmp_path))
    sched = AcScheduler(_FakeCardSet(["a", "b", "c"]), store)
    assert sched.getNextCard().id in ("a", "b", "c")


# ── compute_deck_stats ────────────────────────────────────────────────────────

def test_deck_stats_all_unseen():
    """With no cards reviewed, all cards are unseen and expected_correct is 0."""
    stats = compute_deck_stats({}, total_cards=10)
    assert stats["total"] == 10
    assert stats["unseen"] == 10
    assert stats["learning"] == 0
    assert stats["relearning"] == 0
    assert stats["learned"] == 0
    assert stats["expected_correct"] == 0.0


def test_deck_stats_counts_states_correctly():
    """State counts from cards_dict are classified into learning/relearning/learned."""
    cards = {
        "a": {"state": 1, "stability": 1.0, "last_review": datetime.now(_UTC).isoformat()},
        "b": {"state": 3, "stability": 1.0, "last_review": datetime.now(_UTC).isoformat()},
        "c": {"state": 2, "stability": 5.0, "last_review": datetime.now(_UTC).isoformat()},
        "d": {"state": 2, "stability": 5.0, "last_review": datetime.now(_UTC).isoformat()},
    }
    stats = compute_deck_stats(cards, total_cards=10)
    assert stats["learning"] == 1
    assert stats["relearning"] == 1
    assert stats["learned"] == 2
    assert stats["unseen"] == 6


def test_deck_stats_expected_correct_increases_after_recent_good_review():
    """A card reviewed as Good moments ago should push expected_correct above 0."""
    now = datetime.now(_UTC)
    cards = {
        "a": {
            "state": 2,
            "stability": 2.307,
            "last_review": (now - timedelta(seconds=1)).isoformat(),
        }
    }
    stats = compute_deck_stats(cards, total_cards=5, now=now)
    # One of 5 cards is freshly learned; deck expected_correct > 0 and < 1/5 * 0.9
    assert stats["expected_correct"] > 0.0
    assert stats["expected_correct"] < 1.0


def test_deck_stats_expected_correct_zero_total():
    """A zero-total deck should not divide by zero."""
    stats = compute_deck_stats({}, total_cards=0)
    assert stats["expected_correct"] == 0.0


def test_deck_stats_via_scheduler_method(tmp_path):
    """AcScheduler.deck_stats() should return the same structure as compute_deck_stats."""
    store = AcReviewStore(str(tmp_path))
    cardset = _FakeCardSet(["a", "b", "c"])
    sched = AcScheduler(cardset, store)
    stats = sched.deck_stats()
    assert stats["total"] == 3
    assert stats["unseen"] == 3
    assert stats["expected_correct"] == 0.0


def test_deck_stats_total_cards_persisted_after_record(tmp_path):
    """After recordResult, the JSON includes total_cards so menu can show full stats."""
    store = AcReviewStore(str(tmp_path))
    cardset = _FakeCardSet(["a", "b"])
    sched = AcScheduler(cardset, store)
    sched.recordResult(_FakeCard("a"), Rating.Good, elapsed_s=3.0)
    saved = store.load("test")
    assert saved.get("total_cards") == 2
