from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from hydcd_yomitan.package import deterministic_zip, write_json
from hydcd_yomitan.validation import validate_dictionary


def test_deterministic_zip_and_schema_validation(tmp_path: Path):
    schemas = Path(__file__).parents[1] / "hydcd_yomitan" / "schemas"
    stage = tmp_path / "stage"
    stage.mkdir()
    index = {"title": "test", "revision": "1", "format": 3, "sequenced": True, "sourceLanguage": "zh", "targetLanguage": "zh"}
    term = ["漢", "hàn", "", "", 0, [{
        "type": "structured-content",
        "content": {
            "tag": "span", "lang": "zh-Hans", "data": {"content": "hydcd-entry"},
            "content": "汉字",
        },
    }], 1, ""]
    write_json(stage / "index.json", index)
    write_json(stage / "term_bank_1.json", [term])
    (stage / "styles.css").write_text(
        '[data-sc-content="hydcd-entry"] { font-family: sans-serif; line-height: 1.55; }\n',
        encoding="utf-8",
    )
    first = tmp_path / "a.zip"
    second = tmp_path / "b.zip"
    files = [(p.name, p) for p in stage.iterdir()]
    assert deterministic_zip(first, files) == deterministic_zip(second, files)
    assert first.read_bytes() == second.read_bytes()
    result = validate_dictionary(first, schemas)
    assert result["valid"], result["errors"]
    assert result["validation_mode"] == "targeted"
    assert result["structured_glossaries"] == result["zh_hans_roots"] == 1
    assert result["nested_lang_attributes"] == 0
    assert result["css_uses_sans_serif"]


@pytest.mark.parametrize(("reading", "language", "title", "error"), [
    ("gā", "zh-Hans", "test", None),
    ("ɡā", "zh-Hans", "test", "reading is not normalized pinyin"),
    ("mɑ", "zh-Hans", "test", "reading is not normalized pinyin"),
    ("ga\u0304", "zh-Hans", "test", "reading is not normalized pinyin"),
    ("ｋé", "zh-Hans", "test", "reading is not normalized pinyin"),
    ("dｅ", "zh-Hans", "test", "reading is not normalized pinyin"),
    ("gā\u2003gà", "zh-Hans", "test", "reading is not normalized pinyin"),
    ("gā/gà", "zh-Hans", "test", "reading is not normalized pinyin"),
    ("［xiū ㄒㄧㄡ］", "zh-Hans", "test", "reading is not normalized pinyin"),
    ("ế（又读éi）", "zh-Hans", "test", "reading is not normalized pinyin"),
    ("\U00100000 mā", "zh-Hans", "test", "reading is not normalized pinyin"),
    ("yāo ?", "zh-Hans", "test", "reading is not normalized pinyin"),
    ("", "zh-Hans", "test", None),
    ("gā", "zh-Hant", "test", "root lang is not zh-Hans"),
    ("gā", "zh-Hans", None, "index.json"),
])
def test_archive_only_retains_reading_language_and_index_checks(tmp_path, reading, language, title, error):
    schemas = Path(__file__).parents[1] / "hydcd_yomitan" / "schemas"
    index = {"revision": "1", "format": 3}
    if title is not None:
        index["title"] = title
    term = ["字", reading, "", "", 0, [{
        "type": "structured-content",
        "content": {
            "tag": "span", "lang": language, "data": {"content": "hydcd-entry"},
            "content": "音标 ɡɑ 保留在释义中。",
        },
    }], 1, ""]
    path = tmp_path / "dictionary.zip"
    deterministic_zip(path, [
        ("index.json", json.dumps(index).encode()),
        ("term_bank_1.json", json.dumps([term]).encode()),
        ("styles.css", b'[data-sc-content="hydcd-entry"] { font-family: sans-serif; }'),
    ])
    result = validate_dictionary(path, schemas, archive_only=True)
    assert result["validation_mode"] == "archive-only"
    assert result["schema_validated_banks"] == []
    assert result["valid"] == (error is None)
    if error:
        assert any(error in value for value in result["errors"])


def test_validation_modes_are_mutually_exclusive(tmp_path):
    from hydcd_yomitan.cli import _parser

    with pytest.raises(ValueError, match="mutually exclusive"):
        validate_dictionary(tmp_path / "unused.zip", tmp_path, exhaustive=True, archive_only=True)
    with pytest.raises(SystemExit) as exc:
        _parser().parse_args(["validate", "unused.zip", "--exhaustive", "--archive-only"])
    assert exc.value.code == 2
