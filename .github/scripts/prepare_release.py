"""Compare validated editions and prepare their exact indexes and release assets."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work/hydcd-yomitan"))
from hydcd_yomitan.editions import EDITIONS, UPDATE_BASE


def inspect_archive(path: Path) -> tuple[dict, Counter, bytes, bytes]:
    lookup = Counter()
    with zipfile.ZipFile(path) as archive:
        index_bytes = archive.read("index.json")
        css = archive.read("styles.css")
        for name in archive.namelist():
            if name.startswith("term_bank_") and name.endswith(".json"):
                for row in json.loads(archive.read(name)):
                    key = json.dumps(row[:5] + row[6:], ensure_ascii=False, separators=(",", ":")).encode()
                    lookup[hashlib.sha256(key).digest()] += 1
        uncompressed = sum(info.file_size for info in archive.infolist())
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "archive": path.name, "compressed_bytes": path.stat().st_size,
        "uncompressed_bytes": uncompressed, "sha256": digest, "terms": lookup.total(),
    }, lookup, index_bytes, css


def prepare(output: Path) -> dict:
    sizes = {}
    indexes = {}
    full_lookup = None
    full_css = None
    full_inputs = None
    revision = None
    for edition, identity in EDITIONS.items():
        info, lookup, index_bytes, css = inspect_archive(output / identity.archive)
        index = json.loads(index_bytes)
        for key, expected in {
            "title": identity.title, "indexUrl": UPDATE_BASE + identity.index,
            "downloadUrl": UPDATE_BASE + identity.archive, "isUpdatable": True,
        }.items():
            if index.get(key) != expected:
                raise ValueError(f"{edition}: incorrect {key}")
        if edition == "full":
            full_lookup, full_css, revision = lookup, css, index["revision"]
        elif lookup != full_lookup or css != full_css or index["revision"] != revision:
            raise ValueError("Editions differ in lookup rows, CSS, or revision; refusing publication")
        report = json.loads((output / identity.report).read_text(encoding="utf-8"))
        if report["output"]["sha256"] != info["sha256"] or report["dictionary_revision"] != revision:
            raise ValueError(f"{edition}: conversion report does not match archive")
        if edition == "full":
            full_inputs = report["input"]["files"]
        elif report["input"]["files"] != full_inputs:
            raise ValueError("Editions were built from different source inputs; refusing publication")
        sizes[edition] = info
        indexes[identity.index] = index_bytes
        print(f"{edition}: {info['compressed_bytes']:,} compressed bytes; {info['uncompressed_bytes']:,} uncompressed bytes; {info['terms']:,} terms", flush=True)
    reduction = 1 - sizes["light"]["compressed_bytes"] / sizes["full"]["compressed_bytes"]
    comparison = {"dictionary_revision": revision, "lookup_rows_identical": True, "css_identical": True,
                  "editions": sizes, "compressed_reduction_percent": round(reduction * 100, 2)}
    for name, data in indexes.items():
        (output / name).write_bytes(data)
    (output / "edition-comparison.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text("".join(f"{info['sha256']}  {info['archive']}\n" for info in sizes.values()), encoding="utf-8")
    provenance = {key: os.environ[key] for key in (
        "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_REF", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
    ) if key in os.environ}
    provenance.update(validation_mode="archive-only", dictionary_revision=revision, editions=sizes)
    (output / "build-info.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    notes = [f"HYDCD Qiding {revision}", "", "Import either ZIP into Yomitan/Lapis:", ""]
    for edition, info in sizes.items():
        notes.append(f"- **{edition.title()}**: `{info['archive']}` — {info['compressed_bytes'] / 1_000_000:.2f} MB download; {info['uncompressed_bytes'] / 1_000_000:.2f} MB uncompressed archive contents.")
    notes.extend([
        "", f"Light is {reduction:.1%} smaller. It removes all images, their captions, and complete example blocks, including their citations and notes.",
        "Definitions, readings, historical phonology, other explanatory notes, lookup aliases, and styling are preserved.",
        "Image/example-only senses display a short omission notice. Quotations and source details within definitions remain.",
        "", "Each edition updates independently. To switch editions, import the chosen ZIP and disable or remove the other edition if installed.",
        "", "Both editions passed archive-wide validation and have identical lookup rows and CSS. Recursive term-schema validation is skipped for complete builds; fixtures exercise the schema.",
        "Conversion and validation reports, edition size comparison, build provenance, and SHA256SUMS are attached.",
    ])
    if "GITHUB_SHA" in os.environ:
        notes.extend(["", f"Built from commit {os.environ['GITHUB_SHA']}."])
    if "GITHUB_RUN_ID" in os.environ:
        notes.append(f"Build: {os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}")
    (output / "release-notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
    return comparison


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs")
    prepare(parser.parse_args().output)
