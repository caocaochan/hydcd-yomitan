"""Stable identities for the two independently updatable editions."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Edition:
    title: str
    archive: str
    index: str
    report: str


EDITIONS = {
    "full": Edition("汉语大词典 2025", "hydcd-qiding-yomitan.zip", "index.json",
                    "hydcd-qiding-conversion-report.json"),
    "light": Edition("汉语大词典 2025 Light", "hydcd-qiding-yomitan-light.zip", "index-light.json",
                     "hydcd-qiding-light-conversion-report.json"),
}
UPDATE_BASE = "https://github.com/caocaochan/hydcd-yomitan/releases/latest/download/"
LIGHT_REMOVED_TAGS = frozenset({"img", "examples", "example", "examplenote"})
LIGHT_OMISSION = "（精简版已省略图片或例证）"


def get_edition(name: str) -> Edition:
    if name not in EDITIONS:
        raise ValueError(f"Unknown edition: {name!r}; expected full or light")
    return EDITIONS[name]
