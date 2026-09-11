from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft7Validator

from .readings import is_clean_reading


REMOTE_RE = re.compile(r"^(?:https?:)?//", re.I)
EXECUTABLE_RE = re.compile(r"<(?:script|iframe|object|embed|form|audio|video)\b|\bon\w+\s*=", re.I)
MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _load_schema(root: Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _bank_number(name: str) -> int:
    match = re.fullmatch(r"term_bank_(\d+)\.json", name)
    return int(match.group(1)) if match else -1


def validate_dictionary(
    path: Path, schemas: Path, *, exhaustive: bool = False, archive_only: bool = False,
) -> dict:
    if exhaustive and archive_only:
        raise ValueError("exhaustive and archive_only are mutually exclusive")
    path = path.resolve()
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(4 * 1024 * 1024):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    errors: list[str] = []
    warnings: list[str] = []
    term_count = 0
    bank_count = 0
    referenced_resources: set[str] = set()
    structured_glossaries = 0
    language_roots = 0
    nested_language_attributes = 0
    schema_validated_banks: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        name_set = set(names)
        for name in names:
            parts = Path(name).parts
            if Path(name).is_absolute() or ".." in parts or "\\" in name:
                errors.append(f"Unsafe ZIP path: {name}")
        if "index.json" not in name_set:
            errors.append("Missing index.json")
            index = {}
        else:
            index = json.loads(archive.read("index.json"))
            validator = Draft7Validator(_load_schema(schemas, "dictionary-index-schema.json"))
            errors.extend(f"index.json {list(err.path)}: {err.message}" for err in validator.iter_errors(index))
        term_validator = Draft7Validator(_load_schema(schemas, "dictionary-term-bank-v3-schema.json"))
        banks = sorted(
            (name for name in names if re.fullmatch(r"term_bank_\d+\.json", name)),
            key=_bank_number,
        )
        if not banks:
            errors.append("No term banks found")
        sampled_banks = set(banks if exhaustive else (
            [banks[0], banks[len(banks) // 2], banks[-1]] if banks else []
        ))
        if archive_only:
            sampled_banks.clear()
        for bank_name in banks:
            bank_count += 1
            bank = json.loads(archive.read(bank_name))
            if not isinstance(bank, list):
                errors.append(f"{bank_name} is not a JSON array")
                continue
            if len(bank) > 10_000:
                errors.append(f"{bank_name} contains {len(bank)} terms (limit 10000)")
            term_count += len(bank)
            if bank_name in sampled_banks:
                schema_validated_banks.append(bank_name)
                for error in term_validator.iter_errors(bank):
                    errors.append(f"{bank_name} {list(error.path)}: {error.message}")
                    if len(errors) >= 1000:
                        break
            for term_index, term in enumerate(bank):
                if not isinstance(term, list) or len(term) != 8:
                    if len(errors) < 1000:
                        errors.append(f"{bank_name}[{term_index}] is not an 8-field term row")
                    continue
                reading = term[1]
                if not isinstance(reading, str):
                    if len(errors) < 1000:
                        errors.append(f"{bank_name}[{term_index}] reading is not a string")
                elif not is_clean_reading(reading):
                    if len(errors) < 1000:
                        errors.append(f"{bank_name}[{term_index}] reading is not normalized pinyin")
                glossary = term[5]
                if not isinstance(glossary, list):
                    if len(errors) < 1000:
                        errors.append(f"{bank_name}[{term_index}] glossary is not an array")
                    continue
                for glossary_index, item in enumerate(glossary):
                    location = f"{bank_name}[{term_index}].glossary[{glossary_index}]"
                    if not isinstance(item, dict) or item.get("type") != "structured-content":
                        if len(errors) < 1000:
                            errors.append(f"{location} is not structured content")
                        continue
                    structured_glossaries += 1
                    root = item.get("content")
                    is_root = (
                        isinstance(root, dict)
                        and root.get("tag") == "span"
                        and isinstance(root.get("data"), dict)
                        and root["data"].get("content") == "hydcd-entry"
                    )
                    if not is_root:
                        if len(errors) < 1000:
                            errors.append(f"{location} does not have a hydcd-entry root")
                        continue
                    if root.get("lang") != "zh-Hans":
                        if len(errors) < 1000:
                            errors.append(f"{location} root lang is not zh-Hans")
                    else:
                        language_roots += 1
                    for value in _walk(root.get("content")):
                        if isinstance(value, dict) and "lang" in value:
                            nested_language_attributes += 1
                            if len(errors) < 1000:
                                errors.append(f"{location} contains a redundant nested lang attribute")
            for value in _walk(bank):
                if isinstance(value, dict):
                    if value.get("tag") == "img" and isinstance(value.get("path"), str):
                        referenced_resources.add(value["path"])
                    href = value.get("href")
                    if isinstance(href, str) and not href.startswith("?"):
                        if len(errors) < 1000:
                            errors.append(f"Non-internal link retained in {bank_name}: {href}")
                elif isinstance(value, str) and EXECUTABLE_RE.search(value):
                    if len(errors) < 1000:
                        errors.append(f"Executable markup-like text found in {bank_name}")
        missing = sorted(referenced_resources - name_set)
        errors.extend(f"Missing referenced resource: {name}" for name in missing)
        unused_media = sorted(name for name in names if name.startswith("media/") and name not in referenced_resources)
        warnings.extend(f"Unused packaged resource: {name}" for name in unused_media[:100])
        packaged_media = sorted(name for name in names if name.startswith("media/"))
        for name in packaged_media:
            if Path(name).suffix.casefold() not in MEDIA_EXTENSIONS:
                errors.append(f"Unsupported packaged media type: {name}")
        css_uses_sans_serif = False
        if "styles.css" not in name_set:
            errors.append("Missing styles.css")
        else:
            css = archive.read("styles.css").decode("utf-8")
            if "@import" in css or re.search(r"url\s*\(\s*['\"]?(?:https?:)?//", css, re.I):
                errors.append("styles.css contains a remote import or URL")
            if re.search(r"@font-face|\.(?:woff2?|ttf|otf|eot)\b", css, re.I):
                errors.append("styles.css contains a bundled-font reference")
            css_uses_sans_serif = bool(re.search(
                r'\[data-sc-content=["\']hydcd-entry["\']\]\s*\{[^}]*'
                r'font-family\s*:\s*sans-serif\s*;',
                css,
                re.I | re.S,
            ))
            if not css_uses_sans_serif:
                errors.append("hydcd-entry does not use the generic sans-serif font")
    return {
        "path": str(path), "size": path.stat().st_size, "sha256": digest,
        "valid": not errors, "term_banks": bank_count, "terms": term_count,
        "validation_mode": "archive-only" if archive_only else "exhaustive" if exhaustive else "targeted",
        "schema_validated_banks": schema_validated_banks,
        "structured_glossaries": structured_glossaries,
        "zh_hans_roots": language_roots,
        "nested_lang_attributes": nested_language_attributes,
        "css_uses_sans_serif": css_uses_sans_serif,
        "referenced_resources": len(referenced_resources), "errors": errors, "warnings": warnings,
    }


def format_validation(result: dict) -> str:
    lines = [
        f"Dictionary: {result['path']}",
        f"SHA-256: {result['sha256']}",
        f"Size: {result['size']} bytes",
        f"Mode: {result['validation_mode']}",
        f"Term banks: {result['term_banks']}",
        f"Terms: {result['terms']}",
        f"Schema-validated banks: {', '.join(result['schema_validated_banks']) or 'none (term-schema validation skipped)'}",
        f"Structured glossaries: {result['structured_glossaries']}",
        f"zh-Hans roots: {result['zh_hans_roots']}",
        f"Nested lang attributes: {result['nested_lang_attributes']}",
        f"Generic sans-serif CSS: {'YES' if result['css_uses_sans_serif'] else 'NO'}",
        f"Referenced resources: {result['referenced_resources']}",
        f"Valid: {'YES' if result['valid'] else 'NO'}",
    ]
    if result["errors"]:
        lines.append("Errors:")
        lines.extend(f"- {item}" for item in result["errors"])
    if result["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in result["warnings"])
    return "\n".join(lines) + "\n"
