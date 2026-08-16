from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from quant_platform.markets.nt.golden import verify_golden_cases

GOLDEN_ROOT = Path(__file__).resolve().parents[3] / "docs" / "golden"


def load_cases(name: str) -> list[dict[str, Any]]:
    document = json.loads((GOLDEN_ROOT / f"{name}.json").read_text())
    return cast(list[dict[str, Any]], document["cases"])


@pytest.mark.parametrize(
    ("market", "name"),
    [
        ("CN_A", "cn_a"),
        ("CN_COMMODITY_FUTURES", "cn_commodity_futures"),
    ],
)
def test_golden_cases_verified_on_nt_adapter(market: str, name: str) -> None:
    cases = load_cases(name)
    passed, verdicts = verify_golden_cases(market, cases)

    failed = [verdict for verdict in verdicts if not verdict.passed]
    assert not failed, "failed golden cases on NautilusTrader adapter: " + ", ".join(
        f"{item.case_id}: {item.detail}" for item in failed
    )
    assert passed == len(cases)
