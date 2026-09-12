from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import build_dictionary
from .editions import EDITIONS
from .source import discover_input, input_inventory
from .validation import format_validation, validate_dictionary


PACKAGE_ROOT = Path(__file__).parent
DEFAULT_SCHEMAS = PACKAGE_ROOT / "schemas"
DEFAULT_CORRECTIONS = PACKAGE_ROOT / "data" / "corrections.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hydcd-yomitan")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Inventory and hash an input MDX/MDD set")
    inspect.add_argument("--input", type=Path, required=True)
    build = sub.add_parser("build", help="Build a deterministic Yomitan dictionary ZIP")
    build.add_argument("--input", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--schemas", type=Path, default=DEFAULT_SCHEMAS)
    build.add_argument("--corrections", type=Path, default=DEFAULT_CORRECTIONS)
    build.add_argument("--edition", choices=EDITIONS, default="full")
    validate = sub.add_parser("validate", help="Run targeted archive-wide validation")
    validate.add_argument("dictionary", type=Path)
    validate.add_argument("--schemas", type=Path, default=DEFAULT_SCHEMAS)
    validate.add_argument("--report", type=Path)
    validate.add_argument("--edition", choices=EDITIONS, default="full")
    validation_mode = validate.add_mutually_exclusive_group()
    validation_mode.add_argument(
        "--exhaustive", action="store_true",
        help="Validate every term bank recursively against the official schema (very slow)",
    )
    validation_mode.add_argument(
        "--archive-only", action="store_true",
        help="Run all archive checks and index-schema validation, skipping recursive term-schema validation",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "inspect":
        print(json.dumps(input_inventory(discover_input(args.input)), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "build":
        report, report_path = build_dictionary(
            discover_input(args.input), args.output, args.schemas.resolve(), args.corrections.resolve(),
            edition=args.edition,
        )
        print(json.dumps({"output": report["output"], "report": str(report_path)}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "validate":
        result = validate_dictionary(
            args.dictionary, args.schemas.resolve(),
            exhaustive=args.exhaustive, archive_only=args.archive_only,
            edition=args.edition,
        )
        text = format_validation(result)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(text, encoding="utf-8")
        print(text, end="")
        return 0 if result["valid"] else 1
    return 2
