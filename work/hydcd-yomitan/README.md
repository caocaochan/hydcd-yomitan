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

## Conversion policy

- Unicode is normalized with NFC, never NFKC.
- Pinyin readings replace `ɡ` (U+0261) with ASCII `g` and `ɑ` (U+0251)
  with ASCII `a` before NFC composition of tone marks. Canonical entries,
  variants, and redirects share these normalized readings; definitions and
  Chinese expressions are unchanged.
- Existing simplified/traditional records and redirects are preserved; OpenCC
  aliases are not invented.
- `@@@LINK=` aliases receive the canonical definition directly.
- Examples are retained in native `<details>` blocks, collapsed by default.
- Only referenced local images are packaged.
- Unknown tags are unwrapped without losing their text and are reported.
- Glossaries use `lang="zh-Hans"` and the browser's generic `sans-serif` font.
- Corrections require an exact source hash and exact before-text match.
