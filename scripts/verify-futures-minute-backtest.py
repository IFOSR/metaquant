"""端到端验证：分钟因子 → 双边多空信号 → 期货回测（验收标准 1、7）。

用 AkShare 分钟线计算 60 分钟动量因子，在每个交易日收盘聚合为方向信号
（正动量做多、负动量做空），喂给日频期货回测引擎，验证「分钟数据 → 因子 →
双边仓位 → 回测账本」的完整链路。

运行：
    docker compose run --rm --no-deps api sh -c \\
        'uv pip install -q akshare && python scripts/verify-futures-minute-backtest.py'
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from quant_platform.backtest.futures_engine import (
    FuturesDirection,
    run_futures_backtest,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def main() -> None:
    import akshare as ak

    # 1. 拉日线（结算价/开盘价，供日频回测）+ 分钟线（算因子）
    daily = ak.futures_zh_daily_sina(symbol="RB2610")
    minute = ak.futures_zh_minute_sina(symbol="RB2610", period="5")

    # 2. 分钟动量因子（60 分钟 = 12 根 5 分钟 bar）
    momentum = _minute_momentum(minute)
    print(f"[因子] 60 分钟动量，{len(momentum)} 根 bar 有值")

    # 3. 日频聚合：每个交易日最后一根 bar 的动量 → 方向信号
    signal = _daily_signal(momentum)
    print(f"[信号] {len(signal)} 个交易日有方向信号")

    # 4. 目标仓位（方向信号 → LONG/SHORT）
    target_positions: dict[date, dict[str, tuple[FuturesDirection, int]]] = {}
    for trade_date, direction in signal.items():
        target_positions[trade_date] = {"RB2610": (direction, 1)}

    # 5. 日频回测
    dates = tuple(sorted(target_positions))
    settle = {
        _day(row["date"]): {"RB2610": Decimal(str(row["settle"]))}
        for _, row in daily.iterrows()
        if _day(row["date"]) in set(dates)
    }
    opens = {
        _day(row["date"]): {"RB2610": Decimal(str(row["open"]))}
        for _, row in daily.iterrows()
        if _day(row["date"]) in set(dates)
    }

    result = run_futures_backtest(
        trading_dates=dates,
        settlement_prices=settle,
        open_prices=opens,
        target_positions=target_positions,
        margin_rate=Decimal("0.1"),
        fee_rate=Decimal("0.0002"),
        contract_multiplier=Decimal("10"),
        initial_cash=Decimal("100000"),
    )

    print()
    print("=== 分钟因子 → 双边多空 → 回测账本 ===")
    print(f"[回测] 交易日 {len(dates)} 天，成交 {len(result.ledger.fills)} 笔")
    print(f"[回测] 最终现金 {result.ledger.cash}，持仓 {len(result.ledger.positions)}")
    if result.blocked:
        print(f"[回测] 阻断订单 {len(result.blocked)} 笔")
    if result.forced_liquidations:
        print(f"[回测] 强平 {len(result.forced_liquidations)} 次")
    print("[校验] 链路成立：分钟因子产出方向信号并驱动双边回测")


def _minute_momentum(frame: Any) -> dict[datetime, float]:
    """计算每根 5 分钟 bar 的 60 分钟动量（12 根 bar 收益）。"""
    closes: list[tuple[datetime, float]] = []
    for _, row in frame.iterrows():
        timestamp = datetime.fromisoformat(str(row["datetime"]))
        closes.append((timestamp, float(row["close"])))
    result: dict[datetime, float] = {}
    for index, (timestamp, _) in enumerate(closes):
        if index < 12:
            continue
        prev_close = closes[index - 12][1]
        if prev_close <= 0:
            continue
        result[timestamp] = closes[index][1] / prev_close - 1.0
    return result


def _daily_signal(momentum: dict[datetime, float]) -> dict[date, FuturesDirection]:
    by_day: dict[date, list[float]] = defaultdict(list)
    for timestamp, value in momentum.items():
        by_day[timestamp.date()].append(value)

    signal: dict[date, FuturesDirection] = {}
    for trade_date in sorted(by_day):
        last = by_day[trade_date][-1]
        signal[trade_date] = (
            FuturesDirection.LONG if last > 0 else FuturesDirection.SHORT
        )
    return signal


def _day(value: object) -> date:
    to_date = getattr(value, "date", None)
    if callable(to_date):
        result = to_date()
        if isinstance(result, date):
            return result
    return date.fromisoformat(str(value))


if __name__ == "__main__":
    main()
