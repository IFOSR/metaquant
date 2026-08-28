"""Drift report: paper fills/equity vs a fresh backtest over the same window.

The comparison is a *tool* for validating execution assumptions (slippage,
fill rate, cost drag) — not the definition of paper trading. It runs the
frozen strategy through the deterministic backtest runner for the account's
live window and diffs the daily equity curves.
"""

from __future__ import annotations

from typing import Any


def compute_drift(
    *,
    backtest_payload: dict[str, Any],
    paper_equity: list[dict[str, Any]],
) -> dict[str, Any]:
    """Diff daily equity curves on their common dates.

    ``backtest_payload`` is a ``StrategyBacktestResult.payload()`` dict;
    ``paper_equity`` rows come from ``repository.list_equity``.
    """
    backtest_curve = {
        str(point["date"]): float(point["equity"])
        for point in backtest_payload.get("equity_curve", [])
    }
    paper_curve = {str(row["trade_date"]): float(row["equity"]) for row in paper_equity}
    common = sorted(set(backtest_curve) & set(paper_curve))
    points: list[dict[str, Any]] = [
        {
            "date": day,
            "backtest_equity": backtest_curve[day],
            "paper_equity": paper_curve[day],
            "diff": round(paper_curve[day] - backtest_curve[day], 4),
        }
        for day in common
    ]
    max_abs = max((abs(point["diff"]) for point in points), default=0.0)
    return {
        "schema_version": "paper-drift/v1",
        "points": points,
        "common_days": len(common),
        "paper_days": len(paper_curve),
        "backtest_days": len(backtest_curve),
        "max_abs_diff": round(max_abs, 4),
        "cost_basis": backtest_payload.get("cost_basis"),
        "backtest_hash": backtest_payload.get("backtest_hash"),
    }
