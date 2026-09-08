"""信号算子库（时间周期无关，NT 指标薄壳）。

原则：NT 已内置且正确的算子直接包壳，统一成 ``update`` / ``snapshot`` /
``initialized`` 接口；NT 没有（adx）或不完整（macd 缺 dea）的自实现。

算子只吃数值序列，对 bar 颗粒度（1d/15m/…）无感知；颗粒度由调用方
（SignalStrategy）决定。加新算子 = 在 ``_NT_INDICATORS`` 里加一行。
"""

from __future__ import annotations

from typing import Any

import nautilus_trader.indicators as nt_ind


class Operator:
    """算子基类：统一接口。"""

    def __init__(self) -> None:
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def update(
        self,
        *,
        open: float | None = None,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
        volume: float | None = None,
    ) -> None:
        raise NotImplementedError

    def snapshot(self) -> dict[str, float]:
        raise NotImplementedError


class NtOperator(Operator):
    """NT 指标薄壳：把 NT 指标包装成统一接口。

    ``inputs``：喂给 NT ``update_raw`` 的 bar 字段序列，如 ``("high","low","close")``。
    ``outputs``：快照字段名 → NT 属性名（如 ``{"mid": "middle"}``）。
    """

    def __init__(
        self,
        indicator: Any,
        inputs: tuple[str, ...],
        outputs: dict[str, str],
    ) -> None:
        super().__init__()
        self._ind = indicator
        self._inputs = inputs
        self._outputs = outputs

    @property
    def initialized(self) -> bool:
        return bool(self._ind.initialized)

    def update(
        self,
        *,
        open: float | None = None,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
        volume: float | None = None,
    ) -> None:
        fields = {
            "open": open,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
        self._ind.update_raw(*(fields[key] for key in self._inputs))

    def snapshot(self) -> dict[str, float]:
        return {
            name: float(getattr(self._ind, attr))
            for name, attr in self._outputs.items()
        }


class MacdOperator(Operator):
    """MACD：dif = NT MACD 线；dea = NT EMA(signal) of dif（NT 的 MACD 无 dea）。"""

    def __init__(self, fast: int, slow: int, signal: int = 9) -> None:
        super().__init__()
        self._macd = nt_ind.MovingAverageConvergenceDivergence(fast, slow)
        self._dea = nt_ind.ExponentialMovingAverage(signal)
        self.dif = 0.0
        self.dea = 0.0

    @property
    def initialized(self) -> bool:
        return bool(self._macd.initialized) and bool(self._dea.initialized)

    def update(
        self,
        *,
        open: float | None = None,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
        volume: float | None = None,
    ) -> None:
        assert close is not None
        self._macd.update_raw(close)
        self.dif = float(self._macd.value)
        self._dea.update_raw(self.dif)
        self.dea = float(self._dea.value)

    def snapshot(self) -> dict[str, float]:
        return {"dif": self.dif, "dea": self.dea}


class AdxOperator(Operator):
    """ADX（Wilder 自实现）。

    NT 的 ``DirectionalMovement`` 只暴露 +DM/-DM，``.value`` 恒为 0（无 ADX），
    故自实现：TR/+DM/-DM Wilder 平滑 → +DI/-DI → DX → ADX 平滑。
    """

    def __init__(self, period: int) -> None:
        super().__init__()
        self.period = period
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
        open: float | None = None,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
        volume: float | None = None,
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
        dx = 100.0 * abs(self.di_plus - self.di_minus) / denom if denom > 0 else 0.0
        self._dxs.append(dx)
        if len(self._dxs) <= self.period:
            self._adx_s = sum(self._dxs) / len(self._dxs)
        else:
            k = 1.0 / self.period
            self._adx_s = self._adx_s + k * (dx - self._adx_s)
        self.adx = self._adx_s
        self._initialized = True

    def snapshot(self) -> dict[str, float]:
        return {"adx": self.adx, "di_plus": self.di_plus, "di_minus": self.di_minus}


# type → (NT 类, update_raw 入参字段, 快照字段→NT 属性, spec 键→构造参数)
_NT_INDICATORS: dict[
    str,
    tuple[Any, tuple[str, ...], dict[str, str], dict[str, str]],
] = {
    "sma": (
        nt_ind.SimpleMovingAverage,
        ("close",),
        {"value": "value"},
        {"period": "period"},
    ),
    "ema": (
        nt_ind.ExponentialMovingAverage,
        ("close",),
        {"value": "value"},
        {"period": "period"},
    ),
    "wma": (
        nt_ind.WeightedMovingAverage,
        ("close",),
        {"value": "value"},
        {"period": "period"},
    ),
    "dema": (
        nt_ind.DoubleExponentialMovingAverage,
        ("close",),
        {"value": "value"},
        {"period": "period"},
    ),
    "hma": (
        nt_ind.HullMovingAverage,
        ("close",),
        {"value": "value"},
        {"period": "period"},
    ),
    "atr": (
        nt_ind.AverageTrueRange,
        ("high", "low", "close"),
        {"value": "value"},
        {"period": "period"},
    ),
    "bollinger": (
        nt_ind.BollingerBands,
        ("high", "low", "close"),
        {"upper": "upper", "mid": "middle", "lower": "lower"},
        {"period": "period", "k": "k"},
    ),
    "rsi": (
        nt_ind.RelativeStrengthIndex,
        ("close",),
        {"value": "value"},
        {"period": "period"},
    ),
    "roc": (nt_ind.RateOfChange, ("close",), {"value": "value"}, {"period": "period"}),
    "cci": (
        nt_ind.CommodityChannelIndex,
        ("high", "low", "close"),
        {"value": "value"},
        {"period": "period"},
    ),
    "stoch": (
        nt_ind.Stochastics,
        ("high", "low", "close"),
        {"k": "value_k", "d": "value_d"},
        {"period_k": "period_k", "period_d": "period_d", "slowing": "slowing"},
    ),
    "aroon": (
        nt_ind.AroonOscillator,
        ("high", "low"),
        {"value": "value", "up": "aroon_up", "down": "aroon_down"},
        {"period": "period"},
    ),
    "cmo": (
        nt_ind.ChandeMomentumOscillator,
        ("close",),
        {"value": "value"},
        {"period": "period"},
    ),
    "linreg": (
        nt_ind.LinearRegression,
        ("close",),
        {"value": "value", "slope": "slope", "intercept": "intercept"},
        {"period": "period"},
    ),
    "keltner": (
        nt_ind.KeltnerChannel,
        ("high", "low", "close"),
        {"upper": "upper", "mid": "middle", "lower": "lower"},
        {"period": "period", "k": "k_multiplier"},
    ),
    "donchian": (
        nt_ind.DonchianChannel,
        ("high", "low"),
        {"upper": "upper", "mid": "middle", "lower": "lower"},
        {"period": "period"},
    ),
    "obv": (
        nt_ind.OnBalanceVolume,
        ("open", "close", "volume"),
        {"value": "value"},
        {"period": "period"},
    ),
}


def build_operator(spec: dict[str, Any]) -> Operator:
    """由声明式指标 spec 构建算子（``{"type": "sma", "period": 20}``）。"""
    type_name = spec.get("type")
    if not isinstance(type_name, str):
        raise ValueError("indicator spec requires a string 'type'")
    if type_name == "macd":
        return MacdOperator(
            fast=spec["fast"], slow=spec["slow"], signal=spec.get("signal", 9)
        )
    if type_name == "adx":
        return AdxOperator(period=spec["period"])
    entry = _NT_INDICATORS.get(type_name)
    if entry is None:
        raise ValueError(f"unknown operator: {type_name}")
    cls, inputs, outputs, param_map = entry
    if type_name in ("bollinger", "keltner") and "k" not in spec:
        spec = {**spec, "k": 2.0}
    kwargs = {arg: spec[key] for key, arg in param_map.items() if key in spec}
    return NtOperator(cls(**kwargs), inputs, outputs)
