from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
import unicodedata
import zlib
from pathlib import Path
from typing import Any

import psutil

from . import __version__
from .content import is_navigation_record, is_navigation_redirect, parse_record, redirect_target
from .corrections import apply_corrections, load_corrections
from .editions import UPDATE_BASE, get_edition
from .models import ConversionStats, InputSet, ParsedEntry
from .package import TermBankWriter, deterministic_zip, write_json
from .resources import ResourceCatalog
from .source import input_inventory, iter_mdx_records


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=FILE")
    conn.executescript(
        """
        CREATE TABLE source_entries (
            id INTEGER PRIMARY KEY,
            headword TEXT NOT NULL,
            raw BLOB,
            redirect TEXT,
            exclusion TEXT
        );
        CREATE TABLE rendered (
            source_id INTEGER PRIMARY KEY,
            payload BLOB NOT NULL
        );
        CREATE TABLE dedupe (signature BLOB PRIMARY KEY);
        """
    )
    return conn


def _record_signature(entry: list[Any]) -> bytes:
    encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).digest()


def _emit(
    bank: TermBankWriter, conn: sqlite3.Connection, entry: list[Any], stats: ConversionStats,
    omitted_content_id: str = "",
) -> bool:
    signature = _record_signature(entry)
    if omitted_content_id:
        signature = hashlib.sha256(signature + omitted_content_id.encode("ascii")).digest()
    inserted = conn.execute("INSERT OR IGNORE INTO dedupe(signature) VALUES (?)", (signature,)).rowcount
    if not inserted:
        stats.counters["deduplicated_terms"] += 1
        return False
    bank.add(entry)
    stats.counters["emitted_terms"] += 1
    return True


def _term_row(expression: str, reading: str, glossary: list[Any], sequence: int, tags: str = "") -> list[Any]:
    return [unicodedata.normalize("NFC", expression), unicodedata.normalize("NFC", reading), "", "", 0, glossary, sequence, tags]


def _payload(parsed: list[ParsedEntry]) -> bytes:
    data = [
        {"expression": p.expression, "reading": p.reading, "glossary": p.glossary, "alternate_terms": p.alternate_terms,
         "omitted_content_id": p.omitted_content_id}
        for p in parsed
    ]
    return zlib.compress(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), level=9)


def _decode_payload(value: bytes) -> list[dict[str, Any]]:
    return json.loads(zlib.decompress(value).decode("utf-8"))


def _resolve_ids(conn: sqlite3.Connection, target: str, cache: dict[str, tuple[int, ...]], stack: tuple[str, ...] = ()) -> tuple[int, ...]:
    if target in cache:
        return cache[target]
    if target in stack or len(stack) >= 64:
        cache[target] = ()
        return ()
    rows = conn.execute(
        "SELECT id, redirect, exclusion FROM source_entries WHERE headword=? ORDER BY id", (target,)
    ).fetchall()
    canonical = tuple(row[0] for row in rows if row[1] is None and row[2] is None)
    if canonical:
        cache[target] = canonical
        return canonical
    result: list[int] = []
    for _, redirect, exclusion in rows:
        if redirect and exclusion is None:
            result.extend(_resolve_ids(conn, redirect, cache, stack + (target,)))
    cache[target] = tuple(dict.fromkeys(result))
    return cache[target]


def _max_rss_bytes() -> int:
    memory = psutil.Process().memory_info()
    return int(getattr(memory, "peak_wset", memory.rss))


def build_dictionary(
    inputs: InputSet, output: Path, schemas: Path, corrections_path: Path, *, edition: str = "full",
) -> tuple[dict, Path]:
    identity = get_edition(edition)
    started = time.perf_counter()
    inventory = input_inventory(inputs)
    mdx_sha = next(item["sha256"] for item in inventory["files"] if item["name"] == inputs.mdx.name)
    stats = ConversionStats()
    corrections = load_corrections(corrections_path)
    output = output.resolve()
    report_path = output.with_name(identity.report)
    with tempfile.TemporaryDirectory(prefix="hydcd-yomitan-") as temporary:
        temp = Path(temporary)
        stage = temp / "dictionary"
        stage.mkdir()
        resources = ResourceCatalog.build(inputs.mdds, temp / "resources", stats) if edition == "full" else None
        conn = _connect(temp / "index.db")
        batch: list[tuple[int, str, bytes | None, str | None, str | None]] = []
        for ordinal, headword, raw_bytes in iter_mdx_records(inputs.mdx):
            stats.counters["input_records"] += 1
            target = redirect_target(raw_bytes)
            if target is not None:
                if is_navigation_redirect(headword, target):
                    batch.append((ordinal, headword, None, target, "navigation_redirect"))
                    stats.exclusions["navigation_redirect"] += 1
                    stats.counters["excluded_records"] += 1
                else:
                    batch.append((ordinal, headword, None, target, None))
                    stats.counters["redirect_records"] += 1
            else:
                raw = raw_bytes.decode("utf-8", "strict").replace("\x00", "")
                exclusion = "navigation" if is_navigation_record(headword, raw) else None
                if exclusion:
                    stats.exclusions[exclusion] += 1
                    stats.counters["excluded_records"] += 1
                    batch.append((ordinal, headword, None, None, exclusion))
                else:
                    raw = apply_corrections(headword, raw, mdx_sha, corrections, stats)
                    batch.append((ordinal, headword, zlib.compress(raw.encode("utf-8"), 6), None, None))
                    stats.counters["canonical_records"] += 1
            if len(batch) >= 1024:
                conn.executemany("INSERT INTO source_entries VALUES (?,?,?,?,?)", batch)
                conn.commit()
                batch.clear()
        if batch:
            conn.executemany("INSERT INTO source_entries VALUES (?,?,?,?,?)", batch)
            conn.commit()
        conn.execute("CREATE INDEX source_headword ON source_entries(headword)")
        conn.execute("CREATE INDEX source_redirect ON source_entries(redirect)")
        conn.commit()

        bank = TermBankWriter(stage, 10_000)
        cursor = conn.execute("SELECT id, headword, raw FROM source_entries WHERE raw IS NOT NULL ORDER BY id")
        for source_id, headword, compressed in cursor:
            raw = zlib.decompress(compressed).decode("utf-8")
            parsed = parse_record(headword, raw, resources, stats, edition=edition)
            conn.execute("INSERT INTO rendered VALUES (?,?)", (source_id, _payload(parsed)))
            for item in parsed:
                _emit(bank, conn, _term_row(item.expression, item.reading, item.glossary, source_id), stats, item.omitted_content_id)
                for alternate in item.alternate_terms:
                    exists = conn.execute("SELECT 1 FROM source_entries WHERE headword=? LIMIT 1", (alternate,)).fetchone()
                    if not exists:
                        _emit(bank, conn, _term_row(alternate, item.reading, item.glossary, source_id, "variant"), stats, item.omitted_content_id)
                        stats.counters["generated_source_variants"] += 1
            if source_id % 2048 == 0:
                conn.commit()
        conn.commit()

        resolution_cache: dict[str, tuple[int, ...]] = {}
        redirects = conn.execute(
            "SELECT id, headword, redirect FROM source_entries "
            "WHERE redirect IS NOT NULL AND exclusion IS NULL ORDER BY id"
        )
        for source_id, alias, target in redirects:
            canonical_ids = _resolve_ids(conn, target, resolution_cache)
            if not canonical_ids:
                stats.counters["unresolved_redirects"] += 1
                stats.error(f"Unresolved source redirect {alias} -> {target}")
                continue
            stats.counters["resolved_redirects"] += 1
            for canonical_id in canonical_ids:
                row = conn.execute("SELECT payload FROM rendered WHERE source_id=?", (canonical_id,)).fetchone()
                if row is None:
                    stats.counters["unresolved_redirects"] += 1
                    stats.error(f"Redirect target was not rendered: {alias} -> {target} ({canonical_id})")
                    continue
                for rendered in _decode_payload(row[0]):
                    _emit(
                        bank, conn,
                        _term_row(alias, rendered["reading"], rendered["glossary"], canonical_id, "redirect"),
                        stats, rendered["omitted_content_id"],
                    )
            if source_id % 4096 == 0:
                conn.commit()
        bank.close()
        conn.commit()

        revision = os.environ.get(
            "HYDCD_RELEASE_REVISION",
            f"2025.12.13-qiding+converter-{__version__}+{mdx_sha[:12]}",
        )
        index = {
            "title": identity.title,
            "revision": revision,
            "isUpdatable": True,
            "indexUrl": UPDATE_BASE + identity.index,
            "downloadUrl": UPDATE_BASE + identity.archive,
            "format": 3,
            "sequenced": True,
            "author": "Original lexicographers and FreeMdict community editors; private Yomitan conversion",
            "url": "https://forum.freemdict.com/t/topic/43800",
            "description": "Private structured-content conversion. Definitions, citations, pinyin, source labels, dual-script redirects, and referenced images are preserved; executable and network features are removed.",
            "attribution": "Source supplied by the user for private research use. Converter does not grant redistribution rights.",
            "sourceLanguage": "zh",
            "targetLanguage": "zh",
        }
        if edition == "light":
            index["description"] = (
                "Light structured-content conversion. Images and complete example blocks, including their "
                "citations and notes, are removed. Definitions, pinyin, historical phonology, other notes, "
                "source labels, dual-script redirects, and styling are preserved."
            )
        write_json(stage / "index.json", index)
        styles = (Path(__file__).parent / "data" / "styles.css").read_bytes()
        (stage / "styles.css").write_bytes(styles)

        package_files: list[tuple[str, Path | bytes]] = []
        for file in stage.iterdir():
            package_files.append((file.name, file))
        if resources is not None:
            for resource in sorted(resources.used_outputs):
                package_files.append((resource, resources.output_to_file[resource]))
        output_sha = deterministic_zip(output, package_files)
        elapsed = time.perf_counter() - started
        report = {
            "edition": edition,
            "converter_version": __version__,
            "dictionary_revision": revision,
            "input": inventory,
            "output": {
                "path": str(output), "size": output.stat().st_size, "sha256": output_sha,
                "term_banks": bank.bank_number, "terms": bank.total,
            },
            "counts": dict(sorted(stats.counters.items())),
            "exclusions": dict(sorted(stats.exclusions.items())),
            "unknown_tags": dict(stats.unknown_tags.most_common()),
            "resource_extensions": dict(sorted(stats.resource_extensions.items())),
            "used_resources": len(resources.used_outputs) if resources is not None else 0,
            "missing_reading_samples": stats.missing_reading_samples,
            "unresolved_pua_samples": stats.unresolved_pua_samples,
            "warning_samples": stats.warning_samples,
            "error_samples": stats.error_samples,
            "corrections": stats.correction_log,
            "reading_diagnostics": {
                "counts": dict(sorted(stats.reading_counts.items())),
                "samples": stats.reading_samples,
                "sample_limit_per_reason": 25,
                "count_unit": "source pronunciation block (before variants and redirects)",
            },
            "performance": {"build_seconds": elapsed, "peak_rss_bytes": _max_rss_bytes()},
            "schema_source": str(schemas),
        }
        write_json(report_path, report)
        conn.close()
    return report, report_path
