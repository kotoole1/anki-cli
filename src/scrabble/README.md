The Anki Scrabble sets are designed to teach and reinforce word knowledge, with a focus on making your time learning most useful and fitting cleanly into Anki's flashcard paradigm. Each card allows typing of an answer directly, and this method of learning is recommended.

There are two types of card sets: Anagram cards present alphagrams (e.g. AEINRST). They are answered correctly with *any* valid NWL word which anagrams those letters (e.g. RETINAS).

Extension cards present an existing word on the board and a direction to extend with a single letter (e.g. AA? or ?AA). They are answered correctly with *all* single letters that extend that into a valid word in any order (e.g. SHL or B).

Answers are presented with some syntax to help you recall when extension plays are valid:
    - `+` before or after a word indicates there is exactly one valid 1-letter extension on that side (e.g. +RAINED or RETINA+)
    - `#` is used exactly like `+`, but indicates more than one valid 1-letter extension on that side
    - Words of 5+ letters will also show:
        - `-` before or after a word indicates there is at least one valid extension of 1-7 letters
        - `~` before and after a word indicates there is at least one valid extension of 1-7 letters using both sides.

For brevity, the more specific symbols higher on the list above will override lower symbols. In Anki CLI, whenever you see these symbols, you can press tab (or ctrl-o) to expand the view, revealing the complete words and definitions of all valid extensions of all words currently on your screen. The in-app `?` help shows this symbol legend and the tab shortcut for every scrabble set.

A word is marked by how common it is in everyday English: ▶ if it is "common" (in the 20k most commonly used English words), ▷ if it is "less common" (in the top 50k), and ▹ if it is "rare" (beyond the top 50k).

Existing anagram sets:
 - `scrabble-7s-2k` is all 2000 most commonly used 7-letter words, sorted by tile probability — TODO-ANKI-2: remove
 - `scrabble-8s-2k` is the 2000 most commonly used 7-letter words, sorted by tile probability — TODO-ANKI-2: remove
 - `scrabble-7s-1k-common` is the most probable 1000 7-alphagrams, filtered to those with common english answers. It is the list used when running `ankiCLI scrabble7`
 - `scrabble-8s-1k-common` is the most probable 1000 8-alphagrams, filtered to those most common english answers. It is the list used when running `ankiCLI scrabble8`
 - `scrabble-7s-1k` is the most probable 1000 7-alphagrams with any legal word.
 - `scrabble-8s-1k` is the most probable 1000 8-alphagrams with any legal word.
 - `scrabble-hv` (shortcut `shv`) is every short word (2–4 letters) built around a high-value tile (Q, Z, J, X, K, V, W), drawn from the entire NWL word list (no common-word filter), shown as anagrams. When a rack has more than one valid word, *all* of them are required (separated by any combination of spaces and commas). Learning order is the rarest tiles first (any of Q, J, Z, X), then shorter words before longer, then more common words first. Run with `ankiCLI scrabble-hv`.


Extension sets. Each comes in three flavours; the canonical id is the batched one:
 - `scrabble-2s` (shortcut `s2`) learns/optimizes your 2s recall: extend each letter in either direction. Batched — only vowel bases (A/E/I/O/U) split into per-alphabet-segment cards; a consonant's extensions cluster in the vowel segment, so it stays one "type them all" card.
 - `scrabble-2s+` (shortcuts `s2+`, `s3`) learns/optimizes your recall of the most useful 3s: the ones that extend 2s. Batched — every bigram with ≤4 extensions is one "type them all" card; 5+ split into per-segment cloze-by-segment cards. New cards are drip-fed by how commonly each 2-letter root is actually *played* (real Quackle self-play frequency; `cache/two_letter_playability.tsv`), so you learn QI/XI/OX/ZA extensions before rarely-played roots.
 - Legacy "type every extension at once" cards live under `scrabble-2s-legacy` (`s2l`) and `scrabble-2s+legacy` (`s2+l`).
 - `scrabble-2s+-cloze` (`s2+c`) is the atomic per-extension variant: each card hides a single extension and shows the others as context.
