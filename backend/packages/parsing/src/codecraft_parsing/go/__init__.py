"""The Go parser.

It reads text only: module files, workspace files and Go source. It never runs
the Go toolchain, downloads a module, or needs a module cache.
"""

from codecraft_parsing.go.parser import parse_go_repository
from codecraft_parsing.go.version import PARSER_VERSION

__all__ = ["PARSER_VERSION", "parse_go_repository"]
