"""The TypeScript and JavaScript parser.

The compiler's resolver is authoritative. This parser reads syntax and asks a
Node helper for every module target in one batch; it never runs analysed code.
"""

from codecraft_parsing.typescript.parser import parse_typescript_repository

__all__ = ["parse_typescript_repository"]
