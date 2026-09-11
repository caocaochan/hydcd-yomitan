from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path
from typing import Iterator

from mdict_utils.base.readmdict import MDD, MDX
from mdict_utils.reader import meta as read_meta

from .models import InputSet


def discover_input(root: Path) -> InputSet:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {root}")
    mdx = sorted(p for p in root.glob("*.mdx") if p.is_file())
    if len(mdx) != 1:
        raise ValueError(f"Expected exactly one MDX in {root}; found {len(mdx)}")
    mdds = tuple(sorted(p for p in root.glob("*.mdd") if p.is_file()))
    if not mdds:
        raise ValueError(f"Expected at least one MDD in {root}")
    css = tuple(sorted(p for p in root.glob("*.css") if p.is_file()))
    return InputSet(root=root, mdx=mdx[0], mdds=mdds, css=css)


def sha256_file(path: Path, block_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def input_inventory(inputs: InputSet) -> dict:
    files = [inputs.mdx, *inputs.mdds, *inputs.css]
    return {
        "root": str(inputs.root),
        "files": [
            {"name": p.name, "size": p.stat().st_size, "sha256": sha256_file(p)}
            for p in files
        ],
        "mdx_meta": read_meta(str(inputs.mdx)),
    }


def iter_mdx_records(path: Path) -> Iterator[tuple[int, str, bytes]]:
    mdx = MDX(str(path), "", False, None)
    for ordinal, (key, value) in enumerate(mdx.items(), start=1):
        yield ordinal, unicodedata.normalize("NFC", key.decode("utf-8")), value


def iter_mdd_records(path: Path) -> Iterator[tuple[str, bytes]]:
    mdd = MDD(str(path), None)
    for key, value in mdd.items():
        yield key.decode("utf-8"), value
