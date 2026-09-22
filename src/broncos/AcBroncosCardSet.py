"""The `broncos` set: every player on the depth chart plus the coaching staff.

Responsibility: turn a roster into cards and decide the order new ones are
introduced — starters first (unit by unit, so a batch comes from the group the
post-answer table shows; the seven skill-position starters split in two), then the head coach and coordinators, then
backups unit by unit with the 2s ahead of the 3s, and last the position and
assistant coaches. Inside a batch all the position cards come before any
number card, and those before any name card (cards.ordering).

Card ids are built on ESPN athlete ids, so a player keeps his review history
through a number or depth-chart change; only the card whose answer changed is
reset (AcBroncosCard.answer_key, AcScheduler).
"""

from cards.cardSet import CardSet
from cards.ordering import batched_variant_order, chunk_evenly
from broncos.AcBroncosCard import AcBroncosCard
from broncos.AcBroncosData import load_overrides, load_snapshot
from broncos.AcBroncosRoster import AcBroncosRoster

_MAX_BATCH = 6
# "pos" and "title" are the same step for players and coaches respectively.
_VARIANT_ORDER = ["pos", "title", "num", "name"]


class AcBroncosCardSet(CardSet):
    rating_time_threshold_s = 7

    def __init__(self, refresh: bool | None = None, snapshot: dict | None = None,
                 overrides: dict | None = None):
        snapshot = snapshot or load_snapshot(refresh)
        self.roster = AcBroncosRoster(snapshot, overrides if overrides is not None else load_overrides())

        cards = []
        for p in self.roster.players():
            variants = ["pos", "num", "name"] if p.jersey else ["pos", "name"]
            cards += [AcBroncosCard(p, v, self.roster) for v in variants]
        for c in self.roster.coaches:
            cards += [AcBroncosCard(c, v, self.roster) for v in ("title", "name")]

        super().__init__("broncos", "Denver Broncos roster", cards)
        self.new_card_order = batched_variant_order(
            self._batches(), _VARIANT_ORDER, valid_ids={c.id for c in cards})

    def _batches(self) -> list[list[str]]:
        by_depth = self.roster.unit_depth_order()
        starters = [b for _, depth, ids in by_depth if depth == 1 for b in chunk_evenly(ids, _MAX_BATCH)]
        leads = chunk_evenly(self.roster.lead_coaches(), _MAX_BATCH)
        assistants = [b for group in self.roster.assistant_groups() for b in chunk_evenly(group, _MAX_BATCH)]
        backups = []
        for unit in dict.fromkeys(u for u, _, _ in by_depth):
            ids = [i for u, depth, ids in by_depth if u == unit and depth > 1 for i in ids]
            backups += chunk_evenly(ids, _MAX_BATCH)
        return starters + leads + backups + assistants
