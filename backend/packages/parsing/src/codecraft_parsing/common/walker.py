"""Walk a repository without knowing its language.

This module owns file discovery, hashing, the bounded-parsing limits and the
exclusions that are true for every language. A language parser supplies a small
classifier that decides which suffixes are nodes and what reason the rest carry.
"""

import hashlib
import os
import posixpath
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from codecraft_core.model import ExcludedDirectory, Language

MAX_FILE_COUNT = 50_000
MAX_FILE_BYTES = 2_000_000

_DIRECTORY_REASONS: dict[str, str] = {
    ".git": "version control metadata",
    ".hg": "version control metadata",
    ".svn": "version control metadata",
    "__pycache__": "bytecode cache",
    ".mypy_cache": "tool cache",
    ".pytest_cache": "tool cache",
    ".ruff_cache": "tool cache",
    ".tox": "tool cache",
    ".nox": "tool cache",
    "node_modules": "dependency installation",
    ".venv": "virtual environment",
    "venv": "virtual environment",
    "site-packages": "virtual environment",
}

_ENVIRONMENT_FILE = "environment file"
_SYMBOLIC_LINK = "symbolic link"
_FILE_TOO_LARGE = "file exceeds size limit"


class RepositoryLimitError(Exception):
    """The repository is larger than the parser is allowed to read."""


@dataclass(frozen=True)
class FileClassification:
    """What one language says a file is, before any bytes are read."""

    is_node: bool
    language: Language | None
    excluded_reason: str | None


@dataclass(frozen=True)
class WalkedFile:
    """One file as the shared walk saw it.

    ``data`` is present only for a node that is within the size limit; the
    language parser decodes it. Excluded files keep their hash and byte-line
    count where they can be read.
    """

    path: str
    folder: str
    language: Language | None
    line_count: int | None
    content_hash: str | None
    is_node: bool
    excluded_reason: str | None
    data: bytes | None


@dataclass(frozen=True)
class WalkResult:
    files: list[WalkedFile]
    directories: list[str]
    excluded_directories: list[ExcludedDirectory]


def walk_repository(root: Path, classify: Callable[[str], FileClassification]) -> WalkResult:
    """Walk ``root`` in path order, applying the shared exclusions and limits."""
    file_paths: list[str] = []
    directories: list[str] = []
    excluded_directories: list[ExcludedDirectory] = []

    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        folder = _relative(current_path, root)
        kept: list[str] = []
        for name in sorted(dirnames):
            relative = _join(folder, name)
            candidate = current_path / name
            if candidate.is_symlink():
                excluded_directories.append(
                    ExcludedDirectory(path=f"{relative}/", reason=_SYMBOLIC_LINK)
                )
                continue
            reason = directory_exclusion_reason(name, candidate)
            if reason is None:
                kept.append(name)
                directories.append(relative)
            else:
                excluded_directories.append(ExcludedDirectory(path=f"{relative}/", reason=reason))
        dirnames[:] = kept

        for name in sorted(filenames):
            candidate = current_path / name
            if not candidate.is_symlink() and not candidate.is_file():
                continue
            file_paths.append(_join(folder, name))
            if len(file_paths) > MAX_FILE_COUNT:
                raise RepositoryLimitError(f"repository exceeds the {MAX_FILE_COUNT} file limit")

    file_paths.sort()
    excluded_directories.sort(key=lambda entry: entry.path)
    files = [_walked_file(root, path, classify) for path in file_paths]

    return WalkResult(
        files=files,
        directories=sorted(directories),
        excluded_directories=excluded_directories,
    )


def _walked_file(
    root: Path, path: str, classify: Callable[[str], FileClassification]
) -> WalkedFile:
    name = posixpath.basename(path)
    folder = posixpath.dirname(path) or "."

    if name == ".env" or name.startswith(".env."):
        return _excluded(path, folder, language=None, reason=_ENVIRONMENT_FILE)

    candidate = root / path
    if candidate.is_symlink():
        classification = classify(name)
        return _excluded(path, folder, language=classification.language, reason=_SYMBOLIC_LINK)

    classification = classify(name)
    if candidate.stat().st_size > MAX_FILE_BYTES:
        return _excluded(path, folder, language=classification.language, reason=_FILE_TOO_LARGE)

    data = candidate.read_bytes()
    content_hash = f"sha256:{hashlib.sha256(data).hexdigest()}"
    if classification.is_node:
        return WalkedFile(
            path=path,
            folder=folder,
            language=classification.language,
            line_count=None,
            content_hash=content_hash,
            is_node=True,
            excluded_reason=None,
            data=data,
        )
    if classification.excluded_reason is None:
        raise ValueError(f"classifier gave no node and no exclusion reason for {path}")
    return WalkedFile(
        path=path,
        folder=folder,
        language=classification.language,
        line_count=len(data.splitlines()),
        content_hash=content_hash,
        is_node=False,
        excluded_reason=classification.excluded_reason,
        data=None,
    )


def _excluded(path: str, folder: str, *, language: Language | None, reason: str) -> WalkedFile:
    return WalkedFile(
        path=path,
        folder=folder,
        language=language,
        line_count=None,
        content_hash=None,
        is_node=False,
        excluded_reason=reason,
        data=None,
    )


def directory_exclusion_reason(name: str, path: Path) -> str | None:
    reason = _DIRECTORY_REASONS.get(name)
    if reason is not None:
        return reason
    # A virtual environment is recognised by its marker rather than its name,
    # because the name is chosen by whoever created it.
    if (path / "pyvenv.cfg").is_file():
        return "virtual environment"
    return None


def _join(folder: str, name: str) -> str:
    return f"{folder}/{name}" if folder else name


def _relative(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    return "" if relative == "." else relative
