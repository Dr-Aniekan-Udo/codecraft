"""The Python parser."""

from codecraft_parsing.python.parser import parse_python_repository
from codecraft_parsing.python.version import PARSER_VERSION

__all__ = ["PARSER_VERSION", "parse_python_repository"]
