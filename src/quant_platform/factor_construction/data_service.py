"""Read-only PIT data service for the factor construction sandbox.

The sandbox never touches the database or the network at large; it fetches data
through this read-only HTTP surface. PIT safety is enforced *here* (server
side): the feature frame only contains rows whose ``available_time`` is at or
before the decision time, and labels are only produced through a separate
endpoint gated by a training grant.

Pure helpers operate on ``PITRow`` sequences so the safety rules are unit
testable without a database.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header

from quant_platform.data_gateway.models import PITRow
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.factor_construction.schemas import LabelFrameCommand
from quant_platform.research.api import (
    ProblemError,
    ResearchPrincipal,
    ResearchPrincipalProvider,
)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def visible_pit_rows(
    rows: Sequence[PITRow], *, decision_time: datetime
) -> tuple[PITRow, ...]:
    """Keep only rows visible at ``decision_time`` (no future leakage)."""
    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("decision_time must be timezone-aware")
    return tuple(
        row
        for row in rows
        if row.available_time <= decision_time and row.ingested_at <= decision_time
    )


def _short_name(field: str) -> str:
    return field.rsplit(".", 1)[-1]


def _number(value: object) -> float | None:
    """Coerce a PIT row value to a finite float, else ``None``."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"unsupported PIT value: {type(value).__name__}")
    result = float(value)
    return result if math.isfinite(result) else None


def pivot_frame(rows: Sequence[PITRow], *, fields: tuple[str, ...]) -> dict[str, Any]:
    """Pivot PIT rows into per-(instrument, event_time) records with short columns."""
    wanted = set(fields)
    grouped: dict[tuple[str, datetime], dict[str, float | str]] = {}
    for row in rows:
        short = _short_name(row.field)
        if short not in wanted:
            continue
        value = _number(row.value)
        if value is None:
            continue
        key = (row.instrument_id, row.event_time)
        record = grouped.setdefault(
            key,
            {"instrument_id": row.instrument_id, "event_time": _iso(row.event_time)},
        )
        record[short] = value
    return {
        "rows": [
            record for _, record in sorted(grouped.items(), key=lambda item: item[0])
        ]
    }


def forward_returns(
    rows: Sequence[PITRow],
    *,
    price_field: str,
    horizon: int,
    return_type: str = "simple",
) -> dict[str, Any]:
    """Compute per-instrument forward returns over ``horizon`` periods.

    ``label[i]`` is the return from event i to event i+horizon, so it is
    inherently future data; it is only ever produced through this function,
    which the router gates behind a training grant.
    """
    if horizon < 1:
        raise ValueError("horizon must be positive")
    by_instrument: dict[str, list[tuple[datetime, float]]] = {}
    for row in rows:
        if row.field != price_field:
            continue
        value = _number(row.value)
        if value is None:
            continue
        by_instrument.setdefault(row.instrument_id, []).append((row.event_time, value))
    out: list[dict[str, Any]] = []
    for instrument_id, series in sorted(by_instrument.items()):
        ordered = sorted(series, key=lambda item: item[0])
        prices = [value for _, value in ordered]
        for index in range(len(prices) - horizon):
            current = prices[index]
            future = prices[index + horizon]
            if current == 0:
                continue
            if return_type == "log":
                label = math.log(future / current) if future > 0 else None
            else:
                label = future / current - 1
            if label is None or not math.isfinite(label):
                continue
            out.append(
                {
                    "instrument_id": instrument_id,
                    "event_time": _iso(ordered[index][0]),
                    "label": label,
                }
            )
    return {"rows": out}


class PitDataService:
    """Server-side read path over the raw PIT store."""

    def __init__(self, store: SqlAlchemyPitStore) -> None:
        self._store = store

    def pit_frame(
        self,
        *,
        instrument_ids: tuple[str, ...],
        fields: tuple[str, ...],
        decision_time: datetime,
        field_prefix: str = "market.eod.",
    ) -> dict[str, Any]:
        rows = self._store.load(
            instrument_ids=instrument_ids, field_prefix=field_prefix
        )
        visible = visible_pit_rows(rows, decision_time=decision_time)
        return pivot_frame(visible, fields=fields)

    def label_frame(
        self,
        *,
        instrument_ids: tuple[str, ...],
        price_field: str,
        horizon: int,
        decision_time: datetime,
        field_prefix: str = "market.eod.",
        return_type: str = "simple",
    ) -> dict[str, Any]:
        del decision_time  # the label is future data by construction
        rows = self._store.load(
            instrument_ids=instrument_ids, field_prefix=field_prefix
        )
        return forward_returns(
            rows,
            price_field=f"{field_prefix}{price_field}",
            horizon=horizon,
            return_type=return_type,
        )


def build_data_service_router(
    service: PitDataService,
    principal_provider: ResearchPrincipalProvider,
) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["Data"])

    def principal(
        authorization: str | None = Header(default=None),
    ) -> ResearchPrincipal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise ProblemError(
                status=401,
                code="AUTHENTICATION_REQUIRED",
                title="Authentication required",
                detail="A Bearer access token is required.",
            )
        resolved = principal_provider(authorization.removeprefix("Bearer ").strip())
        if resolved is None:
            raise ProblemError(
                status=401,
                code="INVALID_ACCESS_TOKEN",
                title="Invalid access token",
                detail="The supplied access token is not recognized.",
            )
        return resolved

    @router.get("/data/pit-frame")
    def pit_frame(
        instrument_ids: str,
        fields: str,
        decision_time: datetime,
        field_prefix: str = "market.eod.",
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        return service.pit_frame(
            instrument_ids=tuple(instrument_ids.split(",")),
            fields=tuple(fields.split(",")),
            decision_time=decision_time,
            field_prefix=field_prefix,
        )

    @router.post("/data/label-frame")
    def label_frame(
        command: LabelFrameCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        if not actor.can(
            {"factor_construction.train"}, project_id="local", market="CN_A"
        ):
            raise _forbidden()
        return service.label_frame(
            instrument_ids=tuple(command.instrument_ids),
            price_field=command.price_field,
            horizon=command.horizon,
            decision_time=command.decision_time,
            field_prefix=command.field_prefix,
            return_type=command.return_type,
        )

    return router


def _forbidden() -> ProblemError:
    return ProblemError(
        status=403,
        code="TRAINING_GRANT_REQUIRED",
        title="Training grant required",
        detail="Labels require the factor_construction.train capability.",
    )
