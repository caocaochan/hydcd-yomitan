from __future__ import annotations

import pytest
from lxml import html

from hydcd_yomitan.content import parse_record
from hydcd_yomitan.models import ConversionStats
from hydcd_yomitan.readings import extract_pronunciation, is_clean_reading, normalize_pinyin


def flatten(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(map(flatten, value))
    if isinstance(value, dict):
        return flatten(value.get("content", ""))
    return ""


def parse(pron, headword="字", extra_header="", body="<item><mean>原释义。</mean></item>"):
    stats = ConversionStats()
    raw = f"<hdcs><hdc><hm><hw>{headword}</hw>{pron}{extra_header}</hm>{body}</hdc></hdcs>"
    return parse_record(headword, raw, None, stats), stats


@pytest.mark.parametrize(("source", "expected"), [
    ("néng dｅ", "néng de"), ("qīng ｋuì", "qīng kuì"),
    ("ɡɑ\u0304", "gā"), ("xiū\u2003xí", "xiū xí"),
    ("lǜ  nǚ", "lǜ  nǚ"), ("ê\u0301 ê\u0300", "ế ề"),
    ("ê\u0304 ê\u030c ń ň ǹ ḿ m\u0300", "ê\u0304 ê\u030c ń ň ǹ ḿ m\u0300"),
    ("Hú Zǐ chuán､ Liǔ Lóng qīng", "Hú Zǐ chuán､ Liǔ Lóng qīng"),
    ("yī, èr，sān", "yī, èr，sān"),
])
def test_reading_normalization_preserves_pronunciation(source, expected):
    assert normalize_pinyin(source) == expected
    assert is_clean_reading(expected)


@pytest.mark.parametrize("value", [
    "ɡā", "mɑ", "dｅ", "ｋé", "xiū\u2003xí", "ga\u0304", "（又读éi）",
    "［xiū］", "xiū ㄒㄧㄡ", "gā/gà", "?", "yāo ?", "\U00100000 mā",
    "xiū\u200bxí", "音未详。", "  gā", ",",
])
def test_dirty_readings_are_rejected(value):
    assert not is_clean_reading(value)


@pytest.mark.parametrize(("pron", "expected", "note"), [
    ("<pron>ế<duyin>（又读éi）</duyin></pron>", "ế", "（又读éi）"),
    ("<pron>nǐ, hǎo，<duyin>（又读ní hǎo）</duyin></pron>", "nǐ, hǎo", "（又读ní hǎo）"),
    ("<pron>dǒu<duyin type='1'>dul</duyin></pron>", "dǒu", "dul"),
    ("<pron>ěi<duyin type='1'>ê?</duyin></pron>", "ěi", "ê?"),
    ("<pron>gā<span>，<duyin><em>gà/gá</em></duyin></span></pron>", "gā", "gà/gá"),
    ("<pron>gā<duyin>甲<duyin>乙</duyin></duyin></pron>", "gā", "甲乙"),
])
def test_notes_are_displayed_once_and_never_indexed(pron, expected, note):
    entries, stats = parse(pron, extra_header="<yinyun>原音韵。</yinyun>")
    assert [entry.reading for entry in entries] == [expected]
    text = flatten(entries[0].glossary)
    assert text.count(note) == 1
    assert "原音韵。" in text and "原释义。" in text
    assert stats.reading_counts["notes_extracted"] == 1
    assert not any(key.startswith("unresolved") for key in stats.reading_counts)


@pytest.mark.parametrize(("source", "expected"), [
    ("［xiū\u2003ㄒㄧㄡ］［<book>《集韻》</book>思留切，平尤，心。］", "xiū"),
    ("［kū］［<book>《廣韻》</book>苦骨切，入没，溪。］", "kū"),
    ("[mì]", "mì"), ("［音未详。］", ""), ("［xiū］unrecognized", ""),
])
def test_brackets_extract_only_pinyin_and_preserve_source(source, expected):
    entries, _ = parse(f"<pron>{source}</pron>")
    assert entries[0].reading == expected
    assert "原文读音：" in flatten(entries[0].glossary)
    original = "".join(html.fromstring(f"<pron>{source}</pron>").itertext())
    assert flatten(entries[0].glossary).count(original) == 1


@pytest.mark.parametrize(("word", "pron", "expected"), [
    ("傳風", "chuán fěnɡ/chuán fènɡ", ["chuán fěng", "chuán fèng"]),
    ("厎績", "dǐ jì/zhǐ jì", ["dǐ jì", "zhǐ jì"]),
    ("呵呀", "ā yā/hē yā", ["ā yā", "hē yā"]),
    ("字", "ɡɑ\u0304/gā/gà", ["gā", "gà"]),
])
def test_explicit_alternatives_share_definition_in_source_order(word, pron, expected):
    entries, stats = parse(f"<pron>{pron}</pron>", headword=word)
    assert [entry.reading for entry in entries] == expected
    assert all(entry.glossary == entries[0].glossary for entry in entries)
    assert stats.counters["source_pronunciation_blocks"] == 1
    assert stats.reading_counts["slash_alternatives"] == 1


@pytest.mark.parametrize(("source", "expected", "reason"), [
    ("yāo ?", [""], "unresolved_question_mark"),
    ("?<duyin>éi</duyin>", [""], "unresolved_question_mark"),
    ("\U00100000 mā", [""], "unresolved_private_use"),
    ("gā/?", ["gā"], "unresolved_question_mark"),
    ("?/gà", ["gà"], "unresolved_question_mark"),
    ("?/\U00100000", [""], "unresolved_private_use"),
    ("gā/", ["gā"], "unresolved_missing_primary"),
    ("<duyin>éi</duyin>", [""], "unresolved_missing_primary"),
])
def test_unresolved_text_is_preserved_without_partial_or_invented_readings(source, expected, reason):
    entries, stats = parse(f"<pron>{source}</pron>")
    assert [entry.reading for entry in entries] == expected
    assert "原文读音：" in flatten(entries[0].glossary)
    assert stats.reading_counts[reason] == 1
    if "\U00100000" in source:
        assert "U+100000" in flatten(entries[0].glossary)
    if "<duyin>" in source:
        assert flatten(entries[0].glossary).count("éi") == 1


def test_missing_reading_and_empty_definition_remain_distinct_from_added_metadata():
    entries, stats = parse("<pron></pron>")
    assert entries[0].reading == ""
    assert "原文读音" not in flatten(entries[0].glossary)
    assert not stats.reading_counts
    entries, _ = parse("<pron>gā<duyin>附注。</duyin></pron>", body="")
    assert "（无可显示释义）" in flatten(entries[0].glossary)
    assert "附注。" in flatten(entries[0].glossary)


def test_extraction_does_not_mutate_source_and_diagnostics_are_bounded():
    pron = html.fromstring("<pron>gā，<duyin><em>gà</em></duyin></pron>")
    before = html.tostring(pron)
    extract_pronunciation(pron)
    assert html.tostring(pron) == before
    stats = ConversionStats()
    for index in range(40):
        stats.record_reading(str(index), "?", [""], ["unresolved_question_mark"])
    assert stats.reading_counts["unresolved_question_mark"] == 40
    assert len(stats.reading_samples["unresolved_question_mark"]) == 25
