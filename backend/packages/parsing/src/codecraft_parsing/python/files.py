"""Turn shared walked files into Python file records."""

import io
import posixpath
import tokenize

from codecraft_core.model import (
    AdapterRole,
    FileRecord,
    Language,
    PackageKind,
    ParseFailure,
    PythonFileDetails,
)

from codecraft_parsing.common.walker import WalkedFile, WalkResult


def build_python_files(
    walked: WalkResult, import_root: str
) -> tuple[list[FileRecord], dict[str, str]]:
    """Attach Python module identity and decoded source to the shared walk."""
    regular_directories = {
        posixpath.dirname(record.path)
        for record in walked.files
        if posixpath.basename(record.path) == "__init__.py"
    }
    files: list[FileRecord] = []
    sources: dict[str, str] = {}

    for walked_file in walked.files:
        if not walked_file.is_node:
            files.append(_excluded_record(walked_file))
            continue
        files.append(_node_record(walked_file, import_root, regular_directories, sources))

    return files, sources


def _node_record(
    walked: WalkedFile,
    import_root: str,
    regular_directories: set[str],
    sources: dict[str, str],
) -> FileRecord:
    name = posixpath.basename(walked.path)
    is_package = name == "__init__.py"
    module, package_kind = _module_identity(
        walked.path, import_root, is_package, regular_directories
    )
    data = walked.data
    if data is None:
        raise ValueError(f"node {walked.path} has no bytes")
    text = _decode(data)
    failure = None
    if text is None:
        line_count = len(data.splitlines())
        failure = ParseFailure(reason="cannot decode source", line=None, column=None)
    else:
        line_count = len(text.splitlines())
        sources[walked.path] = text

    return FileRecord(
        path=walked.path,
        folder=walked.folder,
        language=Language.PYTHON,
        line_count=line_count,
        content_hash=walked.content_hash,
        is_node=True,
        excluded_reason=None,
        parse_failure=failure,
        adapter_role=AdapterRole.FALLBACK,
        python=PythonFileDetails(
            module=module,
            package_kind=package_kind,
            is_package=is_package,
        ),
    )


def _excluded_record(walked: WalkedFile) -> FileRecord:
    return FileRecord(
        path=walked.path,
        folder=walked.folder,
        language=walked.language,
        line_count=walked.line_count,
        content_hash=walked.content_hash,
        is_node=False,
        excluded_reason=walked.excluded_reason,
        parse_failure=None,
        adapter_role=AdapterRole.FALLBACK,
        python=None,
    )


def _module_identity(
    path: str, import_root: str, is_package: bool, regular_directories: set[str]
) -> tuple[str | None, PackageKind | None]:
    relative = _relative_to_import_root(path, import_root)
    if relative is None:
        return None, None

    if is_package:
        # An __init__ file names the package it defines, not a module inside it.
        package_path = posixpath.dirname(relative)
        return (package_path.replace("/", ".") if package_path else None), PackageKind.REGULAR

    module = relative[: -len(".py")].replace("/", ".")
    parent = posixpath.dirname(relative)
    if not parent:
        return module, None
    repository_parent = posixpath.dirname(path)
    kind = (
        PackageKind.REGULAR if repository_parent in regular_directories else PackageKind.NAMESPACE
    )
    return module, kind


def _relative_to_import_root(path: str, import_root: str) -> str | None:
    if import_root == ".":
        return path
    if path.startswith(import_root + "/"):
        return path[len(import_root) + 1 :]
    return None


def _decode(data: bytes) -> str | None:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        return data.decode(encoding)
    except SyntaxError, UnicodeDecodeError, LookupError:
        return None
