"""The contract of record, checked against every fixture and against the parser.

jsonschema is a dev-only dependency of this package because the contract is a
JSON Schema document and the test must validate real output against it.
"""

import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Protocol, cast

import pytest
from codecraft_core import (
    AdapterRole,
    Coverage,
    Edge,
    EdgeKind,
    ExternalReference,
    FileCoverage,
    FileRecord,
    ImportCondition,
    Language,
    PackageKind,
    ParseFailure,
    PythonCoverageDetails,
    PythonFileDetails,
    PythonRepositoryDetails,
    ReferenceRecord,
    RepositoryParse,
    StarImportRecord,
    StarImportStatus,
    SymbolRecord,
    SymbolStatus,
)
from codecraft_parsing import parse_repository
from jsonschema import Draft202012Validator  # pyright: ignore[reportMissingTypeStubs]
from pydantic import BaseModel, ValidationError

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_PATH = _REPOSITORY_ROOT / "docs" / "contracts" / "parser-output.schema.json"
_FIXTURES = _REPOSITORY_ROOT / "backend" / "fixtures" / "python"

type JsonSchema = dict[str, object]

_FIXTURE_NAMES = tuple(path.name for path in sorted(p for p in _FIXTURES.iterdir() if p.is_dir()))


def _load_schema() -> JsonSchema:
    return cast("JsonSchema", json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


class _ValidationError(Protocol):
    @property
    def message(self) -> str: ...


class _Validator(Protocol):
    def iter_errors(self, instance: object) -> Iterable[_ValidationError]: ...


def _schema_errors(value: object, schema: JsonSchema) -> list[str]:
    # The library's own annotations narrow the instance to a private JSON type;
    # this protocol names the part of its API the contract test actually uses.
    validator = cast("_Validator", Draft202012Validator(schema))
    return [error.message for error in validator.iter_errors(value)]


def _schema_for(definition: str) -> JsonSchema:
    # A definition validated alone cannot follow its local $refs, so the root
    # schema's definitions travel with the reference to the one under test.
    definitions = _load_schema()["$defs"]
    return cast(
        "JsonSchema",
        {"$ref": f"#/$defs/{definition}", "$defs": definitions},
    )


@pytest.mark.parametrize("name", _FIXTURE_NAMES)
def test_expected_output_matches_the_schema(name: str) -> None:
    document: object = json.loads((_FIXTURES / name / "expected.json").read_text(encoding="utf-8"))
    errors = _schema_errors(document, _load_schema())
    assert errors == [], f"{name}: {errors}"


@pytest.mark.parametrize("name", _FIXTURE_NAMES)
def test_parser_output_matches_the_schema(name: str) -> None:
    document: object = parse_repository(_FIXTURES / name / "repo").model_dump(mode="json")
    errors = _schema_errors(document, _load_schema())
    assert errors == [], f"{name}: {errors}"


def test_the_schema_is_valid() -> None:
    Draft202012Validator.check_schema(_load_schema())


def test_the_schema_lists_every_field_the_model_emits() -> None:
    schema = _load_schema()
    definitions = cast("Mapping[str, object]", schema["$defs"])

    def fields(definition: str) -> set[str]:
        node = cast("Mapping[str, object]", definitions[definition])
        return set(cast("Mapping[str, object]", node["properties"]))

    def required(definition: str) -> set[str]:
        node = cast("Mapping[str, object]", definitions[definition])
        names = cast("list[object]", node["required"])
        return {name for name in names if isinstance(name, str)}

    assert fields("file_record") == set(FileRecord.model_fields) == required("file_record")
    assert fields("coverage") == set(Coverage.model_fields) == required("coverage")
    assert fields("file_coverage") == set(FileCoverage.model_fields) == required("file_coverage")
    assert fields("edge") == set(Edge.model_fields) == required("edge")
    assert (
        fields("reference_record")
        == set(ReferenceRecord.model_fields)
        == required("reference_record")
    )
    assert (
        fields("external_reference")
        == set(ExternalReference.model_fields)
        == required("external_reference")
    )
    assert fields("symbol_record") == set(SymbolRecord.model_fields) == required("symbol_record")
    assert (
        fields("star_import_record")
        == set(StarImportRecord.model_fields)
        == required("star_import_record")
    )
    assert (
        fields("python_file_details")
        == set(PythonFileDetails.model_fields)
        == required("python_file_details")
    )
    assert (
        fields("python_coverage_details")
        == set(PythonCoverageDetails.model_fields)
        == required("python_coverage_details")
    )
    assert (
        fields("python_repository_details")
        == set(PythonRepositoryDetails.model_fields)
        == required("python_repository_details")
    )
    root_properties = cast("Mapping[str, object]", schema["properties"])
    root_required = cast("list[object]", schema["required"])
    assert set(root_properties) == set(RepositoryParse.model_fields)
    assert {name for name in root_required if isinstance(name, str)} == set(
        RepositoryParse.model_fields
    )


def test_the_schema_enums_match_the_models() -> None:
    schema = _load_schema()
    definitions = cast("Mapping[str, object]", schema["$defs"])

    def enum(definition: str, field: str) -> set[object]:
        node = cast("Mapping[str, object]", definitions[definition])
        properties = cast("Mapping[str, object]", node["properties"])
        prop = cast("Mapping[str, object]", properties[field])
        return set(cast("list[object]", prop["enum"]))

    file_record = cast("Mapping[str, object]", definitions["file_record"])
    file_properties = cast("Mapping[str, object]", file_record["properties"])
    language = cast("Mapping[str, object]", file_properties["language"])
    assert set(cast("list[object]", language["enum"])) == {
        *(value.value for value in Language),
        None,
    }
    assert enum("python_file_details", "package_kind") == {
        *(value.value for value in PackageKind),
        None,
    }
    assert enum("edge", "kind") == {value.value for value in EdgeKind}
    assert enum("edge", "condition") == {
        *(value.value for value in ImportCondition),
        None,
    }
    assert enum("symbol_record", "status") == {value.value for value in SymbolStatus}
    assert enum("star_import_record", "status") == {value.value for value in StarImportStatus}
    assert enum("file_record", "adapter_role") == {value.value for value in AdapterRole}


def test_the_validator_rejects_broken_documents() -> None:
    schema = _load_schema()
    fixture = _FIXTURES / _FIXTURE_NAMES[0]
    valid = cast(
        "dict[str, object]",
        json.loads((fixture / "expected.json").read_text(encoding="utf-8")),
    )
    assert _schema_errors(valid, schema) == []

    wrong_type = dict(valid)
    wrong_type["parser_version"] = 7
    assert _schema_errors(wrong_type, schema) != []

    missing = dict(valid)
    del missing["coverage"]
    assert _schema_errors(missing, schema) != []

    with_fan = dict(valid)
    files = list(cast("list[object]", with_fan["files"]))
    first = dict(cast("Mapping[str, object]", files[0]))
    first["fan_in"] = 0
    files[0] = first
    with_fan["files"] = files
    assert _schema_errors(with_fan, schema) != []


type PositionedFactory = Callable[[int, int], BaseModel]

_POSITIONED_RECORDS: tuple[tuple[str, PositionedFactory], ...] = (
    (
        "edge",
        lambda line, column: Edge(
            source="a.py",
            target="b.py",
            kind=EdgeKind.IMPORT,
            condition=None,
            line=line,
            column=column,
        ),
    ),
    (
        "symbol_record",
        lambda line, column: SymbolRecord(
            source="a.py",
            module="m",
            name="n",
            status=SymbolStatus.UNVERIFIED,
            line=line,
            column=column,
        ),
    ),
    (
        "star_import_record",
        lambda line, column: StarImportRecord(
            source="a.py",
            module="m",
            status=StarImportStatus.NAMES_NOT_ENUMERATED,
            line=line,
            column=column,
        ),
    ),
    (
        "reference_record",
        lambda line, column: ReferenceRecord(
            source="a.py",
            reference="m",
            reason="r",
            line=line,
            column=column,
        ),
    ),
    (
        "external_reference",
        lambda line, column: ExternalReference(
            source="a.py",
            reference="m",
            top_level="m",
            line=line,
            column=column,
        ),
    ),
    (
        "parse_failure",
        lambda line, column: ParseFailure(reason="r", line=line, column=column),
    ),
)


@pytest.mark.parametrize(("definition", "factory"), _POSITIONED_RECORDS)
def test_a_zero_position_is_rejected_by_the_model(
    definition: str, factory: PositionedFactory
) -> None:
    assert factory(1, 1) is not None
    with pytest.raises(ValidationError):
        factory(0, 1)
    with pytest.raises(ValidationError):
        factory(1, 0)


@pytest.mark.parametrize(("definition", "factory"), _POSITIONED_RECORDS)
def test_a_zero_position_is_rejected_by_the_schema(
    definition: str, factory: PositionedFactory
) -> None:
    schema = _schema_for(definition)
    record = cast("dict[str, object]", factory(1, 1).model_dump(mode="json"))
    assert _schema_errors(record, schema) == []
    for field in ("line", "column"):
        broken = dict(record)
        broken[field] = 0
        assert _schema_errors(broken, schema) != []


_COVERAGE_COUNTS = (
    "references",
    "resolved",
    "symbols",
    "star_imports",
    "external",
    "excluded",
    "failed",
)
_FILE_COVERAGE_COUNTS = ("found", "parsed", "failed_parse", "excluded")


def _coverage_document() -> dict[str, object]:
    values: dict[str, object] = {name: 0 for name in _COVERAGE_COUNTS}
    values["python"] = None
    values["failures_by_reason"] = {}
    values["failure_examples"] = []
    return values


def _file_coverage_document() -> dict[str, object]:
    values: dict[str, object] = {name: 0 for name in _FILE_COVERAGE_COUNTS}
    values["excluded_by_reason"] = {}
    return values


@pytest.mark.parametrize("field", _COVERAGE_COUNTS)
def test_a_negative_coverage_count_is_rejected_by_the_model(field: str) -> None:
    values = _coverage_document()
    values[field] = -1
    with pytest.raises(ValidationError) as invalid:
        Coverage.model_validate(values)
    assert any(item["type"] == "greater_than_equal" for item in invalid.value.errors())


@pytest.mark.parametrize("field", _COVERAGE_COUNTS)
def test_a_negative_coverage_count_is_rejected_by_the_schema(field: str) -> None:
    schema = _schema_for("coverage")
    values = _coverage_document()
    assert _schema_errors(values, schema) == []
    values[field] = -1
    assert _schema_errors(values, schema) != []


@pytest.mark.parametrize("field", _FILE_COVERAGE_COUNTS)
def test_a_negative_file_coverage_count_is_rejected_by_the_model(field: str) -> None:
    values = _file_coverage_document()
    values[field] = -1
    with pytest.raises(ValidationError) as invalid:
        FileCoverage.model_validate(values)
    assert any(item["type"] == "greater_than_equal" for item in invalid.value.errors())


@pytest.mark.parametrize("field", _FILE_COVERAGE_COUNTS)
def test_a_negative_file_coverage_count_is_rejected_by_the_schema(field: str) -> None:
    schema = _schema_for("file_coverage")
    values = _file_coverage_document()
    assert _schema_errors(values, schema) == []
    values[field] = -1
    assert _schema_errors(values, schema) != []


_VALID_HASH = "sha256:" + "0" * 64


def _file_record(line_count: int = 1, content_hash: str | None = _VALID_HASH) -> FileRecord:
    return FileRecord(
        path="a.py",
        folder=".",
        language=Language.PYTHON,
        line_count=line_count,
        content_hash=content_hash,
        is_node=True,
        excluded_reason=None,
        parse_failure=None,
        adapter_role=AdapterRole.FALLBACK,
        python=PythonFileDetails(module="a", package_kind=None, is_package=False),
    )


def test_a_negative_line_count_is_rejected_by_the_model_and_the_schema() -> None:
    with pytest.raises(ValidationError) as invalid:
        _file_record(line_count=-1)
    assert any(item["type"] == "greater_than_equal" for item in invalid.value.errors())

    schema = _schema_for("file_record")
    document = cast("dict[str, object]", _file_record().model_dump(mode="json"))
    assert _schema_errors(document, schema) == []
    document["line_count"] = -1
    assert _schema_errors(document, schema) != []


def test_a_negative_namespace_package_count_is_rejected_by_the_model_and_the_schema() -> None:
    with pytest.raises(ValidationError) as invalid:
        PythonCoverageDetails(namespace_packages=-1)
    assert any(item["type"] == "greater_than_equal" for item in invalid.value.errors())

    schema = _schema_for("python_coverage_details")
    document = cast(
        "dict[str, object]",
        PythonCoverageDetails(namespace_packages=0).model_dump(mode="json"),
    )
    assert _schema_errors(document, schema) == []
    document["namespace_packages"] = -1
    assert _schema_errors(document, schema) != []


def test_a_malformed_content_hash_is_rejected_by_the_model_and_the_schema() -> None:
    with pytest.raises(ValidationError) as invalid:
        _file_record(content_hash="sha256:not-a-hash")
    assert any(item["type"] == "string_pattern_mismatch" for item in invalid.value.errors())

    schema = _schema_for("file_record")
    document = cast("dict[str, object]", _file_record().model_dump(mode="json"))
    assert _schema_errors(document, schema) == []
    document["content_hash"] = "sha256:not-a-hash"
    assert _schema_errors(document, schema) != []
    document["content_hash"] = _VALID_HASH
    assert _schema_errors(document, schema) == []
