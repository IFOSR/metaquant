"""Single-factor validation contracts (G4-001).

A forward-return label is the prediction target used to validate a factor's
predictive power. It is a validation-only input: the Factor IR compiler keeps
rejecting ``LabelSeries``, so a label can never enter factor computation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from quant_platform.experiments import canonical_hash

_VALID_HORIZONS = frozenset({1, 5, 10, 20, 60})
_VALID_MARKETS = frozenset({"CN_A", "CN_COMMODITY_FUTURES"})


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ForwardReturnLabel:
    """A forward-return prediction target for a single market and horizon."""

    label_id: str
    market: str
    horizon: int
    field_ref: str
    return_definition: str = "close_to_close"

    def __post_init__(self) -> None:
        _require_identifier(self.label_id, "label_id")
        if self.market not in _VALID_MARKETS:
            raise ValueError("market must be CN_A or CN_COMMODITY_FUTURES")
        if self.horizon not in _VALID_HORIZONS:
            raise ValueError("horizon must be one of 1/5/10/20/60 trading days")
        _require_identifier(self.field_ref, "field_ref")
        if self.return_definition != "close_to_close":
            raise ValueError("return_definition must be close_to_close")


@dataclass(frozen=True, slots=True)
class LabelObservation:
    """One forward-return observation: the t->t+h return for an instrument."""

    instrument_id: str
    event_time: datetime
    value: float | None

    def __post_init__(self) -> None:
        _require_identifier(self.instrument_id, "instrument_id")
        _require_aware(self.event_time, "event_time")
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("label value must be finite or None")


@dataclass(frozen=True, slots=True)
class LabelSeries:
    """An immutable set of label observations bound to one label contract."""

    label: ForwardReturnLabel
    observations: tuple[LabelObservation, ...]

    def __post_init__(self) -> None:
        keys = [(item.instrument_id, item.event_time) for item in self.observations]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "label observations must be unique per instrument and time"
            )

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "label-series/v1",
            "label": {
                "label_id": self.label.label_id,
                "market": self.label.market,
                "horizon": self.label.horizon,
                "field_ref": self.label.field_ref,
                "return_definition": self.label.return_definition,
            },
            "observations": [
                {
                    "instrument_id": item.instrument_id,
                    "event_time": item.event_time.isoformat(),
                    "value": item.value,
                }
                for item in self.observations
            ],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def assert_label_pit_safe(
    *,
    label_available_time: datetime,
    decision_time: datetime,
) -> None:
    """Require a forward-return label to be unavailable at decision time.

    The label for a factor decided at ``decision_time`` realizes its return only
    later, so its ``available_time`` must be strictly after ``decision_time``.
    This is the structural guard that keeps the label out of factor computation:
    the PIT gateway (``available_time <= decision_time``) would refuse it.
    """
    _require_aware(label_available_time, "label_available_time")
    _require_aware(decision_time, "decision_time")
    if label_available_time <= decision_time:
        raise ValueError("label available_time must be strictly after decision_time")
