from __future__ import annotations

import json
import zipfile
from pathlib import Path

import jsonschema
import pytest

from hydcd_yomitan import builder
from hydcd_yomitan.models import InputSet


@pytest.mark.parametrize("revision", [None, "2025.12.13.9.1", "2025.12.13.10.1", "2025.12.13.10.2"])
def test_archive_contains_valid_update_metadata_and_matching_report(tmp_path, monkeypatch, revision):
    if revision is None:
        monkeypatch.delenv("HYDCD_RELEASE_REVISION", raising=False)
    else:
        monkeypatch.setenv("HYDCD_RELEASE_REVISION", revision)
    inputs = InputSet(tmp_path, tmp_path / "test.mdx", (), ())
    monkeypatch.setattr(builder, "iter_mdx_records", lambda _: iter([
        (1, "字", "<div>释义。</div>".encode()),
    ]))
    monkeypatch.setattr(builder, "input_inventory", lambda _: {
        "files": [{"name": "test.mdx", "sha256": "0" * 64}],
    })
    corrections = tmp_path / "corrections.json"
    corrections.write_text("[]", encoding="utf-8")
    schemas = Path(builder.__file__).parent / "schemas"
    output = tmp_path / "dictionary.zip"

    report, report_path = builder.build_dictionary(inputs, output, schemas, corrections)
    with zipfile.ZipFile(output) as archive:
        index = json.loads(archive.read("index.json"))
    schema = json.loads((schemas / "dictionary-index-schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(index, schema)
    assert index["isUpdatable"] is True
    base = "https://github.com/caocaochan/hydcd-yomitan/releases/latest/download/"
    assert index["indexUrl"] == base + "index.json"
    assert index["downloadUrl"] == base + "hydcd-qiding-yomitan.zip"
    assert index["title"] == "汉语大词典 2025"
    assert index["revision"] == report["dictionary_revision"]
    assert index["revision"] == json.loads(report_path.read_text(encoding="utf-8"))["dictionary_revision"]
    if revision is not None:
        assert index["revision"] == revision
    else:
        assert index["revision"].startswith("2025.12.13-qiding+converter-")
