# local-history/

Runtime FSRS state for each card set. JSON files are gitignored — each user's learning history stays local.

## File format

`{cardset_id}.json` stores per-card FSRS state plus a review history log:

```json
{
  "cardset_id": "oscars",
  "cards": {
    "2025-desc": {
      "card_id": 1234567,
      "state": 2,
      "step": null,
      "stability": 4.07,
      "difficulty": 5.1,
      "due": "2026-05-03T10:00:00+00:00",
      "last_review": "2026-04-30T10:00:00+00:00",
      "reviews": [
        {"ts": "2026-04-30T10:00:00Z", "rating": 3, "response_time_s": 4.2}
      ]
    }
  }
}
```

FSRS fields (`card_id` through `last_review`) are the standard py-fsrs `CardDict` fields and can be loaded directly by `fsrs.Card.from_dict()`. The `reviews` list is our own addition and is stripped before passing to py-fsrs.

## Anki export

The `rating_time_threshold_s` behavior (auto-rating based on response time) has no direct Anki deck-option equivalent. It is embedded as a card tag (`anki-cli::threshold=7`) in exported `.apkg` files so any downstream tool can read it without special-casing the deck name.

Because we skip Anki's learning steps, early stability values may differ from what Anki would have produced for the same cards. The FSRS fields are valid and importable into Anki, but the spacing history won't match Anki's own learning-queue progression.
