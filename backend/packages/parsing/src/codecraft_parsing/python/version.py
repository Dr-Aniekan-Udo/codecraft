"""The version of the parser that produced an output.

The string is derived from installed package metadata rather than written by
hand, so a parse result can always be traced back to the exact grammar and
binding that produced it.
"""

from importlib.metadata import version

PARSER_VERSION: str = (
    f"codecraft-parsing {version('codecraft-parsing')} "
    f"(language python; tree-sitter {version('tree-sitter')}; "
    f"tree-sitter-python {version('tree-sitter-python')})"
)
