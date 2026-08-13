from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from quant_platform.factor_ir import compile_factor_ir

GOLDEN_ROOT = Path(__file__).parent / "golden"


def load_cases() -> list[dict[str, object]]:
    payload = cast(
        dict[str, Any],
        json.loads((GOLDEN_ROOT / "classic_factors.json").read_text()),
    )
    assert payload["schema_version"] == "factor-ir-golden/v1"
    return cast(list[dict[str, object]], payload["cases"])


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
def test_classic_factor_compilation_golden(case: dict[str, object]) -> None:
    compiled = compile_factor_ir(cast(Mapping[str, Any], case["ir"]))

    assert {
        "factor_id": compiled.factor_id,
        "expression_hash": compiled.expression_hash,
        "lookback": compiled.lookback,
        "available_time": compiled.available_time,
        "output_kind": compiled.output_type.kind.value,
        "output_unit": compiled.output_type.unit,
        "operators": list(compiled.operator_names),
    } == case["expected"]
