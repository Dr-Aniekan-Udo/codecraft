"""Regression test for the sample cleanup rule.

A sample project is removed only when it holds no non-sample analysis. A sample
project that has a real analysis keeps its sample label, so a later create run
is still rejected by the existing guard.
"""

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "seed_sample_data.py"


def _load_removable_project_ids() -> Callable[[list[tuple[object, ...]]], list[UUID]]:
    spec = importlib.util.spec_from_file_location("_seed_sample_data", _SCRIPT)
    assert spec is not None
    loader = spec.loader
    assert loader is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return cast(
        Callable[[list[tuple[object, ...]]], list[UUID]],
        module._removable_project_ids,
    )


def test_sample_project_with_real_analysis_is_kept() -> None:
    removable_project_ids = _load_removable_project_ids()
    kept_id = uuid4()
    removable_id = uuid4()

    result = removable_project_ids([(kept_id, True), (removable_id, False)])

    assert kept_id not in result
    assert result == [removable_id]
