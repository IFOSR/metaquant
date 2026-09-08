"""算子库单元测试：统一接口 + NT 薄壳 + 自实现 adx/macd。"""

from __future__ import annotations

import math

import pytest

from quant_platform.signal.operators import (
    AdxOperator,
    MacdOperator,
    build_operator,
)

# type -> (spec, 喂值所需字段集合, 快照字段集合)
_NT_TYPES = {
    "sma": ({"type": "sma", "period": 3}, {"close"}, {"value"}),
    "ema": ({"type": "ema", "period": 3}, {"close"}, {"value"}),
    "wma": ({"type": "wma", "period": 3}, {"close"}, {"value"}),
    "dema": ({"type": "dema", "period": 3}, {"close"}, {"value"}),
    "hma": ({"type": "hma", "period": 4}, {"close"}, {"value"}),
    "atr": ({"type": "atr", "period": 3}, {"high", "low", "close"}, {"value"}),
    "bollinger": ({"type": "bollinger", "period": 3}, {"high", "low", "close"}, {"upper", "mid", "lower"}),
    "rsi": ({"type": "rsi", "period": 3}, {"close"}, {"value"}),
    "roc": ({"type": "roc", "period": 3}, {"close"}, {"value"}),
    "cci": ({"type": "cci", "period": 3}, {"high", "low", "close"}, {"value"}),
    "stoch": ({"type": "stoch", "period_k": 5, "period_d": 3}, {"high", "low", "close"}, {"k", "d"}),
    "aroon": ({"type": "aroon", "period": 3}, {"high", "low"}, {"value", "up", "down"}),
    "cmo": ({"type": "cmo", "period": 3}, {"close"}, {"value"}),
    "linreg": ({"type": "linreg", "period": 3}, {"close"}, {"value", "slope", "intercept"}),
    "keltner": ({"type": "keltner", "period": 3}, {"high", "low", "close"}, {"upper", "mid", "lower"}),
    "donchian": ({"type": "donchian", "period": 3}, {"high", "low"}, {"upper", "mid", "lower"}),
    "obv": ({"type": "obv", "period": 3}, {"open", "close", "volume"}, {"value"}),
}


def _feed(op, fields: set[str], n: int = 40) -> None:
    close = 10.0
    for _ in range(n):
        close += 0.1
        op.update(
            open=close - 0.05 if "open" in fields else None,
            high=close + 0.1 if "high" in fields else None,
            low=close - 0.1 if "low" in fields else None,
            close=close,
            volume=1000.0 if "volume" in fields else None,
        )


@pytest.mark.parametrize("type_name", sorted(_NT_TYPES))
def test_nt_operator_initializes_and_snapshots(type_name: str) -> None:
    spec, fields, snapshot_fields = _NT_TYPES[type_name]
    op = build_operator(spec)
    _feed(op, fields)
    assert op.initialized is True
    snap = op.snapshot()
    assert set(snap) == snapshot_fields
    for value in snap.values():
        assert math.isfinite(value)


def test_unknown_operator_raises() -> None:
    with pytest.raises(ValueError):
        build_operator({"type": "nope", "period": 3})


def test_adx_not_zero_and_direction_matches() -> None:
    """单边上涨序列：adx 非 0（不可恒 0），+DI > -DI。"""
    op = build_operator({"type": "adx", "period": 14})
    close = 100.0
    for _ in range(60):
        op.update(high=close + 1.0, low=close - 0.2, close=close)
        close += 0.5
    assert op.initialized
    assert op.adx > 0
    assert op.di_plus > op.di_minus


def test_macd_exposes_dif_and_dea() -> None:
    op = build_operator({"type": "macd", "fast": 3, "slow": 5})
    _feed(op, {"close"})
    assert op.initialized
    assert set(op.snapshot()) == {"dif", "dea"}
    assert math.isfinite(op.dif) and math.isfinite(op.dea)
