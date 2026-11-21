"""Run the parser over one directory and report what it found."""

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from codecraft_core.model import ExcludedDirectory, RepositoryParse
from codecraft_parsing import SUPPORTED_LANGUAGES, parse_repository
from codecraft_parsing.common.walker import (
    UNREADABLE_DIRECTORY_REASON,
    UNREADABLE_FILE_REASON,
    RepositoryLimitError,
)
from codecraft_settings import Settings


def main(argv: Sequence[str] | None = None) -> int:
    arguments_parser = argparse.ArgumentParser(
        prog="python -m codecraft_app.parse",
        description="Parse a repository directory into files, edges and coverage.",
    )
    arguments_parser.add_argument("directory", help="repository directory to parse")
    arguments_parser.add_argument(
        "--language",
        choices=SUPPORTED_LANGUAGES,
        default="python",
        help="language parser to use",
    )
    arguments_parser.add_argument(
        "--output", type=Path, help="write the full JSON output to this file"
    )
    arguments = arguments_parser.parse_args(argv)

    directory: str = arguments.directory
    language: str = arguments.language
    output: Path | None = arguments.output

    try:
        settings = Settings()
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    root = Path(directory)
    if not root.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2

    try:
        model = parse_repository(
            root,
            language,
            max_file_count=settings.PARSE_MAX_FILES,
            max_file_bytes=settings.PARSE_MAX_FILE_BYTES,
        )
    except RepositoryLimitError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    for line in _summary(model, root.resolve()):
        print(line)

    if output is not None:
        payload = json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
        output.write_bytes(payload.encode("utf-8"))
    return 0


def _summary(model: RepositoryParse, root: Path) -> list[str]:
    files = model.file_coverage
    coverage = model.coverage
    lines = [
        f"parser: {model.parser_version}",
        f"root: {root}",
    ]
    if model.python is not None:
        lines.append(f"import root: {model.python.import_root} ({model.python.import_root_rule})")
    elif model.go is not None:
        context = model.go.build_context
        lines.append(f"go build context: {context.os}/{context.arch}")
    elif model.typescript is not None:
        configs = ", ".join(model.typescript.config_files)
        lines.append(f"typescript configuration files: {configs if configs else 'none'}")
    else:
        lines.append("import root: not reported")
    asset_count = f", {files.assets} assets" if files.assets else ""
    lines.extend(
        [
            f"files: {files.found} found, {files.parsed} parsed, "
            f"{files.failed_parse} failed to parse, {files.excluded} excluded{asset_count}",
            f"excluded directories: {len(model.excluded_directories)}",
        ]
    )
    lines.extend(
        f"  {reason}: {count}"
        for reason, count in _counts_by_reason(model.excluded_directories).items()
    )
    unreadable_directories = sum(
        1 for entry in model.excluded_directories if entry.reason == UNREADABLE_DIRECTORY_REASON
    )
    unreadable_files = sum(
        1 for entry in model.files if entry.excluded_reason == UNREADABLE_FILE_REASON
    )
    incomplete: list[str] = []
    if unreadable_directories:
        noun = "directory" if unreadable_directories == 1 else "directories"
        incomplete.append(f"{unreadable_directories} {noun} could not be listed")
    if unreadable_files:
        noun = "file" if unreadable_files == 1 else "files"
        incomplete.append(f"{unreadable_files} {noun} could not be read")
    if incomplete:
        lines.append(f"scan: incomplete ({', '.join(incomplete)})")
    else:
        lines.append("scan: complete")
    lines.extend(
        [
            f"edges: {len(model.edges)}",
            f"references: {coverage.references} total, {coverage.resolved} resolved, "
            f"{coverage.symbols} symbols, {coverage.star_imports} star imports, "
            f"{coverage.cgo} cgo, {coverage.external} external, "
            f"{coverage.excluded} excluded, {coverage.failed} failed",
        ]
    )
    if coverage.python is not None:
        lines.append(f"namespace packages: {coverage.python.namespace_packages}")
    elif model.go is not None and coverage.go is not None:
        module_list = ", ".join(
            f"{module.module_path}={module.folder}" for module in model.go.modules
        )
        lines.append(f"go modules: {module_list if module_list else 'none'}")
        lines.append(f"go packages: {coverage.go.packages}")
    elif coverage.typescript is not None:
        lines.append(
            f"re-exports: {coverage.typescript.re_exports} found, "
            f"{coverage.typescript.re_exports_resolved} resolved"
        )
    lines.append(f"unresolved: {coverage.failed}")
    lines.extend(f"  {reason}: {count}" for reason, count in coverage.failures_by_reason.items())
    parse_failures = Counter(
        record.parse_failure.reason for record in model.files if record.parse_failure is not None
    )
    if parse_failures:
        lines.append("parse failures:")
        lines.extend(f"  {reason}: {count}" for reason, count in sorted(parse_failures.items()))
    lines.append("file exclusions:")
    lines.extend(f"  {reason}: {count}" for reason, count in files.excluded_by_reason.items())
    return lines


def _counts_by_reason(directories: Sequence[ExcludedDirectory]) -> dict[str, int]:
    return dict(sorted(Counter(entry.reason for entry in directories).items()))


if __name__ == "__main__":
    raise SystemExit(main())
