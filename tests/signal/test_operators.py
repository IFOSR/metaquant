"""算子库单元测试（sma / ema）。"""

from __future__ import annotations

import pytest

from quant_platform.signal.operators import build_operator


def test_sma_values() -> None:
    op = build_operator({"type": "sma", "period": 3})
    for close in (1.0, 2.0, 3.0, 4.0):
        op.update(close=close)
    assert op.value == (2.0 + 3.0 + 4.0) / 3
    assert op.initialized is True


def test_ema_values() -> None:
    op = build_operator({"type": "ema", "period": 3})
    for close in (1.0, 2.0, 3.0):
        op.update(close=close)
    op.update(close=4.0)
    # seed = 前 3 根均值 = 2.0；第 4 根 k = 2/(3+1) = 0.5
    assert abs(op.value - (2.0 + 0.5 * (4.0 - 2.0))) < 1e-9


def test_unknown_operator_raises() -> None:
    with pytest.raises(ValueError):
        build_operator({"type": "nope", "period": 3})
