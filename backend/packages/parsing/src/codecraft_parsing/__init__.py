"""The CodeCraft parser package.

One shared walk and output assembly, one subpackage per language, and a small
dispatcher that selects the parser.
"""

from collections.abc import Callable
from pathlib import Path

from codecraft_core.model import RepositoryParse

from codecraft_parsing.go.parser import parse_go_repository
from codecraft_parsing.python.parser import parse_python_repository

type LanguageParser = Callable[[Path], RepositoryParse]

_PARSERS: dict[str, LanguageParser] = {
    "python": parse_python_repository,
    "go": parse_go_repository,
}
SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(_PARSERS)


def parse_repository(root: Path, language: str = "python") -> RepositoryParse:
    """Parse ``root`` with the parser for ``language``."""
    parser = _PARSERS.get(language)
    if parser is None:
        raise ValueError(f"unknown language: {language}")
    return parser(Path(root))


__all__ = ["SUPPORTED_LANGUAGES", "parse_repository"]
