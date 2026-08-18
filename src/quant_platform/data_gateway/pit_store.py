"""PIT 行情数据的 PostgreSQL 落库与读取（G18 数据接入）。

表结构由 ``alembic/versions/20260814_0011_create_market_data_tables.py``
建立（``pit_observations`` / ``market_data_sources``），本模块提供唯一的
写入与查询入口：

- ``persist``：按 ``(field, instrument_id, event_time, revision_id)`` 去重写入，
  并登记数据源到 ``market_data_sources``
- ``load``：按标的 + 字段 + 时间窗读取；同一 key 多 revision 时取
  ``ingested_at`` 最新者（与 loader 的 revision 语义一致）
- ``coverage``：汇总每个标的已入库的时间区间与行数，供 UI 界定回测周期
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from quant_platform.data_gateway.loader import RawPITRow, validate_pit_rows
from quant_platform.data_gateway.models import PITRow
from quant_platform.research.models import (
    MarketDataSourceModel,
    PitObservationModel,
)

_SOURCE_REGISTRY: dict[str, dict[str, object]] = {
    "ifind-cn": {
        "name": "同花顺 iFinD",
        "license": "licensed-research",
        "revision_capable": True,
        "pit_capable": True,
    },
    "akshare-cn": {
        "name": "AkShare (Sina)",
        "license": "exploratory",
        "revision_capable": False,
        "pit_capable": False,
    },
}


@dataclass(frozen=True, slots=True)
class CoverageEntry:
    instrument_id: str
    field_prefix: str
    source_id: str
    license_tag: str
    row_count: int
    first_event: str
    last_event: str

    @property
    def artifact_class(self) -> str:
        return (
            "FORMAL"
            if self.license_tag in {"licensed-research", "formal"}
            else "EXPLORATORY"
        )

    def payload(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "field_prefix": self.field_prefix,
            "source_id": self.source_id,
            "license_tag": self.license_tag,
            "artifact_class": self.artifact_class,
            "row_count": self.row_count,
            "first_event": self.first_event,
            "last_event": self.last_event,
        }


def _aware(value: datetime) -> datetime:
    """统一补回 UTC（SQLite 不保留时区；PostgreSQL timestamptz 读出即带时区）。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


_FORMAL_LICENSE_TAGS = frozenset({"formal", "licensed-research"})


def _preferred(
    candidate: PitObservationModel, current: PitObservationModel
) -> bool:
    """同一 key 的行选取：FORMAL 源优先，其次取 ingested_at 最新者。"""
    candidate_formal = candidate.license_tag in _FORMAL_LICENSE_TAGS
    current_formal = current.license_tag in _FORMAL_LICENSE_TAGS
    if candidate_formal != current_formal:
        return candidate_formal
    return _aware(candidate.ingested_at) > _aware(current.ingested_at)


class SqlAlchemyPitStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def persist(self, rows: tuple[RawPITRow, ...] | list[RawPITRow]) -> int:
        """写入 PIT 行（先过 loader 校验），返回实际新增行数。"""
        validate_pit_rows(rows)
        if not rows:
            return 0
        with self._sessions.begin() as session:
            existing = {
                (field, instrument, _aware(event_time), revision)
                for field, instrument, event_time, revision in session.execute(
                    select(
                        PitObservationModel.field,
                        PitObservationModel.instrument_id,
                        PitObservationModel.event_time,
                        PitObservationModel.revision_id,
                    ).where(
                        PitObservationModel.instrument_id.in_(
                            {row.instrument_id for row in rows}
                        )
                    )
                ).all()
            }
            inserted = 0
            for row in rows:
                key = (
                    row.field,
                    row.instrument_id,
                    _aware(row.event_time),
                    row.revision_id,
                )
                if key in existing:
                    continue
                session.add(
                    PitObservationModel(
                        id=f"pit_{uuid4().hex}",
                        source_id=row.source_id,
                        dataset_id=row.dataset_id,
                        field=row.field,
                        instrument_id=row.instrument_id,
                        event_time=row.event_time,
                        available_time=row.available_time,
                        ingested_at=row.ingested_at,
                        revision_id=row.revision_id,
                        license_tag=row.license_tag,
                        value_type=row.value_type,
                        value=row.value,
                    )
                )
                existing.add(key)
                inserted += 1
            self._register_sources(session, {row.source_id for row in rows})
        return inserted

    def load(
        self,
        *,
        instrument_ids: tuple[str, ...],
        field_prefix: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[PITRow, ...]:
        """读取 PIT 行；同一 (field, instrument, event_time) 取最新 revision。"""
        with self._sessions() as session:
            query = select(PitObservationModel).where(
                PitObservationModel.instrument_id.in_(instrument_ids),
                PitObservationModel.field.startswith(field_prefix),
            )
            if start is not None:
                query = query.where(PitObservationModel.event_time >= start)
            if end is not None:
                query = query.where(PitObservationModel.event_time <= end)
            models = session.scalars(query).all()

        latest: dict[tuple[str, str, datetime], PitObservationModel] = {}
        for model in models:
            key = (model.field, model.instrument_id, model.event_time)
            current = latest.get(key)
            if current is None or _preferred(model, current):
                latest[key] = model

        return tuple(
            PITRow(
                dataset_id=model.dataset_id,
                field=model.field,
                instrument_id=model.instrument_id,
                event_time=_aware(model.event_time),
                available_time=_aware(model.available_time),
                ingested_at=_aware(model.ingested_at),
                revision_id=model.revision_id,
                source_id=model.source_id,
                license_tag=model.license_tag,
                value=float(model.value),
            )
            for model in sorted(
                latest.values(),
                key=lambda model: (model.instrument_id, model.event_time, model.field),
            )
        )

    def coverage(
        self, *, instrument_ids: tuple[str, ...]
    ) -> tuple[CoverageEntry, ...]:
        """每个标的 × 字段前缀（market.eod / market.minute）的入库区间。"""
        with self._sessions() as session:
            models = session.scalars(
                select(PitObservationModel).where(
                    PitObservationModel.instrument_id.in_(instrument_ids)
                )
            ).all()
        grouped: dict[tuple[str, str, str, str], list[datetime]] = {}
        for model in models:
            prefix = model.field.rsplit(".", 1)[0]
            key = (model.instrument_id, prefix, model.source_id, model.license_tag)
            grouped.setdefault(key, []).append(model.event_time)
        return tuple(
            CoverageEntry(
                instrument_id=instrument,
                field_prefix=prefix,
                source_id=source,
                license_tag=license_tag,
                row_count=len(times),
                first_event=min(times).isoformat(),
                last_event=max(times).isoformat(),
            )
            for (instrument, prefix, source, license_tag), times in sorted(
                grouped.items()
            )
        )

    def _register_sources(self, session: Session, source_ids: set[str]) -> None:
        for source_id in sorted(source_ids):
            if session.get(MarketDataSourceModel, source_id) is not None:
                continue
            info = _SOURCE_REGISTRY.get(
                source_id,
                {
                    "name": source_id,
                    "license": "unknown",
                    "revision_capable": False,
                    "pit_capable": False,
                },
            )
            session.add(
                MarketDataSourceModel(
                    source_id=source_id,
                    name=str(info["name"]),
                    license=str(info["license"]),
                    coverage_scope="CN 期货/股票 日频+分钟",
                    revision_capable=bool(info["revision_capable"]),
                    pit_capable=bool(info["pit_capable"]),
                    cross_validation_status="REGISTERED",
                    registered_at=datetime.now(UTC),
                )
            )
