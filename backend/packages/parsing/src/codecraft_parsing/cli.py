"""Run the parser over one directory and report what it found."""

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from codecraft_core.model import ExcludedDirectory, RepositoryParse

from codecraft_parsing import SUPPORTED_LANGUAGES, parse_repository
from codecraft_parsing.common.walker import RepositoryLimitError


def main(argv: Sequence[str] | None = None) -> int:
    arguments_parser = argparse.ArgumentParser(
        prog="python -m codecraft_parsing",
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
    root = Path(directory)
    if not root.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2

    try:
        model = parse_repository(root, language)
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
    python = model.python
    import_root = python.import_root if python is not None else "not reported"
    import_rule = python.import_root_rule if python is not None else "not reported"
    namespace_packages = coverage.python.namespace_packages if coverage.python is not None else 0
    lines = [
        f"parser: {model.parser_version}",
        f"root: {root}",
        f"import root: {import_root} ({import_rule})",
        f"files: {files.found} found, {files.parsed} parsed, "
        f"{files.failed_parse} failed to parse, {files.excluded} excluded",
        f"excluded directories: {len(model.excluded_directories)}",
    ]
    lines.extend(
        f"  {reason}: {count}"
        for reason, count in _counts_by_reason(model.excluded_directories).items()
    )
    lines.extend(
        [
            f"edges: {len(model.edges)}",
            f"references: {coverage.references} total, {coverage.resolved} resolved, "
            f"{coverage.symbols} symbols, {coverage.star_imports} star imports, "
            f"{coverage.external} external, "
            f"{coverage.excluded} excluded, {coverage.failed} failed",
            f"namespace packages: {namespace_packages}",
            f"unresolved: {coverage.failed}",
        ]
    )
    lines.extend(f"  {reason}: {count}" for reason, count in coverage.failures_by_reason.items())
    lines.append("file exclusions:")
    lines.extend(f"  {reason}: {count}" for reason, count in files.excluded_by_reason.items())
    return lines


def _counts_by_reason(directories: Sequence[ExcludedDirectory]) -> dict[str, int]:
    return dict(sorted(Counter(entry.reason for entry in directories).items()))
