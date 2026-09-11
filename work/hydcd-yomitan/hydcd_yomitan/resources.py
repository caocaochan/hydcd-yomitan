from __future__ import annotations

import hashlib
import io
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image
from resvg_py import svg_to_bytes

from .models import ConversionStats
from .source import iter_mdd_records


SUPPORTED = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
RASTERIZE = {".bmp", ".tif", ".tiff", ".svg"}


def normalize_resource_path(value: str) -> str:
    value = unquote(value.strip()).replace("\\", "/")
    if value.startswith("bres://"):
        value = urlsplit(value).path
    elif "://" in value:
        value = urlsplit(value).path
    value = posixpath.normpath("/" + value).lstrip("/")
    if value.startswith("../") or value == "..":
        raise ValueError(f"Unsafe resource path: {value}")
    return value.casefold()


@dataclass
class ResourceCatalog:
    staging: Path
    stats: ConversionStats
    source_to_output: dict[str, str] = field(default_factory=dict)
    output_to_file: dict[str, Path] = field(default_factory=dict)
    used_outputs: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, mdds: tuple[Path, ...], staging: Path, stats: ConversionStats) -> "ResourceCatalog":
        catalog = cls(staging=staging, stats=stats)
        staging.mkdir(parents=True, exist_ok=True)
        for mdd in mdds:
            for source_name, raw in iter_mdd_records(mdd):
                catalog._add(source_name, raw)
        return catalog

    def _add(self, source_name: str, raw: bytes) -> None:
        normalized = normalize_resource_path(source_name)
        suffix = Path(normalized).suffix.lower()
        self.stats.resource_extensions[suffix or "<none>"] += 1
        self.stats.counters["mdd_resources"] += 1
        if suffix not in SUPPORTED | RASTERIZE:
            self.stats.counters["discarded_non_image_resources"] += 1
            return
        try:
            converted, out_suffix = self._normalize_image(raw, suffix)
        except Exception as exc:
            self.stats.warning(f"Unreadable image {source_name}: {exc}")
            return
        digest = hashlib.sha256(converted).hexdigest()
        output = f"media/{digest[:24]}{out_suffix}"
        target = self.staging / f"{digest}{out_suffix}"
        if output not in self.output_to_file:
            target.write_bytes(converted)
            self.output_to_file[output] = target
        else:
            self.stats.counters["deduplicated_resources"] += 1
        self.source_to_output[normalized] = output
        self.stats.counters["image_resources"] += 1

    @staticmethod
    def _normalize_image(raw: bytes, suffix: str) -> tuple[bytes, str]:
        if suffix == ".svg":
            return svg_to_bytes(svg_string=raw.decode("utf-8")), ".png"
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        if suffix in SUPPORTED:
            return raw, ".jpg" if suffix == ".jpeg" else suffix
        with Image.open(io.BytesIO(raw)) as image:
            out = io.BytesIO()
            image.save(out, format="PNG", optimize=False)
            return out.getvalue(), ".png"

    def resolve(self, source: str) -> str:
        normalized = normalize_resource_path(source)
        output = self.source_to_output.get(normalized)
        if output is None:
            self.stats.counters["missing_resources"] += 1
            raise FileNotFoundError(f"Definition references missing image: {source}")
        self.used_outputs.add(output)
        return output
