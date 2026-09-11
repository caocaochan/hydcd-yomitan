from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, Iterable


FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class TermBankWriter:
    def __init__(self, root: Path, limit: int = 10_000):
        self.root = root
        self.limit = limit
        self.bank_number = 0
        self.bank_count = 0
        self.total = 0
        self._stream = None

    def add(self, entry: list[Any]) -> None:
        if self._stream is None or self.bank_count >= self.limit:
            self._open_next()
        assert self._stream is not None
        if self.bank_count:
            self._stream.write(",\n")
        self._stream.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
        self.bank_count += 1
        self.total += 1

    def _open_next(self) -> None:
        self.close_bank()
        self.bank_number += 1
        self.bank_count = 0
        self._stream = (self.root / f"term_bank_{self.bank_number}.json").open("w", encoding="utf-8", newline="\n")
        self._stream.write("[\n")

    def close_bank(self) -> None:
        if self._stream is not None:
            self._stream.write("\n]\n")
            self._stream.close()
            self._stream = None

    def close(self) -> None:
        self.close_bank()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def deterministic_zip(output: Path, files: Iterable[tuple[str, Path | bytes]]) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=False) as archive:
        for name, source in sorted(files, key=lambda item: item[0]):
            data = source if isinstance(source, bytes) else source.read_bytes()
            archive.writestr(_zip_info(name.replace("\\", "/")), data, compresslevel=9)
    digest = hashlib.sha256()
    with output.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()
