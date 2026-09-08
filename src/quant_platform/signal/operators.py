"""信号算子库（时间周期无关）。

算子只对「喂进来的数值序列」负责，对 bar 颗粒度（1d/15m/…）无感知；
颗粒度由调用方（SignalStrategy）决定。每个算子暴露：
- ``update(high=None, low=None, close=None)`` 推进
- ``value``（或命名字段）当前值
- ``initialized`` 是否已完成预热
"""

from __future__ import annotations


class Operator:
    """算子基类。"""

    def __init__(self, period: int) -> None:
        self.period = period
        self.initialized = False

    def update(
        self,
        *,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
    ) -> None:
        raise NotImplementedError


class SmaOperator(Operator):
    def __init__(self, period: int) -> None:
        super().__init__(period)
        self._buf: list[float] = []
        self.value = 0.0

    def update(
        self,
        *,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
    ) -> None:
        assert close is not None
        self._buf.append(close)
        if len(self._buf) > self.period:
            self._buf.pop(0)
        self.value = sum(self._buf) / len(self._buf)
        self.initialized = len(self._buf) >= self.period


class EmaOperator(Operator):
    def __init__(self, period: int) -> None:
        super().__init__(period)
        self._n = 0
        self._seed_sum = 0.0
        self.value = 0.0

    def update(
        self,
        *,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
    ) -> None:
        assert close is not None
        self._n += 1
        if self._n < self.period:
            self._seed_sum += close
            return
        if self._n == self.period:
            self._seed_sum += close
            self.value = self._seed_sum / self.period
            self.initialized = True
            return
        k = 2.0 / (self.period + 1)
        self.value = self.value + k * (close - self.value)


OPERATORS: dict[str, type[Operator]] = {
    "sma": SmaOperator,
    "ema": EmaOperator,
}


def build_operator(spec: dict) -> Operator:
    """由声明式指标 spec 构建算子（``{"type": "sma", "period": 3}``）。"""
    type_name = spec.get("type")
    cls = OPERATORS.get(type_name)
    if cls is None:
        raise ValueError(f"unknown operator: {type_name}")
    return cls(period=spec["period"])
