from __future__ import annotations

import json
import importlib.util
import zipfile
from pathlib import Path

import pytest

from hydcd_yomitan import builder
from hydcd_yomitan.cli import _parser
from hydcd_yomitan.content import parse_record
from hydcd_yomitan.editions import EDITIONS, LIGHT_OMISSION, UPDATE_BASE
from hydcd_yomitan.models import ConversionStats, InputSet
from hydcd_yomitan.package import deterministic_zip
from hydcd_yomitan.validation import validate_dictionary
from test_content import flatten, form_badges, nodes_with_kind


def parse(raw, stats=None):
    return parse_record("字", raw, None, stats or ConversionStats(), edition="light")[0]


def test_light_removes_subtrees_and_preserves_surrounding_definition_text():
    stats = ConversionStats()
    entry = parse('''<hdc><hm><hw>字</hw><pron>zì</pron><yinyun>古音。</yinyun></hm>
    <item><mean><xh>1</xh>之前<img src="missing.png">之后<quote>定义引文</quote>
    <book>定义书名</book><source>定义来源</source><sourcedetail>卷一</sourcedetail>
    <note>解释注释</note><see><a href="entry://詞">参见詞</a></see></mean>
    <examples><example>删除例句<note>删除注释</note><img src="also-missing.png"></example></examples>
    <example>删除独立例句</example>保留尾文<examplenote>删除例注</examplenote>
    <div><span><img src="third.png"></span></div></item></hdc>''', stats)
    text = flatten(entry.glossary)
    for retained in ["古音。", "之前之后", "定义引文", "定义书名", "定义来源", "卷一", "解释注释", "保留尾文"]:
        assert retained in text
    assert "删除" not in text
    assert LIGHT_OMISSION not in text
    assert entry.reading == "zì"
    assert nodes_with_kind(entry.glossary, "sense-number")
    assert not nodes_with_kind(entry.glossary, "examples")
    assert "missing.png" not in json.dumps(entry.glossary)
    assert stats.counters["light_removed_img"] == 3
    assert stats.counters["light_removed_examples"] == 1
    assert stats.counters["light_removed_example"] == 2
    assert stats.counters["light_removed_examplenote"] == 1
    assert stats.counters["light_removed_empty_containers"] == 2


@pytest.mark.parametrize("body", [
    '<mean><xh>2</xh><img src="missing.png"></mean>',
    '<submean><sensenum>2</sensenum><examples><example>删除</example></examples></submean>',
    '<item><examples><example>删除</example></examples></item>',
    '<div><img src="missing.png"></div>',
    '<mean><span><xh>2</xh><img src="missing.png"></span>。</mean>',
])
def test_light_empty_senses_and_entries_get_one_notice(body):
    entry = parse(f'<hdc><hm><hw>字</hw><pron>zì</pron><yinyun>古音</yinyun></hm>{body}</hdc>')
    text = flatten(entry.glossary)
    assert text.count(LIGHT_OMISSION) == 1
    assert "删除" not in text
    assert "古音" in text
    if "num>" in body or "xh>" in body:
        assert flatten(nodes_with_kind(entry.glossary, "sense-number")) == "2"


def test_light_generic_text_and_top_level_tails_never_restore_examples():
    assert flatten(parse('前<example>删除</example>后<div><img src="x"></div>').glossary) == "字前后"
    assert flatten(parse('<example>删除</example>').glossary) == "字" + LIGHT_OMISSION
    entry = parse('<hdc><hm><hw>字</hw></hm>前<examples>删除</examples>后</hdc>')
    assert flatten(entry.glossary) == "字前后"


def test_light_preserves_reading_metadata_and_script_forms():
    raw = '''<hdc><hm><hw>傳</hw><simp>传</simp><pron>ɡɑ̄<note>旧读</note></pron>
    <yinyun>《广韵》古音</yinyun></hm><item><mean>释义<quote>引文</quote></mean>
    <examples><example>例句</example></examples></item></hdc>'''
    full = parse_record("傳", raw, None, ConversionStats())[0]
    light = parse(raw)
    assert (light.expression, light.reading, light.alternate_terms) == (full.expression, full.reading, full.alternate_terms)
    assert form_badges(light) == form_badges(full)
    for kind in ["header", "reading-metadata", "phonology", "sense", "quote"]:
        assert nodes_with_kind(light.glossary, kind) == nodes_with_kind(full.glossary, kind)


def build_fixture(tmp_path, monkeypatch, edition):
    raw = '''<hdc><hm><hw>傳</hw><simp>传</simp><pron>ɡɑ̄/ɡɑ̀</pron></hm>
    <item><mean>释义。</mean><examples><example>例句</example></examples></item></hdc>'''.encode()
    records = [(1, "傳", raw), (2, "別", "@@@LINK=傳".encode()), (3, "别", "@@@LINK=別".encode())]
    monkeypatch.setattr(builder, "iter_mdx_records", lambda _: iter(records))
    monkeypatch.setattr(builder, "input_inventory", lambda _: {"files": [{"name": "test.mdx", "sha256": "0" * 64}]})
    monkeypatch.setenv("HYDCD_RELEASE_REVISION", "2025.12.13.99.1")
    corrections = tmp_path / "corrections.json"
    corrections.write_text("[]", encoding="utf-8")
    output = tmp_path / EDITIONS[edition].archive
    schemas = Path(builder.__file__).parent / "schemas"
    report, report_path = builder.build_dictionary(
        InputSet(tmp_path, tmp_path / "test.mdx", (), ()), output, schemas, corrections, edition=edition,
    )
    return output, report, report_path, schemas


def test_both_editions_preserve_lookup_rows_css_and_independent_update_channels(tmp_path, monkeypatch):
    full, full_report, full_report_path, _ = build_fixture(tmp_path, monkeypatch, "full")

    def fail_resources(*args, **kwargs):
        pytest.fail("Light must not extract or process MDD resources")

    monkeypatch.setattr(builder.ResourceCatalog, "build", fail_resources)
    light, report, report_path, schemas = build_fixture(tmp_path, monkeypatch, "light")
    first_bytes = light.read_bytes()
    build_fixture(tmp_path, monkeypatch, "light")
    assert light.read_bytes() == first_bytes
    assert full_report_path.exists() and full_report_path != report_path
    assert report["edition"] == "light" and report["used_resources"] == 0
    assert report["dictionary_revision"] == full_report["dictionary_revision"]
    with zipfile.ZipFile(full) as f, zipfile.ZipFile(light) as l:
        full_rows = json.loads(f.read("term_bank_1.json"))
        light_rows = json.loads(l.read("term_bank_1.json"))
        assert len(light_rows) == 8
        assert [r[:5] + r[6:] for r in light_rows] == [r[:5] + r[6:] for r in full_rows]
        assert all(r[5] == light_rows[0][5] for r in light_rows)
        assert f.read("styles.css") == l.read("styles.css")
        assert not any(name.startswith("media/") for name in l.namelist())
        index = json.loads(l.read("index.json"))
        assert index["title"] == EDITIONS["light"].title
        assert index["indexUrl"] == UPDATE_BASE + "index-light.json"
        assert index["downloadUrl"] == UPDATE_BASE + light.name
    result = validate_dictionary(light, schemas, edition="light")
    assert result["valid"], result["errors"]


@pytest.mark.parametrize("bad_node,media", [
    ({"tag": "img", "path": "x.png"}, False),
    ({"tag": "details", "data": {"content": "examples"}, "content": "bad"}, False),
    ({"tag": "div", "data": {"content": "example"}, "content": "bad"}, False),
    ({"tag": "examplenote", "content": "bad"}, False),
    (None, True),
])
def test_light_validation_rejects_removed_content_and_unreferenced_media(tmp_path, monkeypatch, bad_node, media):
    path, _, _, schemas = build_fixture(tmp_path, monkeypatch, "light")
    with zipfile.ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    if bad_node:
        rows = json.loads(files["term_bank_1.json"])
        rows[0][5][0]["content"]["content"].append(bad_node)
        files["term_bank_1.json"] = json.dumps(rows).encode()
    if media:
        files["orphan.svg"] = b"<svg/>"
    deterministic_zip(path, files.items())
    result = validate_dictionary(path, schemas, edition="light", archive_only=True)
    assert not result["valid"]
    assert any("Light edition" in error for error in result["errors"])


def test_cli_edition_defaults_and_invalid_api_values():
    parser = _parser()
    assert parser.parse_args(["build", "--input", ".", "--output", "x.zip"]).edition == "full"
    assert parser.parse_args(["validate", "x.zip", "--edition", "light"]).edition == "light"
    with pytest.raises(ValueError, match="Unknown edition"):
        parse_record("字", "字", None, ConversionStats(), edition="tiny")


def release_module():
    script = Path(__file__).resolve().parents[3] / ".github/scripts/prepare_release.py"
    spec = importlib.util.spec_from_file_location("prepare_release", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_preparation_extracts_exact_indexes_and_both_checksums(tmp_path, monkeypatch):
    for edition in EDITIONS:
        build_fixture(tmp_path, monkeypatch, edition)
    comparison = release_module().prepare(tmp_path)
    assert comparison["lookup_rows_identical"] and comparison["css_identical"]
    checksums = (tmp_path / "SHA256SUMS").read_text().splitlines()
    assert len(checksums) == 2
    for edition, identity in EDITIONS.items():
        with zipfile.ZipFile(tmp_path / identity.archive) as archive:
            assert (tmp_path / identity.index).read_bytes() == archive.read("index.json")
            assert comparison["editions"][edition]["uncompressed_bytes"] == sum(i.file_size for i in archive.infolist())
        assert any(line.endswith("  " + identity.archive) for line in checksums)
    assert "Light" in (tmp_path / "release-notes.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("mutation", ["lookup", "css", "revision", "update_channel"])
def test_release_preparation_refuses_mismatched_editions(tmp_path, monkeypatch, mutation):
    for edition in EDITIONS:
        build_fixture(tmp_path, monkeypatch, edition)
    path = tmp_path / EDITIONS["light"].archive
    with zipfile.ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    if mutation == "lookup":
        rows = json.loads(files["term_bank_1.json"])
        rows.pop()
        files["term_bank_1.json"] = json.dumps(rows).encode()
    elif mutation == "css":
        files["styles.css"] += b"/* changed */"
    else:
        index = json.loads(files["index.json"])
        index["revision" if mutation == "revision" else "indexUrl"] = "wrong"
        files["index.json"] = json.dumps(index).encode()
    deterministic_zip(path, files.items())
    with pytest.raises(ValueError, match="lookup rows, CSS, or revision|incorrect indexUrl"):
        release_module().prepare(tmp_path)
    assert not (tmp_path / "index-light.json").exists()


def test_release_preparation_requires_identical_source_hashes(tmp_path, monkeypatch):
    for edition in EDITIONS:
        build_fixture(tmp_path, monkeypatch, edition)
    path = tmp_path / EDITIONS["light"].report
    report = json.loads(path.read_text(encoding="utf-8"))
    report["input"]["files"][0]["sha256"] = "1" * 64
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="different source inputs"):
        release_module().prepare(tmp_path)


def test_light_preserves_definitions_that_only_differ_in_examples_and_deduplicates_true_copies(tmp_path, monkeypatch):
    def definition(number, example):
        return f'<hdc><hm><hw>詞<sup>{number}</sup></hw><simp>词</simp><pron>cí</pron></hm><item><mean>释义。</mean><examples><example>{example}</example></examples></item></hdc>'

    raw = (definition(1, "甲") + definition(2, "乙") + definition(3, "乙")).encode()
    records = [(1, "詞", raw), (2, "別", "@@@LINK=詞".encode()), (3, "别", "@@@LINK=別".encode()),
               (4, "別", "@@@LINK=詞".encode())]
    monkeypatch.setattr(builder, "iter_mdx_records", lambda _: iter(records))
    monkeypatch.setattr(builder, "input_inventory", lambda _: {"files": [{"name": "test.mdx", "sha256": "0" * 64}]})
    corrections = tmp_path / "corrections.json"
    corrections.write_text("[]", encoding="utf-8")
    rows = {}
    for edition in EDITIONS:
        path = tmp_path / EDITIONS[edition].archive
        builder.build_dictionary(InputSet(tmp_path, tmp_path / "test.mdx", (), ()), path,
                                 Path(builder.__file__).parent / "schemas", corrections, edition=edition)
        with zipfile.ZipFile(path) as archive:
            rows[edition] = json.loads(archive.read("term_bank_1.json"))
    assert [r[:5] + r[6:] for r in rows["light"]] == [r[:5] + r[6:] for r in rows["full"]]
    assert len(rows["light"]) == 8
    assert all(r[5] == rows["light"][0][5] for r in rows["light"])
    assert "omitted_content_id" not in json.dumps(rows["light"])
