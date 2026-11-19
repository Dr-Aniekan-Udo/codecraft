"""Read and evaluate Go build constraints for the fixed target.

The target is linux/amd64 so a repository gives the same result on every
machine. Constraints are read from //go:build lines, legacy // +build lines and
filename suffixes. Nothing here runs or imports the code being read.
"""

import posixpath
import re
from dataclasses import dataclass

from codecraft_core.model import GoBuildConstraint, GoConstraintSource

TARGET_OS = "linux"
TARGET_ARCH = "amd64"
EXCLUSION_REASON = f"build constraint excludes file for {TARGET_OS}/{TARGET_ARCH}"
MALFORMED_BUILD_CONSTRAINT_REASON = "malformed build constraint"
_MAX_EXPRESSION_DEPTH = 100

_GOOS = frozenset(
    {
        "aix",
        "android",
        "darwin",
        "dragonfly",
        "freebsd",
        "hurd",
        "illumos",
        "ios",
        "js",
        "linux",
        "netbsd",
        "openbsd",
        "plan9",
        "solaris",
        "wasip1",
        "windows",
    }
)
_GOARCH = frozenset(
    {
        "386",
        "amd64",
        "arm",
        "arm64",
        "loong64",
        "mips",
        "mips64",
        "mips64le",
        "mipsle",
        "ppc64",
        "ppc64le",
        "riscv64",
        "s390x",
        "wasm",
    }
)

# Tags that the fixed target establishes. A tag outside this set, including a
# custom tag or cgo, is false: the parser has no toolchain or build settings
# that would prove it true.
_TARGET_TAGS = frozenset({TARGET_OS, TARGET_ARCH, "unix", "gc"})
_TOKEN = re.compile(r"&&|\|\||!|\(|\)|[A-Za-z0-9_.]+")
_UNRECOGNISED = re.compile(r"[^A-Za-z0-9_.!(),\s]")

_GO_BUILD_PREFIX = "//go:build "
_LEGACY_BUILD_PREFIX = "// +build "


@dataclass(frozen=True)
class ConstraintResult:
    """The constraints written for one file and whether they exclude it."""

    constraints: tuple[GoBuildConstraint, ...]
    excluded: bool
    exclusion_reason: str | None = None


def read_build_constraints(path: str, text: str) -> ConstraintResult:
    """Read every constraint for ``path`` and evaluate it for the target."""
    constraints: list[GoBuildConstraint] = []
    modern: list[str] = []
    legacy: list[str] = []
    malformed = False
    excluded = False

    for stripped in _constraint_lines(text):
        if stripped.startswith(_GO_BUILD_PREFIX):
            expression = stripped[len(_GO_BUILD_PREFIX) :].strip()
            if not expression:
                continue
            constraints.append(_constraint(GoConstraintSource.BUILD_LINE, expression))
            modern.append(expression)
        elif stripped.startswith(_LEGACY_BUILD_PREFIX):
            expression = stripped[len(_LEGACY_BUILD_PREFIX) :].strip()
            if not expression:
                continue
            constraints.append(_constraint(GoConstraintSource.BUILD_LINE, expression))
            legacy.append(expression)

    # Go gives //go:build precedence; legacy lines stay metadata only.
    for expression in modern:
        evaluator = _Expression(expression)
        if not evaluator.evaluate():
            if evaluator.malformed:
                malformed = True
            else:
                excluded = True
    if not modern:
        for expression in legacy:
            if not _legacy_expression(expression):
                excluded = True

    for expression in _filename_constraints(posixpath.basename(path)):
        constraints.append(_constraint(GoConstraintSource.FILENAME, expression))
        if expression not in {TARGET_OS, TARGET_ARCH}:
            excluded = True

    if malformed:
        return ConstraintResult(
            constraints=tuple(constraints),
            excluded=True,
            exclusion_reason=MALFORMED_BUILD_CONSTRAINT_REASON,
        )
    return ConstraintResult(
        constraints=tuple(constraints),
        excluded=excluded,
        exclusion_reason=EXCLUSION_REASON if excluded else None,
    )


def _constraint(source: GoConstraintSource, expression: str) -> GoBuildConstraint:
    return GoBuildConstraint(source=source, expression=expression)


def _constraint_lines(text: str) -> tuple[str, ...]:
    """Lines that may carry a build constraint, stopping at the package clause.

    A ``//go:build`` line inside a block comment is not a constraint, so block
    comments are skipped rather than scanned as if they were line comments.
    """
    lines: list[str] = []
    in_block_comment = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block_comment = True
            continue
        if re.match(r"package(?:\s|/\*)", stripped):
            break
        lines.append(stripped)
    return tuple(lines)


def _filename_constraints(name: str) -> tuple[str, ...]:
    """Return the GOOS/GOARCH terms a filename suffix carries.

    Go only tags a file when a non-empty name precedes the first underscore.
    ``js.go`` and ``js_test.go`` are plain files; ``windows_amd64.go`` carries
    only the amd64 suffix because ``windows`` is the prefix, not a second tag.
    """
    if not name.endswith(".go"):
        return ()
    stem = name[: -len(".go")]
    if stem.endswith("_test"):
        stem = stem[: -len("_test")]
    index = stem.find("_")
    if index <= 0:
        return ()
    parts = stem[index + 1 :].split("_")
    if len(parts) >= 2 and parts[-2] in _GOOS and parts[-1] in _GOARCH:
        return (parts[-2], parts[-1])
    if parts and (parts[-1] in _GOOS or parts[-1] in _GOARCH):
        return (parts[-1],)
    return ()


def _legacy_expression(expression: str) -> bool:
    """Evaluate one // +build line: space means OR, comma means AND."""
    groups = expression.split()
    if not groups:
        return False
    return any(all(_legacy_term(term) for term in group.split(",")) for group in groups)


def _legacy_term(term: str) -> bool:
    if term in {"", "!"} or term.startswith("!!"):
        return False
    negated = term.startswith("!")
    value = _tag_is_set(term.removeprefix("!"))
    return not value if negated else value


def _tag_is_set(tag: str) -> bool:
    return tag in _TARGET_TAGS


class _Expression:
    """A recursive-descent reader for the //go:build expression grammar."""

    def __init__(self, text: str) -> None:
        self._tokens = _TOKEN.findall(text)
        self._position = 0
        operators_removed = text.replace("&&", "").replace("||", "")
        self._valid = not _UNRECOGNISED.search(operators_removed)
        self._depth = 0
        self.malformed = not self._valid

    def evaluate(self) -> bool:
        if not self._tokens:
            return False
        value = self._or()
        return self._valid and value and self._position == len(self._tokens)

    def _enter(self) -> bool:
        self._depth += 1
        if self._depth > _MAX_EXPRESSION_DEPTH:
            self._valid = False
            self.malformed = True
            self._position = len(self._tokens)
            return False
        return True

    def _leave(self) -> None:
        self._depth -= 1

    def _or(self) -> bool:
        value = self._and()
        while self._peek() == "||":
            self._position += 1
            right = self._and()
            value = value or right
        return value

    def _and(self) -> bool:
        value = self._unary()
        while self._peek() == "&&":
            self._position += 1
            right = self._unary()
            value = value and right
        return value

    def _unary(self) -> bool:
        if self._peek() == "!":
            self._position += 1
            if not self._enter():
                return False
            value = not self._unary()
            self._leave()
            return value
        return self._primary()

    def _primary(self) -> bool:
        if self._peek() == "(":
            self._position += 1
            if not self._enter():
                return False
            value = self._or()
            self._leave()
            if self._peek() == ")":
                self._position += 1
            else:
                self._valid = False
            return value
        token = self._peek()
        if token is None or token in {"&&", "||", "!", "(", ")"}:
            self._valid = False
            self._position = len(self._tokens)
            return False
        self._position += 1
        return _tag_is_set(token)

    def _peek(self) -> str | None:
        if self._position >= len(self._tokens):
            return None
        return self._tokens[self._position]
