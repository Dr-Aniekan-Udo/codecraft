"""Language parsers must not import another language's parser.

Import-linter checks the same boundaries. This test is the allowlist that also
catches a later language being imported by an existing one.
"""

import ast
from pathlib import Path

_LANGUAGES = Path(__file__).resolve().parents[1] / "src" / "codecraft_parsing"
_ALLOWED = {
    "python": (
        "codecraft_core",
        "codecraft_parsing.common",
        "codecraft_parsing.python",
    ),
    "go": (
        "codecraft_core",
        "codecraft_parsing.common",
        "codecraft_parsing.go",
    ),
    "typescript": (
        "codecraft_core",
        "codecraft_parsing.common",
        "codecraft_parsing.typescript",
    ),
}


def _imported_modules(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == "codecraft_parsing":
                modules.extend(f"codecraft_parsing.{alias.name}" for alias in node.names)
            else:
                modules.append(node.module)
    return modules


def _assert_language_imports_only(language: str) -> None:
    allowed = _ALLOWED[language]
    offenders: list[str] = []
    for path in sorted((_LANGUAGES / language).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            if module != "codecraft_parsing" and not module.startswith("codecraft_parsing."):
                continue
            if not any(module == item or module.startswith(f"{item}.") for item in allowed):
                offenders.append(f"{path.as_posix()}: {module}")
    assert offenders == []


def test_the_python_parser_imports_no_other_language_parser() -> None:
    _assert_language_imports_only("python")


def test_the_go_parser_imports_no_other_language_parser() -> None:
    _assert_language_imports_only("go")


def test_the_typescript_parser_imports_no_other_language_parser() -> None:
    _assert_language_imports_only("typescript")
