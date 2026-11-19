"""Read one Go file's package name and imports from its syntax tree.

Only grammar nodes produce imports, so a line that looks like an import in a
string or comment cannot become an edge. Positions are reported in characters,
not in the UTF-8 byte columns the grammar uses.
"""

import ast
from dataclasses import dataclass
from typing import Self

from codecraft_core.model import EdgeKind, ParseFailure
from tree_sitter import Node, Parser, Tree

_NEW_EXPRESSION_REASON = "Go 1.26 new with expression argument, not read by the current grammar"
FILE_SYNTAX_REASON = "file has a syntax error"
MALFORMED_IMPORT_SPEC_REASON = "malformed import spec"


_NEW_EXPRESSION_FOLLOWERS = frozenset("([{.+\\-*/%&|^!<>")


@dataclass(frozen=True)
class SourceText:
    """A decoded file, split into lines for a byte column to become a character column."""

    lines: tuple[str, ...]

    @classmethod
    def from_text(cls, text: str) -> Self:
        return cls(lines=tuple(text.split("\n")))

    def remainder(self, node: Node) -> str:
        """The rest of the node's start line after its byte position."""
        row, byte_column = node.start_point
        if row >= len(self.lines):
            return ""
        line = self.lines[row]
        try:
            prefix = line.encode("utf-8")[:byte_column].decode("utf-8")
        except UnicodeDecodeError:
            return line[byte_column:]
        return line[len(prefix) :]

    def position(self, node: Node) -> tuple[int, int]:
        row, byte_column = node.start_point
        if row >= len(self.lines):
            return row + 1, byte_column + 1
        try:
            prefix = self.lines[row].encode("utf-8")[:byte_column].decode("utf-8")
        except UnicodeDecodeError:
            return row + 1, byte_column + 1
        return row + 1, len(prefix) + 1


@dataclass(frozen=True)
class RawGoImport:
    """One import path as written, before it is resolved to a package folder."""

    reference: str
    kind: EdgeKind
    alias: str | None
    line: int
    column: int
    failure_reason: str | None = None
    file_failure_reason: str | None = None


@dataclass(frozen=True)
class ParsedGoFile:
    """A decoded Go source file and what the grammar found in it."""

    text: str | None
    package: str
    imports: tuple[RawGoImport, ...]
    failure: ParseFailure | None


def parse_go_file(data: bytes, parser: Parser) -> ParsedGoFile:
    """Parse one Go file. Reads bytes only; never builds or runs the file."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ParsedGoFile(
            text=None,
            package="",
            imports=(),
            failure=ParseFailure(reason="cannot decode source", line=None, column=None),
        )

    source = SourceText.from_text(text)
    tree = parser.parse(data)
    package = _package_name(tree)
    failure = _first_syntax_problem(tree.root_node, source)
    imports = (
        _read_imports(tree, source)
        if failure is None
        else _read_failed_imports(tree, source, parser)
    )
    return ParsedGoFile(text=text, package=package, imports=imports, failure=failure)


def _package_name(tree: Tree) -> str:
    for child in tree.root_node.named_children:
        if child.type != "package_clause":
            continue
        for part in child.named_children:
            if part.type == "package_identifier":
                return _node_text(part)
    return ""


def _read_imports(tree: Tree, source: SourceText) -> tuple[RawGoImport, ...]:
    found: list[RawGoImport] = []
    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "import_declaration":
            found.extend(_declaration_imports(node, source))
        stack.extend(reversed(node.named_children))
    return tuple(found)


def _read_failed_imports(
    tree: Tree,
    source: SourceText,
    parser: Parser,
) -> tuple[RawGoImport, ...]:
    """Keep every import path the grammar could still read in a failed file.

    A failed file draws no edges. A readable path is marked so resolution can
    decide whether it points inside the repository, where it fails, or outside,
    where it stays external. A path the grammar could not read keeps its own
    reason and is never guessed.
    """
    found: list[RawGoImport] = []
    declarations = False
    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "import_declaration":
            declarations = True
            found.extend(_declaration_failed_imports(node, source))
        stack.extend(reversed(node.named_children))
    found.extend(_recover_error_imports(tree, source, parser))
    if not declarations and not found:
        error = _first_error_node(tree.root_node)
        if error is not None and _starts_import_statement(error):
            found.append(_missing_path_import(error, source))
    return _unique_imports(found)


def _unique_imports(items: list[RawGoImport]) -> tuple[RawGoImport, ...]:
    seen: set[tuple[str, EdgeKind, str | None, int, int, str | None, str | None]] = set()
    unique: list[RawGoImport] = []
    for item in items:
        key = (
            item.reference,
            item.kind,
            item.alias,
            item.line,
            item.column,
            item.failure_reason,
            item.file_failure_reason,
        )
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return tuple(unique)


def _scan_malformed_import_declaration(
    node: Node,
    source: SourceText,
) -> list[RawGoImport] | None:
    """Read a declaration that puts more than one path on one line.

    The grammar mangles these forms, so the declaration text is read as a
    sequence of import specs: one path per line, or several paths on one line.
    The first path on a line is ordinary; every later path is malformed.
    """
    declaration_line, declaration_column = source.position(node)
    text = _strip_comments(_node_text(node))
    lines = text.splitlines()
    grouped = "(" in (lines[0] if lines else "")
    return _scan_import_text(
        text,
        declaration_line,
        declaration_column,
        grouped,
    )


def _scan_malformed_single_line(
    node: Node,
    source: SourceText,
) -> list[RawGoImport] | None:
    if any(child.type == "import_spec_list" for child in node.named_children):
        return None
    line_number, column = source.position(node)
    if line_number - 1 >= len(source.lines):
        return None
    line = _strip_comments(source.lines[line_number - 1][column - 1 :])
    return _scan_import_text(line, line_number, column, False)


def _scan_import_text(
    text: str,
    declaration_line: int,
    declaration_column: int,
    grouped: bool,
) -> list[RawGoImport] | None:
    segments: list[tuple[int, str, int]] = []
    for index, line in enumerate(text.splitlines()):
        start = 0
        if grouped and "import" in line:
            opening = line.find("(")
            if opening >= 0:
                start = opening + 1
        for segment, offset in _line_segments(line, start, grouped):
            if segment.strip():
                segments.append((index, segment, offset))
    if not any(len(_string_literals(segment)) > 1 for _, segment, _ in segments):
        return None

    found: list[RawGoImport] = []
    for index, segment, offset in segments:
        literals = _string_literals(segment)
        if not literals:
            stripped = segment.strip()
            if stripped != ")" and not (not grouped and stripped.startswith("import")):
                kind, alias = _prefix_kind_alias(segment)
                found.append(
                    RawGoImport(
                        reference="(missing import path)",
                        kind=kind,
                        alias=alias,
                        line=declaration_line + index,
                        column=offset + len(segment) - len(segment.lstrip()) + 1,
                        failure_reason="import spec has no path",
                    )
                )
            continue
        prefix = segment[: literals[0][1]]
        kind, alias = _prefix_kind_alias(prefix)
        if grouped:
            first_position = (
                declaration_line + index,
                offset + len(segment) - len(segment.lstrip()) + 1,
            )
        else:
            first_position = (declaration_line, declaration_column)
        first_value = literals[0][0]
        found.append(
            _as_file_failed(
                RawGoImport(
                    reference=first_value,
                    kind=kind,
                    alias=alias,
                    line=first_position[0],
                    column=first_position[1],
                )
            )
        )
        for value, literal_offset in literals[1:]:
            found.append(
                RawGoImport(
                    reference=value,
                    kind=EdgeKind.IMPORT,
                    alias=None,
                    line=declaration_line + index,
                    column=offset + literal_offset + 1,
                    failure_reason=MALFORMED_IMPORT_SPEC_REASON,
                )
            )
    return found


def _line_segments(line: str, start: int, split: bool) -> list[tuple[str, int]]:
    segments: list[tuple[str, int]] = []
    quote: str | None = None
    index = start
    segment_start = start
    while index < len(line):
        character = line[index]
        if quote is not None:
            if quote == '"' and character == "\\":
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue
        if character in {'"', "`"}:
            quote = character
        elif character == ";":
            if not split:
                return [(line[start:index], start)]
            segments.append((line[segment_start:index], segment_start))
            segment_start = index + 1
        index += 1
    segments.append((line[segment_start:], segment_start))
    return segments


def _strip_comments(text: str) -> str:
    """Blank comments without moving any character or line."""
    result = list(text)
    index = 0
    quote: str | None = None
    while index < len(text):
        character = text[index]
        if quote is not None:
            if quote == '"' and character == "\\":
                index += 2
                continue
            if character == quote or (quote == '"' and character == "\n"):
                quote = None
            index += 1
            continue
        if character in {'"', "`"}:
            quote = character
            index += 1
            continue
        if character == "/" and index + 1 < len(text):
            following = text[index + 1]
            if following == "/":
                while index < len(text) and text[index] != "\n":
                    result[index] = " "
                    index += 1
                continue
            if following == "*":
                result[index] = " "
                result[index + 1] = " "
                index += 2
                while index < len(text):
                    if text[index] == "*" and index + 1 < len(text) and text[index + 1] == "/":
                        result[index] = " "
                        result[index + 1] = " "
                        index += 2
                        break
                    if text[index] != "\n":
                        result[index] = " "
                    index += 1
                continue
        index += 1
    return "".join(result)


def _string_literals(line: str) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    index = 0
    while index < len(line):
        character = line[index]
        if character not in {'"', "`"}:
            index += 1
            continue
        start = index
        quote = character
        index += 1
        while index < len(line):
            if quote == '"' and line[index] == "\\":
                index += 2
                continue
            if line[index] == quote:
                index += 1
                found.append((_decode_string(line[start:index]), start))
                break
            index += 1
    return found


def _decode_string(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] == "`":
        return text[1:-1].replace("\r", "")
    try:
        value = ast.literal_eval(text)
    except ValueError, SyntaxError, TypeError:
        return text[1:-1] if len(text) >= 2 else text
    return value if isinstance(value, str) else text


def _prefix_kind_alias(prefix: str) -> tuple[EdgeKind, str | None]:
    tokens = prefix.replace("(", " ").replace(")", " ").split()
    if tokens and tokens[0] == "import":
        tokens = tokens[1:]
    if not tokens:
        return EdgeKind.IMPORT, None
    last = tokens[-1]
    if last == "_":
        return EdgeKind.BLANK_IMPORT, None
    if last == ".":
        return EdgeKind.DOT_IMPORT, None
    return EdgeKind.IMPORT, last if last.isidentifier() else None


def _recover_error_imports(
    tree: Tree,
    source: SourceText,
    parser: Parser,
) -> list[RawGoImport]:
    """Read an import the grammar left inside an ERROR node."""
    recovered: list[RawGoImport] = []
    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        text = _strip_comments(_node_text(node)).strip()
        if node.type == "ERROR" and text.startswith("import"):
            if "(" in text:
                line, column = source.position(node)
                scanned = _scan_import_text(text, line, column, True)
                if scanned is not None:
                    recovered.extend(scanned)
            elif text == "import":
                sibling = node.next_named_sibling
                if sibling is not None:
                    sibling_text = _node_text(sibling)
                    if sibling_text.startswith(("(", '"', "`")):
                        recovered.extend(_reparse_import(node, sibling_text, parser))
        stack.extend(reversed(node.named_children))
    return recovered


def _reparse_import(node: Node, text: str, parser: Parser) -> list[RawGoImport]:
    prefix = "package p\n" + " " * node.start_point[1]
    synthetic = f"{prefix}import {text}"
    parsed = parser.parse(synthetic.encode())
    if parsed.root_node.has_error:
        return []
    found = _read_imports(parsed, SourceText.from_text(synthetic))
    start_row = node.start_point[0]
    return [_shift_import(item, start_row) for item in found]


def _shift_import(item: RawGoImport, start_row: int) -> RawGoImport:
    return RawGoImport(
        reference=item.reference,
        kind=item.kind,
        alias=item.alias,
        line=item.line - 1 + start_row,
        column=item.column,
        failure_reason=item.failure_reason,
        file_failure_reason=FILE_SYNTAX_REASON,
    )


def _declaration_failed_imports(node: Node, source: SourceText) -> list[RawGoImport]:
    scanned = _scan_malformed_import_declaration(node, source)
    if scanned is not None:
        return scanned
    scanned = _scan_malformed_single_line(node, source)
    if scanned is not None:
        return scanned
    lists = [child for child in node.named_children if child.type == "import_spec_list"]
    children = lists[0].named_children if lists else node.named_children
    position = source.position(node)
    found: list[RawGoImport] = []
    errors: list[RawGoImport] = []
    has_unreadable = False
    for child in children:
        if child.type == "import_spec":
            spec_position = source.position(child) if lists else position
            for item in _spec_import(child, spec_position):
                if item.failure_reason is not None:
                    has_unreadable = True
                    found.append(item)
                else:
                    found.append(_as_file_failed(item))
        elif child.is_error:
            errors.append(_missing_path_import(child, source))
    if has_unreadable:
        # The spec's own failure is more precise than a duplicate error node.
        return found
    return [*found, *errors]


def _as_file_failed(item: RawGoImport) -> RawGoImport:
    return RawGoImport(
        reference=item.reference,
        kind=item.kind,
        alias=item.alias,
        line=item.line,
        column=item.column,
        file_failure_reason=FILE_SYNTAX_REASON,
    )


def _missing_path_import(node: Node, source: SourceText) -> RawGoImport:
    line, column = source.position(node)
    return RawGoImport(
        reference="(missing import path)",
        kind=EdgeKind.IMPORT,
        alias=None,
        line=line,
        column=column,
        failure_reason="import spec has no path",
    )


def _starts_import_statement(node: Node) -> bool:
    text = _node_text(node).lstrip()
    if text == "import":
        return True
    return (
        text.startswith("import")
        and len(text) > len("import")
        and not (text[len("import")].isalnum() or text[len("import")] == "_")
    )


def _declaration_imports(node: Node, source: SourceText) -> list[RawGoImport]:
    lists = [child for child in node.named_children if child.type == "import_spec_list"]
    found: list[RawGoImport] = []
    if lists:
        for spec in lists[0].named_children:
            if spec.type == "import_spec":
                found.extend(_spec_import(spec, source.position(spec)))
    else:
        for spec in node.named_children:
            if spec.type == "import_spec":
                found.extend(_spec_import(spec, source.position(node)))
    return found


def _spec_import(spec: Node, position: tuple[int, int]) -> list[RawGoImport]:
    name_node = spec.child_by_field_name("name")
    kind = EdgeKind.IMPORT
    alias: str | None = None
    if name_node is not None:
        if name_node.type == "blank_identifier":
            kind = EdgeKind.BLANK_IMPORT
        elif name_node.type == "dot":
            kind = EdgeKind.DOT_IMPORT
        else:
            alias = _node_text(name_node)

    line, column = position
    path_node = spec.child_by_field_name("path")
    if path_node is None:
        return [
            RawGoImport(
                reference="(missing import path)",
                kind=kind,
                alias=alias,
                line=line,
                column=column,
                failure_reason="import spec has no path",
            )
        ]
    reference = _string_literal(path_node)
    if reference is None:
        # A damaged literal can span into a comment line; the reference is the
        # path text on its own line, never the comment that follows.
        text = _node_text(path_node).split("\n", 1)[0].rstrip("\r")
        return [
            RawGoImport(
                reference=text.strip('"`'),
                kind=kind,
                alias=alias,
                line=line,
                column=column,
                failure_reason="import path is not a literal string",
            )
        ]
    return [RawGoImport(reference=reference, kind=kind, alias=alias, line=line, column=column)]


def _string_literal(node: Node) -> str | None:
    text = _node_text(node)
    if len(text) >= 2 and text[0] == text[-1] == "`":
        # A Go raw string drops carriage returns and has no escapes.
        return text[1:-1].replace("\r", "")
    try:
        value = ast.literal_eval(text)
    except ValueError, SyntaxError, TypeError:
        return None
    return value if isinstance(value, str) else None


def _first_syntax_problem(root: Node, source: SourceText) -> ParseFailure | None:
    if not root.has_error:
        return None
    node = _first_error_node(root)
    if node is None:
        # The grammar says the tree is damaged but identifies no node. The
        # reason must still be a failure, not a silently parsed file.
        return ParseFailure(reason="syntax error", line=1, column=1)
    line, column = source.position(node)
    if _error_is_on_new_expression(node, root, source):
        return ParseFailure(
            reason=_NEW_EXPRESSION_REASON,
            line=line,
            column=column,
        )
    return ParseFailure(reason="syntax error", line=line, column=column)


def _first_error_node(root: Node) -> Node | None:
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        if node.is_error or node.is_missing:
            return node
        stack.extend(reversed(node.children))
    return None


def _error_is_on_new_expression(error: Node, root: Node, source: SourceText) -> bool:
    if error.start_byte == 0 and error.end_byte >= root.end_byte:
        # An error over the whole file does not identify one cause.
        return False
    current = error.parent
    while current is not None:
        if current.type == "call_expression" and _is_new_expression_call(current, source):
            return True
        current = current.parent
    stack: list[Node] = [error]
    while stack:
        node = stack.pop()
        if (
            node.type == "call_expression"
            and node.start_point == error.start_point
            and _is_new_expression_call(node, source)
        ):
            return True
        stack.extend(node.children)
    if error.is_error and error.end_point[0] - error.start_point[0] <= 5:
        stack = [error]
        while stack:
            node = stack.pop()
            if node.type == "call_expression" and _is_new_expression_call(node, source):
                return True
            stack.extend(node.children)
    return False


def _is_new_expression_call(call: Node, source: SourceText) -> bool:
    function = call.child_by_field_name("function")
    if function is None or _node_text(function) != "new":
        return False
    arguments = call.child_by_field_name("arguments")
    if arguments is None:
        return False
    stack: list[Node] = [arguments]
    while stack:
        node = stack.pop()
        if node.is_error and not _argument_is_obviously_type(arguments):
            return True
        if node.is_missing and node.type == ")":
            remainder = source.remainder(node).lstrip()
            if remainder and remainder[0] in _NEW_EXPRESSION_FOLLOWERS:
                return True
        stack.extend(node.children)
    return False


def _argument_is_obviously_type(arguments: Node) -> bool:
    text = _node_text(arguments).strip()
    if text.startswith("("):
        text = text[1:]
    if text.endswith(")"):
        text = text[:-1]
    text = text.strip()
    if not text or text in {"*", "chan", "map", "func", "struct", "interface", "[]", "..."}:
        return True
    if text.startswith(("map[", "chan ", "chan<-", "<-chan", "func(", "[]")) and "{" not in text:
        return True
    return text.startswith(("struct{", "interface{")) and "}" not in text


def _node_text(node: Node) -> str:
    data = node.text
    if data is None:
        return ""
    return data.decode("utf-8")
