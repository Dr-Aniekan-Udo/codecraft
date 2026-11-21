"""Turn shared walked files into TypeScript and JavaScript file records."""

import posixpath

from codecraft_core.model import (
    AdapterRole,
    FileRecord,
    Language,
    ParseFailure,
    TypeScriptFileDetails,
    TypeScriptFileKind,
)

from codecraft_parsing.common.walker import WalkedFile, WalkResult

_NOT_SOURCE = "not a TypeScript or JavaScript file"
_DECLARATION_SUFFIXES = (".d.ts", ".d.mts", ".d.cts")
_GENERATED_MARKERS = (
    "@generated",
    "DO NOT EDIT",
    "auto-generated",
    "This file was generated",
)


def build_typescript_files(walked: WalkResult) -> tuple[list[FileRecord], dict[str, str]]:
    """Attach TypeScript details and decoded source to the shared walk."""
    files: list[FileRecord] = []
    sources: dict[str, str] = {}

    for walked_file in walked.files:
        if not walked_file.is_node:
            files.append(_excluded_record(walked_file))
            continue
        marker = _generated_marker(walked_file.data)
        if marker is not None:
            files.append(_generated_record(walked_file, marker))
            continue
        files.append(_node_record(walked_file, sources))

    return files, sources


def classify_typescript_file(name: str) -> bool:
    """Whether ``name`` is a TypeScript or JavaScript source file."""
    return name.endswith((".ts", ".tsx", ".js", ".jsx"))


def file_language(name: str) -> Language:
    return Language.JAVASCRIPT if name.endswith((".js", ".jsx")) else Language.TYPESCRIPT


def file_kind(name: str) -> TypeScriptFileKind:
    return (
        TypeScriptFileKind.DECLARATION
        if name.endswith(_DECLARATION_SUFFIXES)
        else TypeScriptFileKind.SOURCE
    )


def _node_record(walked: WalkedFile, sources: dict[str, str]) -> FileRecord:
    data = walked.data
    if data is None:
        raise ValueError(f"node {walked.path} has no bytes")
    name = posixpath.basename(walked.path)
    line_count = len(data.splitlines())
    failure = None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        failure = ParseFailure(reason="cannot decode source", line=None, column=None)
    else:
        sources[walked.path] = text

    return FileRecord(
        path=walked.path,
        folder=walked.folder,
        language=file_language(name),
        line_count=line_count,
        content_hash=walked.content_hash,
        is_node=True,
        excluded_reason=None,
        parse_failure=failure,
        adapter_role=AdapterRole.FALLBACK,
        python=None,
        go=None,
        typescript=TypeScriptFileDetails(kind=file_kind(name)),
    )


def _generated_record(walked: WalkedFile, marker: str) -> FileRecord:
    data = walked.data
    if data is None:
        raise ValueError(f"generated file {walked.path} has no bytes")
    name = posixpath.basename(walked.path)
    return FileRecord(
        path=walked.path,
        folder=walked.folder,
        language=file_language(name),
        line_count=len(data.splitlines()),
        content_hash=walked.content_hash,
        is_node=False,
        excluded_reason=f"generated file: {marker}",
        parse_failure=None,
        adapter_role=AdapterRole.FALLBACK,
        python=None,
        go=None,
    )


def _generated_marker(data: bytes | None) -> str | None:
    if data is None:
        return None
    for line in data.splitlines()[:10]:
        lowered = line.lower()
        for marker in _GENERATED_MARKERS:
            if marker.lower().encode("utf-8") in lowered:
                return marker
    return None


def _excluded_record(walked: WalkedFile) -> FileRecord:
    return FileRecord(
        path=walked.path,
        folder=walked.folder,
        language=walked.language,
        line_count=walked.line_count,
        content_hash=walked.content_hash,
        is_node=False,
        excluded_reason=walked.excluded_reason or _NOT_SOURCE,
        parse_failure=None,
        adapter_role=AdapterRole.FALLBACK,
        python=None,
        go=None,
    )
