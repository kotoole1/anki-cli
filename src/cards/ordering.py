"""New-card ordering shared by the multi-fact sets (oscars, broncos).

Those sets make several cards ("variants") about each entity and introduce
entities a small batch at a time: every entity in the batch is met through
variant A before any of them is asked about through variant B. That keeps the
cards of one entity apart in time, so an earlier card doesn't hand you the
answer to the next one. The result feeds CardSet.new_card_order.
"""


def chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def chunk_evenly(items: list, max_size: int) -> list[list]:
    """Split into the fewest near-equal batches of at most max_size, so a group
    of 7 becomes 4+3 rather than 6+1."""
    if not items:
        return []
    n = -(-len(items) // max_size)
    base, extra = divmod(len(items), n)
    out, i = [], 0
    for b in range(n):
        step = base + (1 if b < extra else 0)
        out.append(items[i:i + step])
        i += step
    return out


def batched_variant_order(batches: list[list], variants: list[str],
                          valid_ids=None) -> list[str]:
    """Card ids `{entity}-{variant}`, batch by batch, variant by variant.

    `valid_ids` (any container) drops ids that don't exist, for sets where not
    every entity has every variant."""
    order = []
    for batch in batches:
        for variant in variants:
            for entity in batch:
                cid = f"{entity}-{variant}"
                if valid_ids is None or cid in valid_ids:
                    order.append(cid)
    return order
