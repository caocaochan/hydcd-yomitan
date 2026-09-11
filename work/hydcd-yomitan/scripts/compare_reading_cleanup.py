"""Independent, source-based 1.0.3 -> 1.0.4 archive comparison.

Run from the converter directory: python -m scripts.compare_reading_cleanup
OLD.zip NEW.zip SOURCE.mdx REPORT.json. No archive is modified.
"""
import hashlib
import json
import re
import sys
import unicodedata as ud
import zipfile
from collections import Counter
from pathlib import Path

from lxml import html
from hydcd_yomitan.source import iter_mdx_records


def nfc(text):
    return ud.normalize("NFC", text).strip()


def old_normalize(text):
    return nfc(text.replace("ɡ", "g").replace("ɑ", "a"))


def expected_pronunciation(raw):
    # Deliberately does not call the production reading parser/checker.
    pron = html.fromstring(raw)
    original = "".join(pron.itertext())
    notes = []
    for note in list(pron.xpath(".//duyin[not(ancestor::duyin)]")):
        notes.append("".join(note.itertext()))
        note.text = "__EXTRACTED_NOTE__"
        for child in list(note):
            note.remove(child)
    primary = re.sub(r"[,，]?\s*__EXTRACTED_NOTE__", "", "".join(pron.itertext())).strip()
    bracketed = primary.startswith(("［", "["))
    if bracketed:
        primary = re.split(r"[］\]]", primary[1:], maxsplit=1)[0]
        primary = re.split(r"[\u3100-\u312f\u31a0-\u31bf]", primary, maxsplit=1)[0].strip()
    readings = []
    unresolved = False
    for alternative in primary.split("/"):
        reading = nfc(old_normalize(alternative).replace("ｅ", "e").replace("ｋ", "k").replace("\u2003", " "))
        # The audited source uncertainties, not an inferred replacement.
        invalid = not reading or "?" in reading or any(ud.category(c) == "Co" for c in reading) or "音未详" in reading
        if invalid:
            unresolved = bool(original.strip())
        elif reading not in readings:
            readings.append(reading)
    metadata = ("original", nfc(original)) if bracketed or unresolved else (("notes", [nfc(t) for t in notes]) if notes else None)
    return old_normalize(original), readings or [""], metadata


def terms(archive):
    names = sorted((n for n in archive.namelist() if re.fullmatch(r"term_bank_\d+\.json", n)), key=lambda n: int(n[10:-5]))
    for name in names:
        yield from json.loads(archive.read(name))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).digest()


def text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(map(text, value))
    return text(value.get("content", "")) if isinstance(value, dict) else ""


def remove_metadata(value, found):
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := remove_metadata(item, found)) is not None]
    if isinstance(value, dict):
        if value.get("data", {}).get("content") == "reading-metadata":
            found.append(text(value))
            return None
        value = dict(value)
        if "content" in value:
            value["content"] = remove_metadata(value["content"], found)
        if value.get("data", {}).get("content") == "header" and not value.get("content"):
            return None
    return value


old_path, new_path, source_path, report_path = map(Path, sys.argv[1:])
mapping = {}
for ordinal, headword, raw in iter_mdx_records(source_path):
    for match in re.finditer(r"<pron\b[^>]*>.*?</pron>", raw.decode("utf-8").replace("\x00", ""), re.S):
        markup = match[0]
        if not any(c in markup for c in ("duyin", "［", "[", "/", "?", "ｅ", "ｋ", "\u2003", "\U00100000")):
            continue
        before, after, metadata = expected_pronunciation(markup)
        key = (ordinal, before)
        assert key not in mapping or mapping[key] == (after, metadata), (headword, key)
        mapping[key] = (after, metadata)
print(f"Independent source map: {len(mapping)} pronunciation blocks", flush=True)
counts = Counter()
expected = set()
expected_metadata = {}
with zipfile.ZipFile(old_path) as old, zipfile.ZipFile(new_path) as new:
    old_index, new_index = (json.loads(z.read("index.json")) for z in (old, new))
    assert new_index.pop("revision") == old_index.pop("revision").replace("converter-1.0.3+", "converter-1.0.4+")
    assert old_index == new_index
    assets = lambda z: {n for n in z.namelist() if not re.fullmatch(r"term_bank_\d+\.json", n) and n != "index.json"}
    assert assets(old) == assets(new)
    for name in assets(old):
        assert old.read(name) == new.read(name), name
    counts["unchanged_assets"] = len(assets(old))
    for row in terms(old):
        counts["old_rows"] += 1
        after, metadata = mapping.get((row[6], row[1]), ([row[1]], None))
        counts["changed_original_rows"] += after != [row[1]]
        counts["expanded_original_rows"] += len(after) > 1
        for reading in after:
            row[1] = reading
            signature = digest(row)
            counts["expected_exact_duplicates"] += signature in expected
            expected.add(signature)
            if metadata:
                expected_metadata[signature] = metadata
    print(f"Expected rows after cleanup: {len(expected)}", flush=True)
    for row in terms(new):
        counts["new_rows"] += 1
        found = []
        row[5] = remove_metadata(row[5], found)
        signature = digest(row)
        assert signature in expected, ("Unexpected or duplicate row", row[0], row[1], row[6])
        expected.remove(signature)
        metadata = expected_metadata.pop(signature, None)
        assert bool(found) == bool(metadata), ("Unexpected/missing metadata", row[0], row[1])
        if metadata:
            counts["rows_with_retained_pronunciation"] += 1
            assert len(found) == 1
            kind, value = metadata
            if kind == "original":
                assert found[0].startswith("原文读音：" + value), (row[0], found, metadata)
                if "\U00100000" in value:
                    assert "U+100000" in found[0]
            else:
                assert found[0] == "读音附注：" + "；".join(value), (row[0], found, metadata)
        # Independent whole-archive forbidden-character scan; CI also applies
        # the stricter shared clean-reading predicate to every emitted row.
        assert not re.search(r"[ɡɑｅｋ\u2003/？?［］\[\]（）()\u3100-\u312f\u31a0-\u31bf]", row[1])
        assert not any(ud.category(c) == "Co" for c in row[1])
    assert not expected and not expected_metadata
report = {"status": "passed", "counts": dict(counts), "old_archive": str(old_path.resolve()), "new_archive": str(new_path.resolve())}
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
