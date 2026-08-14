"""Performance attribution report (G16-007, FR-507).

Aggregates a backtest ledger into the attribution metrics required for a
promotion report: gross versus net return, cost breakdown, factor exposure,
capacity utilization, unfillable share, roll return, and factor ablation.
The report is content-addressed so it can be referenced as evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quant_platform.experiments import canonical_hash


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    commission: Decimal
    stamp_duty: Decimal
    slippage: Decimal
    impact: Decimal

    def total(self) -> Decimal:
        return self.commission + self.stamp_duty + self.slippage + self.impact

    def payload(self) -> dict[str, object]:
        return {
            "commission": str(self.commission),
            "stamp_duty": str(self.stamp_duty),
            "slippage": str(self.slippage),
            "impact": str(self.impact),
        }


@dataclass(frozen=True, slots=True)
class AttributionReport:
    gross_return: Decimal
    net_return: Decimal
    cost_breakdown: CostBreakdown
    risk_exposures: tuple[tuple[str, float], ...]
    capacity_utilization: float
    unfillable_count: int
    unfillable_ratio: float
    roll_return: Decimal | None
    factor_ablation: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not 0.0 <= self.capacity_utilization <= 1.0:
            raise ValueError("capacity_utilization must be within [0, 1]")
        if not 0.0 <= self.unfillable_ratio <= 1.0:
            raise ValueError("unfillable_ratio must be within [0, 1]")
        if self.unfillable_count < 0:
            raise ValueError("unfillable_count must be non-negative")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "attribution-report/v1",
            "gross_return": str(self.gross_return),
            "net_return": str(self.net_return),
            "cost_breakdown": self.cost_breakdown.payload(),
            "risk_exposures": [list(item) for item in self.risk_exposures],
            "capacity_utilization": self.capacity_utilization,
            "unfillable_count": self.unfillable_count,
            "unfillable_ratio": self.unfillable_ratio,
            "roll_return": (
                str(self.roll_return) if self.roll_return is not None else None
            ),
            "factor_ablation": [list(item) for item in self.factor_ablation],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def build_attribution_report(
    *,
    start_nav: Decimal,
    gross_pnl: Decimal,
    cost_breakdown: CostBreakdown,
    risk_exposures: tuple[tuple[str, float], ...],
    capacity_utilization: float,
    unfillable_count: int,
    total_orders: int,
    roll_return: Decimal | None = None,
    factor_ablation: tuple[tuple[str, float], ...] = (),
) -> AttributionReport:
    """Build an attribution report from backtest aggregates.

    ``gross_return`` is the P&L before costs over starting NAV; ``net_return``
    subtracts the cost breakdown. The unfillable ratio is the share of orders
    that could not be filled.
    """
    if start_nav <= 0:
        raise ValueError("start_nav must be positive")
    if total_orders < 0:
        raise ValueError("total_orders must be non-negative")
    if unfillable_count < 0 or unfillable_count > total_orders:
        raise ValueError("unfillable_count must be within [0, total_orders]")

    gross_return = gross_pnl / start_nav
    net_return = (gross_pnl - cost_breakdown.total()) / start_nav
    return AttributionReport(
        gross_return=gross_return,
        net_return=net_return,
        cost_breakdown=cost_breakdown,
        risk_exposures=risk_exposures,
        capacity_utilization=capacity_utilization,
        unfillable_count=unfillable_count,
        unfillable_ratio=(
            unfillable_count / total_orders if total_orders else 0.0
        ),
        roll_return=roll_return,
        factor_ablation=factor_ablation,
    )
