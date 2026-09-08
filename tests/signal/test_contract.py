"""信号契约测试：声明式指标 + compute_signal 纯函数 + 注入式隔离。"""

from __future__ import annotations

import pytest

from quant_platform.signal.contract import Signal, load_signal_spec

GOOD = """
INDICATORS = [{"key": "macd", "fast": 3, "slow": 5}]
def compute_signal(ctx):
    return Signal(target_qty=1)
"""


def test_load_valid_spec() -> None:
    spec = load_signal_spec(GOOD)
    assert [item["key"] for item in spec.indicators] == ["macd"]
    assert spec.compute_signal(None).target_qty == 1


def test_missing_compute_signal_rejected() -> None:
    with pytest.raises(ValueError):
        load_signal_spec("INDICATORS = []")


def test_import_rejected() -> None:
    with pytest.raises(ValueError):
        load_signal_spec("import os\nINDICATORS = []\ndef compute_signal(ctx):\n    return Signal()")


def test_dangerous_call_rejected() -> None:
    with pytest.raises(ValueError):
        load_signal_spec(
            "INDICATORS = []\n"
            "def compute_signal(ctx):\n"
            '    open("/etc/passwd")\n'
            "    return Signal(target_qty=0)"
        )


def test_dunder_escape_rejected() -> None:
    with pytest.raises(ValueError):
        load_signal_spec(
            "INDICATORS = []\n"
            "def compute_signal(ctx):\n"
            "    return (1).__class__\n"
        )
