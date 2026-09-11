"""Extract lookup readings without discarding pronunciation metadata."""
from __future__ import annotations

import re
import string
import unicodedata
from copy import deepcopy
from dataclasses import dataclass, field

from lxml import etree


LETTER_MAP = str.maketrans({"ɡ": "g", "ɑ": "a", "ｅ": "e", "ｋ": "k", "\u2003": " "})
# Character validation, not a syllable dictionary: preserve proper names and
# the phrase separators already used by this source.
READING_CHARACTERS = frozenset(string.ascii_letters + " ,，､、'’-" + "\u0300\u0301\u0302\u0304\u0308\u030c")
BRACKET_GROUPS = re.compile(r"\s*(?:［[^［］]*］|\[[^\[\]]*\])")
BOPOMOFO = re.compile(r"[\u3100-\u312f\u31a0-\u31bf]")


def normalize_pinyin(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\x00", "").translate(LETTER_MAP)).strip()


def is_clean_reading(value: str) -> bool:
    if not value:
        return True
    if value != normalize_pinyin(value):
        return False
    decomposed = unicodedata.normalize("NFD", value)
    return (
        any(char in string.ascii_letters for char in decomposed)
        and all(char in READING_CHARACTERS for char in decomposed)
    )


@dataclass
class Pronunciation:
    original: str = ""
    readings: list[str] = field(default_factory=lambda: [""])
    notes: list[etree._Element] = field(default_factory=list)
    retain_source: bool = False
    reasons: list[str] = field(default_factory=list)
    unresolved_codepoints: list[str] = field(default_factory=list)


def _remove_note(note: etree._Element) -> None:
    parent = note.getparent()
    assert parent is not None
    previous = note.getprevious()
    prefix = previous.tail if previous is not None else parent.text
    # Remove only the comma adjacent to this note, not phrase-internal commas.
    prefix = re.sub(r"[,，]\s*$", "", prefix or "")
    combined = prefix + (note.tail or "")
    if previous is not None:
        previous.tail = combined
    else:
        parent.text = combined
    parent.remove(note)


def extract_pronunciation(pron: etree._Element | None) -> Pronunciation:
    if pron is None:
        return Pronunciation()
    result = Pronunciation(original="".join(pron.itertext()))
    clone = deepcopy(pron)
    for note in list(clone.xpath(".//duyin[not(ancestor::duyin)]")):
        retained = deepcopy(note)
        retained.tail = None
        result.notes.append(retained)
        _remove_note(note)
    if result.notes:
        result.reasons.append("notes_extracted")
    value = "".join(clone.itertext()).strip()
    if value.startswith(("［", "[")):
        result.retain_source = True
        groups = list(BRACKET_GROUPS.finditer(value))
        if not groups or "".join(match[0] for match in groups).strip() != value:
            result.reasons.append("unrecognized_brackets")
            value = ""
        else:
            first = groups[0][0].strip()[1:-1]
            value = BOPOMOFO.split(first, maxsplit=1)[0].strip()
            result.reasons.append("brackets_extracted")
    parts = value.split("/")
    if len(parts) > 1:
        result.reasons.append("slash_alternatives")
    readings: list[str] = []
    for part in parts:
        reading = normalize_pinyin(part)
        if any(char in part for char in "ɡɑｅｋ"):
            result.reasons.append("letters_normalized")
        if any(char in part for char in "ｅｋ"):
            result.reasons.append("width_letters_normalized")
        if "\u2003" in part:
            result.reasons.append("em_spaces_normalized")
        if reading and is_clean_reading(reading):
            if reading not in readings:
                readings.append(reading)
            continue
        if not result.original.strip():
            continue
        result.retain_source = True
        if "?" in reading:
            result.reasons.append("unresolved_question_mark")
        elif any(unicodedata.category(char) == "Co" for char in reading):
            result.reasons.append("unresolved_private_use")
        elif not reading:
            result.reasons.append("unresolved_missing_primary")
        else:
            result.reasons.append("unresolved_metadata")
        result.unresolved_codepoints.extend(
            f"U+{ord(char):04X}" for char in reading
            if unicodedata.category(char) in {"Co", "Cc", "Cf"}
        )
    result.readings = readings or [""]
    result.reasons = list(dict.fromkeys(result.reasons))
    result.unresolved_codepoints = sorted(set(result.unresolved_codepoints))
    return result
