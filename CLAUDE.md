# anki-cli

## Naming conventions

All module-level constructs (classes, important constants) defined in this project use the `Ac` two-letter prefix. This distinguishes project code from identically-named third-party imports. Examples: `AcScheduler`, `AcReviewStore`. Third-party classes (`fsrs.Scheduler`, `fsrs.Card`) are imported with explicit aliases where ambiguous.
