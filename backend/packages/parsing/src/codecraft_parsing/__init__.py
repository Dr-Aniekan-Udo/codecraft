"""The CodeCraft parser package.

One shared walk and output assembly, one subpackage per language, and a small
dispatcher that selects the parser.
"""

from pathlib import Path
from typing import Protocol

from codecraft_core.model import RepositoryParse

from codecraft_parsing.go.parser import parse_go_repository
from codecraft_parsing.python.parser import parse_python_repository
from codecraft_parsing.typescript.parser import parse_typescript_repository


class LanguageParser(Protocol):
    def __call__(
        self,
        root: Path,
        *,
        max_file_count: int,
        max_file_bytes: int,
    ) -> RepositoryParse: ...


_PARSERS: dict[str, LanguageParser] = {
    "python": parse_python_repository,
    "go": parse_go_repository,
    "typescript": parse_typescript_repository,
    "javascript": parse_typescript_repository,
}
SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(_PARSERS)


def parse_repository(
    root: Path,
    language: str = "python",
    *,
    max_file_count: int,
    max_file_bytes: int,
) -> RepositoryParse:
    """Parse ``root`` with the parser for ``language``."""
    parser = _PARSERS.get(language)
    if parser is None:
        raise ValueError(f"unknown language: {language}")
    return parser(
        Path(root),
        max_file_count=max_file_count,
        max_file_bytes=max_file_bytes,
    )


__all__ = ["SUPPORTED_LANGUAGES", "parse_repository"]
