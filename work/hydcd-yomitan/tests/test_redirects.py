from __future__ import annotations

from hydcd_yomitan.builder import _connect, _resolve_ids


def test_redirect_chains_duplicates_and_cycles(tmp_path):
    conn = _connect(tmp_path / "redirects.db")
    rows = [
        (1, "漢", b"canonical-a", None, None),
        (2, "漢", b"canonical-b", None, None),
        (3, "汉", None, "漢", None),
        (4, "汉字", None, "汉", None),
        (5, "甲", None, "乙", None),
        (6, "乙", None, "甲", None),
        (7, "x1", None, "x2", "navigation_redirect"),
    ]
    conn.executemany("INSERT INTO source_entries VALUES (?,?,?,?,?)", rows)
    assert _resolve_ids(conn, "汉字", {}) == (1, 2)
    assert _resolve_ids(conn, "甲", {}) == ()
    assert _resolve_ids(conn, "x1", {}) == ()
    conn.close()
