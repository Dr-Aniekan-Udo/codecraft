"""Language parsers must not import another language's parser.

Import-linter can forbid the common package from importing the Python parser.
It refuses to name a language module that does not exist yet, so the second half
of the isolation rule is checked here as an allowlist until a second language is
added.
"""

import ast
from pathlib import Path

_PYTHON_ROOT = Path(__file__).resolve().parents[1] / "src" / "codecraft_parsing" / "python"
_ALLOWED = (
    "codecraft_core",
    "codecraft_parsing.common",
    "codecraft_parsing.python",
)


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


def test_the_python_parser_imports_no_other_language_parser() -> None:
    offenders: list[str] = []
    for path in sorted(_PYTHON_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            if module != "codecraft_parsing" and not module.startswith("codecraft_parsing."):
                continue
            if not any(
                module == allowed or module.startswith(f"{allowed}.") for allowed in _ALLOWED
            ):
                offenders.append(f"{path.as_posix()}: {module}")
    assert offenders == []
