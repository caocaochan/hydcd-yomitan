# 《漢語大詞典 七訂 Fork》 → Yomitan

Private, reproducible converter for the 2026 `hdc2025.mdx` / `hdc2025.mdd`
release. It emits current Yomitan format-3 structured content and intentionally
removes JavaScript, online TTS, AI hooks, audio, fonts, forms, remote media, and
tracking behavior.

## Input

Place exactly one `.mdx`, all matching `.mdd` files, and the optional source CSS
in an input directory. Do not put alternative MDX editions in the same folder.

## Commands

```powershell
python -m pip install -r requirements-lock.txt
python -m hydcd_yomitan inspect --input ..\input\hydcd-seven
python -m hydcd_yomitan build --input ..\input\hydcd-seven --output ..\..\outputs\hydcd-qiding-yomitan.zip
python -m hydcd_yomitan validate ..\..\outputs\hydcd-qiding-yomitan.zip
python -m hydcd_yomitan build --input ..\input\hydcd-seven --edition light --output ..\..\outputs\hydcd-qiding-yomitan-light.zip
python -m hydcd_yomitan validate ..\..\outputs\hydcd-qiding-yomitan-light.zip --edition light --archive-only
python -m pytest
```

`validate` performs archive-wide safety, resource, bank-size, and `zh-Hans`
checks, plus official-schema validation of the index and representative banks.
Pass `--exhaustive` only when a slow recursive schema pass over every term is
required.

CI uses `validate --archive-only`: it checks every bank for safety, resources,
language structure, and normalized pinyin, and validates the index schema.
It explicitly skips recursive term-schema validation, which is too slow for
routine builds. The default targeted and optional exhaustive modes remain
available for manual use.

`build` writes a conversion report next to the ZIP. Source data and generated
dictionary files are not licensed or distributed by this converter.

`--edition full` is the default for build and validation. Light has a separate
title, ZIP, update endpoint, and `hydcd-qiding-light-conversion-report.json`.
Its internal `index.json` is attached to releases as `index-light.json`.
Switch editions by importing the chosen ZIP and disabling/removing the other
edition if installed. Subsequent updates stay within the installed edition.

Light uses the same input inventory/checksums but skips MDD extraction and image
processing. Its report records source-element removal counts (including nested
images and examples), empty-container removals, and omission notices, before
variant/redirect duplication. Complete builds use the same release revision.

## Conversion policy

- Unicode is normalized with NFC, never NFKC.
- Pinyin readings replace `ɡ` (U+0261), `ɑ` (U+0251), `ｅ` (U+FF45), and
  `ｋ` (U+FF4B) with ASCII `g`, `a`, `e`, and `k`, respectively, and U+2003
  with ordinary space before NFC composition. Tone marks, `ü`, `ê`, syllabic
  nasals, capitalization, internal ASCII spacing, and phrase punctuation remain.
- Nested pronunciation notes are displayed once in the definition header,
  including notes without parentheses; they never supply lookup alternatives.
  Only a comma directly separating a pronunciation from a note is removed.
- Bracketed pronunciation records supply pinyin from their first bracket,
  excluding Bopomofo and historical phonology. The original record remains in
  the header. Explicit slash alternatives produce separate entries in source
  order, with duplicate readings removed.
- Unresolved primary pronunciations (question marks, private-use characters,
  or unrecognized metadata) yield empty readings and retain the complete source
  pronunciation in the header. Private-use code points are identified visibly.
  Mixed slash lists retain valid alternatives and report unresolved ones.
- Canonical entries, variants, and redirects share the resulting single-valued
  readings. Extraction and archive validation use the same character checks;
  these check character hygiene, not linguistic correctness of each syllable.
  Reports count source pronunciation blocks separately from emitted rows and
  retain at most 25 examples per reason. See the versioned
  [reading audit](../../docs/reading-character-audit.md).
- Existing simplified/traditional records and redirects are preserved; OpenCC
  aliases are not invented.
- `@@@LINK=` aliases receive the canonical definition directly.
- Full: examples are retained in native `<details>` blocks, collapsed by default;
  only referenced local images are packaged.
- Light: images, example blocks, standalone examples, and example notes are
  removed before their descendants are converted or resources resolved.
  Empty containers caused by these cuts are removed; otherwise-empty senses and
  entries retain their numbering and display `（精简版已省略图片或例证）`.
- Light retains historical phonology, other explanatory notes, quotations and
  source details outside example blocks, all lookup forms, and identical CSS.
- Unknown tags are unwrapped without losing their text and are reported.
- Glossaries use `lang="zh-Hans"` and the browser's generic `sans-serif` font.
- Corrections require an exact source hash and exact before-text match.
