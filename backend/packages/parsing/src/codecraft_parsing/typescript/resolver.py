"""The Python side of the JavaScript resolver protocol.

The helper is one Node process per repository. Its answer is authoritative; this
module only validates the envelope and maps named failures. It never retries a
missing helper silently.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from codecraft_core.model import ResolutionPath

PROTOCOL_VERSION = 1
_HELPER = Path(__file__).resolve().parents[3] / "js" / "resolver" / "resolver.js"


class ResolverFailure(Exception):
    """The helper could not answer, with the contract's named failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ResolutionRequest:
    id: str
    source: str
    specifier: str
    kind: str


@dataclass(frozen=True)
class Resolution:
    resolved_path: str | None
    resolution_path: ResolutionPath | None
    reason: str | None


@dataclass(frozen=True)
class ResolverResponse:
    typescript_version: str
    config_files: tuple[str, ...]
    results: dict[str, Resolution]


def resolve_references(
    root: Path,
    requests: tuple[ResolutionRequest, ...],
    *,
    max_file_bytes: int,
) -> ResolverResponse:
    """Ask the helper for every literal module reference in one batch."""
    node = shutil.which("node")
    if node is None or not _HELPER.is_file():
        raise ResolverFailure("js resolver is missing")

    request = {
        "protocol_version": PROTOCOL_VERSION,
        "repository_root": str(root),
        "max_file_bytes": max_file_bytes,
        "references": [
            {
                "id": item.id,
                "source": item.source,
                "specifier": item.specifier,
                "kind": item.kind,
            }
            for item in requests
        ],
    }
    try:
        completed = subprocess.run(
            [node, str(_HELPER)],
            input=json.dumps(request),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
    except UnicodeDecodeError as error:
        raise ResolverFailure("js resolver returned an invalid response") from error
    if completed.returncode != 0:
        code = _error_code(completed.stdout)
        if code == "unsupported_protocol_version":
            raise ResolverFailure("js resolver rejected the protocol version")
        raise ResolverFailure("js resolver failed")
    if completed.stdout.strip() == "":
        raise ResolverFailure("js resolver returned an invalid response")

    try:
        loaded: object = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ResolverFailure("js resolver returned an invalid response") from error
    document = _object(loaded)
    if document is None:
        raise ResolverFailure("js resolver returned an invalid response")

    error = _object(document.get("error"))
    if error is not None:
        code = error.get("code")
        if code == "unsupported_protocol_version":
            raise ResolverFailure("js resolver rejected the protocol version")
        raise ResolverFailure("js resolver failed")
    if document.get("protocol_version") != PROTOCOL_VERSION:
        raise ResolverFailure("js resolver returned an invalid response")

    typescript_version = document.get("typescript_version")
    config_values = document.get("config_files")
    raw_results_value = document.get("results")
    if not isinstance(typescript_version, str) or not isinstance(config_values, list):
        raise ResolverFailure("js resolver returned an invalid response")
    config_files: list[str] = []
    for value in cast("list[object]", config_values):
        if not isinstance(value, str):
            raise ResolverFailure("js resolver returned an invalid response")
        config_files.append(value)
    if not isinstance(raw_results_value, list):
        raise ResolverFailure("js resolver returned an invalid response")
    raw_results = cast("list[object]", raw_results_value)
    if len(raw_results) != len(requests):
        raise ResolverFailure("js resolver returned an invalid response")

    results: dict[str, Resolution] = {}
    for raw_value in raw_results:
        raw = _object(raw_value)
        if raw is None:
            raise ResolverFailure("js resolver returned an invalid response")
        item_id = raw.get("id")
        resolved_path = raw.get("resolved_path")
        reason = raw.get("reason")
        raw_resolution = raw.get("resolution_path")
        if not isinstance(item_id, str) or item_id in results:
            raise ResolverFailure("js resolver returned an invalid response")
        if resolved_path is not None and not isinstance(resolved_path, str):
            raise ResolverFailure("js resolver returned an invalid response")
        if reason is not None and not isinstance(reason, str):
            raise ResolverFailure("js resolver returned an invalid response")
        if (resolved_path is None) == (reason is None):
            raise ResolverFailure("js resolver returned an invalid response")
        resolution_path: ResolutionPath | None
        if resolved_path is None:
            if raw_resolution is not None:
                raise ResolverFailure("js resolver returned an invalid response")
            resolution_path = None
        else:
            if not isinstance(raw_resolution, str):
                raise ResolverFailure("js resolver returned an invalid response")
            try:
                resolution_path = ResolutionPath(raw_resolution)
            except ValueError as error:
                raise ResolverFailure("js resolver returned an invalid response") from error
        results[item_id] = Resolution(
            resolved_path=resolved_path,
            resolution_path=resolution_path,
            reason=reason,
        )

    if set(results) != {item.id for item in requests}:
        raise ResolverFailure("js resolver returned an invalid response")
    return ResolverResponse(
        typescript_version=typescript_version,
        config_files=tuple(config_files),
        results=results,
    )


def _object(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    return None


def _error_code(stdout: str) -> str | None:
    try:
        loaded: object = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    document = _object(loaded)
    if document is None:
        return None
    error = _object(document.get("error"))
    if error is None:
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None
