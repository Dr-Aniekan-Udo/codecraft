"""The version of the parser that produced an output."""

from importlib.metadata import version

PARSER_VERSION: str = (
    f"codecraft-parsing {version('codecraft-parsing')} "
    f"(language go; tree-sitter {version('tree-sitter')}; "
    f"tree-sitter-go {version('tree-sitter-go')})"
)
