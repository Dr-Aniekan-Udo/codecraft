"""The version of the parser that produced an output."""

from importlib.metadata import version


def parser_version(typescript_version: str) -> str:
    """Name the parser, both grammars, the protocol and the TypeScript pin."""
    return (
        f"codecraft-parsing {version('codecraft-parsing')} "
        f"(languages typescript and javascript; tree-sitter {version('tree-sitter')}; "
        f"tree-sitter-typescript {version('tree-sitter-typescript')}; "
        f"tree-sitter-javascript {version('tree-sitter-javascript')}; "
        f"js resolver protocol 1; typescript {typescript_version})"
    )
