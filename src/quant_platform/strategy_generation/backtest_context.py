"""Format verified strategy backtests for Agent conversation context."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _number(value: object, *, percent: bool = False) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return "—"
    if percent:
        return f"{value * 100:.2f}%"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _text(value: object, default: str = "—") -> str:
    return str(value).strip() if value is not None and str(value).strip() else default


def _action(trade: Mapping[str, Any]) -> str:
    action = _text(trade.get("action"), "")
    if action != "":
        return action
    return "买入" if str(trade.get("side", "")).upper() == "BUY" else "卖出"


def _position_direction(position: Mapping[str, Any]) -> str:
    return "开多" if str(position.get("entry", "")).upper() == "BUY" else "开空"


def _sample_curve(
    curve: Sequence[object],
    max_points: int,
) -> list[Mapping[str, Any]]:
    valid = [point for point in curve if isinstance(point, Mapping)]
    if max_points <= 0:
        return []
    if len(valid) <= max_points:
        return [point for point in valid]
    indexes = {
        round(index * (len(valid) - 1) / (max_points - 1))
        for index in range(max_points)
    }
    return [valid[index] for index in sorted(indexes)]


def format_backtest_context(
    payload: Mapping[str, Any],
    *,
    backtest_hash: str,
    market: str,
    max_equity_points: int = 80,
) -> str:
    """Return a bounded, deterministic text representation of a backtest."""
    metrics = payload.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    venue = payload.get("venue_spec")
    venue = venue if isinstance(venue, Mapping) else {}
    instruments = payload.get("instrument_ids")
    instruments = instruments if isinstance(instruments, Sequence) else []

    lines = [
        "[导入的历史回测结果]",
        "来源：当前策略草稿的一次已记录回测",
        f"结果指纹：{backtest_hash}",
        f"市场：{market}",
        f"标的：{', '.join(_text(item) for item in instruments) or '—'}",
        f"周期：{_text(payload.get('frequency'))}",
        f"回测区间：{_text(payload.get('start'))} 至 {_text(payload.get('end'))}",
        f"初始资金：{_number(payload.get('initial_cash'))}",
        f"费用口径：{_text(venue.get('cost_basis'))}",
        f"费用模型：{_text(venue.get('fee_model'))}",
        "绩效指标：",
        f"- 总收益：{_number(metrics.get('total_return'), percent=True)}",
        f"- Sharpe：{_number(metrics.get('sharpe'))}",
        f"- 最大回撤：{_number(metrics.get('max_drawdown'), percent=True)}",
        f"- 成交数：{_text(metrics.get('trade_count'))}",
        f"- 总手续费：{_number(payload.get('total_fees'))}",
        "持仓回合：",
    ]

    positions = payload.get("positions")
    if isinstance(positions, Sequence) and positions:
        for position in positions:
            if not isinstance(position, Mapping):
                continue
            lines.append(
                "- "
                + " · ".join(
                    (
                        _position_direction(position),
                        _text(position.get("instrument_id")),
                        f"数量 {_text(position.get('peak_qty'))}",
                        f"开仓 {_text(position.get('opened_at'))} @ "
                        f"{_text(position.get('avg_px_open'))}",
                        f"平仓 {_text(position.get('closed_at'))} @ "
                        f"{_text(position.get('avg_px_close'))}",
                        f"已实现盈亏 {_number(position.get('realized_pnl'))}",
                    )
                )
            )
    else:
        lines.append("- 无")

    lines.append("逐笔成交：")
    trades = payload.get("trades")
    if isinstance(trades, Sequence) and trades:
        for trade in trades:
            if not isinstance(trade, Mapping):
                continue
            lines.append(
                "- "
                + " · ".join(
                    (
                        _text(trade.get("time")),
                        _action(trade),
                        _text(trade.get("instrument_id")),
                        f"{_text(trade.get('quantity'))} @ "
                        f"{_text(trade.get('price'))}",
                        f"手续费 {_number(trade.get('commission'))}",
                    )
                )
            )
    else:
        lines.append("- 无")

    lines.append("净值曲线采样：")
    curve = payload.get("equity_curve")
    sampled = _sample_curve(
        curve if isinstance(curve, Sequence) and not isinstance(curve, str) else [],
        max_equity_points,
    )
    if sampled:
        for point in sampled:
            lines.append(
                f"- {_text(point.get('date'))} · 净值 {_number(point.get('equity'))}"
            )
    else:
        lines.append("- 无")
    lines.append("[回测结果结束]")
    return "\n".join(lines)
