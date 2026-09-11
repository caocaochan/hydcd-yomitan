from __future__ import annotations

import json
import zipfile
from pathlib import Path

from hydcd_yomitan import builder
from hydcd_yomitan.models import InputSet


def test_build_normalizes_canonical_variant_and_chained_redirect_readings(tmp_path, monkeypatch):
    # Exercise the real parse/cache/emit pipeline with a small in-memory source.
    raw = '''<hdcs><hdc><hm><hw>傳</hw><simp>传</simp><pron>ɡɑ\u0304</pron></hm>
    <item><mean>音标 ɡɑ。</mean></item></hdc></hdcs>'''.encode()
    records = [(1, "傳", raw), (2, "別", "@@@LINK=傳".encode()),
               (3, "别", "@@@LINK=別".encode())]
    inputs = InputSet(tmp_path, tmp_path / "test.mdx", (), ())
    monkeypatch.setattr(builder, "iter_mdx_records", lambda _: iter(records))
    monkeypatch.setattr(builder, "input_inventory", lambda _: {
        "files": [{"name": "test.mdx", "sha256": "0" * 64}],
    })
    corrections = tmp_path / "corrections.json"
    corrections.write_text("[]", encoding="utf-8")
    output = tmp_path / "dictionary.zip"
    schemas = Path(builder.__file__).parent / "schemas"
    report, _ = builder.build_dictionary(inputs, output, schemas, corrections)
    with zipfile.ZipFile(output) as archive:
        terms = json.loads(archive.read("term_bank_1.json"))
    assert [(term[0], term[1], term[7]) for term in terms] == [
        ("傳", "gā", ""), ("传", "gā", "variant"),
        ("別", "gā", "redirect"), ("别", "gā", "redirect"),
    ]
    assert all(term[6] == 1 for term in terms)
    assert all(term[5] == terms[0][5] for term in terms)
    assert "音标 ɡɑ。" in json.dumps(terms[0][5], ensure_ascii=False)
    assert report["counts"]["resolved_redirects"] == 2
