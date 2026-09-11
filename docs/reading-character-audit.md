# Reading character audit: converter 1.0.4

The pinned source remains `source-qiding-2025.12.13`; these are converter fixes,
not edits to the MDX, MDD, or source CSS. Findings below were verified against
the source MDX and the 1.0.3 archive (936,899 emitted rows). Row counts include
generated variants and redirects and overlap across categories.

## Findings and resolution

| 1.0.3 finding | Emitted rows | 1.0.4 policy |
|---|---:|---|
| Fullwidth `ｅ` U+FF45 | 1 | ASCII `e`: 能地 `néng de` |
| Fullwidth `ｋ` U+FF4B | 16 | ASCII `k`: 傾觖 `qīng kuì` |
| Parenthesized pronunciation notes | 319 | Extract all nested `duyin` notes into the header, including notes without parentheses |
| Fullwidth brackets | 39 | Extract first-bracket pinyin; retain the complete bracketed source in the header |
| EM SPACE U+2003 | 34 | Ordinary space where it remains in extracted pinyin |
| Slash alternatives | 7 | One row per complete, distinct explicit alternative |
| Question marks | 26 | Keep valid primary readings if the question mark occurs only in a note; otherwise retain unresolved text and use an empty reading |
| Private-use U+100000 | 2 | Empty reading for 姆媽/姆妈; preserve the source and visibly label U+100000 |

The earlier 1.0.3 fix already replaced `ɡ` U+0261 and `ɑ` U+0251 with `g` and
`a`. All four letter substitutions precede NFC. No global NFKC is applied.
Tone accents, `ü`, `ê`, syllabic nasals, capitalization, existing internal ASCII
spacing, and phrase punctuation remain unchanged. No further ASCII letter
substitutions were supported by the source character inventory.

Notes keep their text and supported formatting under the existing `reading-note`
styling. A comma directly before an extracted note is removed from the reading;
internal phrase commas remain. Noted alternatives never become lookup readings.
When a complete original pronunciation must be retained, its notes appear there
once rather than also appearing as separate notes.

The three source slash blocks are 傳風 (`chuán fěng`, `chuán fèng`), 厎績
(`dǐ jì`, `zhǐ jì`), and 呵呀 (`ā yā`, `hē yā`). Each alternative keeps the
same definition and source sequence and propagates through variants and redirects.

Bracket examples: 俢 supplies `xiū` from `［xiū ㄒㄧㄡ］` before historical
phonology; 𡼿 supplies `kū` without Bopomofo; `［音未详。］` supplies no reading.

## Remaining source uncertainties

Question-mark primaries include 夭𫊸, 犮乙, 萎𦬼, 虼𧒮脸儿，好大面皮儿,
some 诶 pronunciations, 𡹗崇, 𧮼𠱛, and 𩶭鮈. Their unknown syllables are not
guessed and their known syllables are not indexed as partial pronunciations.
The U+100000 syllable in 姆媽 has no established safe replacement. The source's
unknown-reading labels also remain unresolved. All of this source information
stays visible in the definition header.

Mixed valid/unresolved slash lists index only the valid alternatives and report
the unresolved source. Extraction and archive validation share a character
predicate that rejects leaked notes, brackets, Bopomofo, slashes, question marks,
private-use characters, em spaces, and the four identified letter lookalikes.
This is a character-hygiene check, not a claim of linguistic correctness.

## Reporting and verification

`counts.source_pronunciation_blocks` counts source pronunciation blocks once,
before reading expansion, variants, or redirects. `counts.emitted_terms` counts
final rows. `reading_diagnostics.counts` counts source blocks by reason (reasons
may overlap), with at most 25 examples per reason containing the source headword,
complete original pronunciation, and resulting readings.

Regression tests cover normalization and legitimate accents, nested notes and
formatting, separator commas, bracket records, all three slash blocks, mixed
uncertainties, empty readings, and propagation through variants and chained
redirects. The standalone
[`compare_reading_cleanup.py`](../work/hydcd-yomitan/scripts/compare_reading_cleanup.py)
derives expected readings independently from source pronunciation markup and
compares every rebuilt row to 1.0.3. It requires unchanged definitions, citations,
images, styles, existing header metadata, expression fields, source sequences,
and tags, allowing only the documented readings, added pronunciation metadata,
exact deduplication/expansion, and revision change.

Full archive validation uses `--archive-only`, including every emitted reading,
with the existing ten-minute CI limit. Recursive term-schema validation runs
on unit fixtures. Yomitan/Lapis coloring and cross-dictionary grouping require
reimport in an installed setup and are reported separately from archive checks.

### 1.0.4 delivery status (2026-09-11)

The local build completed with 936,906 emitted rows (+7), 418,969 source
pronunciation blocks, 220 blocks with extracted notes, 34 bracketed blocks,
three slash blocks, and six blocks with fullwidth-letter replacements.
Eleven source primary pronunciations remain unresolved: nine with question
marks, one private-use reading, and one unknown-reading label. The existing
unresolved redirect `垂直綫 → 垂直线` is unchanged from 1.0.3.

All 89 regression tests passed before the user requested that testing stop.
The full archive validator and independent comparison were then interrupted;
neither is recorded as passed. CI is skipped for this delivery commit to avoid
starting more tests, and the completed local ZIP is published with that status.
Future commits retain the existing automatic build workflow. The available UI
tools exposed only an empty in-app browser, so installed Yomitan/Lapis reimport,
tone coloring, and cross-dictionary grouping remain unverified.
