"""Predictive-power validation for model factors (factor construction, phase 3).

Model factors are validated against a forward-return label exactly like declared
factors: cross-sectional IC / Rank IC / ICIR / coverage. This module computes the
same core statistics directly from factor observations + label rows, without the
``ForwardReturnLabel`` horizon whitelist (model labels may use any horizon, e.g.
the StableAlpha 21-day vwap label).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime

from quant_platform.experiments import canonical_hash


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"unsupported numeric value: {type(value).__name__}")
    result = float(value)
    return result if math.isfinite(result) else None


def _canonical_time(value: object) -> str:
    """Normalize ISO timestamps ('Z' or '+00:00') to a canonical UTC string."""
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return (
        datetime.fromisoformat(text).astimezone(UTC).isoformat().replace("+00:00", "Z")
    )


def _spearman(xs: list[float], ys: list[float]) -> float:
    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        result = [0.0] * len(values)
        for position, index in enumerate(order):
            result[index] = float(position)
        return result

    if len(xs) < 2:
        return 0.0
    return _pearson(ranks(xs), ranks(ys))


@dataclass(frozen=True, slots=True)
class ModelFactorValidationReport:
    observation_count: int
    finite_count: int
    coverage_ratio: float
    cross_sections: int
    pearson_ic: float | None
    rank_ic: float | None
    icir: float | None
    output_hash: str

    def payload(self) -> dict[str, object]:
        return {
            "observation_count": self.observation_count,
            "finite_count": self.finite_count,
            "coverage_ratio": self.coverage_ratio,
            "cross_sections": self.cross_sections,
            "pearson_ic": self.pearson_ic,
            "rank_ic": self.rank_ic,
            "icir": self.icir,
            "output_hash": self.output_hash,
        }


def validate_model_factor(
    factor_rows: list[dict[str, object]],
    label_rows: list[dict[str, object]],
) -> ModelFactorValidationReport:
    """Compute IC / Rank IC / ICIR from factor and label rows.

    ``factor_rows`` / ``label_rows`` are ``[{instrument_id, event_time, value}]``
    where event_time is an ISO string; factor values may be ``None``.
    """
    factor_by_key: dict[tuple[str, str], float] = {}
    for row in factor_rows:
        value = _number(row.get("value"))
        if value is None:
            continue
        factor_by_key[
            (str(row["instrument_id"]), _canonical_time(row["event_time"]))
        ] = value

    label_by_time: dict[str, list[tuple[str, float]]] = {}
    for row in label_rows:
        value = _number(row.get("value"))
        if value is None:
            continue
        label_by_time.setdefault(_canonical_time(row["event_time"]), []).append(
            (str(row["instrument_id"]), value)
        )

    pearson_ics: list[float] = []
    rank_ics: list[float] = []
    for event_time in sorted(label_by_time):
        xs: list[float] = []
        ys: list[float] = []
        for instrument_id, label_value in label_by_time[event_time]:
            factor_value = factor_by_key.get((instrument_id, event_time))
            if factor_value is not None:
                xs.append(factor_value)
                ys.append(label_value)
        if len(xs) >= 2:
            pearson_ics.append(_pearson(xs, ys))
            rank_ics.append(_spearman(xs, ys))

    total = len(factor_rows)
    finite = len(factor_by_key)
    pearson_ic: float | None = statistics.fmean(pearson_ics) if pearson_ics else None
    rank_ic = statistics.fmean(rank_ics) if rank_ics else None
    if pearson_ics and pearson_ic is not None:
        std = statistics.pstdev(pearson_ics)
        icir: float | None = pearson_ic / std if std else None
    else:
        icir = None

    report = ModelFactorValidationReport(
        observation_count=total,
        finite_count=finite,
        coverage_ratio=finite / total if total else 0.0,
        cross_sections=len(pearson_ics),
        pearson_ic=pearson_ic,
        rank_ic=rank_ic,
        icir=icir,
        output_hash="",
    )
    object.__setattr__(
        report,
        "output_hash",
        canonical_hash(
            {
                "observation_count": report.observation_count,
                "finite_count": report.finite_count,
                "coverage_ratio": report.coverage_ratio,
                "cross_sections": report.cross_sections,
                "pearson_ic": report.pearson_ic,
                "rank_ic": report.rank_ic,
                "icir": report.icir,
            }
        ),
    )
    return report


def label_rows_from_observations(
    observations: list[tuple[str, datetime, float | None]],
) -> list[dict[str, object]]:
    """Adapt (instrument_id, event_time, value) tuples to label rows."""
    return [
        {
            "instrument_id": instrument_id,
            "event_time": event_time.isoformat(),
            "value": value,
        }
        for instrument_id, event_time, value in observations
    ]
