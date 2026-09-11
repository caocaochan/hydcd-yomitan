from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import ConversionStats


@dataclass(frozen=True)
class Correction:
    source_sha256: str
    headword: str
    before: str
    after: str
    reason: str
    evidence: str


def load_corrections(path: Path) -> list[Correction]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Correction(**item) for item in data]


def apply_corrections(
    headword: str,
    raw: str,
    source_sha256: str,
    corrections: list[Correction],
    stats: ConversionStats,
) -> str:
    for correction in corrections:
        if correction.source_sha256 != source_sha256 or correction.headword != headword:
            continue
        count = raw.count(correction.before)
        if count != 1:
            raise ValueError(
                f"Correction for {headword!r} expected one exact match, found {count}: "
                f"{correction.before!r}"
            )
        raw = raw.replace(correction.before, correction.after, 1)
        stats.correction_log.append(correction.__dict__)
        stats.counters["corrections"] += 1
    return raw
