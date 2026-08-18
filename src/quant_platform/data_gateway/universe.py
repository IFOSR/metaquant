"""Universe 解析：把抽象 universe_ref 解析成具体合约列表。

这是"研究任务驱动的数据管线"的第一环。``universe_ref`` 在此之前是死字符串，
数据采集靠手工脚本里的硬编码合约清单。现在由 :class:`UniverseResolver` 把它
解析成可审计的具体合约代码，解析结果记录数据源与时间，防止"挑标的池"式的
数据窥探。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class UniverseSpec:
    universe_ref: str
    instruments: tuple[str, ...]
    resolved_at: datetime
    source: str


_EXCHANGE_SUFFIX = {
    "shfe": "SHF",
    "dce": "DCE",
    "czce": "CZCE",
    "ine": "INE",
    "gfex": "GFEX",
    "cffex": "CFFEX",
}

# 金融期货不属于商品期货研究范围，默认排除
_FINANCIAL_EXCHANGES = frozenset({"CFFEX"})


def normalize_czce_code(code: str) -> str:
    """郑商所合约代码 4 位月份 → 3 位（2701 → 701）。"""
    match = re.match(r"^([A-Za-z]{1,2})(\d{4})$", code)
    if match:
        prefix, ym = match.group(1), match.group(2)
        return f"{prefix}{ym[1:]}"
    return code


class UniverseResolver:
    """把 universe_ref 解析成具体合约代码列表。"""

    def __init__(self, *, top_n: int = 30) -> None:
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        self.top_n = top_n

    def resolve(
        self,
        universe_ref: str,
        *,
        explicit: tuple[str, ...] = (),
        exchange_scope: tuple[str, ...] = (),
    ) -> UniverseSpec:
        if universe_ref == "futures:explicit":
            if not explicit:
                raise ValueError("futures:explicit requires an explicit contract list")
            return UniverseSpec(
                universe_ref=universe_ref,
                instruments=tuple(explicit),
                resolved_at=datetime.now(UTC),
                source="explicit",
            )
        if universe_ref == "futures:liquid-initial":
            instruments = self._resolve_liquid_futures(exchange_scope)
            if not instruments:
                raise ValueError("no liquid futures resolved for universe")
            return UniverseSpec(
                universe_ref=universe_ref,
                instruments=instruments,
                resolved_at=datetime.now(UTC),
                source="akshare",
            )
        raise ValueError(f"unknown universe_ref: {universe_ref}")

    def _resolve_liquid_futures(
        self, exchange_scope: tuple[str, ...]
    ) -> tuple[str, ...]:
        import akshare as ak  # 可选依赖，懒加载

        main = ak.futures_display_main_sina()
        candidates: list[tuple[str, float]] = []
        for _, row in main.iterrows():
            name = str(row["name"]).replace("连续", "").strip()
            exch = str(row["exchange"]).lower()
            suffix = _EXCHANGE_SUFFIX.get(exch, exch.upper())
            if suffix in _FINANCIAL_EXCHANGES:
                continue
            if exchange_scope and suffix not in exchange_scope:
                continue
            try:
                frame = ak.futures_zh_realtime(symbol=name)
            except Exception:
                continue
            if frame is None or frame.empty:
                continue
            frame = frame[frame["volume"].astype(float) > 0]
            frame = frame[~frame["symbol"].str.endswith("0")]
            if frame.empty:
                continue
            top = frame.sort_values("volume", ascending=False).iloc[0]
            code = str(top["symbol"])
            if suffix == "CZCE":
                code = normalize_czce_code(code)
            candidates.append((f"{code}.{suffix}", float(top["volume"])))

        candidates.sort(key=lambda item: -item[1])
        return tuple(code for code, _ in candidates[: self.top_n])
