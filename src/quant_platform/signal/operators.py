"""信号算子库（时间周期无关）。

算子只对「喂进来的数值序列」负责，对 bar 颗粒度（1d/15m/…）无感知；
颗粒度由调用方（SignalStrategy）决定。每个算子暴露：
- ``update(high=None, low=None, close=None)`` 推进
- ``value``（或命名字段）当前值
- ``initialized`` 是否已完成预热
"""

from __future__ import annotations

from typing import Any


class Operator:
    """算子基类。"""

    def __init__(self, period: int) -> None:
        self.period = period
        self.initialized = False

    _FIELDS: tuple[str, ...] = ("value",)

    def snapshot(self) -> dict[str, float]:
        """当前值的字段快照（供信号 ctx 暴露，不暴露算子对象本身）。"""
        return {field: getattr(self, field) for field in self._FIELDS}

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


class MacdOperator(Operator):
    """MACD：dif = ema(fast) - ema(slow)；dea = ema(signal) of dif。"""

    _FIELDS = ("dif", "dea")

    def __init__(self, fast: int, slow: int, signal: int = 9) -> None:
        super().__init__(slow)
        self.fast_ema = EmaOperator(fast)
        self.slow_ema = EmaOperator(slow)
        self.dea_ema = EmaOperator(signal)
        self.dif = 0.0
        self.dea = 0.0

    def update(
        self,
        *,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
    ) -> None:
        assert close is not None
        self.fast_ema.update(close=close)
        self.slow_ema.update(close=close)
        self.dif = self.fast_ema.value - self.slow_ema.value
        self.dea_ema.update(close=self.dif)
        self.dea = self.dea_ema.value
        self.initialized = self.slow_ema.initialized


class AtrOperator(Operator):
    """真实波幅（Wilder 平滑）。"""

    def __init__(self, period: int) -> None:
        super().__init__(period)
        self._prev_close: float | None = None
        self._trs: list[float] = []
        self._tr = 0.0
        self.value = 0.0

    def update(
        self,
        *,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
    ) -> None:
        assert high is not None and low is not None and close is not None
        if self._prev_close is None:
            tr = high - low
        else:
            tr = max(
                high - low,
                abs(high - self._prev_close),
                abs(low - self._prev_close),
            )
        self._prev_close = close
        self._trs.append(tr)
        if len(self._trs) < self.period:
            self.value = 0.0
            return
        if len(self._trs) == self.period:
            self._tr = sum(self._trs) / self.period
        else:
            k = 1.0 / self.period
            self._tr = self._tr + k * (tr - self._tr)
        self.value = self._tr
        self.initialized = True


class AdxOperator(Operator):
    """ADX（Wilder 自实现）。

    平台自建而非复用 NautilusTrader 的 ``DirectionalMovement``：后者只暴露
    +DM/-DM，``.value`` 恒为 0（无 ADX）。此处输出 ``adx`` / ``di_plus`` /
    ``di_minus``。
    """

    _FIELDS = ("adx", "di_plus", "di_minus")

    def __init__(self, period: int) -> None:
        super().__init__(period)
        self._prev_high: float | None = None
        self._prev_low: float | None = None
        self._prev_close: float | None = None
        self._trs: list[float] = []
        self._pdms: list[float] = []
        self._ndms: list[float] = []
        self._dxs: list[float] = []
        self._tr = 0.0
        self._pdm_s = 0.0
        self._ndm_s = 0.0
        self._adx_s = 0.0
        self.adx = 0.0
        self.di_plus = 0.0
        self.di_minus = 0.0

    def update(
        self,
        *,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
    ) -> None:
        assert high is not None and low is not None and close is not None
        prev_high = self._prev_high
        prev_low = self._prev_low
        prev_close = self._prev_close
        if prev_high is None or prev_low is None or prev_close is None:
            tr = high - low
            pdm = 0.0
            ndm = 0.0
        else:
            up = high - prev_high
            dn = prev_low - low
            pdm = up if (up > dn and up > 0) else 0.0
            ndm = dn if (dn > up and dn > 0) else 0.0
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
        self._prev_high = high
        self._prev_low = low
        self._prev_close = close
        self._trs.append(tr)
        self._pdms.append(pdm)
        self._ndms.append(ndm)
        if len(self._trs) < self.period:
            return
        if len(self._trs) == self.period:
            self._tr = sum(self._trs) / self.period
            self._pdm_s = sum(self._pdms) / self.period
            self._ndm_s = sum(self._ndms) / self.period
        else:
            k = 1.0 / self.period
            self._tr = self._tr + k * (tr - self._tr)
            self._pdm_s = self._pdm_s + k * (pdm - self._pdm_s)
            self._ndm_s = self._ndm_s + k * (ndm - self._ndm_s)
        self.di_plus = 100.0 * self._pdm_s / self._tr if self._tr > 0 else 0.0
        self.di_minus = 100.0 * self._ndm_s / self._tr if self._tr > 0 else 0.0
        denom = self.di_plus + self.di_minus
        dx = (
            100.0 * abs(self.di_plus - self.di_minus) / denom if denom > 0 else 0.0
        )
        self._dxs.append(dx)
        if len(self._dxs) <= self.period:
            self._adx_s = sum(self._dxs) / len(self._dxs)
        else:
            k = 1.0 / self.period
            self._adx_s = self._adx_s + k * (dx - self._adx_s)
        self.adx = self._adx_s
        self.initialized = True


class BollingerOperator(Operator):
    """布林带：mid/upper/lower（总体标准差，k 默认 2）。"""

    _FIELDS = ("upper", "mid", "lower")

    def __init__(self, period: int, k: float = 2.0) -> None:
        super().__init__(period)
        self.k = k
        self._buf: list[float] = []
        self.mid = 0.0
        self.upper = 0.0
        self.lower = 0.0

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
        if len(self._buf) < self.period:
            return
        mean = sum(self._buf) / self.period
        variance = sum((x - mean) ** 2 for x in self._buf) / self.period
        std = variance ** 0.5
        self.mid = mean
        self.upper = mean + self.k * std
        self.lower = mean - self.k * std
        self.initialized = True


class RsiOperator(Operator):
    """RSI（Wilder 平滑）。"""

    def __init__(self, period: int) -> None:
        super().__init__(period)
        self._prev_close: float | None = None
        self._gains: list[float] = []
        self._losses: list[float] = []
        self._avg_gain = 0.0
        self._avg_loss = 0.0
        self.value = 0.0

    def update(
        self,
        *,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
    ) -> None:
        assert close is not None
        if self._prev_close is None:
            self._prev_close = close
            return
        change = close - self._prev_close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        self._prev_close = close
        self._gains.append(gain)
        self._losses.append(loss)
        if len(self._gains) < self.period:
            return
        if len(self._gains) == self.period:
            self._avg_gain = sum(self._gains) / self.period
            self._avg_loss = sum(self._losses) / self.period
        else:
            k = 1.0 / self.period
            self._avg_gain = self._avg_gain + k * (gain - self._avg_gain)
            self._avg_loss = self._avg_loss + k * (loss - self._avg_loss)
        if self._avg_loss == 0:
            self.value = 100.0
        else:
            rs = self._avg_gain / self._avg_loss
            self.value = 100.0 - 100.0 / (1.0 + rs)
        self.initialized = True


OPERATORS: dict[str, type[Operator]] = {
    "sma": SmaOperator,
    "ema": EmaOperator,
    "atr": AtrOperator,
    "adx": AdxOperator,
    "bollinger": BollingerOperator,
    "rsi": RsiOperator,
}


def build_operator(spec: dict[str, Any]) -> Operator:
    """由声明式指标 spec 构建算子（``{"type": "sma", "period": 3}``）。"""
    type_name = spec.get("type")
    if not isinstance(type_name, str):
        raise ValueError("indicator spec requires a string 'type'")
    if type_name == "macd":
        return MacdOperator(
            fast=spec["fast"], slow=spec["slow"], signal=spec.get("signal", 9)
        )
    if type_name == "bollinger" and "k" in spec:
        return BollingerOperator(period=spec["period"], k=spec["k"])
    cls = OPERATORS.get(type_name)
    if cls is None:
        raise ValueError(f"unknown operator: {type_name}")
    return cls(period=spec["period"])
