"""Alpha-pool backtest orchestration service.

Extracted from the experiment repository so backtest orchestration — load the
factor context, prepare snapshot/realtime data, run the NautilusTrader
backtest, and store the result — lives in its own module.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from quant_platform.artifacts import ArtifactStore, canonical_bytes
from quant_platform.data_gateway import FrozenSnapshot
from quant_platform.data_gateway.models import PITRow
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.experiments import (
    FactorComputationArtifact,
    FactorObservation,
    FormalSnapshotBinding,
)
from quant_platform.factor_executor import FactorInputRow, FactorTable, execute_factor
from quant_platform.factor_ir import compile_factor_ir
from quant_platform.research.models import (
    AlphaPoolFactorModel,
    ExperimentSpecModel,
)

FactorContext = tuple[ExperimentSpecModel, FactorComputationArtifact]
LoadContext = Callable[[Session, str], FactorContext | None]
SnapshotFn = Callable[[dict[str, Any]], tuple[FrozenSnapshot, FormalSnapshotBinding]]


def _recompute_factor(
    factor_ir_payload: dict[str, Any], eod_rows: tuple[PITRow, ...]
) -> tuple[FactorObservation, ...]:
    """在实时接入的日频数据上按因子 IR 重算因子值（realtime 回测路径）。"""
    compiled = compile_factor_ir(factor_ir_payload)
    by_key: dict[tuple[datetime, str], dict[str, float]] = defaultdict(dict)
    for input_item in factor_ir_payload["inputs"]:
        alias = str(input_item["alias"])
        field = str(input_item["field_ref"])
        for row in eod_rows:
            if row.field == field and row.value is not None:
                by_key[(row.event_time, row.instrument_id)][alias] = float(
                    str(row.value)
                )
    table = FactorTable(
        rows=tuple(
            FactorInputRow(timestamp=ts, instrument_id=instrument, values=values)
            for (ts, instrument), values in sorted(by_key.items())
        )
    )
    result = execute_factor(compiled, table)
    return tuple(
        FactorObservation(item.instrument_id, item.timestamp, item.value)
        for item in result.observations
    )


class BacktestService:
    """Orchestrates alpha-pool factor backtests on NautilusTrader."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        artifact_store: ArtifactStore,
        load_context: LoadContext,
        snapshot_fn: SnapshotFn,
    ) -> None:
        self._sessions = sessions
        self._artifacts = artifact_store
        self._load_context = load_context
        self._snapshot_fn = snapshot_fn

    def run(
        self,
        *,
        factor_ir_hash: str,
        instrument_ids: tuple[str, ...] | None,
        start: date | None,
        end: date | None,
        frequency: str,
        data_source: str,
        lot_size: int,
        initial_cash: Decimal,
        scopes: frozenset[tuple[str, str]],
    ) -> dict[str, Any]:
        """对 Alpha 池因子跑 NautilusTrader 回测（策略台面）。

        ``data_source=snapshot``：预注册时封存的快照 + 封存因子产物。
        ``data_source=realtime``：pit_observations 里的真实接入数据，
        因子值按 IR 在该数据上重算（研究级用途，与封存产物区分披露）。
        """
        from quant_platform.backtest import run_factor_backtest as _run_backtest

        with self._sessions() as session:
            alpha = session.get(AlphaPoolFactorModel, factor_ir_hash)
            if alpha is None or not any(market == alpha.market for _, market in scopes):
                raise ValueError("RESOURCE_NOT_FOUND")
            context = self._load_context(session, factor_ir_hash)
            if context is None:
                raise ValueError("FACTOR_ARTIFACT_NOT_FOUND")
            spec, factor = context

            if data_source == "snapshot":
                snapshot, _binding = self._snapshot_fn(dict(spec.snapshot_payload))
                rows: tuple[PITRow, ...] = snapshot.rows
                observations = factor.observations
                artifact_class = "FORMAL"
            elif data_source == "realtime":
                store = SqlAlchemyPitStore(self._sessions)
                if instrument_ids is None:
                    instrument_ids = tuple(
                        sorted(
                            {
                                item.instrument_id
                                for item in factor.observations
                                if item.value is not None
                            }
                        )
                    )
                field_prefix = "market.eod" if frequency == "1d" else "market.minute"
                start_dt = (
                    datetime.combine(start, datetime.min.time(), tzinfo=UTC)
                    if start
                    else None
                )
                end_dt = (
                    datetime.combine(end, datetime.max.time(), tzinfo=UTC)
                    if end
                    else None
                )
                rows = store.load(
                    instrument_ids=instrument_ids,
                    field_prefix=field_prefix,
                    start=start_dt,
                    end=end_dt,
                )
                if not rows:
                    raise ValueError("MARKET_DATA_NOT_INGESTED")
                # 因子信号用完整历史重算（窗口只截行情 bar，不截信号），
                # 否则窗口首日永远拿不到信号。
                eod_rows = store.load(
                    instrument_ids=instrument_ids,
                    field_prefix="market.eod",
                )
                if not eod_rows:
                    raise ValueError("MARKET_DATA_NOT_INGESTED")
                observations = _recompute_factor(dict(spec.factor_ir_payload), eod_rows)
                artifact_class = (
                    "FORMAL"
                    if all(
                        row.license_tag in {"formal", "licensed-research"}
                        for row in rows
                    )
                    else "EXPLORATORY"
                )
            else:
                raise ValueError("UNKNOWN_DATA_SOURCE")

        result = _run_backtest(
            factor_ir_hash=factor_ir_hash,
            observations=observations,
            snapshot_rows=rows,
            instrument_ids=instrument_ids,
            start=start,
            end=end,
            frequency=frequency,
            initial_cash=initial_cash,
            lot_size=lot_size,
        )
        payload = result.payload()
        payload["data_source"] = data_source
        payload["artifact_class"] = artifact_class
        self._artifacts.put(canonical_bytes(payload), media_type="application/json")
        return payload
