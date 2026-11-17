"""Read the imports a file really contains, from its syntax tree.

Only grammar nodes produce imports. A line in a docstring or a comment that
looks like an import is a string or a comment to the grammar, so it cannot
become an edge. Positions are reported in characters, not in the UTF-8 byte
columns the grammar speaks in, because a reader counts characters.
"""

import ast
from dataclasses import dataclass
from typing import Self

from codecraft_core.model import EdgeKind, ImportCondition
from tree_sitter import Node, Tree

_TYPE_CHECKING_GUARDS = frozenset({"TYPE_CHECKING", "typing.TYPE_CHECKING"})
_LITERAL_STRING_TYPES = frozenset({"string", "concatenated_string"})

# Call text is the evidence for a dynamic import without a literal name. It is
# bounded so one very long call cannot carry an unbounded amount of source text
# into the output. Only the call-text references are bounded; a literal module
# name is stored as written.
MAX_REFERENCE_TEXT = 120


@dataclass(frozen=True)
class SourceText:
    """A decoded file, split into lines so a byte column can become a character column."""

    text: str
    lines: tuple[str, ...]

    @classmethod
    def from_text(cls, text: str) -> Self:
        # Splitting on newlines only matches how the grammar counts rows; other
        # characters that str.splitlines treats as breaks would shift them.
        return cls(text=text, lines=tuple(text.split("\n")))

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
class RawImport:
    """One module reference as written, before it is resolved against the index.

    A from-import is one reference for its base module plus a name for each
    imported module candidate; names are only resolved when the base resolves,
    since ``from missing import x`` names ``x`` as a symbol of a missing module.
    """

    reference: str
    parts: tuple[str, ...]
    kind: EdgeKind
    line: int
    column: int
    condition: ImportCondition | None
    is_relative: bool = False
    levels_up: int = 0
    names: tuple[str, ...] = ()
    anchor: tuple[str, ...] | None = None
    failure_reason: str | None = None
    is_star: bool = False


def read_imports(tree: Tree, source: SourceText) -> list[RawImport]:
    found: list[RawImport] = []
    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        match node.type:
            case "import_statement":
                found.extend(_plain_imports(node, source))
            case "import_from_statement":
                from_import = _from_import(node, source)
                if from_import is not None:
                    found.append(from_import)
            case "future_import_statement":
                line, column = source.position(node)
                found.append(
                    RawImport(
                        reference="__future__",
                        parts=("__future__",),
                        kind=EdgeKind.IMPORT,
                        line=line,
                        column=column,
                        condition=_condition(node),
                    )
                )
            case "call":
                dynamic_import = _dynamic_import(node, source)
                if dynamic_import is not None:
                    found.append(dynamic_import)
            case _:
                pass
        stack.extend(reversed(node.children))
    return found


def _plain_imports(node: Node, source: SourceText) -> list[RawImport]:
    line, column = source.position(node)
    condition = _condition(node)
    imports: list[RawImport] = []
    for child in node.children_by_field_name("name"):
        name_node = _imported_name_node(child)
        if name_node is None:
            continue
        reference = _node_text(name_node)
        imports.append(
            RawImport(
                reference=reference,
                parts=tuple(reference.split(".")),
                kind=EdgeKind.IMPORT,
                line=line,
                column=column,
                condition=condition,
            )
        )
    return imports


def _from_import(node: Node, source: SourceText) -> RawImport | None:
    module_node = node.child_by_field_name("module_name")
    if module_node is None:
        return None
    line, column = source.position(node)
    reference = _node_text(module_node)
    names = _imported_names(node)
    condition = _condition(node)
    is_star = any(child.type == "wildcard_import" for child in node.named_children)

    if module_node.type != "relative_import":
        return RawImport(
            reference=reference,
            parts=tuple(reference.split(".")),
            kind=EdgeKind.IMPORT,
            line=line,
            column=column,
            condition=condition,
            names=names,
            is_star=is_star,
        )

    dotted = next((child for child in module_node.children if child.type == "dotted_name"), None)
    parts = tuple(_node_text(dotted).split(".")) if dotted is not None else ()
    leading_dots = len(reference) - len(reference.lstrip("."))
    return RawImport(
        reference=reference,
        parts=parts,
        kind=EdgeKind.IMPORT,
        line=line,
        column=column,
        condition=condition,
        is_relative=True,
        levels_up=leading_dots - 1,
        names=names,
        is_star=is_star,
    )


def _dynamic_import(node: Node, source: SourceText) -> RawImport | None:
    if not _is_dynamic_import_call(node):
        return None
    line, column = source.position(node)
    condition = _condition(node)
    call_source = _bounded_reference(_node_text(node))
    value = _literal_string(_module_argument(node))
    if value is None:
        return RawImport(
            reference=call_source,
            parts=(),
            kind=EdgeKind.DYNAMIC_IMPORT,
            line=line,
            column=column,
            condition=condition,
            failure_reason="non-literal dynamic import",
        )
    if not value:
        # The call text names the reference, because the empty literal alone
        # would not say which import produced the failure.
        return RawImport(
            reference=call_source,
            parts=(),
            kind=EdgeKind.DYNAMIC_IMPORT,
            line=line,
            column=column,
            condition=condition,
            failure_reason="empty module name",
        )
    if _is_dunder_import_call(node):
        if value.startswith("."):
            # __import__ takes its package from the caller's globals, not from a
            # package argument, so a dot-leading name has no anchor to resolve
            # against here. Refuse it rather than guess a base.
            return RawImport(
                reference=value,
                parts=(),
                kind=EdgeKind.DYNAMIC_IMPORT,
                line=line,
                column=column,
                condition=condition,
                failure_reason="relative __import__ is not resolved",
            )
        level_node = _level_argument(node)
        if level_node is not None:
            level = _literal_int(level_node)
            if level is None:
                # Without a literal level the package the name is measured from
                # is unknown, so no target can be chosen without guessing.
                return RawImport(
                    reference=call_source,
                    parts=(),
                    kind=EdgeKind.DYNAMIC_IMPORT,
                    line=line,
                    column=column,
                    condition=condition,
                    failure_reason="non-literal dynamic import",
                )
            if level < 0:
                return RawImport(
                    reference=call_source,
                    parts=(),
                    kind=EdgeKind.DYNAMIC_IMPORT,
                    line=line,
                    column=column,
                    condition=condition,
                    failure_reason="negative __import__ level",
                )
            if level > 0:
                return RawImport(
                    reference=value,
                    parts=tuple(value.split(".")),
                    kind=EdgeKind.DYNAMIC_IMPORT,
                    line=line,
                    column=column,
                    condition=condition,
                    is_relative=True,
                    levels_up=level - 1,
                )
    dots = len(value) - len(value.lstrip("."))
    if dots:
        package_node = _package_argument(node) if _is_import_module_call(node) else None
        if package_node is None:
            return RawImport(
                reference=value,
                parts=(),
                kind=EdgeKind.DYNAMIC_IMPORT,
                line=line,
                column=column,
                condition=condition,
                failure_reason="relative dynamic import requires a package argument",
            )
        package = _literal_string(package_node)
        if package is None:
            return RawImport(
                reference=value,
                parts=(),
                kind=EdgeKind.DYNAMIC_IMPORT,
                line=line,
                column=column,
                condition=condition,
                failure_reason="non-literal dynamic import package",
            )
        if not package:
            return RawImport(
                reference=value,
                parts=(),
                kind=EdgeKind.DYNAMIC_IMPORT,
                line=line,
                column=column,
                condition=condition,
                failure_reason="empty package name",
            )
        base = value[dots:]
        return RawImport(
            reference=value,
            parts=tuple(base.split(".")) if base else (),
            kind=EdgeKind.DYNAMIC_IMPORT,
            line=line,
            column=column,
            condition=condition,
            is_relative=True,
            levels_up=dots - 1,
            anchor=tuple(package.split(".")),
        )
    return RawImport(
        reference=value,
        parts=tuple(value.split(".")),
        kind=EdgeKind.DYNAMIC_IMPORT,
        line=line,
        column=column,
        condition=condition,
    )


def _is_import_module_call(node: Node) -> bool:
    function = node.child_by_field_name("function")
    if function is None or function.type != "attribute":
        return False
    owner = function.child_by_field_name("object")
    attribute = function.child_by_field_name("attribute")
    return (
        owner is not None
        and owner.type == "identifier"
        and _node_text(owner) == "importlib"
        and attribute is not None
        and attribute.type == "identifier"
        and _node_text(attribute) == "import_module"
    )


def _arguments(call: Node) -> list[Node]:
    arguments = call.child_by_field_name("arguments")
    if arguments is None:
        return []
    # A comment is a named extra and is not an argument.
    return [child for child in arguments.named_children if child.type != "comment"]


def _module_argument(call: Node) -> Node | None:
    arguments = _arguments(call)
    for child in arguments:
        if child.type == "keyword_argument":
            name = child.child_by_field_name("name")
            if name is not None and _node_text(name) == "name":
                return child.child_by_field_name("value")
    for child in arguments:
        if child.type == "keyword_argument":
            continue
        return child
    return None


def _package_argument(call: Node) -> Node | None:
    position = 0
    for child in _arguments(call):
        if child.type == "keyword_argument":
            name = child.child_by_field_name("name")
            if name is not None and _node_text(name) == "package":
                return child.child_by_field_name("value")
            continue
        if position == 1:
            return child
        position += 1
    return None


def _is_dunder_import_call(node: Node) -> bool:
    function = node.child_by_field_name("function")
    return (
        function is not None
        and function.type == "identifier"
        and _node_text(function) == "__import__"
    )


def _is_dynamic_import_call(node: Node) -> bool:
    if _is_dunder_import_call(node):
        return True
    function = node.child_by_field_name("function")
    if function is None:
        return False
    if function.type != "attribute":
        return False
    owner = function.child_by_field_name("object")
    attribute = function.child_by_field_name("attribute")
    return (
        owner is not None
        and owner.type == "identifier"
        and _node_text(owner) == "importlib"
        and attribute is not None
        and attribute.type == "identifier"
        and _node_text(attribute) == "import_module"
    )


def _level_argument(call: Node) -> Node | None:
    """The ``level`` argument of ``__import__``, keyword or fifth positional."""
    position = 0
    for child in _arguments(call):
        if child.type == "keyword_argument":
            name = child.child_by_field_name("name")
            if name is not None and _node_text(name) == "level":
                return child.child_by_field_name("value")
            continue
        if position == 4:
            return child
        position += 1
    return None


def _literal_int(argument: Node) -> int | None:
    if argument.type == "integer":
        literal = _node_text(argument)
    elif argument.type == "unary_operator":
        literal = _node_text(argument)
        operand = argument.named_children[0] if len(argument.named_children) == 1 else None
        if not literal.startswith(("+", "-")) or operand is None or operand.type != "integer":
            return None
    else:
        return None
    try:
        value = ast.literal_eval(literal)
    except ValueError, SyntaxError, TypeError:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _literal_string(argument: Node | None) -> str | None:
    if argument is None or argument.type not in _LITERAL_STRING_TYPES:
        return None
    try:
        value = ast.literal_eval(_node_text(argument))
    except ValueError, SyntaxError, TypeError:
        return None
    # ast.literal_eval is used only to decode a literal. Nothing here parses or
    # executes the repository's code.
    return value if isinstance(value, str) else None


def _imported_names(node: Node) -> tuple[str, ...]:
    names: list[str] = []
    for child in node.children_by_field_name("name"):
        if child.type == "wildcard_import":
            continue
        name_node = _imported_name_node(child)
        if name_node is not None:
            names.append(_node_text(name_node))
    return tuple(names)


def _imported_name_node(child: Node) -> Node | None:
    if child.type == "aliased_import":
        return child.child_by_field_name("name")
    return child


def _condition(node: Node) -> ImportCondition | None:
    current = node.parent
    descendant = node
    while current is not None:
        if current.type in {"if_statement", "elif_clause"}:
            consequence = current.child_by_field_name("consequence")
            # A condition guards only the branch whose text follows it. An
            # import under an elif or else is reached through a clause child,
            # not through the if's consequence, so the outer if does not guard
            # it; the elif's own condition still guards its own branch.
            if descendant == consequence:
                condition = current.child_by_field_name("condition")
                # The guard is compared as written: a broader expression may or
                # may not guard on typing, and guessing would mislabel the edge.
                if condition is not None and _node_text(condition) in _TYPE_CHECKING_GUARDS:
                    return ImportCondition.TYPE_ONLY
        elif current.type == "try_statement":
            return ImportCondition.OPTIONAL
        elif current.type in {"function_definition", "async_function_definition"}:
            return ImportCondition.LAZY
        descendant = current
        current = current.parent
    return None


def _bounded_reference(text: str) -> str:
    if len(text) <= MAX_REFERENCE_TEXT:
        return text
    return f"{text[:MAX_REFERENCE_TEXT]}..."


def _node_text(node: Node) -> str:
    data = node.text
    if data is None:
        return ""
    # The source was decoded before parsing, so every byte slice is valid UTF-8.
    return data.decode("utf-8")
