from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InputSet:
    root: Path
    mdx: Path
    mdds: tuple[Path, ...]
    css: tuple[Path, ...]


@dataclass
class ParsedEntry:
    expression: str
    reading: str
    glossary: list[dict[str, Any] | str]
    alternate_terms: list[str] = field(default_factory=list)


@dataclass
class ConversionStats:
    counters: Counter[str] = field(default_factory=Counter)
    unknown_tags: Counter[str] = field(default_factory=Counter)
    exclusions: Counter[str] = field(default_factory=Counter)
    missing_reading_samples: list[str] = field(default_factory=list)
    unresolved_pua_samples: list[str] = field(default_factory=list)
    warning_samples: list[str] = field(default_factory=list)
    error_samples: list[str] = field(default_factory=list)
    correction_log: list[dict[str, Any]] = field(default_factory=list)
    resource_extensions: Counter[str] = field(default_factory=Counter)

    def sample(self, target: list[str], value: str, limit: int = 100) -> None:
        if value not in target and len(target) < limit:
            target.append(value)

    def warning(self, value: str) -> None:
        self.counters["warnings"] += 1
        self.sample(self.warning_samples, value)

    def error(self, value: str) -> None:
        self.counters["errors"] += 1
        self.sample(self.error_samples, value)
