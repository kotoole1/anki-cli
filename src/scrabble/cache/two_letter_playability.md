# `two_letter_playability.tsv` — where it comes from, and how to improve it

**What it is:** a `WORD<tab>PLAYABILITY` table for the two-letter words, used to
drip-feed the `scrabble-2s+` set most-played-root-first. Higher = played more
often in real games. Loaded by `load_two_letter_playability()` in
`../extensions.py`; consumed by `_playability_order_key` /
`_build_2s_plus_batched` in `../ExtensionCardSet.py`. Affects **new-card
introduction order only** — not review scheduling.

## Provenance

The numbers are **John O'Laughlin's Quackle self-play "playability"** values
(VORW-style: Quackle plays itself millions of times; a word's value reflects how
much not knowing it costs you, which for short words tracks how often it is
played). This is the primary data behind FiveThirtyEight's "QI is the
most-played word" claim — and QI does rank #1 here (10,025,400).

Source file: `csw-playability.txt` from
<https://pages.cs.wisc.edu/~o-laughl/collins/csw-playability.txt>, filtered to
NWL two-letter words.

## ⚠️ Caveat: this is Collins-derived, not NWL

O'Laughlin publishes a *modern, complete* playability run only for **Collins
(CSW)**. His North-American (`twl-*`) two-letter files
(`pages.cs.wisc.edu/~o-laughl/twl-counts/twos.txt`, `.../playable`) predate the
2006 lexicon and therefore **lack QI, ZA, DA, GI, KI, OI, PO, TE, FE** — words
that are now among the most important 2s — so they are unusable. His post-2020
run (`newplayability/`) covers only 5–8-letter words.

Why the Collins table is nonetheless a good NWL proxy for **two-letter** words:
the 2-letter lexicons overlap almost entirely, and 2-letter play frequency is
driven by tile mechanics that are lexicon-independent. QI/XI/OX/ZA/EX/AX lead in
both. The Collins-only 2s (GU, ZO, JA, OB, KY, DI, …) are filtered out; their
presence in self-play only perturbs the shared words' values slightly, not their
rank order.

Coverage: **105 of 107** NWL two-letter words. The two NWL2020 additions **EW**
and **OK** were not in the Collins run; they fall to the end of the drip order
via the tile-probability fallback in `_playability_order_key`. Both are trivial
2-extension roots, so the impact is negligible.

## How to replace with true NWL data (future agent)

Keep the exact same file format (`WORD<tab>integer`, one per line, `#` comments
ignored) and the loader/builder need no changes. A genuine NWL 2-letter
play-frequency table can be built from real NWL games:

- **Woogles.io bot games** (NWL): Kaggle `mrisdal/scrabble-data-from-wooglesio`
  or the "Scrabble Player Rating" competition `turns.csv` (~73k NWL games).
  Count, per two-letter word, how many turns played it (the `move`/`rack`
  columns), then write the counts here. Requires a Kaggle download (auth) and
  per-turn parsing.
- Or run **Quackle** self-play under an NWL2020 lexicon and export playability
  for the twos (mirrors how the Collins file was produced).

## Reproducing the current file

```
curl -sL "https://pages.cs.wisc.edu/~o-laughl/collins/csw-playability.txt" -o csw-play.txt
# then keep lines "<int> <WORD>" where WORD is a 2-letter NWL word,
# emit "WORD<tab>int" sorted by int desc (see git history for the exact script).
```
