"""Tests for the generated-strategy security policy (G19 review P0-1)."""

from __future__ import annotations

import pytest

from quant_platform.strategy_generation.security import scan_strategy_source

_MINIMAL_STRATEGY = """\
from nautilus_trader.trading.strategy import Strategy


class GenStrategy(Strategy):
    pass
"""


def test_allows_nautilus_and_safe_stdlib() -> None:
    source = (
        "from decimal import Decimal\n"
        "import math\n"
        "from nautilus_trader.indicators import ExponentialMovingAverage\n"
        + _MINIMAL_STRATEGY
    )
    assert scan_strategy_source(source) == ()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import os\n" + _MINIMAL_STRATEGY, "forbidden import: os"),
        ("import subprocess\n" + _MINIMAL_STRATEGY, "forbidden import: subprocess"),
        (
            "from pathlib import Path\n" + _MINIMAL_STRATEGY,
            "forbidden import: pathlib",
        ),
        ("x = __import__('os')\n", "forbidden call: __import__()"),
        ("x = eval('1+1')\n" + _MINIMAL_STRATEGY, "forbidden call: eval()"),
        ("open('/etc/passwd')\n" + _MINIMAL_STRATEGY, "forbidden call: open()"),
        ("y = object.__class__\n" + _MINIMAL_STRATEGY, "forbidden attribute access"),
        ("z = __builtins__\n" + _MINIMAL_STRATEGY, "forbidden name reference"),
    ],
)
def test_blocks_violations(source: str, expected: str) -> None:
    violations = scan_strategy_source(source)
    assert violations
    assert any(expected in violation for violation in violations)


def test_syntax_error_is_reported_not_raised() -> None:
    violations = scan_strategy_source("def broken(:\n")
    assert len(violations) == 1
    assert "syntax error" in violations[0]
