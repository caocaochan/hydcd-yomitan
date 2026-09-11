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


def test_alternatives_and_unresolved_readings_reach_variants_and_redirects(tmp_path, monkeypatch):
    raw = '''<hdcs><hdc><hm><hw>傳風</hw><simp>传风</simp>
    <pron>chuán fěnɡ/chuán fènɡ</pron></hm><item>原释义。</item></hdc></hdcs>'''.encode()
    unknown = '''<hdcs><hdc><hm><hw>姆媽</hw><simp>姆妈</simp><pron>\U00100000 mā</pron></hm>
    <item>方言。</item></hdc></hdcs>'''.encode()
    records = [(1, "傳風", raw), (2, "別稱", "@@@LINK=傳風".encode()),
               (3, "别称", "@@@LINK=別稱".encode()), (4, "姆媽", unknown),
               (5, "未知別稱", "@@@LINK=姆媽".encode()),
               (6, "未知别称", "@@@LINK=未知別稱".encode())]
    inputs = InputSet(tmp_path, tmp_path / "test.mdx", (), ())
    monkeypatch.setattr(builder, "iter_mdx_records", lambda _: iter(records))
    monkeypatch.setattr(builder, "input_inventory", lambda _: {
        "files": [{"name": "test.mdx", "sha256": "0" * 64}],
    })
    corrections = tmp_path / "corrections.json"
    corrections.write_text("[]", encoding="utf-8")
    output = tmp_path / "dictionary.zip"
    report, _ = builder.build_dictionary(inputs, output, Path(builder.__file__).parent / "schemas", corrections)
    with zipfile.ZipFile(output) as archive:
        terms = json.loads(archive.read("term_bank_1.json"))
    for expression in ["傳風", "传风", "別稱", "别称"]:
        rows = [term for term in terms if term[0] == expression]
        assert [term[1] for term in rows] == ["chuán fěng", "chuán fèng"]
        assert all(term[6] == 1 and term[5] == terms[0][5] for term in rows)
    unknown_rows = [term for term in terms if term[0] in {"姆媽", "姆妈", "未知別稱", "未知别称"}]
    assert len(unknown_rows) == 4
    assert [term[7] for term in unknown_rows] == ["", "variant", "redirect", "redirect"]
    assert all(term[1] == "" and term[6] == 4 for term in unknown_rows)
    assert all("U+100000" in json.dumps(term[5], ensure_ascii=False) for term in unknown_rows)
    assert report["counts"]["source_pronunciation_blocks"] == 2
    assert report["reading_diagnostics"]["counts"]["slash_alternatives"] == 1
    assert report["reading_diagnostics"]["counts"]["unresolved_private_use"] == 1
    assert report["counts"]["emitted_terms"] == 12
