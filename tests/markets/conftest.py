from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_ROOT = ROOT / "docs" / "golden"


def load_golden_cases(name: str) -> list[dict[str, Any]]:
    path = GOLDEN_ROOT / f"{name}.json"
    document = json.loads(path.read_text())
    assert document["schema_version"] == "1.0"
    assert document["market"] in {"CN_A", "CN_COMMODITY_FUTURES"}
    cases = cast(list[dict[str, Any]], document["cases"])
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert case["evidence_status"] == "SYNTHETIC_CONTRACT"
        assert case["formal_eligible"] is False
        assert case["inputs"]
        assert case["expected"]
    return cases


@pytest.fixture(scope="session")
def golden_manifest() -> dict[str, str]:
    document = json.loads((GOLDEN_ROOT / "manifest.json").read_text())
    return cast(dict[str, str], document["sha256"])


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
