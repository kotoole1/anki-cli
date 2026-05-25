import math
import random
from datetime import datetime, timezone

from fsrs import Scheduler as FsrsScheduler, Card as FsrsCard, Rating
from fsrs.card import CardDict

from memory.AcReviewStore import AcReviewStore

_FSRS_FIELDS: frozenset[str] = frozenset(CardDict.__annotations__.keys())
_UTC = timezone.utc
NEW_CARD_WEIGHT = 0.6
_DRIP_WEIGHT = 1e-6  # weight for out-of-order unseen cards — nearly unreachable

# ── Learning-state urgency ────────────────────────────────────────────────────
#
# Philosophy: urgency = 1 - retention uses the FSRS retention formula at all
# stages, but Learning and Relearning cards (state ∈ {1, 3}) need a compressed
# time axis so their urgency grows on a minutes scale rather than a days scale.
#
# We deliberately avoid py-fsrs's "due" field. "Due" conflates "ought" with
# "is": FSRS predicts what you actually retain, but an arbitrary 1-minute due
# date does not follow from that prediction — it is a scheduling overlay that
# Anki adds on top of FSRS. Instead we multiply Learning-state stability by
# _LEARNING_SCALE < 1, keeping the same exponential formula throughout and
# letting FSRS answer quality (encoded in stability) determine the timescale.
#
# Calibration: _LEARNING_SCALE is chosen so that a card rated Again for the
# first time (py-fsrs default stability = _AGAIN_STABILITY_DAYS ≈ 0.212 days)
# reaches urgency == NEW_CARD_WEIGHT at t = 1 minute exactly. Cards with higher
# stability (Hard ≈ 1.29 d, Good ≈ 2.31 d) cross that threshold later,
# preserving the FSRS shape: again >>> hard > good >> easy.
#
# Concretely: 1-3 Again answers produce stability near 0.212 d, so the failing
# card beats new-card weight after ~1 minute. A Hard answer (stability ≈ 1.29 d)
# doesn't cross NEW_CARD_WEIGHT until ~6 minutes; Good (~2.31 d) until ~11 min.

_AGAIN_STABILITY_DAYS: float = 0.212  # py-fsrs first-Again stability
_LEARNING_SCALE: float = (
    math.log(0.9) * (1.0 / 1440)
    / (_AGAIN_STABILITY_DAYS * math.log(1.0 - NEW_CARD_WEIGHT))
)  # ≈ 3.77e-4


def compute_deck_stats(cards_dict: dict, total_cards: int, now: datetime | None = None) -> dict:
    """Compute deck health stats from raw stored card data.

    Args:
        cards_dict: The 'cards' dict from the stored JSON state.
        total_cards: Total card count in the cardset (including unseen cards).
        now: Reference time for elapsed calculation; defaults to UTC now.

    Returns a dict with keys: total, unseen, learning, relearning, learned,
    expected_correct (fraction 0.0–1.0 of all cards expected correct right now).
    """
    if now is None:
        now = datetime.now(_UTC)
    unseen = max(0, total_cards - len(cards_dict))
    learning = relearning = learned = 0
    total_retention = 0.0

    for entry in cards_dict.values():
        state = entry.get("state", 2)
        if state == 1:
            learning += 1
        elif state == 3:
            relearning += 1
        else:
            learned += 1

        stability = entry.get("stability")
        last_review_str = entry.get("last_review")
        if stability and last_review_str:
            elapsed = (now - datetime.fromisoformat(last_review_str)).total_seconds() / 86400
            effective_stability = stability * _LEARNING_SCALE if state in (1, 3) else stability
            total_retention += math.exp(math.log(0.9) * elapsed / effective_stability)

    return {
        "total": total_cards,
        "unseen": unseen,
        "learning": learning,
        "relearning": relearning,
        "learned": learned,
        "expected_correct": total_retention / total_cards if total_cards > 0 else 0.0,
    }


class AcScheduler:
    def __init__(self, cardset, store: AcReviewStore):
        self._cardset = cardset
        self._store = store
        self._fsrs = FsrsScheduler()
        self._state = store.load(cardset.id)
        # Persist total so the menu can show deck-wide stats from the JSON alone.
        self._state["total_cards"] = len(cardset.cards)
        self._first_unseen_id: str | None = self._compute_first_unseen()

    def _compute_first_unseen(self) -> str | None:
        for cid in getattr(self._cardset, 'new_card_order', []):
            if cid not in self._state["cards"]:
                return cid
        return None

    def getNextCard(self):
        cards = self._cardset.cards
        weights = [self._urgency(c.id) for c in cards]
        return random.choices(cards, weights=weights)[0]

    def _urgency(self, card_id: str) -> float:
        new_order = getattr(self._cardset, 'new_card_order', [])
        stored = self._state["cards"].get(card_id)

        if stored is None:
            return NEW_CARD_WEIGHT if (not new_order or card_id == self._first_unseen_id) \
                   else _DRIP_WEIGHT

        last_review_str = stored.get("last_review")
        stability = stored.get("stability")

        if last_review_str is None or stability is None:
            return NEW_CARD_WEIGHT  # safe fallback for incomplete FSRS state

        state = stored.get("state", 2)  # default Review if missing
        last_dt = datetime.fromisoformat(last_review_str)
        elapsed_days = (datetime.now(_UTC) - last_dt).total_seconds() / 86400

        if state in (1, 3):  # Learning or Relearning: compressed time axis
            effective_stability = stability * _LEARNING_SCALE
        else:  # Review: standard FSRS decay
            effective_stability = stability

        retention = math.exp(math.log(0.9) * elapsed_days / effective_stability)
        return max(1.0 - retention, 1e-6)

    def deck_stats(self) -> dict:
        return compute_deck_stats(self._state["cards"], len(self._cardset.cards))

    def inferRating(self, elapsed_s: float, used_glob: bool, card=None) -> Rating:
        card_threshold = getattr(card, 'rating_time_threshold_s', None)
        threshold = card_threshold if card_threshold is not None \
                    else getattr(self._cardset, 'rating_time_threshold_s', 7)
        if used_glob and elapsed_s < threshold:
            return Rating.Easy
        if elapsed_s > threshold:
            return Rating.Hard
        return Rating.Good

    def recordResult(self, card, rating: Rating, elapsed_s: float) -> None:
        stored = self._state["cards"].get(card.id)
        fsrs_dict = {k: stored[k] for k in _FSRS_FIELDS if k in stored} if stored else {}
        fsrs_card = FsrsCard.from_dict(fsrs_dict) if fsrs_dict else FsrsCard()
        fsrs_card, _ = self._fsrs.review_card(fsrs_card, rating)
        updated = fsrs_card.to_dict()
        updated["reviews"] = (stored or {}).get("reviews", []) + [{
            "ts": datetime.now(_UTC).isoformat(),
            "rating": rating.value,
            "response_time_s": round(elapsed_s, 2),
        }]
        self._state["cards"][card.id] = updated
        self._store.save(self._cardset.id, self._state)
        self._first_unseen_id = self._compute_first_unseen()
