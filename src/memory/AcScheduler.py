import math
import random
from datetime import datetime, timezone

from fsrs import Scheduler as FsrsScheduler, Card as FsrsCard, Rating
from fsrs.card import CardDict

from memory.AcReviewStore import AcReviewStore

_FSRS_FIELDS: frozenset[str] = frozenset(CardDict.__annotations__.keys())
_UTC = timezone.utc
NEW_CARD_WEIGHT = 0.6


class AcScheduler:
    def __init__(self, cardset, store: AcReviewStore):
        self._cardset = cardset
        self._store = store
        self._fsrs = FsrsScheduler()
        self._state = store.load(cardset.id)

    def getNextCard(self):
        cards = self._cardset.cards
        weights = [self._urgency(c.id) for c in cards]
        return random.choices(cards, weights=weights)[0]

    def _urgency(self, card_id: str) -> float:
        new_order = getattr(self._cardset, 'new_card_order', [])
        stored = self._state["cards"].get(card_id)

        if stored is None:
            unseen = [cid for cid in new_order if cid not in self._state["cards"]]
            return NEW_CARD_WEIGHT if (not unseen or unseen[0] == card_id) else NEW_CARD_WEIGHT * 0.05

        last_review_str = stored.get("last_review")
        stability = stored.get("stability")

        if last_review_str is None or stability is None:
            return NEW_CARD_WEIGHT

        last_dt = datetime.fromisoformat(last_review_str)
        elapsed_days = (datetime.now(_UTC) - last_dt).total_seconds() / 86400
        retention = math.exp(math.log(0.9) * elapsed_days / stability)
        return max(1.0 - retention, 1e-6)

    def inferRating(self, elapsed_s: float, used_glob: bool) -> Rating:
        threshold = getattr(self._cardset, 'rating_time_threshold_s', 7)
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
