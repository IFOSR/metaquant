from __future__ import annotations

import json
from pathlib import Path


def test_published_factor_ir_v1_schema_encodes_closed_contract() -> None:
    path = (
        Path(__file__).parents[2]
        / "docs"
        / "schemas"
        / "factor-ir"
        / "factor-ir-v1.schema.json"
    )
    schema = json.loads(path.read_text())

    assert schema["$id"] == "https://quant-platform.local/schemas/factor-ir/v1"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == "factor-ir/v1"
    assert schema["$defs"]["marketScope"]["properties"]["market"]["enum"] == [
        "CN_A",
        "CN_COMMODITY_FUTURES",
    ]
    assert schema["$defs"]["marketScope"]["properties"]["frequency"]["enum"] == [
        "1d",
        "1m",
        "5m",
        "15m",
        "30m",
        "60m",
    ]
    futures_rule = schema["$defs"]["marketScope"]["allOf"][0]
    assert futures_rule["then"]["required"] == [
        "exchange_scope",
        "contract_chain_ref",
        "roll_policy_ref",
    ]
    assert schema["$defs"]["call"]["properties"]["op"]["enum"]
    assert schema["$defs"]["input"]["properties"]["data_type"]["not"] == {
        "const": "LabelSeries"
    }
    postprocess = schema["$defs"]["postprocess"]
    assert schema["properties"]["postprocess"] == {"$ref": "#/$defs/postprocess"}
    assert postprocess["additionalProperties"] is False
    assert postprocess["required"] == ["steps"]
    assert postprocess["properties"]["steps"]["minItems"] == 1
    variants = schema["$defs"]["postprocessStep"]["oneOf"]
    assert {variant["properties"]["op"]["const"] for variant in variants} == {
        "winsorize",
        "zscore",
        "cs_rank",
    }
    assert all(variant["additionalProperties"] is False for variant in variants)
