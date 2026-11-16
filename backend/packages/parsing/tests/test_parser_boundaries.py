"""The parser core names no Python web framework, per Part 3a acceptance check 7."""

import re
from pathlib import Path

_FRAMEWORK_NAMES = (
    "flask",
    "django",
    "fastapi",
    "starlette",
    "tornado",
    "aiohttp",
    "pyramid",
    "bottle",
    "sanic",
    "quart",
)

_PATTERN = re.compile(r"\b(?:" + "|".join(_FRAMEWORK_NAMES) + r")\b", re.IGNORECASE)


def test_the_parser_core_contains_no_web_framework_name() -> None:
    backend = Path(__file__).resolve().parents[3]
    offenders: list[str] = []
    for package in ("core", "parsing"):
        source = backend / "packages" / package / "src"
        for path in sorted(source.rglob("*.py")):
            if _PATTERN.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(backend).as_posix())
    assert offenders == []
