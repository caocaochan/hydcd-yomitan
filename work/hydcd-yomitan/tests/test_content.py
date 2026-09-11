from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydcd_yomitan.content import is_navigation_record, is_navigation_redirect, parse_record, redirect_target
from hydcd_yomitan.models import ConversionStats
from hydcd_yomitan.resources import ResourceCatalog


def flatten(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(flatten(item) for item in value)
    if isinstance(value, dict):
        return flatten(value.get("content", ""))
    return ""


def nested_lang_values(value):
    result = []
    if isinstance(value, list):
        for item in value:
            result.extend(nested_lang_values(item))
    elif isinstance(value, dict):
        if "lang" in value:
            result.append(value["lang"])
        result.extend(nested_lang_values(value.get("content")))
    return result


def nodes_with_kind(value, kind):
    result = []
    if isinstance(value, list):
        for item in value:
            result.extend(nodes_with_kind(item, kind))
    elif isinstance(value, dict):
        if value.get("data", {}).get("content") == kind:
            result.append(value)
        result.extend(nodes_with_kind(value.get("content"), kind))
    return result


def form_badges(entry):
    root = entry.glossary[0]["content"]
    traditional = [flatten(node) for node in nodes_with_kind(root, "traditional-term")]
    simplified = [flatten(node) for node in nodes_with_kind(root, "simplified-term")]
    return traditional, simplified


def test_redirect_and_navigation_detection():
    assert redirect_target("@@@LINK=漢\r\n\x00") == "漢"
    assert redirect_target("<hdcs></hdcs>") is None
    assert is_navigation_record("x㐌", '<hw>㐌</hw><ul><li>委㐌</li></ul>')
    assert not is_navigation_record("㐌", "<hdcs><hdc></hdc></hdcs>")
    assert is_navigation_redirect("x12", "x34")
    assert not is_navigation_redirect("汉", "漢")


def test_nested_senses_links_security_and_pinyin():
    raw = '''
    <link href="hydcd.css"><script src="evil.js"></script>
    <hdcs><hdc><hm><div class="hw">期度<sup>1</sup></div><simp>期度</simp><pron>qī dù</pron></hm>
    <item><mean><xh>1</xh>法度；<u>限度</u>。</mean>
    <submeans><submean><xh>1</xh>子义。</submean></submeans>
    <examples><example><book>《汉书》</book>：<quote>无期度。</quote>
    <note>参见<a href="entry://法度">法度</a>。</note></example></examples></item>
    </hdc></hdcs>'''
    stats = ConversionStats()
    result = parse_record("期度", raw, None, stats)
    assert len(result) == 1
    assert result[0].expression == "期度"
    assert result[0].reading == "qī dù"
    encoded = json.dumps(result[0].glossary, ensure_ascii=False)
    assert "evil.js" not in encoded
    assert "?query=%E6%B3%95%E5%BA%A6" in encoded
    assert "details" in encoded
    assert "法度" in flatten(result[0].glossary)
    root = result[0].glossary[0]["content"]
    assert root["lang"] == "zh-Hans"
    assert nested_lang_values(root["content"]) == []
    assert not stats.unknown_tags


def test_literal_corner_brackets_inside_quote_are_stripped():
    raw = '''<hdcs class="fw"><hdc><hm><div class="hw">俢</div><pron>xiū</pron></hm>
    <item><mean><a href="entry://修"><quote>「修」</quote></a>的古字。</mean>
    <examples><example><quote>「甲<u>乙</u>丙」</quote></example>
    <example><quote>无期度。</quote></example></examples></item></hdc></hdcs>'''
    stats = ConversionStats()
    result = parse_record("俢", raw, None, stats)
    quotes = [node["content"] for node in nodes_with_kind(result[0].glossary[0]["content"], "quote")]
    assert quotes[0] == ["修"]
    assert quotes[1][0] == "甲" and quotes[1][-1] == "丙"
    assert quotes[2] == ["无期度。"]
    assert "「" not in flatten(result[0].glossary)
    assert stats.counters["quote_literal_brackets_stripped"] == 2


def test_generic_record_has_one_zh_hans_language_boundary():
    result = parse_record("通用", "<div>通用释义。</div>", None, ConversionStats())
    root = result[0].glossary[0]["content"]
    assert root["tag"] == "span"
    assert root["data"]["content"] == "hydcd-entry"
    assert root["lang"] == "zh-Hans"
    assert nested_lang_values(root["content"]) == []
    assert form_badges(result[0]) == (["通用"], [])
    assert nodes_with_kind(root, "generic-content")


def test_multiple_homographs_and_extension_character():
    raw = '''<hdcs>
    <hdc><hm><div class="hw">𠮷期<sup>1</sup></div><pron>jí qī</pron></hm><item><mean>甲。</mean></item></hdc>
    <hdc><hm><div class="hw">𠮷期<sup>2</sup></div><pron>jí qí</pron></hm><item><mean>乙。</mean></item></hdc>
    </hdcs>'''
    result = parse_record("𠮷期", raw, None, ConversionStats())
    assert [item.expression for item in result] == ["𠮷期", "𠮷期"]
    assert [item.reading for item in result] == ["jí qī", "jí qí"]
    assert [form_badges(item) for item in result] == [(["𠮷期"], []), (["𠮷期"], [])]


@pytest.mark.parametrize(("source", "expected"), [
    ("ɡɑ", "ga"),
    ("ɡɑ\u0304", "gā"),
    ("ɡɑ\u0301", "gá"),
    ("ɡɑ\u030c", "gǎ"),
    ("ɡɑ\u0300", "gà"),
    ("fǎnɡ  huɑi", "fǎng  huai"),
    ("lǜ nü\u030c  nǚ", "lǜ nǚ  nǚ"),
    ("", ""),
])
def test_pinyin_letters_and_tones_are_normalized_only_in_readings(source, expected):
    raw = f'''<hdcs><hdc><hm><hw>字</hw><pron>{source}</pron></hm>
    <item><mean>音标 ɡɑ；保留原文。</mean></item></hdc></hdcs>'''
    entry = parse_record("字", raw, None, ConversionStats())[0]
    assert entry.expression == "字"
    assert entry.reading == expected
    assert "音标 ɡɑ；保留原文。" in flatten(entry.glossary)


def test_multiple_readings_normalize_nested_pronunciation_text():
    raw = '''<hdcs>
    <hdc><hm><hw>字</hw><pron>ɡ<span>ɑ\u0304</span></pron></hm><item>甲</item></hdc>
    <hdc><hm><hw>字</hw><pron>ɡɑ\u0300</pron></hm><item>乙</item></hdc>
    </hdcs>'''
    entries = parse_record("字", raw, None, ConversionStats())
    assert [entry.reading for entry in entries] == ["gā", "gà"]


def test_unknown_tag_unwraps_text():
    stats = ConversionStats()
    result = parse_record(
        "测试", '<hdcs><hdc><hm><div class="hw">测试</div></hm><item><mean><mystery>保留</mystery></mean></item></hdc></hdcs>',
        None, stats,
    )
    assert "保留" in flatten(result[0].glossary)
    assert stats.unknown_tags["mystery"] == 1


def test_missing_image_is_fatal(tmp_path: Path):
    catalog = ResourceCatalog(tmp_path, ConversionStats())
    raw = '<hdcs><hdc><hm><div class="hw">图</div></hm><item><mean><img src="404.jpg"></mean></item></hdc></hdcs>'
    with pytest.raises(FileNotFoundError):
        parse_record("图", raw, catalog, catalog.stats)


def test_dual_script_pua_table_and_explicit_source_tags(tmp_path: Path):
    stats = ConversionStats()
    catalog = ResourceCatalog(tmp_path, stats)
    media = tmp_path / "fixture.jpg"
    media.write_bytes(b"fixture")
    catalog.source_to_output["plate.jpg"] = "media/fixture.jpg"
    catalog.output_to_file["media/fixture.jpg"] = media
    raw = '''<hdcs><hdc><hm><div class="hw">\ue000𠮷</div><simplified>吉</simplified><pron>jí</pron></hm>
    <item><mean><sensenum>1</sensenum><math><mrow><mi>x</mi><mo>+</mo><msqrt><mi>y</mi></msqrt></mrow></math>
    <table><tr><th>甲</th><td colspan="2">乙</td></tr></table><img src="plate.jpg"></mean></item>
    </hdc></hdcs>'''
    result = parse_record("\ue000𠮷", raw, catalog, stats)
    encoded = json.dumps(result[0].glossary, ensure_ascii=False)
    assert result[0].alternate_terms == ["吉"]
    assert form_badges(result[0]) == (["\ue000𠮷"], ["吉"])
    assert not nodes_with_kind(result[0].glossary, "header")
    assert "media/fixture.jpg" in encoded and '"colSpan": 2' in encoded
    assert stats.counters["entries_with_unresolved_pua"] == 1
    assert stats.unresolved_pua_samples == ["\ue000𠮷"]
    assert not stats.unknown_tags


def test_script_forms_are_ordered_deduplicated_and_separate_from_header_metadata():
    raw = '''<hdcs><hdc><hm><div class="hw">學習</div><simp>学习</simp><simp>学习</simp>
    <pron>xué xí</pron><duyin>旧读</duyin></hm><item><mean>释义。</mean></item></hdc></hdcs>'''
    result = parse_record("學習", raw, None, ConversionStats())
    assert result[0].alternate_terms == ["学习"]
    assert form_badges(result[0]) == (["學習"], ["学习"])
    header = nodes_with_kind(result[0].glossary, "header")
    assert len(header) == 1 and flatten(header[0]) == "旧读"
    assert "学习" not in flatten(header[0])


def test_tradition_tag_reverses_badge_roles_and_identical_form_is_omitted():
    reverse = '''<hdcs><hdc><hm><div class="hw">仑</div><tradition>侖</tradition><pron>lún</pron></hm>
    <item><mean>释义。</mean></item></hdc></hdcs>'''
    result = parse_record("仑", reverse, None, ConversionStats())
    assert result[0].alternate_terms == ["侖"]
    assert form_badges(result[0]) == (["侖"], ["仑"])

    identical = '''<hdcs><hdc><hm><div class="hw">期度</div><simp>期度</simp><pron>qī dù</pron></hm>
    <item><mean>释义。</mean></item></hdc></hdcs>'''
    same_result = parse_record("期度", identical, None, ConversionStats())
    assert same_result[0].alternate_terms == []
    assert form_badges(same_result[0]) == (["期度"], [])
