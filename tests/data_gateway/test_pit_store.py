"""SqlAlchemyPitStore 单元测试（sqlite，无需外部服务）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from quant_platform.data_gateway.loader import RawPITRow
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.research.models import Base

START = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def _row(
    instrument: str = "RB2610.SHF",
    field: str = "market.eod.close",
    day: int = 0,
    value: str = "3000.0",
    revision: str = "rev-1",
    ingested: datetime | None = None,
) -> RawPITRow:
    ts = START + timedelta(days=day)
    return RawPITRow(
        source_id="ifind-cn",
        dataset_id="market-eod",
        field=field,
        instrument_id=instrument,
        event_time=ts,
        available_time=ts.replace(minute=30),
        ingested_at=ingested or ts.replace(minute=45),
        revision_id=revision,
        license_tag="licensed-research",
        value_type="decimal",
        value=value,
    )


def _store() -> SqlAlchemyPitStore:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return SqlAlchemyPitStore(sessionmaker(engine, expire_on_commit=False))


class TestPersist:
    def test_persist_deduplicates_identical_rows(self) -> None:
        store = _store()
        first = store.persist([_row(), _row(day=1)])
        assert first == 2
        # 同 key 同 revision 重复写入 → 幂等
        assert store.persist([_row(), _row(day=1)]) == 0

    def test_persist_registers_data_source(self) -> None:
        store = _store()
        store.persist([_row()])
        entries = store.coverage(instrument_ids=("RB2610.SHF",))
        assert entries[0].source_id == "ifind-cn"
        assert entries[0].artifact_class == "FORMAL"

    def test_validate_rejects_bad_rows(self) -> None:
        store = _store()
        # 构造器即拒绝 available_time 早于 event_time 的行
        try:
            RawPITRow(
                source_id="ifind-cn",
                dataset_id="market-eod",
                field="market.eod.close",
                instrument_id="RB2610.SHF",
                event_time=START,
                available_time=START - timedelta(hours=1),
                ingested_at=START,
                revision_id="rev-bad",
                license_tag="licensed-research",
                value_type="decimal",
                value="1.0",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("应拒绝 available_time 早于 event_time 的行")
        # 同批重复 key 被 validate_pit_rows 拒绝
        try:
            store.persist([_row(), _row()])
        except ValueError:
            pass
        else:
            raise AssertionError("应拒绝重复 observation key")


class TestLoad:
    def test_load_returns_latest_revision(self) -> None:
        store = _store()
        store.persist([_row(value="3000.0", revision="rev-1", day=0)])
        store.persist(
            [
                _row(
                    value="3005.0",
                    revision="rev-2",
                    day=0,
                    ingested=START + timedelta(days=2),
                )
            ]
        )
        rows = store.load(
            instrument_ids=("RB2610.SHF",), field_prefix="market.eod"
        )
        assert len(rows) == 1
        assert rows[0].value == 3005.0
        assert rows[0].revision_id == "rev-2"

    def test_load_prefers_formal_source_over_exploratory(self) -> None:
        store = _store()
        exploratory = _row(value="3000.0", revision="ak-1")
        object.__setattr__(exploratory, "source_id", "akshare-cn")
        object.__setattr__(exploratory, "license_tag", "exploratory")
        store.persist([exploratory])
        # FORMAL 行先入库（ingested 更早），后入的 EXPLORATORY 不应覆盖
        store.persist([_row(value="3005.0", revision="if-1", ingested=START + timedelta(days=1))])
        rows = store.load(
            instrument_ids=("RB2610.SHF",), field_prefix="market.eod"
        )
        assert len(rows) == 1
        assert rows[0].value == 3005.0
        assert rows[0].source_id == "ifind-cn"

    def test_load_filters_window_and_prefix(self) -> None:
        store = _store()
        store.persist(
            [_row(day=day) for day in range(5)]
            + [_row(field="market.minute.close", day=0, value="3001.0")]
        )
        rows = store.load(
            instrument_ids=("RB2610.SHF",),
            field_prefix="market.eod",
            start=START + timedelta(days=1),
            end=START + timedelta(days=3),
        )
        assert len(rows) == 3
        assert rows[0].event_time == (START + timedelta(days=1))

    def test_loaded_rows_are_timezone_aware_on_sqlite(self) -> None:
        store = _store()
        store.persist([_row()])
        row = store.load(
            instrument_ids=("RB2610.SHF",), field_prefix="market.eod"
        )[0]
        assert row.event_time.tzinfo is not None


class TestCoverage:
    def test_coverage_groups_by_instrument_and_prefix(self) -> None:
        store = _store()
        store.persist(
            [_row(day=day) for day in range(3)]
            + [
                _row(
                    instrument="AU2612.SHF",
                    field="market.minute.close",
                    day=0,
                )
            ]
        )
        entries = store.coverage(instrument_ids=("RB2610.SHF", "AU2612.SHF"))
        by_prefix = {(entry.instrument_id, entry.field_prefix): entry for entry in entries}
        eod = by_prefix[("RB2610.SHF", "market.eod")]
        assert eod.row_count == 3
        assert eod.first_event.startswith("2026-08-01")
        minute = by_prefix[("AU2612.SHF", "market.minute")]
        assert minute.row_count == 1
